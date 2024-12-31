import os
import signal
import subprocess
import threading
import time
from player import Player
from mutagen.mp3 import MP3



class VLCPlayer(Player):
    """The Player class provides an audio stream for a file."""
    _command = None
    _pid = None
    _length = 0
    _elapsed = 0
    _is_playing = False  # may need a lock
    _callback = None

    def __init__(self, filename):
        """Construct a Player.

        :param filename
        """
        super().__init__(filename)
        self._command = ["/usr/bin/vlc", "--intf", "dummy", "--play-and-exit", filename]
        self._length = MP3(filename).info.length * 1000
        self._elapsed = 0
        self._pid = None
        self._lock = threading.Lock()

    @property
    def length(self):
        """Get the length of the audio stream in milliseconds."""
        with self._lock:
            return self._length

    @property
    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        with self._lock:
            return self._elapsed

    def _play_internal(self):
        """Internal method to simulate playback and track elapsed time."""
        while True:
            with self._lock:
                if not self._is_playing:
                    break
                self._elapsed += 1000

            time.sleep(1.0)

            with self._lock:
                if self._elapsed >= self._length:
                    break

        with self._lock:
            if self._pid:
                os.kill(self._pid, signal.SIGKILL)
                self._pid = None

            if self._callback is not None and self._elapsed >= self._length:
                callback = self._callback
                self._callback = None
                callback()

            self._is_playing = False
            self._elapsed = 0

    def play(self, callback=None):
        """Play the audio stream.

        :param callback: function to call if the stream finishes
        """
        if self._is_playing:
            print(time.asctime() + " :=: " + self.__class__.__name__ + " :: Tried to start, but already playing")
            return

        with self._lock:
            if self._is_playing:
                raise RuntimeError("Audio is already playing")

            self._pid = subprocess.Popen(self._command).pid
            self._is_playing = True
            self._callback = callback

        thread = threading.Thread(target=self._play_internal, daemon=True)  # Set daemon=True
        thread.start()

    def stop(self):
        """Stop the audio stream."""
        with self._lock:
            if not self._is_playing:
                print(time.asctime() + " :=: Player_vlc :: Tried to stop, but not playing")
                return

            self._is_playing = False
            self._callback = None

        if self._pid:
            os.kill(self._pid, signal.SIGKILL)
            self._pid = None

        with self._lock:
            self._elapsed = 0
