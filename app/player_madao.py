"""The player_madao module provides the Player class.

This implementation of Player uses python wrappers for libmad and libao,
which provide interfaces to audio files and audio devices.
"""
import threading
import time
import ao
import mad
from player import Player

AODEV = ao.AudioDevice(0)


class MadaoPlayer(Player):
    """The Player class provides an audio stream for a file."""

    def __init__(self, filename):
        """Construct a Player.

        :param filename
        """
        super().__init__(filename)
        self._madfile = None
        self.reset()

    @property
    def length(self):
        """Get the length of the audio stream in milliseconds."""
        return self._madfile.total_time()

    @property
    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        return self._madfile.current_time()

    def reset(self):
        """Reset the audio stream."""
        self._madfile = mad.MadFile(self._filename)

    def _play_internal(self):
        """Play the audio stream in a separate thread."""
        while self._is_playing:
            buf = self._madfile.read()
            if buf is not None:
                AODEV.play(buf, len(buf))
            else:
                print(time.asctime() + " :=: Player_madao :: Buffer is empty")
                break

        if self._callback is not None and self._is_playing:
            self.reset()
            self._is_playing = False
            self._callback()

    def play(self, callback=None):
        """Play the audio stream.

        :param callback: function to call if the stream finishes
        """
        if self._is_playing:
            print(time.asctime() + " :=: Player_madao :: Tried to start, but already playing")
            return

        self._is_playing = True
        self._callback = callback
        thread = threading.Thread(target=self._play_internal, daemon=True)  # Set daemon=True
        thread.start()

    def stop(self):
        """Stop the audio stream."""
        self._is_playing = False
        self._callback = None
