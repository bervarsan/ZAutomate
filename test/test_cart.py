#!/usr/bin/env python

"""Unit tests for the cart module, using a fake file cache and fake pymad."""
import unittest

import support
from support import FakeAudio, FakeMadFile, FakeCache, wait_until

from cart import Cart, DEFAULT_LENGTH_MS

REMOTE = "/media/Jemaine/carts/psa.mp3"
LOCAL = "/cache/psa.mp3"


class EvictingCache(FakeCache):
    """A fake cache that can forget a copy, like FileCache eviction."""

    def evict(self, remote_path):
        del self.states[remote_path]
        del self.paths[remote_path]


class CartTest(unittest.TestCase):
    def setUp(self):
        FakeMadFile.files.clear()
        FakeMadFile.files[LOCAL] = FakeAudio(frames=3)
        self.cache = EvictingCache()

    def make_cart(self, **kwargs):
        return Cart("123", u"Title", u"Issuer", u"PSA", REMOTE, file_cache=self.cache, **kwargs)

    def test_constructor_does_not_touch_files(self):
        FakeMadFile.files.clear()

        cart = self.make_cart()

        self.assertEqual([], self.cache.requests)
        self.assertFalse(cart.is_ready())
        self.assertFalse(cart.is_failed())

    def test_prefetch_requests_copy(self):
        cart = self.make_cart()
        cart.prefetch()

        self.assertEqual([REMOTE], self.cache.requests)

    def test_ready_once_copy_is_ready(self):
        cart = self.make_cart()
        cart.prefetch()

        self.assertFalse(cart.is_ready())
        self.assertEqual(None, cart.length())
        self.assertEqual(DEFAULT_LENGTH_MS, cart.expected_length())
        self.assertEqual((0, 0, "Title", "Issuer"), cart.get_meter_data())

        self.cache.finish(REMOTE, LOCAL)

        self.assertTrue(cart.is_ready())
        self.assertEqual(300, cart.length())
        self.assertEqual(300, cart.expected_length())
        self.assertEqual((0, 300, "Title", "Issuer"), cart.get_meter_data())

    def test_start_is_refused_until_ready(self):
        cart = self.make_cart()
        cart.prefetch()

        self.assertFalse(cart.start())
        self.assertFalse(cart.is_playing())

        self.cache.finish(REMOTE, LOCAL)

        self.assertTrue(cart.start())
        self.assertTrue(wait_until(lambda: not cart.is_playing()))
        self.assertEqual(None, cart.playback_error())

    def test_failed_copy_is_failed(self):
        cart = self.make_cart()
        cart.prefetch()
        self.cache.fail(REMOTE)

        self.assertTrue(cart.is_failed())
        self.assertFalse(cart.is_ready())

    def test_unloadable_copy_is_failed(self):
        cart = self.make_cart()
        cart.prefetch()
        self.cache.finish(REMOTE, "/cache/corrupt.mp3")

        self.assertFalse(cart.is_ready())
        self.assertTrue(cart.is_failed())

    def test_replay_after_copy_was_evicted_copies_again(self):
        cart = self.make_cart()
        cart.prefetch()
        self.cache.finish(REMOTE, LOCAL)

        self.assertTrue(cart.start())
        self.assertTrue(wait_until(lambda: not cart.is_playing()))

        self.cache.evict(REMOTE)
        del FakeMadFile.files[LOCAL]

        self.assertFalse(cart.start())
        self.assertFalse(cart.is_ready())
        self.assertEqual([REMOTE, REMOTE], self.cache.requests)
        self.assertEqual("pending", self.cache.state(REMOTE))

    def test_uncached_cart_plays_local_file(self):
        cart = Cart(None, "Fallback", "Fallback", "Fallback", LOCAL, file_cache=self.cache, cached=False)
        cart.prefetch()

        self.assertEqual([], self.cache.requests)
        self.assertTrue(cart.is_ready())

    def test_missing_metadata_becomes_empty(self):
        cart = Cart("1", None, None, None, REMOTE, file_cache=self.cache)

        self.assertEqual("", cart.title)
        self.assertEqual("", cart.issuer)
        self.assertEqual("", cart.cart_type)

    def test_non_ascii_metadata_is_dropped(self):
        cart = Cart("1", u"Caf\xe9", "Bj\xc3\xb6rk", "PSA", REMOTE, file_cache=self.cache)

        self.assertEqual("Caf", cart.title)
        self.assertEqual("Bjrk", cart.issuer)


if __name__ == "__main__":
    unittest.main()
