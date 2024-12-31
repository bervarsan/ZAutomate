"""The player_abstract class for other players to inherit from"""
from abc import ABC, abstractmethod


class Player(ABC):
    """The Player class provides an audio stream for a file."""

    @abstractmethod
    def __init__(self, filename):
        """Construct a Player.

        :param filename
        """
        self._filename = filename
        self._is_playing = False
        self._callback = None

    @property
    @abstractmethod
    def length(self):
        """Get the length of the audio stream in milliseconds."""
        pass

    @property
    @abstractmethod
    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        pass

    @property
    def is_playing(self):
        """Get whether the audio stream is currently playing."""
        return self._is_playing

    @abstractmethod
    def play(self, callback=None):
        """Play the audio stream.

        :param callback: function to call if the stream finishes
        """

    @abstractmethod
    def stop(self):
        """Stop the audio stream."""
