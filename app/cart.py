"""The cart module provides the Cart class.

Currently, carts and tracks are both represented by the "Cart"
class, but it may be better to have separate classes.

The Cart class uses the Player class to provide an audio stream. There
are three different implementations of the Player class, and Cart currently
uses madao.
"""
import time
import traceback
from player_madao import Player

# length assumed for scheduling when a cart's length is unknown
DEFAULT_LENGTH_MS = 4 * 60 * 1000

class Cart(object):
    """The Cart class contains the metadata and audio stream of a cart."""
    cart_id = None
    title = None
    issuer = None
    cart_type = None
    filename = None
    start_time = None

    _player = None

    def __init__(self, cart_id, title, issuer, cart_type, filename):
        """Construct a Cart object.

        :param cart_id: cart ID
        :param title: cart title
        :param issuer: cart issuer
        :param cart_type: cart type
        :param filename: location of the cart file
        """
        self.cart_id = cart_id
        self.title = title.encode("ascii", "ignore")
        self.issuer = issuer.encode("ascii", "ignore")
        self.cart_type = cart_type.encode("ascii", "ignore")
        self.filename = filename.encode("ascii", "ignore")

        # uncomment to mock ZAutoLib in development
        # self.filename = "test/test.mp3"

        try:
            self._player = Player(self.filename)
        except IOError:
            print time.asctime() + " :=: Cart :: could not load audio file " + self.filename

    def prefetch(self):
        """Prepare the cart's file for playing.

        The file is loaded when the cart is constructed, so there is
        nothing to do yet.
        """

    def is_playable(self):
        """Get whether the cart has an audio stream."""
        return self._player is not None

    def is_ready(self):
        """Get whether the cart can be played."""
        return self._player is not None

    def is_failed(self):
        """Get whether the cart's file could not be loaded."""
        return self._player is None

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
            print time.asctime() + " :=: Cart :: could not start " + self.filename
            traceback.print_exc()
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
