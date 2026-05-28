"""The player_madao module provides the Player class.

This implementation of Player uses python wrappers for libmad and libao,
which provide interfaces to audio files and audio devices.
"""
import threading
import time
import ao
import mad
from config import madao_config

AO_DRIVER = madao_config.ao_driver
AO_BITS = madao_config.ao_bits
AO_CHANNELS = madao_config.ao_channels
AO_RATE = madao_config.ao_rate
AO_BYTE_FORMAT = madao_config.ao_byte_format

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
    except TypeError:
        return ao.AudioDevice(0)

AODEV = _build_aodev()

class Player(object):
    """The Player class provides an audio stream for a file."""
    _filename = None
    _madfile = None
    _is_playing = False  # may need a lock since stop and play_internal both write
    _callback = None

    def __init__(self, filename):
        """Construct a Player.

        :param filename
        """
        self._filename = filename
        self.reset()

    def length(self):
        """Get the length of the audio stream in milliseconds."""
        return self._madfile.total_time()

    def time_elapsed(self):
        """Get the elapsed time of the audio stream in milliseconds."""
        return self._madfile.current_time()

    def is_playing(self):
        """Get whether the audio stream is currently playing."""
        return self._is_playing

    def reset(self):
        """Reset the audio stream."""
        self._madfile = mad.MadFile(self._filename)

    def _play_internal(self):
        """Play the audio stream in a worker thread."""
        ended = False

        while self._is_playing:
            buf = self._madfile.read()
            if buf is None:
                print time.asctime() + " :=: Player_madao :: Buffer is empty"
                ended = True
                break

            AODEV.play(buffer(buf), len(buf))

        if ended:
            self.reset()
            self._is_playing = False

        if self._callback is not None and ended:
            self._callback()

    def play(self, callback=None):
        """Play the audio stream.

        :param callback: function to call if the stream finishes
        """
        if self._is_playing:
            print time.asctime() + " :=: Player_madao :: Tried to start, but already playing"
            return

        self._is_playing = True
        self._callback = callback
        thread = threading.Thread(target=self._play_internal)
        thread.setDaemon(True)
        thread.start()

    def stop(self):
        """Stop the audio stream."""
        self._is_playing = False
        self._callback = None
