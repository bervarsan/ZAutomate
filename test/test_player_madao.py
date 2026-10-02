#!/usr/bin/env python

"""Unit tests for the player_madao module, using fake pymad and pyao."""
import threading
import time
import unittest

import support
from support import FakeAudio, FakeMadFile, FakeAudioDevice, FakeAoError, wait_until

import player_madao
from player_madao import Player


class PlayerTest(unittest.TestCase):
    def setUp(self):
        FakeMadFile.files.clear()
        self.gates = []
        self.join_timeout = player_madao.STOP_JOIN_TIMEOUT
        self.get_device = player_madao.get_device
        player_madao.STOP_JOIN_TIMEOUT = 0.1

    def tearDown(self):
        # release any worker that is still waiting on a stalled read
        for gate in self.gates:
            gate.set()

        player_madao.STOP_JOIN_TIMEOUT = self.join_timeout
        player_madao.get_device = self.get_device

    def add_file(self, name="a.mp3", **kwargs):
        audio = FakeAudio(**kwargs)
        FakeMadFile.files[name] = audio
        return audio

    def add_gate(self):
        gate = threading.Event()
        self.gates.append(gate)
        return gate

    def test_missing_file_raises_ioerror(self):
        self.assertRaises(IOError, Player, "missing.mp3")

    def test_plays_to_end_then_stops_and_calls_back(self):
        self.add_file(frames=5)
        ended = threading.Event()

        player = Player("a.mp3")
        self.assertTrue(player.play(ended.set))

        self.assertTrue(ended.wait(5))
        self.assertFalse(player.is_playing())
        self.assertEqual(500, player.length())
        self.assertEqual(500, player.time_elapsed())
        self.assertEqual(None, player.error)

    def test_read_error_ends_playback(self):
        # the Samba "Host is down" error from the 2026-08-23 log used to
        # kill the worker and leave the player "playing" forever
        self.add_file(frames=10, read_error_at=3)

        player = Player("a.mp3")
        player.play()

        self.assertTrue(wait_until(lambda: not player.is_playing()))
        self.assertTrue(isinstance(player.error, IOError))

    def test_device_error_ends_playback(self):
        def broken_device():
            raise FakeAoError("no device")

        player_madao.get_device = broken_device
        self.add_file()

        player = Player("a.mp3")
        player.play()

        self.assertTrue(wait_until(lambda: not player.is_playing()))
        self.assertTrue(isinstance(player.error, FakeAoError))

    def test_end_of_track_does_not_reopen_file(self):
        audio = self.add_file(frames=3)

        player = Player("a.mp3")
        player.play()

        self.assertTrue(wait_until(lambda: not player.is_playing()))
        self.assertEqual(1, audio.opens)

    def test_replay_after_end_starts_over(self):
        audio = self.add_file(frames=3)

        player = Player("a.mp3")
        player.play()
        self.assertTrue(wait_until(lambda: not player.is_playing()))

        self.assertTrue(player.play())
        self.assertTrue(wait_until(lambda: not player.is_playing()))

        self.assertEqual(2, audio.opens)
        self.assertEqual(6, audio.reads)

    def test_replay_raises_if_file_cannot_be_reopened(self):
        audio = self.add_file(frames=2)

        player = Player("a.mp3")
        player.play()
        self.assertTrue(wait_until(lambda: not player.is_playing()))

        audio.open_error = IOError(112, "Host is down")

        self.assertRaises(IOError, player.play)
        self.assertFalse(player.is_playing())

    def test_play_while_playing_is_refused(self):
        self.add_file(frames=100, frame_delay=0.005)

        player = Player("a.mp3")
        self.assertTrue(player.play())
        self.assertFalse(player.play())
        player.stop()

    def test_stop_then_play_never_runs_two_readers(self):
        audio = self.add_file(frames=500, frame_delay=0.002)

        player = Player("a.mp3")
        for _ in range(20):
            player.play()
            time.sleep(0.003)
            player.stop()

        player.play()
        time.sleep(0.02)
        player.stop()

        self.assertEqual(1, audio.max_readers)
        self.assertEqual(1, max(device.max_active for device in FakeAudioDevice.instances))

    def test_play_is_refused_while_stopped_worker_is_stuck(self):
        gate = self.add_gate()
        audio = self.add_file(frames=10, gate=gate)

        player = Player("a.mp3")
        player.play()
        self.assertTrue(wait_until(lambda: audio.active_readers == 1))

        player.stop()

        started = time.time()
        self.assertFalse(player.play())
        self.assertTrue(time.time() - started < 1.0)

        # once the stuck read returns, the old worker exits quietly
        gate.set()
        self.assertTrue(wait_until(lambda: not player._thread.is_alive()))
        self.assertFalse(player.is_playing())

        self.assertTrue(player.play())
        self.assertTrue(wait_until(lambda: not player.is_playing()))
        self.assertEqual(1, audio.max_readers)

    def test_stalled_read_does_not_block_callers(self):
        gate = self.add_gate()
        audio = self.add_file(gate=gate)

        started = time.time()

        player = Player("a.mp3")
        player.play()
        self.assertTrue(wait_until(lambda: audio.active_readers == 1))

        player.is_playing()
        player.time_elapsed()
        player.length()
        player.stop()

        self.assertTrue(time.time() - started < 1.0)

    def test_position_is_only_read_by_worker(self):
        audio = self.add_file(frames=20, frame_delay=0.002)

        player = Player("a.mp3")
        player.play()

        def poll_position():
            player.time_elapsed()
            return not player.is_playing()

        self.assertTrue(wait_until(poll_position, interval=0.001))
        self.assertFalse(threading.current_thread().name in audio.position_threads)


if __name__ == "__main__":
    unittest.main()
