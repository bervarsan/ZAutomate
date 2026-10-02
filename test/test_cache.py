#!/usr/bin/env python

"""Unit tests for the cache module, using real child processes and temp files."""
import os
import shutil
import sys
import tempfile
import time
import unittest

import support
from support import wait_until

import cache
from cache import FileCache, STATE_PENDING, STATE_READY, STATE_FAILED

# a copy command that hangs, like a copy from a stalled share
HANG_SCRIPT = "import time; time.sleep(60)"


class FileCacheTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="za-cache-test-")
        self.share = os.path.join(self.root, "share")
        self.cache_dir = os.path.join(self.root, "cache")
        os.makedirs(self.share)
        self.caches = []
        self.now = [1000.0]

    def tearDown(self):
        for file_cache in self.caches:
            file_cache.close()
            for proc in file_cache._abandoned:
                try:
                    proc.kill()
                    proc.wait()
                except (AttributeError, OSError):
                    pass

        # give killed children a moment to release their files on Windows
        wait_until(lambda: self._remove_root(), timeout=5.0, interval=0.1)

    def _remove_root(self):
        try:
            shutil.rmtree(self.root)
            return True
        except OSError:
            return False

    def make_cache(self, **kwargs):
        kwargs.setdefault("clock", lambda: self.now[0])
        file_cache = FileCache(self.cache_dir, **kwargs)
        self.caches.append(file_cache)
        return file_cache

    def make_file(self, name, content="audio"):
        path = os.path.join(self.share, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def wait_for_state(self, file_cache, path, timeout=10.0):
        wait_until(lambda: file_cache.state(path) != STATE_PENDING, timeout=timeout)
        return file_cache.state(path)

    def test_copies_file_to_local_disk(self):
        remote = self.make_file("song.mp3", "some audio")
        file_cache = self.make_cache()

        self.assertEqual(None, file_cache.local_path(remote))
        self.assertEqual(STATE_PENDING, file_cache.request(remote))
        self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))

        local = file_cache.local_path(remote)
        self.assertEqual(self.cache_dir, os.path.dirname(local))
        self.assertTrue(local.endswith(".mp3"))
        with open(local, "rb") as f:
            self.assertEqual("some audio", f.read())
        self.assertFalse(os.path.exists(local + ".part"))

    def test_missing_file_fails(self):
        file_cache = self.make_cache()
        remote = os.path.join(self.share, "missing.mp3")

        file_cache.request(remote)

        self.assertEqual(STATE_FAILED, self.wait_for_state(file_cache, remote))
        self.assertEqual(None, file_cache.local_path(remote))

    def test_stalled_copy_times_out(self):
        remote = self.make_file("song.mp3")
        file_cache = self.make_cache(copy_timeout=0.5,
                                     copy_command=lambda src, dst: [sys.executable, "-c", HANG_SCRIPT])

        started = time.time()
        file_cache.request(remote)

        self.assertEqual(STATE_FAILED, self.wait_for_state(file_cache, remote))
        self.assertTrue(time.time() - started < 5.0)
        self.assertEqual(1, len(file_cache._abandoned))

    def test_stuck_copies_stop_new_copies(self):
        # a child blocked on a dead share survives SIGKILL until the
        # kernel gives up, which a test can't reproduce, so fake it
        class StuckProcess(object):
            def poll(self):
                return None

            def kill(self):
                pass

        commands = []

        def copy(src, dst):
            commands.append(src)
            return cache.default_copy_command(src, dst)

        file_cache = self.make_cache(copy_command=copy)
        file_cache._abandoned.extend([StuckProcess() for _ in range(cache.MAX_ABANDONED)])

        remote = self.make_file("song.mp3")
        file_cache.request(remote)

        self.assertEqual(STATE_FAILED, self.wait_for_state(file_cache, remote))
        self.assertEqual(0, len(commands))

    def test_exited_stuck_copies_are_forgotten(self):
        class ExitedProcess(object):
            def poll(self):
                return -9

        file_cache = self.make_cache()
        file_cache._abandoned.extend([ExitedProcess() for _ in range(cache.MAX_ABANDONED)])

        remote = self.make_file("song.mp3")
        file_cache.request(remote)

        self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))
        self.assertEqual(0, len(file_cache._abandoned))

    def test_request_while_pending_copies_once(self):
        commands = []

        def slow_copy(src, dst):
            commands.append(src)
            return [sys.executable, "-c", "import shutil, sys, time; time.sleep(0.3); shutil.copyfile(sys.argv[1], sys.argv[2])", src, dst]

        remote = self.make_file("song.mp3")
        file_cache = self.make_cache(copy_command=slow_copy)

        for _ in range(5):
            file_cache.request(remote)

        self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))
        file_cache.request(remote)

        self.assertEqual(1, len(commands))

    def test_failed_copy_is_retried_after_delay(self):
        file_cache = self.make_cache(retry_after=60)
        remote = os.path.join(self.share, "late.mp3")

        file_cache.request(remote)
        self.assertEqual(STATE_FAILED, self.wait_for_state(file_cache, remote))

        # the share comes back, but the retry delay hasn't passed
        self.make_file("late.mp3")
        self.assertEqual(STATE_FAILED, file_cache.request(remote))

        self.now[0] += 61
        self.assertEqual(STATE_PENDING, file_cache.request(remote))
        self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))

    def test_evicts_least_recently_used(self):
        file_cache = self.make_cache(max_entries=2)
        remotes = [self.make_file("song%d.mp3" % i) for i in range(3)]

        for remote in remotes:
            self.now[0] += 1
            file_cache.request(remote)
            self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))

        self.assertEqual(None, file_cache.state(remotes[0]))
        self.assertEqual(2, len(os.listdir(self.cache_dir)))

    def test_recently_used_copy_is_kept(self):
        file_cache = self.make_cache(max_entries=2)
        remotes = [self.make_file("song%d.mp3" % i) for i in range(3)]

        for remote in remotes[:2]:
            self.now[0] += 1
            file_cache.request(remote)
            self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remote))

        # using the oldest copy keeps it
        self.now[0] += 1
        file_cache.local_path(remotes[0])

        self.now[0] += 1
        file_cache.request(remotes[2])
        self.assertEqual(STATE_READY, self.wait_for_state(file_cache, remotes[2]))

        self.assertEqual(STATE_READY, file_cache.state(remotes[0]))
        self.assertEqual(None, file_cache.state(remotes[1]))

    def test_startup_removes_only_old_copies(self):
        os.makedirs(self.cache_dir)
        old_copy = os.path.join(self.cache_dir, "0123456789abcdef0123.mp3")
        old_partial = os.path.join(self.cache_dir, "0123456789abcdef0123.mp3.part")
        unrelated = os.path.join(self.cache_dir, "notes.txt")

        for path in (old_copy, old_partial, unrelated):
            with open(path, "wb") as f:
                f.write("x")

        self.make_cache()

        self.assertFalse(os.path.exists(old_copy))
        self.assertFalse(os.path.exists(old_partial))
        self.assertTrue(os.path.exists(unrelated))


if __name__ == "__main__":
    unittest.main()
