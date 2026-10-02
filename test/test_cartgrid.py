#!/usr/bin/env python

"""Unit tests for the cartgrid module. Skipped when Tk has no display."""
import unittest
import Tkinter

import support
from support import FakeCart

import cartgrid
from cartgrid import Grid, TEXT_LOADING, TEXT_UNAVAILABLE


class FakeDatabase(object):
    def __init__(self):
        self.logged = []

    def log_cart_async(self, cart_id):
        self.logged.append(cart_id)


class GridTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = Tkinter.Tk()
        except Tkinter.TclError:
            self.skipTest("no display for Tk")

        self.root.withdraw()
        self.frame = Tkinter.Frame(self.root)

        self.database = cartgrid.database
        self.db = FakeDatabase()
        cartgrid.database = self.db

        self.events = []
        self.grid = Grid(self.frame, 1, 2, True,
                         lambda: self.events.append("start"),
                         lambda: self.events.append("stop"),
                         lambda key: self.events.append("end"),
                         None)

    def tearDown(self):
        cartgrid.database = self.database
        self.root.destroy()

    def cell(self, key="1x1"):
        return self.grid._grid[key]

    def length_text(self, key="1x1"):
        cell = self.cell(key)
        return cell._rect.itemcget(cell._length, "text")

    def test_set_cart_prefetches_and_shows_loading(self):
        cart = FakeCart("108", cart_type="PSA", ready=False)

        self.grid.set_cart("1x1", cart)

        self.assertEqual(1, cart.prefetches)
        self.assertEqual(TEXT_LOADING, self.length_text())

    def test_length_shows_once_ready(self):
        cart = FakeCart("108", cart_type="PSA", length=95000, ready=False)
        self.grid.set_cart("1x1", cart)

        cart.ready = True
        self.cell().refresh()

        self.assertEqual("01:35", self.length_text())

    def test_failed_cart_shows_unavailable_and_is_fetched_again(self):
        cart = FakeCart("108", cart_type="PSA", ready=False)
        self.grid.set_cart("1x1", cart)

        cart.failed = True
        self.cell().refresh()

        self.assertEqual(TEXT_UNAVAILABLE, self.length_text())
        self.assertEqual(2, cart.prefetches)

    def test_cart_that_is_not_ready_does_not_start(self):
        cart = FakeCart("108", cart_type="PSA", ready=False)
        self.grid.set_cart("1x1", cart)

        self.grid._left_click(self.cell(), "1x1")

        self.assertFalse(self.grid.is_playing())
        self.assertEqual([], self.events)
        self.assertEqual([], self.db.logged)

    def test_ready_cart_starts_and_is_logged(self):
        cart = FakeCart("108", cart_type="PSA")
        self.grid.set_cart("1x1", cart)

        self.grid._left_click(self.cell(), "1x1")

        self.assertTrue(self.grid.is_playing())
        self.assertEqual(["start"], self.events)
        self.assertEqual(["108"], self.db.logged)

        self.grid._left_click(self.cell(), "1x1")

        self.assertFalse(self.grid.is_playing())
        self.assertEqual(["start", "stop"], self.events)

    def test_unknown_cart_type_does_not_crash(self):
        cart = FakeCart("x", cart_type="Mystery")

        self.grid.set_cart("1x1", cart)
        self.grid.start("1x1")
        self.grid.stop()


if __name__ == "__main__":
    unittest.main()
