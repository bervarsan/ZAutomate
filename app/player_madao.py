"""The player_madao module provides the Player class.

This implementation of Player uses python wrappers for libmad and libao,
which provide interfaces to audio files and audio devices.

Each Player plays on its own worker thread, and only that thread touches
the MadFile while it is playing. Other threads only read the length and
position that the worker caches. A generation counter retires a stopped
worker, so a worker that hasn't exited yet can never play again or change
the state of a newer playback, and a module lock keeps two workers from
writing to the audio device at once.

Files should be on local disk (see the cache module): pymad may hold the
GIL while it reads, so a read that blocks on a network share freezes
every thread in the process.
"""
import threading
import time
import traceback
import ao
import mad
from config import madao_config

AO_DRIVER = madao_config.ao_driver
AO_BITS = madao_config.ao_bits
AO_CHANNELS = madao_config.ao_channels
AO_RATE = madao_config.ao_rate
AO_BYTE_FORMAT = madao_config.ao_byte_format

# how long play() waits for a stopped worker to exit, in seconds
STOP_JOIN_TIMEOUT = 0.5

def _get_ao_byte_format():
    """Resolve optional byte format from env configuration."""
    if AO_BYTE_FORMAT == "native":
        return getattr(ao, "AO_FMT_NATIVE", None)
    return getattr(ao, "AO_FMT_LITTLE", getattr(ao, "AO_FMT_NATIVE", None))

def _build_aodev():
    """Create a global AO device from env config with fallback."""
    kwargs = {
        "bits": AO_BITS,
        "rate": AO_RATE,
        "channels": AO_CHANNELS
    }

    byte_format = _get_ao_byte_format()
    if byte_format is not None:
        kwargs["byte_format"] = byte_format

    if AO_DRIVER:
        try:
            return ao.AudioDevice(AO_DRIVER, **kwargs)
        except TypeError:
            return ao.AudioDevice(AO_DRIVER)

    try:
        return ao.AudioDevice(0, **kwargs)
    except ao.aoError:
        return ao.AudioDevice(0)

_AODEV = None
_AODEV_LOCK = threading.Lock()
_PLAY_LOCK = threading.Lock()

def get_device():
    """Get the shared AO device, opening it on first use."""
    global _AODEV

    with _AODEV_LOCK:
        if _AODEV is None:
            _AODEV = _build_aodev()
        return _AODEV

class Player(object):
    """The Player class provides an audio stream for a file."""

    def __init__(self, filename):
        """Construct a Player.

        :param filename
        :raises IOError: if the file can't be opened
        """
        self._filename = filename
        self._lock = threading.Lock()
        self._generation = 0
        self._thread = None
        self._is_playing = False
        self._madfile = None
        self._length = 0
        self._elapsed = 0
        self.error = None

        self._open()

    def _open(self):
        """Open the audio stream from the beginning."""
        madfile = mad.MadFile(self._filename)

        self._length = madfile.total_time()
        self._elapsed = 0
        self._madfile = madfile

    def length(self):
        """Get the length of the audio stream in milliseconds."""
        return self._length

    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        return self._elapsed

    def is_playing(self):
        """Get whether the audio stream is currently playing."""
        return self._is_playing

    def play(self, callback=None):
        """Play the audio stream.

        A stopped stream resumes where it stopped, and a finished stream
        starts over.

        :param callback: function to call from the worker thread if the stream finishes
        :return: True if playback started
        :raises IOError: if a finished stream can't be reopened
        """
        if self._is_playing:
            print time.asctime() + " :=: Player_madao :: Tried to start, but already playing"
            return False

        previous = self._thread
        if previous is not None and previous.is_alive():
            previous.join(STOP_JOIN_TIMEOUT)

            if previous.is_alive():
                print time.asctime() + " :=: Player_madao :: Previous playback has not exited, not starting " + self._filename
                return False

        if self._madfile is None:
            self._open()

        with self._lock:
            self._generation += 1
            self._is_playing = True
            self.error = None

            thread = threading.Thread(target=self._play_internal, args=(self._generation, self._madfile, callback))
            thread.setDaemon(True)
            self._thread = thread

        thread.start()
        return True

    def stop(self):
        """Stop the audio stream."""
        with self._lock:
            self._generation += 1
            self._is_playing = False

    def _is_current(self, generation):
        """Get whether a worker still owns the playback."""
        return self._is_playing and generation == self._generation

    def _play_internal(self, generation, madfile, callback):
        """Play the audio stream in a worker thread.

        :param generation: playback this worker belongs to
        :param madfile: stream to play
        :param callback: function to call if the stream finishes
        """
        finished = False

        try:
            device = get_device()

            while self._is_current(generation):
                buf = madfile.read()

                if not buf:
                    print time.asctime() + " :=: Player_madao :: Buffer is empty"
                    finished = True
                    break

                with _PLAY_LOCK:
                    device.play(buffer(buf), len(buf))

                self._elapsed = madfile.current_time()
        except Exception, exc:
            print time.asctime() + " :=: Player_madao :: Playback failed for " + self._filename
            traceback.print_exc()
            self.error = exc
            finished = True

        with self._lock:
            if generation != self._generation:
                # stopped, or a newer playback owns the state
                return

            self._is_playing = False

            if finished:
                # reopened by the next play(), never here, so the end of
                # a track never touches the file system
                self._madfile = None

        if callback is not None:
            try:
                callback()
            except Exception:
                traceback.print_exc()
