"""The cache module provides the FileCache class.

The music library lives on a Samba share. When the share stalls, an open()
or read() on it can block inside the kernel, where the process can't be
interrupted or killed, and pymad may hold the GIL while it waits, which
freezes every thread including Tk. To keep the share away from the GUI and
the audio thread, every library file is copied to local disk by a child
process before it is played. A stalled copy only stalls that child, which
is abandoned after a timeout.
"""
import hashlib
import os
import Queue
import re
import subprocess
import sys
import threading
import time
from config import za_config

STATE_PENDING = "pending"
STATE_READY = "ready"
STATE_FAILED = "failed"

COPY_SCRIPT = """import shutil, sys
try:
    shutil.copyfile(sys.argv[1], sys.argv[2])
except (IOError, OSError) as exc:
    sys.stderr.write("FileCache copy failed: %s\\n" % exc)
    sys.exit(1)
"""
POLL_INTERVAL = 0.05
RETRY_AFTER = 60.0
WORKERS = 2

# a child stuck on a dead share ignores SIGKILL until the kernel gives up,
# so stop starting new copies once this many are stuck
MAX_ABANDONED = 4

# only files named like this are ever deleted from the cache directory
CACHE_FILE_PATTERN = re.compile(r"^[0-9a-f]{20}(\.[^.]+)?(\.part)?$")

def default_copy_command(src, dst):
    """Get the command that copies src to dst in a child process."""
    return [sys.executable, "-c", COPY_SCRIPT, src, dst]

class _Entry(object):
    """The state of one cached file."""

    def __init__(self, local_path):
        self.local_path = local_path
        self.state = STATE_PENDING
        self.touched = 0
        self.failed_at = None

