"""The cartqueue module provides the CartQueue class."""
import datetime
import os
import Queue
import random
import threading
import time
import traceback
import database
from cart import Cart
from config import za_config

# temporary array used to filter carts from the cart queue
CART_TYPES = [
    'StationID',
    'PSA',
    'Underwriting'
]

### Configuration for when to play carts. The configuration must
### at least fulfill the rules established by the FCC and WSBF:
### - 1 StationID at the top of every hour, +/- 5 minutes
### - 2 PSAs each hour
### - 1 Underwriting each hour
###
### type       cart type to play
### minute     target play time within each hour
### max_delta  maximum deviation from minute, in seconds
AUTOMATION_CARTS = [
    {
        "type": "StationID",
        "minute": 5,
        "max_delta": 6000
    },
     {
        "type": "PSA",
        "minute": 15,
        "max_delta": 6000
    },
    {
        "type": "Underwriting",
        "minute": 30,
        "max_delta": 6000
    },
     {
        "type": "PSA",
        "minute": 45,
        "max_delta": 6000
    }
]

PLAYLIST_MIN_LENGTH = 10
PLAYED_MEMORY = 50

# seconds to wait after a failed or empty playlist fetch
FETCH_RETRY_SECONDS = 5

# seconds to wait after the server has no cart of a type
CART_RETRY_SECONDS = 60

# seconds of silence before a file from the fallback directory is played
FALLBACK_WAIT_SECONDS = 15
FALLBACK_TYPE = "Fallback"

# consecutive playback errors before waiting between tracks
ERROR_LIMIT = 3
ERROR_BACKOFF_SECONDS = 5

JOB_PLAYLIST = "playlist"

def _get_pool_sizes():
    """Get the number of carts of each type needed for one hour."""
    sizes = {}

    for entry in AUTOMATION_CARTS:
        sizes[entry["type"]] = sizes.get(entry["type"], 0) + 1

    return sizes

POOL_SIZES = _get_pool_sizes()

def is_artist_in_list(cart, array):
    """Get whether the artist of a cart is in a list of carts.

    :param cart
    :param array
    """
    if cart is None:
        return True

    for item in array:
        if cart.issuer == item.issuer:
            return True

    return False

def load_fallback_cart(directory=None):
    """Get a random MP3 from the local fallback directory.

    :param directory: defaults to ZA_FALLBACK_DIR
    :return: Cart, or None if there is no fallback directory or file
    """
    directory = directory or za_config.fallback_dir

    if not directory:
        return None

    try:
        names = [name for name in os.listdir(directory) if name.lower().endswith(".mp3")]
    except OSError:
        return None

    if len(names) == 0:
        return None

    name = random.choice(names)
    return Cart(None, os.path.splitext(name)[0], FALLBACK_TYPE, FALLBACK_TYPE, os.path.join(directory, name), cached=False)

def _spawn_thread(target):
    """Run a function in a daemon thread."""
    worker = threading.Thread(target=target)
    worker.setDaemon(True)
    worker.start()

