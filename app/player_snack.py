"""The player_snack module provides the Player class.

This implementation of Player uses the tkSnack module to access the
audio stream. However, I have not been able to use it because the
tkSnack module does not seem to load correctly.
"""
import time
from tkinter import Tk
import tkSnack
from player import Player

# TODO: provide reference to Tk root
root = Tk()
tkSnack.initializeSnack(root)


class PlayerSnack(Player):
    """The Player class provides an audio stream for a file."""

    def __init__(self, filename):
        """
        construct a tkSnack Player.

        :param filename
        """
        super().__init__(filename)
        self._snack = None
        self.reset()

    @property
    def length(self):
        """Get the length of the audio stream in milliseconds."""
        return self._snack.length(unit="SECONDS") * 1000

    @property
    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        return tkSnack.audio.elapsedTime() * 1000

    def reset(self):
        """Reset the audio stream."""
        self._snack = tkSnack.Sound(load=self._filename)

    def play(self, callback=None):
        """Play the audio stream.

        :param callback: function to call if the stream finishes
        """
        if self.is_playing:
            print(time.asctime() + " :=: " + self.__class__.__name__ + " :: Tried to start, but already playing")
            return

        self._is_playing = True
        self._callback = callback
        self._snack.play(blocking=False, command=self._callback)

    def stop(self):
        """Stop the audio stream."""
        if not self.is_playing:
            print(time.asctime() + " :=: " + self.__class__.__name__ + " :: Tried to stop, but not playing")
            return

        self._is_playing = False
        self._callback = None
        self._snack.stop()

        self.reset()