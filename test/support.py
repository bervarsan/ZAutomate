"""Shared setup and fakes for the unit tests.

Importing this module puts app/ on the path and replaces the pymad and
pyao modules with fakes, so the tests run without audio hardware, the
music library share or the server API. Import it before any app module.
"""
import os
import sys
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")

if APP not in sys.path:
    sys.path.insert(0, APP)

def wait_until(predicate, timeout=5.0, interval=0.01):
    """Wait until predicate() is true.

    :return: True if it became true before the timeout
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)

    return predicate()

class FakeAudio(object):
    """Describes a fake audio file for FakeMadFile."""

    def __init__(self, frames=5, frame_ms=100, frame_delay=0.001, open_error=None, read_error_at=None, gate=None):
        """Construct a fake audio file.

        :param frames: number of buffers before the end of the stream
        :param frame_ms: milliseconds per buffer
        :param frame_delay: seconds each read takes
        :param open_error: exception raised when the file is opened
        :param read_error_at: buffer index at which read() raises IOError
        :param gate: threading.Event that read() waits on, to simulate a stall
        """
        self.frames = frames
        self.frame_ms = frame_ms
        self.frame_delay = frame_delay
        self.open_error = open_error
        self.read_error_at = read_error_at
        self.gate = gate

        self.lock = threading.Lock()
        self.active_readers = 0
        self.max_readers = 0
        self.opens = 0
        self.reads = 0
        self.position_threads = set()

class FakeMadFile(object):
    """Stands in for mad.MadFile. Files are registered in FakeMadFile.files."""
    files = {}

    def __init__(self, filename):
        audio = FakeMadFile.files.get(filename)

        if audio is None:
            raise IOError(2, "No such file or directory", filename)
        if audio.open_error is not None:
            raise audio.open_error

        audio.opens += 1
        self.audio = audio
        self.position = 0

    def total_time(self):
        return self.audio.frames * self.audio.frame_ms

    def current_time(self):
        self.audio.position_threads.add(threading.current_thread().name)
        return self.position * self.audio.frame_ms

    def read(self):
        audio = self.audio

        with audio.lock:
            audio.active_readers += 1
            audio.max_readers = max(audio.max_readers, audio.active_readers)

        try:
            if audio.gate is not None:
                audio.gate.wait()

            if audio.read_error_at is not None and self.position >= audio.read_error_at:
                raise IOError(112, "Host is down")

            if self.position >= audio.frames:
                return None

            time.sleep(audio.frame_delay)
            self.position += 1
            audio.reads += 1
            return "\0" * 8
        finally:
            with audio.lock:
                audio.active_readers -= 1

class FakeAudioDevice(object):
    """Stands in for ao.AudioDevice and records concurrent writes."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.buffers = 0
        FakeAudioDevice.instances.append(self)

    def play(self, buf, length):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

        time.sleep(0.0005)

        with self.lock:
            self.active -= 1
            self.buffers += 1

class FakeAoError(Exception):
    """Stands in for ao.aoError."""

fake_mad = types.ModuleType("mad")
fake_mad.MadFile = FakeMadFile

fake_ao = types.ModuleType("ao")
fake_ao.AudioDevice = FakeAudioDevice
fake_ao.aoError = FakeAoError
fake_ao.AO_FMT_LITTLE = 1
fake_ao.AO_FMT_NATIVE = 4

sys.modules["mad"] = fake_mad
sys.modules["ao"] = fake_ao