class CartQueue(object):
    """The CartQueue class is a queue that generates radio content.

    The queue is driven by tick(), which the GUI calls from the Tk main
    loop. A tick never blocks: playlists and carts are fetched from the
    server in background threads, and their files are copied to local
    disk by the file cache. Each tick does the following:
    1. collect playlists and carts that finished fetching
    2. drop queued items whose files could not be copied
    3. if the current item ended, move it to the played list
    4. if playing and nothing is playing, start the first ready item,
       or a fallback file if nothing has been ready for a while
    5. insert carts into the queue according to configuration
    6. fetch another playlist if the queue is not sufficiently long,
       and more carts if there aren't enough for the hour
    """

    def __init__(self, on_cart_start, on_cart_stop, on_queue_change=None, spawn=None, now=None, fallback=None):
        """Construct a cart queue.

        :param on_cart_start: callback for when a cart starts
        :param on_cart_stop: callback for when a cart stops
        :param on_queue_change: callback for when queue contents change
        :param spawn: function that runs a function in the background
        :param now: function that returns the current datetime
        :param fallback: function that returns a local Cart for when nothing is ready
        """
        self._on_cart_start = on_cart_start
        self._on_cart_stop = on_cart_stop
        self._on_queue_change = on_queue_change
        self._spawn = spawn or _spawn_thread
        self._now = now or datetime.datetime.now
        self._fallback = fallback or load_fallback_cart

        self._show_id = -1
        self._queue = []
        self._played = []
        self._current = None
        self._is_playing = False

        self._results = Queue.Queue()
        self._in_flight = set()
        self._retry_at = {}
        self._cart_pool = dict((cart_type, []) for cart_type in POOL_SIZES)
        self._filled_slots = {}

        self._ready_count = 0
        self._waiting_since = None
        self._error_count = 0
        self._resume_at = None

    def get_queue(self):
        """Get the queue."""
        return self._queue

    def get_current(self):
        """Get the item that is playing, or None."""
        return self._current

    def is_busy(self):
        """Get whether an item is playing."""
        return self._current is not None

    def start(self):
        """Start the queue."""
        if self._is_playing:
            return

        self._is_playing = True
        self._waiting_since = None
        self._error_count = 0
        self._resume_at = None
        self.tick()

    def stop_soft(self):
        """Stop the queue at the end of the current item."""
        self._is_playing = False

        if self._current is None:
            self._remove_carts()
            self._notify()

    def stop_hard(self):
        """Stop the current item and the queue immediately."""
        self._is_playing = False

        if self._current is not None:
            self._finish_current()
        else:
            self._remove_carts()

        self._notify()

    def tick(self):
        """Advance the queue. Called periodically from the Tk main loop."""
        now = self._now()

        changed = self._collect_results(now)
        changed = self._drop_failed(now) or changed
        changed = self._check_ready() or changed

        if self._current is not None and not self._current.is_playing():
            self._finish_current()
            changed = True

        if self._is_playing and self._current is None:
            changed = self._start_next(now) or changed

        if self._is_playing:
            changed = self._insert_carts(now) or changed

        self._request_work(now)

        if changed:
            self._notify()

    def _notify(self):
        """Update start times and report a change in the queue."""
        self._gen_start_times()

        if self._on_queue_change is not None:
            self._on_queue_change()

    def _collect_results(self, now):
        """Add playlists and carts fetched in the background."""
        changed = False

        while True:
            try:
                job, succeeded, value = self._results.get_nowait()
            except Queue.Empty:
                return changed

            self._in_flight.discard(job)

            if not succeeded:
                self._retry_at[job] = now + datetime.timedelta(seconds=FETCH_RETRY_SECONDS)
            elif job == JOB_PLAYLIST:
                changed = self._add_playlist(value[0], value[1], now) or changed
            else:
                self._add_pool_cart(job, value, now)

    def _add_playlist(self, show_id, playlist, now):
        """Append tracks to the queue.

        :param show_id: show the playlist came from
        :param playlist: list of tracks
        :param now
        """
        if show_id != -1:
            self._show_id = show_id

        added = 0

        # add each track whose artist isn't already in the queue or played list
        for track in playlist:
            if is_artist_in_list(track, self._played) or is_artist_in_list(track, self._queue):
                continue

            track.prefetch()
            self._queue.append(track)
            added += 1

        print time.asctime() + " :=: CartQueue :: Added tracks, length is " + str(len(self._queue))

        if added == 0:
            self._retry_at[JOB_PLAYLIST] = now + datetime.timedelta(seconds=FETCH_RETRY_SECONDS)

        return added > 0

    def _add_pool_cart(self, cart_type, cart, now):
        """Keep a fetched cart until it is inserted into the queue."""
        if cart is None:
            print time.asctime() + " :=: CartQueue :: Could not find cart of type " + cart_type
            self._retry_at[cart_type] = now + datetime.timedelta(seconds=CART_RETRY_SECONDS)
            return

        cart.prefetch()
        self._cart_pool[cart_type].append(cart)

    def _drop_failed(self, now):
        """Remove items whose files could not be copied or loaded.

        While the share is down, every new track fails, so the next
        playlist fetch waits instead of replacing them as fast as the
        server answers.
        """
        changed = False

        for cart in list(self._queue):
            if cart is not self._current and cart.is_failed():
                print time.asctime() + " :=: CartQueue :: Dropping unavailable " + str(cart.cart_id) + " " + cart.filename
                self._queue.remove(cart)
                self._unfill_slot(cart)
                changed = True

        if changed:
            self._retry_at[JOB_PLAYLIST] = now + datetime.timedelta(seconds=FETCH_RETRY_SECONDS)

        for pool in self._cart_pool.values():
            for cart in list(pool):
                if cart.is_failed():
                    pool.remove(cart)

        return changed

    def _check_ready(self):
        """Load items whose files are ready, and report whether that changed."""
        ready_count = len([cart for cart in self._queue if cart.is_ready()])

        for pool in self._cart_pool.values():
            for cart in pool:
                cart.is_ready()

        changed = ready_count != self._ready_count
        self._ready_count = ready_count
        return changed

    def _finish_current(self):
        """Move the current item to the played list."""
        cart = self._current
        self._current = None

        print time.asctime() + " :=: CartQueue :: Dequeuing " + str(cart.cart_id)

        cart.stop()

        if cart in self._queue:
            self._queue.remove(cart)

        if cart.cart_type != FALLBACK_TYPE:
            self._played.append(cart)
            del self._played[:-PLAYED_MEMORY]

        if cart.playback_error() is not None:
            self._error_count += 1

            if self._error_count >= ERROR_LIMIT:
                print time.asctime() + " :=: CartQueue :: Repeated playback errors, waiting before the next item"
                self._resume_at = self._now() + datetime.timedelta(seconds=ERROR_BACKOFF_SECONDS)
        else:
            self._error_count = 0

        self._on_cart_stop()

        if not self._is_playing:
            print time.asctime() + " :=: CartQueue :: Removing all carts"
            self._remove_carts()

    def _start_next(self, now):
        """Start the first ready item in the queue.

        Items whose files are still being copied are skipped. If nothing
        is ready for FALLBACK_WAIT_SECONDS, a fallback file is played.

        :return: True if the queue changed
        """
        if self._resume_at is not None and now < self._resume_at:
            return False

        ready = [i for i, cart in enumerate(self._queue) if cart.is_ready()]

        if len(ready) > 0:
            index = ready[0]
        else:
            if self._waiting_since is None:
                print time.asctime() + " :=: CartQueue :: Waiting for a track to be ready"
                self._waiting_since = now

            if now - self._waiting_since < datetime.timedelta(seconds=FALLBACK_WAIT_SECONDS):
                return False

            # try again after another wait whether or not this works
            self._waiting_since = now

            cart = self._fallback()
            if cart is None or not cart.is_ready():
                return False

            print time.asctime() + " :=: CartQueue :: Nothing is ready, playing fallback " + cart.title
            self._queue.insert(0, cart)
            index = 0

        self._waiting_since = None

        cart = self._queue.pop(index)
        self._queue.insert(0, cart)

        print time.asctime() + " :=: CartQueue :: Enqueuing " + str(cart.cart_id)

        if not cart.start():
            print time.asctime() + " :=: CartQueue :: Could not start " + str(cart.cart_id) + ", dropping it"
            self._queue.remove(cart)
            self._unfill_slot(cart)
            return True

        self._current = cart
        cart.start_time = now

        if cart.cart_type != FALLBACK_TYPE:
            database.log_cart_async(cart.cart_id)

        self._on_cart_start()
        return True

    def _gen_start_times(self):
        """Set the start time of each item in the queue."""
        now = self._now()
        start_time = now

        for cart in self._queue:
            if cart is self._current and cart.start_time is not None:
                start_time = cart.start_time
            else:
                start_time = max(start_time, now)
                cart.start_time = start_time

            start_time = start_time + datetime.timedelta(milliseconds=cart.expected_length())

    def _insert_carts(self, now):
        """Insert carts into the queue for each configured slot this hour.

        Each slot is filled once. A slot is filled again if its cart is
        dropped, and all slots are cleared when the queue stops.

        :return: True if any carts were inserted
        """
        if len(self._queue) < 2:
            return False

        for slot in self._filled_slots.keys():
            if slot[0] < now - datetime.timedelta(hours=1):
                del self._filled_slots[slot]

        self._gen_start_times()

        changed = False
        for entry in AUTOMATION_CARTS:
            changed = self._insert_cart(entry["type"], entry["minute"], entry["max_delta"], now) or changed

        return changed

    def _insert_cart(self, cart_type, minute, max_delta, now):
        """Insert a cart into the current hour according to a config entry.

        This function inserts a cart as close as possible to the target
        start time, even if the target window is not met.

        :param cart_type
        :param minute
        :param max_delta
        :param now
        :return: True if a cart was inserted
        """
        target = now.replace(minute=minute, second=0, microsecond=0)
        slot = (target, cart_type)

        # don't insert if the target minute has already passed this hour
        if target < now or slot in self._filled_slots:
            return False

        # don't insert if the queue has not reached the target window
        last = self._queue[-1]
        last_end = last.start_time + datetime.timedelta(milliseconds=last.expected_length())

        if last_end < target - datetime.timedelta(seconds=max_delta):
            return False

        # don't insert until a cart of this type is ready to play
        ready = [cart for cart in self._cart_pool[cart_type] if cart.is_ready()]

        if len(ready) == 0:
            return False

        # find the position in queue with the closest start time to target,
        # never in front of the first item
        min_index = None
        min_delta = None

        for i in range(1, len(self._queue)):
            delta = abs(target - self._queue[i].start_time)

            if min_delta is None or delta < min_delta:
                min_index = i
                min_delta = delta
            elif delta > min_delta:
                break

        print time.asctime() + " :=: CartQueue :: Target insert time is " + str(target)
        print time.asctime() + " :=: CartQueue :: min_index is " + str(min_index)
        print time.asctime() + " :=: CartQueue :: min_delta is " + str(min_delta)

        if min_delta.total_seconds() <= max_delta:
            print time.asctime() + " :=: CartQueue :: Cart inserted within target window"
        else:
            print time.asctime() + " :=: CartQueue :: Cart not inserted within target window"

        # insert cart into the queue
        cart = ready[0]
        self._cart_pool[cart_type].remove(cart)
        self._queue.insert(min_index, cart)
        self._filled_slots[slot] = cart
        self._gen_start_times()

        return True

    def _unfill_slot(self, cart):
        """Forget the slot a cart was inserted for, so it can be filled again."""
        for slot, slot_cart in self._filled_slots.items():
            if slot_cart is cart:
                del self._filled_slots[slot]

    def _remove_carts(self):
        """Remove all carts from the queue.

        This function is called after a stop. The queue must be cleared
        of carts after every stop because the start times may not meet
        the cart configuration when the queue is restarted. Removed carts
        go back to the pool, since their files are already copied.
        """
        removed = [cart for cart in self._queue if cart.cart_type in CART_TYPES and cart is not self._current]
        self._queue = [cart for cart in self._queue if cart not in removed]

        for cart in removed:
            pool = self._cart_pool.get(cart.cart_type)

            if pool is not None and len(pool) < POOL_SIZES[cart.cart_type] and not cart.is_failed():
                pool.append(cart)

        self._filled_slots.clear()

    def _request_work(self, now):
        """Start background fetches for playlists and carts as needed."""
        if len(self._queue) < PLAYLIST_MIN_LENGTH and self._can_start(JOB_PLAYLIST, now):
            print time.asctime() + " :=: CartQueue :: Refilling tracks"
            self._start_job(JOB_PLAYLIST, self._fetch_playlist)

        for cart_type, size in POOL_SIZES.items():
            if len(self._cart_pool[cart_type]) < size and self._can_start(cart_type, now):
                self._start_job(cart_type, lambda t=cart_type: database.get_cart(t))

    def _can_start(self, job, now):
        """Get whether a background job may start."""
        if job in self._in_flight:
            return False

        retry_at = self._retry_at.get(job)
        return retry_at is None or now >= retry_at

    def _start_job(self, job, work):
        """Run a function in the background and collect its result on a later tick."""
        self._in_flight.add(job)
        results = self._results

        def run():
            try:
                result = (job, True, work())
            except Exception, exc:
                print time.asctime() + " :=: CartQueue :: Background job " + job + " failed"
                traceback.print_exc()
                result = (job, False, exc)

            results.put(result)

        self._spawn(run)

    def _fetch_playlist(self):
        """Fetch the playlist of a random past show. Runs in the background.

        Previously, new playlists were retrieved by incrementing the
        current show ID, but incrementing is not guaranteed to yield
        a valid playlist and it leads to an infinite loop if no valid
        playlists are found up to the present, so now a random show ID
        is selected every time. Since shows are not scheduled according
        to genre continuity, selecting a random show every time has no
        less continuity than incrementing.

        :return: (show ID, list of tracks)
        """
        show_id = database.get_new_show_id(self._show_id)

        if show_id == -1:
            return (-1, [])

        return (show_id, database.get_playlist(show_id))
