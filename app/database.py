"""The database module provides a collection of functions for the server API.

These functions only build Cart objects; they never open the audio files,
which live on the music library share. Carts are copied to local disk
when they are prefetched (see the cache module).
"""
import Queue
import threading
import time
import traceback
from api_client import ApiClient, ApiError
from cart import Cart

LIBRARY_PREFIX = "/media/Jemaine/"

URL_CARTLOAD = "https://wsbf.net/api/zautomate/cartmachine_load.php"
URL_AUTOLOAD = "https://wsbf.net/api/zautomate/automation_generate_showplist.php"
URL_AUTOSTART = "https://wsbf.net/api/zautomate/automation_generate_showid.php"
URL_AUTOCART = "https://wsbf.net/api/zautomate/automation_add_carts.php"
URL_STUDIOSEARCH = "https://wsbf.net/api/zautomate/studio_search.php"
URL_LOG_CART = "https://wsbf.net/api/zautomate/log_cart.php"
URL_LOG_TRACK = "https://wsbf.net/api/zautomate/log_track.php"

CART_TYPE_IDS = {
    "PSA": 0,
    "Underwriting": 1,
    "StationID": 2,
    "Promotion": 3
}

CLIENT = ApiClient()

def _make_cart(cart_res):
    """Build a Cart from a server cart object."""
    filename = LIBRARY_PREFIX + "carts/" + cart_res["filename"]
    return Cart(cart_res["cartID"], cart_res["title"], cart_res["issuer"], cart_res["type"], filename)

def _make_track(track_res, album_code_key, track_num_key, track_name_key):
    """Build a Cart from a server track object."""
    # TODO: move pathname building to Track constructor
    filename = LIBRARY_PREFIX + track_res["file_name"]
    track_id = track_res[album_code_key] + "-" + track_res[track_num_key]
    return Cart(track_id, track_res[track_name_key], track_res["artist_name"], track_res["rotation"], filename)

def _make_all(items, make):
    """Build Carts from a list of server objects, skipping malformed ones."""
    carts = []

    if not isinstance(items, list):
        return carts

    for item in items:
        try:
            carts.append(make(item))
        except (KeyError, TypeError, AttributeError), exc:
            print time.asctime() + " :=: Database :: Skipping malformed item: " + repr(exc)

    return carts

def get_new_show_id(show_id):
    """Get a new show ID for queueing playlists.

    :param show_id: previous show ID, which will be excluded
    """
    try:
        return CLIENT.get_json(URL_AUTOSTART, params={"showid": show_id})
    except ApiError:
        print "Error: Could not fetch starting show ID."
        return -1

def get_cart(cart_type):
    """Get a random cart of a given type.

    :param cart_type: cart type name, such as "PSA"
    :return: Cart, or None if there is no cart of this type
    """
    try:
        cart_res = CLIENT.get_json(URL_AUTOCART, params={"type": CART_TYPE_IDS.get(cart_type, cart_type)})
    except ApiError:
        print time.asctime() + " :=: Error: Could not fetch cart."
        return None

    if not cart_res:
        return None

    carts = _make_all([cart_res], _make_cart)
    return carts[0] if carts else None

def get_playlist(show_id):
    """Get the playlist from a past show.

    :param show_id: show ID
    """
    try:
        playlist_res = CLIENT.get_json(URL_AUTOLOAD, params={"showid": show_id})
    except ApiError:
        print "Error: Could not fetch playlist."
        return []

    return _make_all(playlist_res, lambda t: _make_track(t, "lb_album_code", "lb_track_num", "lb_track_name"))

def get_carts():
    """Load a dictionary of cart arrays for each cart type."""
    carts = {
        0: [],
        1: [],
        2: [],
        3: []
    }

    try:
        for cart_type in carts:
            carts_res = CLIENT.get_json(URL_CARTLOAD, params={"type": cart_type})
            carts[cart_type] = _make_all(carts_res, _make_cart)
    except ApiError:
        print time.asctime() + " :=: Error: Could not fetch carts."

    return carts

def search_library(query):
    """Search the music library for tracks and carts.

    :param query: search term
    """
    try:
        results_res = CLIENT.get_json(URL_STUDIOSEARCH, params={"query": query})
    except ApiError:
        print "Error: Could not fetch search results."
        return []

    if not isinstance(results_res, dict):
        return []

    results = _make_all(results_res.get("carts"), _make_cart)
    results.extend(_make_all(results_res.get("tracks"), lambda t: _make_track(t, "album_code", "track_num", "track_name")))

    return results

def log_cart(cart_id):
    """Log a cart or track.

    :param cart_id: cart ID, or [album_code]-[track_num] for a track
    """
    cart_id = str(cart_id)

    try:
        if cart_id.isdigit():
            text = CLIENT.post_text(URL_LOG_CART, params={"cartid": cart_id})
        else:
            album_id = cart_id.split("-")[0]
            disc_num = 1
            track_num = cart_id.split("-")[1]
            text = CLIENT.post_text(URL_LOG_TRACK, params={"albumID": album_id, "disc_num": disc_num, "track_num": track_num})
        print text
    except ApiError:
        print time.asctime() + " :=: Caught error: Could not access cart logger."

_LOG_QUEUE = Queue.Queue()
_LOG_THREAD = None
_LOG_THREAD_LOCK = threading.Lock()

def _log_worker():
    """Log carts in the order they were queued."""
    while True:
        cart_id = _LOG_QUEUE.get()

        try:
            log_cart(cart_id)
        except Exception:
            traceback.print_exc()

def log_cart_async(cart_id):
    """Log a cart or track from a background thread.

    The GUI never waits on the server, and carts are logged in order.

    :param cart_id: cart ID, or [album_code]-[track_num] for a track
    """
    global _LOG_THREAD

    with _LOG_THREAD_LOCK:
        if _LOG_THREAD is None:
            _LOG_THREAD = threading.Thread(target=_log_worker, name="CartLogger")
            _LOG_THREAD.setDaemon(True)
            _LOG_THREAD.start()

    _LOG_QUEUE.put(cart_id)
