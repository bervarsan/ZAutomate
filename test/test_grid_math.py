#!/usr/bin/env python

"""Unit tests for dependency-free grid helper functions."""
import sys
import unittest

sys.path.insert(0, 'app')

from grid_math import get_next_key, progression, progression_radius # type: ignore


class GridMathTest(unittest.TestCase):
    def test_get_next_key_moves_down_column(self):
        self.assertEqual("2x1", get_next_key(5, 6, "1x1"))

    def test_get_next_key_wraps_to_next_column(self):
        self.assertEqual("1x2", get_next_key(5, 6, "5x1"))

    def test_get_next_key_wraps_bottom_right_to_first_cell(self):
        self.assertEqual("1x1", get_next_key(5, 6, "5x6"))

    def test_progression_radius_from_top_left_corner(self):
        self.assertEqual([(2, 1), (1, 2), (2, 2)], progression_radius(3, 3, (1, 1), 1))

    def test_progression_includes_every_cell_once(self):
        keys = progression(3, 3, (1, 1))

        self.assertEqual(9, len(keys))
        self.assertEqual(9, len(set(keys)))
        self.assertEqual("1x1", keys[0])
        self.assertTrue("3x3" in keys)


if __name__ == "__main__":
    unittest.main()