class FileCache(object):
    """The FileCache class keeps local copies of library files."""

    def __init__(self, cache_dir, copy_timeout=90.0, max_entries=300,
                 retry_after=RETRY_AFTER, workers=WORKERS,
                 copy_command=default_copy_command, clock=time.time):
        """Construct a file cache.

        Any cache files left in cache_dir by a previous run are deleted.

        :param cache_dir: local directory for copies
        :param copy_timeout: seconds before a copy is abandoned
        :param max_entries: number of copies to keep before evicting
        :param retry_after: seconds before a failed copy may be retried
        :param workers: number of copies to run at once
        :param copy_command: function (src, dst) -> argv of the copy process
        :param clock: time source for eviction and retries
        """
        self._dir = cache_dir
        self._copy_timeout = copy_timeout
        self._max_entries = max_entries
        self._retry_after = retry_after
        self._copy_command = copy_command
        self._clock = clock

        self._lock = threading.Lock()
        self._entries = {}
        self._abandoned = []
        self._jobs = Queue.Queue()

        self._clear_dir()

        self._workers = []
        for i in range(workers):
            worker = threading.Thread(target=self._work, name="FileCache-%d" % i)
            worker.setDaemon(True)
            worker.start()
            self._workers.append(worker)

    def request(self, remote_path):
        """Start copying a file unless it is cached or already being copied.

        A failed copy is retried once retry_after seconds have passed.

        :param remote_path
        :return: state of the file
        """
        with self._lock:
            now = self._clock()
            entry = self._entries.get(remote_path)

            if entry is None:
                entry = _Entry(self._local_name(remote_path))
                self._entries[remote_path] = entry
            elif entry.state == STATE_FAILED and now - entry.failed_at >= self._retry_after:
                entry.state = STATE_PENDING
            else:
                entry.touched = now
                return entry.state

            entry.touched = now
            self._jobs.put(remote_path)
            return entry.state

    def state(self, remote_path):
        """Get the state of a file, or None if it was never requested.

        :param remote_path
        """
        with self._lock:
            entry = self._entries.get(remote_path)
            return None if entry is None else entry.state

    def local_path(self, remote_path):
        """Get the local copy of a file, or None if it is not ready.

        :param remote_path
        """
        with self._lock:
            entry = self._entries.get(remote_path)

            if entry is None or entry.state != STATE_READY:
                return None

            entry.touched = self._clock()
            return entry.local_path

    def close(self):
        """Stop the copy workers once their current copies finish."""
        for _ in self._workers:
            self._jobs.put(None)

    def _local_name(self, remote_path):
        """Get the local path for a remote file."""
        if isinstance(remote_path, unicode):
            remote_path = remote_path.encode("utf-8")

        digest = hashlib.sha1(remote_path).hexdigest()[:20]
        extension = os.path.splitext(remote_path)[1]

        return os.path.join(self._dir, digest + extension)

    def _clear_dir(self):
        """Create the cache directory and remove copies from a previous run."""
        if not os.path.isdir(self._dir):
            os.makedirs(self._dir)

        for name in os.listdir(self._dir):
            if CACHE_FILE_PATTERN.match(name):
                try:
                    os.remove(os.path.join(self._dir, name))
                except OSError:
                    pass

    def _work(self):
        """Copy requested files until closed."""
        while True:
            remote_path = self._jobs.get()

            if remote_path is None:
                return

            with self._lock:
                entry = self._entries.get(remote_path)
                local_path = None if entry is None else entry.local_path

            if local_path is None:
                continue

            copied = self._copy(remote_path, local_path)

            with self._lock:
                entry = self._entries.get(remote_path)

                if entry is not None:
                    if copied:
                        entry.state = STATE_READY
                    else:
                        entry.state = STATE_FAILED
                        entry.failed_at = self._clock()

                evicted = self._evict()

            for path in evicted:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _evict(self):
        """Forget the least recently used copies beyond max_entries.

        Must be called with the lock held.

        :return: local paths to delete
        """
        ready = [(e.touched, path) for path, e in self._entries.items() if e.state == STATE_READY]
        excess = len(ready) - self._max_entries

        if excess <= 0:
            return []

        ready.sort()
        evicted = []

        for _, path in ready[:excess]:
            evicted.append(self._entries.pop(path).local_path)

        return evicted

    def _reap(self):
        """Forget abandoned copy processes that have finally exited."""
        with self._lock:
            self._abandoned = [p for p in self._abandoned if p.poll() is None]
            return len(self._abandoned)

    def _copy(self, remote_path, local_path):
        """Copy a file in a child process.

        :param remote_path
        :param local_path
        :return: True if the copy succeeded
        """
        if self._reap() >= MAX_ABANDONED:
            print time.asctime() + " :=: FileCache :: Too many stuck copies, not copying " + remote_path
            return False

        partial_path = local_path + ".part"

        try:
            proc = subprocess.Popen(self._copy_command(remote_path, partial_path), close_fds=(os.name == "posix"))
        except OSError, exc:
            print time.asctime() + " :=: FileCache :: Could not start copy of " + remote_path + ": " + str(exc)
            return False

        deadline = time.time() + self._copy_timeout

        while proc.poll() is None:
            if time.time() > deadline:
                print time.asctime() + " :=: FileCache :: Copy timed out, abandoning " + remote_path

                try:
                    proc.kill()
                except OSError:
                    pass

                with self._lock:
                    self._abandoned.append(proc)

                return False

            time.sleep(POLL_INTERVAL)

        if proc.returncode != 0:
            print time.asctime() + " :=: FileCache :: Could not copy " + remote_path

            try:
                os.remove(partial_path)
            except OSError:
                pass

            return False

        try:
            if os.path.exists(local_path):
                os.remove(local_path)
            os.rename(partial_path, local_path)
        except OSError, exc:
            print time.asctime() + " :=: FileCache :: Could not store copy of " + remote_path + ": " + str(exc)
            return False

        return True

_CACHE = None
_CACHE_LOCK = threading.Lock()

def get_cache():
    """Get the file cache for this program, creating it on first use.

    Each program gets its own subdirectory, so programs running side by
    side never delete each other's copies.
    """
    global _CACHE

    with _CACHE_LOCK:
        if _CACHE is None:
            program = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "zautomate"
            _CACHE = FileCache(os.path.join(za_config.cache_dir, program),
                               copy_timeout=za_config.copy_timeout,
                               max_entries=za_config.cache_max_entries)

        return _CACHE
