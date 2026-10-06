#!/usr/bin/env python

"""Unit tests for the meter's update timer. Skipped when Tk has no display."""
import sys
import time
import unittest
import Tkinter

sys.path.insert(0, 'app')

from meter import Meter # type: ignore


class MeterTimerTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = Tkinter.Tk()
        except Tkinter.TclError:
            self.skipTest("no display for Tk")

        self.root.withdraw()
        self.data = (1000, 100000, "Title", "Artist")
        self.meter = Meter(self.root, 400, lambda: self.data)

    def tearDown(self):
        self.root.destroy()

    def pending_timers(self):
        return len(self.root.tk.splitlist(self.root.tk.call("after", "info")))

    def test_start_schedules_one_update(self):
        self.meter.start()

        self.assertEqual(1, self.pending_timers())

    def test_reset_cancels_pending_update(self):
        self.meter.start()
        self.meter.reset()

        self.assertEqual(0, self.pending_timers())

    def test_restarts_never_stack_update_loops(self):
        # every track change resets and restarts the meter; each restart
        # used to leave the old update loop running next to the new one
        self.meter.start()
        for _ in range(5):
            self.meter.reset()
            self.meter.start()

        self.assertEqual(1, self.pending_timers())

    def test_meter_stops_at_end_of_track(self):
        self.meter.start()
        self.data = (100000, 100000, "Title", "Artist")

        # let the pending update fire
        deadline = time.time() + 5
        while self.pending_timers() > 0 and time.time() < deadline:
            self.root.update()
            time.sleep(0.01)

        self.assertEqual(0, self.pending_timers())
        self.assertFalse(self.meter._is_playing)


if __name__ == "__main__":
    unittest.main()
