#!/usr/bin/env python

"""Unit tests for the cartqueue module, using fake carts, a fake clock and a fake server."""
import datetime
import unittest

import support
from support import FakeAudio, FakeCart, FakeClock, FakeMadFile, wait_until

import cartqueue
from cart import Cart
from cartqueue import CartQueue, CART_TYPES, FALLBACK_TYPE


class FakeDatabase(object):
    """Stands in for the database module."""

    def __init__(self):
        self.playlists = []
        self.next_show_id = 100
        self.playlist_requests = 0
        self.fail_playlists = False
        self.carts = []
        self.cart_factory = lambda cart_type: None
        self.logged = []

    def get_new_show_id(self, show_id):
        self.next_show_id += 1
        return self.next_show_id

    def get_playlist(self, show_id):
        self.playlist_requests += 1

        if self.fail_playlists:
            raise RuntimeError("server error")

        return self.playlists.pop(0) if self.playlists else []

    def get_cart(self, cart_type):
        cart = self.cart_factory(cart_type)
        if cart is not None:
            self.carts.append(cart)
        return cart

    def log_cart_async(self, cart_id):
        self.logged.append(cart_id)


class DeferredSpawner(object):
    """Holds background jobs until the test runs them."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job):
        self.jobs.append(job)

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


class CartQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.database = cartqueue.database
        self.db = FakeDatabase()
        cartqueue.database = self.db

        self.clock = FakeClock()
        self.events = []
        self.fallback_carts = []
        self.queue = self.make_queue()

    def tearDown(self):
        cartqueue.database = self.database

    def make_queue(self, spawn=None):
        return CartQueue(lambda: self.events.append("start"),
                         lambda: self.events.append("stop"),
                         lambda: self.events.append("change"),
                         spawn=spawn or (lambda job: job()),
                         now=self.clock,
                         fallback=self.make_fallback)

    def make_fallback(self):
        return self.fallback_carts.pop(0) if self.fallback_carts else None

    def make_tracks(self, count, prefix="t", **kwargs):
        return [FakeCart("%s%d" % (prefix, i), **kwargs) for i in range(count)]

    def load(self, tracks):
        """Have the server return a playlist and let the queue fetch it."""
        self.db.playlists.append(tracks)
        self.queue.tick()
        self.queue.tick()

    def run_ticks(self, count, step=1.0):
        for _ in range(count):
            self.queue.tick()
            self.clock.advance(step)

    def current(self):
        return self.queue.get_current()

    def carts_in_queue(self, cart_type=None):
        return [c for c in self.queue.get_queue()
                if c.cart_type in CART_TYPES and (cart_type is None or c.cart_type == cart_type)]


class PlaybackTest(CartQueueTestCase):
    def test_start_with_empty_queue_waits_then_plays(self):
        self.queue.start()
        self.run_ticks(3)
        self.assertEqual(None, self.current())

        tracks = self.make_tracks(12)
        self.db.playlists.append(tracks)
        self.run_ticks(10)

        self.assertTrue(self.current() is tracks[0])

    def test_added_tracks_are_prefetched(self):
        tracks = self.make_tracks(12)
        self.load(tracks)

        self.assertEqual(tracks, self.queue.get_queue())
        self.assertEqual([1] * 12, [t.prefetches for t in tracks])

    def test_track_end_starts_next_and_logs_each_once(self):
        tracks = self.make_tracks(12)
        self.load(tracks)

        self.queue.start()
        self.assertTrue(self.current() is tracks[0])

        tracks[0].end()
        self.queue.tick()
        self.queue.tick()

        self.assertTrue(self.current() is tracks[1])
        self.assertFalse(tracks[0] in self.queue.get_queue())
        self.assertEqual(["t0", "t1"], self.db.logged)
        self.assertEqual(["start", "stop", "start"], [e for e in self.events if e != "change"])

    def test_tracks_still_copying_are_skipped(self):
        tracks = self.make_tracks(12)
        tracks[0].ready = False
        self.load(tracks)

        self.queue.start()

        self.assertTrue(self.current() is tracks[1])
        self.assertTrue(self.queue.get_queue()[1] is tracks[0])

    def test_tracks_that_failed_to_copy_are_dropped(self):
        tracks = self.make_tracks(12)
        tracks[1].ready = False
        tracks[1].failed = True
        self.load(tracks)

        self.assertFalse(tracks[1] in self.queue.get_queue())

    def test_track_that_fails_to_start_is_dropped(self):
        tracks = self.make_tracks(12)
        tracks[0].start_result = False
        self.load(tracks)

        self.queue.start()
        self.queue.tick()

        self.assertTrue(self.current() is tracks[1])
        self.assertFalse(tracks[0] in self.queue.get_queue())
        self.assertEqual(["t1"], self.db.logged)

    def test_start_times_follow_queue_order(self):
        tracks = self.make_tracks(12, length=60000)
        self.load(tracks)
        self.queue.start()

        queue = self.queue.get_queue()
        self.assertEqual(self.clock.time, queue[0].start_time)
        for i in range(1, len(queue)):
            self.assertEqual(datetime.timedelta(minutes=1), queue[i].start_time - queue[i - 1].start_time)

    def test_repeated_playback_errors_back_off(self):
        tracks = self.make_tracks(12)
        self.load(tracks)
        self.queue.start()

        for i in range(cartqueue.ERROR_LIMIT):
            self.current().end(error=IOError("broken"))
            self.queue.tick()

        self.assertEqual(None, self.current())

        self.clock.advance(cartqueue.ERROR_BACKOFF_SECONDS + 1)
        self.queue.tick()

        self.assertTrue(self.current() is tracks[cartqueue.ERROR_LIMIT])


class FallbackTest(CartQueueTestCase):
    def test_fallback_plays_when_nothing_is_ready(self):
        tracks = self.make_tracks(12, ready=False)
        self.load(tracks)

        fallback = FakeCart("fallback", cart_type=FALLBACK_TYPE)
        self.fallback_carts.append(fallback)

        self.queue.start()
        self.run_ticks(cartqueue.FALLBACK_WAIT_SECONDS - 1)
        self.assertEqual(None, self.current())

        self.run_ticks(2)
        self.assertTrue(self.current() is fallback)
        self.assertEqual([], self.db.logged)

        # once a track is ready, it plays after the fallback
        tracks[0].ready = True
        fallback.end()
        self.queue.tick()

        self.assertTrue(self.current() is tracks[0])
        self.assertFalse(fallback in self.queue.get_queue())

    def test_no_fallback_keeps_waiting(self):
        self.load(self.make_tracks(12, ready=False))

        self.queue.start()
        self.run_ticks(cartqueue.FALLBACK_WAIT_SECONDS * 3)

        self.assertEqual(None, self.current())


class StopTest(CartQueueTestCase):
    def test_hard_stop_removes_only_current_track(self):
        # a pending monitor callback used to transition a second time
        # after a hard stop, dropping a track that never played
        tracks = self.make_tracks(12)
        self.load(tracks)
        self.queue.start()

        self.queue.stop_hard()
        self.run_ticks(5)

        self.assertEqual(None, self.current())
        self.assertEqual(tracks[1:], self.queue.get_queue())
        self.assertEqual(1, tracks[0].stops)
        self.assertEqual(0, tracks[1].starts)

    def test_soft_stop_finishes_current_track(self):
        tracks = self.make_tracks(12)
        self.load(tracks)
        self.queue.start()

        self.queue.stop_soft()
        self.queue.tick()
        self.assertTrue(self.current() is tracks[0])

        tracks[0].end()
        self.run_ticks(5)

        self.assertEqual(None, self.current())
        self.assertEqual(0, tracks[1].starts)
        self.assertEqual("stop", [e for e in self.events if e != "change"][-1])

    def test_soft_stop_with_nothing_playing_stops_now(self):
        self.queue.start()
        self.queue.stop_soft()

        self.assertFalse(self.queue.is_busy())

    def test_restart_after_hard_stop_plays_next_track(self):
        tracks = self.make_tracks(12)
        self.load(tracks)
        self.queue.start()
        self.queue.stop_hard()

        self.queue.start()

        self.assertTrue(self.current() is tracks[1])


class RefillTest(CartQueueTestCase):
    def test_refills_when_queue_runs_short(self):
        self.load(self.make_tracks(cartqueue.PLAYLIST_MIN_LENGTH))
        self.queue.start()

        more = self.make_tracks(5, prefix="u")
        self.db.playlists.append(more)

        self.current().end()
        self.queue.tick()
        self.queue.tick()

        self.assertEqual(cartqueue.PLAYLIST_MIN_LENGTH - 1 + 5, len(self.queue.get_queue()))

    def test_refill_is_not_repeated_while_in_flight(self):
        spawner = DeferredSpawner()
        self.queue = self.make_queue(spawn=spawner)

        for _ in range(10):
            self.queue.tick()

        spawner.run_all()
        self.assertEqual(1, self.db.playlist_requests)

    def test_empty_playlists_back_off_instead_of_looping(self):
        # add_tracks used to loop forever, blocking the GUI, while the
        # server returned nothing usable
        self.queue.start()
        for _ in range(50):
            self.queue.tick()

        self.assertEqual(1, self.db.playlist_requests)

        self.clock.advance(cartqueue.FETCH_RETRY_SECONDS + 1)
        self.queue.tick()

        self.assertEqual(2, self.db.playlist_requests)

    def test_fetch_errors_are_contained(self):
        self.db.fail_playlists = True

        self.queue.start()
        for _ in range(5):
            self.queue.tick()

        self.assertEqual(1, self.db.playlist_requests)

        self.clock.advance(cartqueue.FETCH_RETRY_SECONDS + 1)
        self.queue.tick()
        self.queue.tick()

        self.assertEqual(2, self.db.playlist_requests)

    def test_tracks_failing_to_copy_slow_down_refills(self):
        # while the share is down every track fails to copy; refilling
        # must not hammer the server as fast as it answers
        def failing_playlist(show_id):
            self.db.playlist_requests += 1
            tracks = self.make_tracks(3, prefix="f%d-" % self.db.playlist_requests)
            for track in tracks:
                track.ready = False
                track.failed = True
            return tracks

        self.db.get_playlist = failing_playlist

        for _ in range(50):
            self.queue.tick()

        self.assertEqual(1, self.db.playlist_requests)

        self.clock.advance(cartqueue.FETCH_RETRY_SECONDS + 1)
        self.queue.tick()

        self.assertEqual(2, self.db.playlist_requests)

    def test_artists_already_queued_are_skipped(self):
        # artists used to be compared with "is", so equal names from
        # different playlists didn't match
        first = FakeCart("a", issuer="".join(["Ar", "tist"]))
        second = FakeCart("b", issuer="".join(["Ar", "tist"]))
        self.assertFalse(first.issuer is second.issuer)

        self.db.playlists.extend([[first], [second]])
        for _ in range(4):
            self.queue.tick()

        self.assertEqual([first], self.queue.get_queue())

    def test_recently_played_artists_are_skipped(self):
        tracks = self.make_tracks(10)
        self.load(tracks)
        self.queue.start()

        self.current().end()
        self.queue.tick()

        self.db.playlists.append([FakeCart("again", issuer=tracks[0].issuer)])
        self.queue.tick()
        self.queue.tick()

        self.assertEqual([], [t for t in self.queue.get_queue() if t.cart_id == "again"])


class CartInsertionTest(CartQueueTestCase):
    def setUp(self):
        CartQueueTestCase.setUp(self)
        self.made = 0
        self.carts_ready = True
        self.db.cart_factory = self.make_cart

    def make_cart(self, cart_type):
        self.made += 1
        return FakeCart("%s%d" % (cart_type, self.made), issuer=cart_type, cart_type=cart_type,
                        length=30000, ready=self.carts_ready)

    def start_hour(self, minute=0, tracks=12):
        self.clock.time = datetime.datetime(2026, 9, 30, 10, minute, 0)
        self.load(self.make_tracks(tracks))
        self.queue.start()
        self.run_ticks(3, step=0.1)

    def test_station_id_is_inserted_near_its_target(self):
        self.start_hour()

        station_ids = self.carts_in_queue("StationID")
        self.assertEqual(1, len(station_ids))

        target = datetime.datetime(2026, 9, 30, 10, 5, 0)
        self.assertTrue(abs(station_ids[0].start_time - target) <= datetime.timedelta(minutes=3))

    def test_each_slot_is_filled_once(self):
        self.start_hour()
        self.run_ticks(20, step=0.1)

        self.assertEqual(1, len(self.carts_in_queue("StationID")))
        self.assertEqual(2, len(self.carts_in_queue("PSA")))
        self.assertEqual(1, len(self.carts_in_queue("Underwriting")))

    def test_passed_slots_are_skipped(self):
        self.start_hour(minute=20)

        self.assertEqual(0, len(self.carts_in_queue("StationID")))
        self.assertEqual(1, len(self.carts_in_queue("PSA")))
        self.assertEqual(1, len(self.carts_in_queue("Underwriting")))

    def test_carts_are_not_inserted_in_front_of_current_track(self):
        self.start_hour()

        self.assertTrue(self.queue.get_queue()[0] is self.current())
        self.assertFalse(self.current().cart_type in CART_TYPES)

    def test_one_track_queue_does_not_crash(self):
        # min_delta was None with a one-item queue, which raised
        self.start_hour(tracks=1)
        self.run_ticks(5, step=0.1)

        self.assertEqual(1, len(self.queue.get_queue()))

    def test_carts_wait_until_ready(self):
        self.carts_ready = False
        self.start_hour()

        self.assertEqual([], self.carts_in_queue())

        for cart in self.db.carts:
            cart.ready = True
        self.queue.tick()

        self.assertEqual(1, len(self.carts_in_queue("StationID")))

    def test_dropped_cart_slot_is_filled_again(self):
        self.start_hour()
        station_id = self.carts_in_queue("StationID")[0]

        station_id.ready = False
        station_id.failed = True
        self.run_ticks(3, step=0.1)

        station_ids = self.carts_in_queue("StationID")
        self.assertEqual(1, len(station_ids))
        self.assertFalse(station_ids[0] is station_id)

    def test_stop_removes_carts_and_restart_inserts_them_again(self):
        self.start_hour()
        self.queue.stop_hard()

        self.assertEqual([], self.carts_in_queue())

        self.queue.start()
        self.run_ticks(3, step=0.1)

        self.assertEqual(1, len(self.carts_in_queue("StationID")))


class RealCartTest(CartQueueTestCase):
    def test_real_carts_play_through_the_queue(self):
        FakeMadFile.files.clear()
        tracks = []

        for i in range(3):
            remote = "/media/Jemaine/t%d.mp3" % i
            FakeMadFile.files[remote] = FakeAudio(frames=3)
            tracks.append(Cart("T%d-1" % i, "Track %d" % i, "Artist %d" % i, "N", remote))

        self.load(tracks)
        self.queue.start()

        def advance():
            self.queue.tick()
            return len(self.db.logged) == 3 and self.current() is None

        self.assertTrue(wait_until(advance))
        self.assertEqual(["T0-1", "T1-1", "T2-1"], self.db.logged)


if __name__ == "__main__":
    unittest.main()
