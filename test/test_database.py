#!/usr/bin/env python

"""Unit tests for the database and api_client modules, using a fake HTTP session."""
import threading
import unittest

import support
from support import FakeResponse, FakeSession, wait_until

import requests
import database
from api_client import ApiClient, ApiError

TRACK = {
    "lb_album_code": u"L652",
    "lb_track_num": u"2",
    "lb_track_name": u"Jeremiah",
    "artist_name": u"Sierra Ferrell",
    "rotation": u"N",
    "file_name": u"s/i/Sierra Ferrell - Jeremiah.mp3"
}

CART = {
    "cartID": u"108",
    "title": u"Give Blood",
    "issuer": u"Red Cross",
    "type": u"PSA",
    "filename": u"give-blood.mp3"
}


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.client = database.CLIENT
        self.session = FakeSession()
        database.CLIENT = ApiClient(session=self.session)

    def tearDown(self):
        database.CLIENT = self.client

    def respond(self, url, response):
        self.session.responses[url] = response

    def test_get_playlist_builds_tracks_without_opening_files(self):
        self.respond(database.URL_AUTOLOAD, FakeResponse([TRACK]))

        tracks = database.get_playlist(25608)

        self.assertEqual(("GET", database.URL_AUTOLOAD, {"showid": 25608}), self.session.calls[0][:3])
        self.assertEqual(1, len(tracks))
        self.assertEqual("L652-2", tracks[0].cart_id)
        self.assertEqual("Jeremiah", tracks[0].title)
        self.assertEqual("Sierra Ferrell", tracks[0].issuer)
        self.assertEqual("N", tracks[0].cart_type)
        self.assertEqual("/media/Jemaine/s/i/Sierra Ferrell - Jeremiah.mp3", tracks[0].filename)
        self.assertEqual(None, tracks[0].length())

    def test_get_playlist_skips_malformed_tracks(self):
        broken = dict(TRACK)
        del broken["file_name"]

        self.respond(database.URL_AUTOLOAD, FakeResponse([TRACK, broken, None]))

        self.assertEqual(1, len(database.get_playlist(1)))

    def test_get_playlist_handles_unexpected_responses(self):
        self.respond(database.URL_AUTOLOAD, FakeResponse(None))
        self.assertEqual([], database.get_playlist(1))

        self.respond(database.URL_AUTOLOAD, FakeResponse({"error": "no show"}))
        self.assertEqual([], database.get_playlist(1))

        self.respond(database.URL_AUTOLOAD, FakeResponse(ValueError("not JSON")))
        self.assertEqual([], database.get_playlist(1))

    def test_get_playlist_handles_connection_errors(self):
        self.respond(database.URL_AUTOLOAD, requests.exceptions.ConnectionError("down"))

        self.assertEqual([], database.get_playlist(1))

    def test_get_cart_sends_type_id(self):
        self.respond(database.URL_AUTOCART, FakeResponse(CART))

        cart = database.get_cart("PSA")

        self.assertEqual({"type": 0}, self.session.calls[0][2])
        self.assertEqual("108", cart.cart_id)
        self.assertEqual("PSA", cart.cart_type)
        self.assertEqual("/media/Jemaine/carts/give-blood.mp3", cart.filename)

    def test_get_cart_returns_none_without_carts(self):
        self.respond(database.URL_AUTOCART, FakeResponse(None))

        self.assertEqual(None, database.get_cart("StationID"))
        self.assertEqual({"type": 2}, self.session.calls[0][2])

    def test_get_carts_skips_failed_types(self):
        def cartload(params):
            if params["type"] == 1:
                return FakeResponse(None)
            return FakeResponse([CART])

        self.respond(database.URL_CARTLOAD, cartload)

        carts = database.get_carts()

        self.assertEqual([1, 0, 1, 1], [len(carts[t]) for t in range(4)])

    def test_search_library_returns_carts_and_tracks(self):
        track = {
            "album_code": u"L652",
            "track_num": u"2",
            "track_name": u"Jeremiah",
            "artist_name": u"Sierra Ferrell",
            "rotation": u"N",
            "file_name": u"s/i/x.mp3"
        }
        self.respond(database.URL_STUDIOSEARCH, FakeResponse({"carts": [CART], "tracks": [track]}))

        results = database.search_library("jeremiah")

        self.assertEqual(["108", "L652-2"], [r.cart_id for r in results])

    def test_log_cart_routes_carts_and_tracks(self):
        database.log_cart("108")
        database.log_cart("L652-2")

        self.assertEqual(("POST", database.URL_LOG_CART, {"cartid": "108"}), self.session.calls[0][:3])
        self.assertEqual(("POST", database.URL_LOG_TRACK, {"albumID": "L652", "disc_num": 1, "track_num": "2"}),
                         self.session.calls[1][:3])

    def test_log_cart_async_logs_in_order_off_the_calling_thread(self):
        for cart_id in ["1", "2", "3"]:
            database.log_cart_async(cart_id)

        self.assertTrue(wait_until(lambda: len(self.session.calls) == 3))
        self.assertEqual(["1", "2", "3"], [call[2]["cartid"] for call in self.session.calls])
        self.assertFalse(threading.current_thread().name in [call[3] for call in self.session.calls])

    def test_log_cart_async_survives_errors(self):
        attempts = []

        def flaky(params):
            attempts.append(params)
            if len(attempts) == 1:
                raise requests.exceptions.Timeout("slow server")
            return FakeResponse(text="ok")

        self.respond(database.URL_LOG_CART, flaky)

        database.log_cart_async("1")
        database.log_cart_async("2")

        self.assertTrue(wait_until(lambda: len(attempts) == 2))


class ApiClientTest(unittest.TestCase):
    def test_each_thread_gets_its_own_session(self):
        sessions = []

        def factory():
            session = FakeSession({"url": FakeResponse({})})
            sessions.append(session)
            return session

        client = ApiClient(session_factory=factory)
        client.get_json("url")
        client.get_json("url")

        worker = threading.Thread(target=client.get_json, args=("url",))
        worker.start()
        worker.join()

        self.assertEqual(2, len(sessions))

    def test_failures_become_api_errors(self):
        client = ApiClient(session=FakeSession({
            "down": requests.exceptions.ConnectionError("down"),
            "bad-json": FakeResponse(ValueError("not JSON")),
            "server-error": FakeResponse(error=requests.exceptions.HTTPError("500"))
        }))

        self.assertRaises(ApiError, client.get_json, "down")
        self.assertRaises(ApiError, client.get_json, "bad-json")
        self.assertRaises(ApiError, client.get_json, "server-error")
        self.assertRaises(ApiError, client.post_text, "down")


if __name__ == "__main__":
    unittest.main()
