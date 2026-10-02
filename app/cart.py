"""The cart module provides the Cart class.

Currently, carts and tracks are both represented by the "Cart"
class, but it may be better to have separate classes.

The Cart class uses the Player class to provide an audio stream. There
are three different implementations of the Player class, and Cart currently
uses madao.

A Cart never opens its file on the music library share. prefetch() asks
the file cache to copy the file to local disk in a child process, and the
Cart only loads a Player once the local copy is ready.
"""
import time
import traceback
import cache
from player_madao import Player

# length assumed for scheduling until a cart's file is loaded
DEFAULT_LENGTH_MS = 4 * 60 * 1000

def _ascii(value):
    """Get a value as an ASCII string, dropping other characters."""
    if value is None:
        return ""
    if isinstance(value, unicode):
        return value.encode("ascii", "ignore")
    return str(value).decode("ascii", "ignore").encode("ascii")

class Cart(object):
    """The Cart class contains the metadata and audio stream of a cart."""
    cart_id = None
    title = None
    issuer = None
    cart_type = None
    filename = None
    start_time = None

    def __init__(self, cart_id, title, issuer, cart_type, filename, file_cache=None, cached=True):
        """Construct a Cart object.

        Nothing is read from disk until the cart is prefetched.

        :param cart_id: cart ID
        :param title: cart title
        :param issuer: cart issuer
        :param cart_type: cart type
        :param filename: location of the cart file
        :param file_cache: cache to copy the file with, defaults to cache.get_cache()
        :param cached: False to play filename directly, for files already on local disk
        """
        self.cart_id = cart_id
        self.title = _ascii(title)
        self.issuer = _ascii(issuer)
        self.cart_type = _ascii(cart_type)
        self.filename = _ascii(filename)

        # uncomment to mock ZAutoLib in development
        # self.filename = "test/test.mp3"

        self._file_cache = file_cache
        self._cached = cached
        self._player = None
        self._load_failed = False

    def _get_cache(self):
        """Get the file cache for this cart."""
        if self._file_cache is None:
            self._file_cache = cache.get_cache()
        return self._file_cache

    def prefetch(self):
        """Start copying the cart's file to local disk."""
        if self._cached and self._player is None:
            self._get_cache().request(self.filename)

    def is_ready(self):
        """Get whether the cart's file is loaded and can be played.

        This loads the Player once the local copy is ready. It never
        touches the music library share.
        """
        if self._player is not None:
            return True

        if self._load_failed:
            return False

        if self._cached:
            path = self._get_cache().local_path(self.filename)

            if path is None:
                return False
        else:
            path = self.filename

        try:
            self._player = Player(path)
        except Exception:
            print time.asctime() + " :=: Cart :: could not load audio file " + self.filename
            traceback.print_exc()
            self._load_failed = True
            return False

        return True

    def is_failed(self):
        """Get whether the cart's file could not be copied or loaded."""
        if self._player is not None:
            return False

        if self._load_failed:
            return True

        return self._cached and self._get_cache().state(self.filename) == cache.STATE_FAILED

    def is_playing(self):
        """Get whether the cart is currently playing."""
        return self._player is not None and self._player.is_playing()

    def playback_error(self):
        """Get the error that ended the last playback, or None."""
        return None if self._player is None else self._player.error

    def start(self, callback=None):
        """Play the cart's audio stream.

        :param callback: function to call if the stream ends
        :return: True if the cart started playing
        """
        if not self.is_ready():
            print time.asctime() + " :=: Cart :: Not ready :: " + self.issuer + " - " + self.title
            return False

        print time.asctime() + " :=: Cart :: Start :: " + self.issuer + " - " + self.title

        try:
            return self._player.play(callback)
        except Exception:
            # the local copy may have been evicted, so copy it again
            print time.asctime() + " :=: Cart :: could not start " + self.filename
            traceback.print_exc()
            self._player = None
            self.prefetch()
            return False

    def stop(self):
        """Stop the cart's audio stream."""
        print time.asctime() + " :=: Cart :: Stop :: " + self.issuer + " - " + self.title

        if self._player is not None:
            self._player.stop()

    def length(self):
        """Get the length of the cart in milliseconds, or None if it is not loaded."""
        return None if self._player is None else self._player.length()

    def expected_length(self):
        """Get the length of the cart in milliseconds, estimated if it is not loaded."""
        length = self.length()
        return length if length else DEFAULT_LENGTH_MS

    def get_meter_data(self):
        """Get the meter data for the cart as a 4-tuple."""
        if self._player is None:
            return (0, 0, self.title, self.issuer)

        return (self._player.time_elapsed(), self._player.length(), self.title, self.issuer)
