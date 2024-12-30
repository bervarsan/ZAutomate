"""The meter module provides the Meter class."""
import time
import threading
import tkinter
from tkinter import Canvas

METER_HEIGHT = 135
METER_INTERVAL = 0.50

COLOR_METER_BG = "#000000"
COLOR_METER_TEXT = "#33CCCC"
COLOR_BAR_BG = "#008500"
COLOR_BAR_FG = "#FF0000"

FONT_HEAD = ("Helvetica", 22, "bold")
FONT_SMALL = ("Helvetica", 12)
FONT_NUM = ("Courier", 22, "bold")

TEXT_POSITION = "Position"
TEXT_LENGTH = "Length"
TEXT_CUE = "To Cue"


def get_fmt_time(seconds):
    """Get a formatted time string from a number of seconds.

    :param seconds
    """
    return time.strftime("%M:%S", time.localtime(seconds))


class Meter(Canvas):
    """The Meter class is a UI element that shows the elapsed time of a track."""
    _data_callback = None
    _is_playing = False

    _position = None
    _length = None
    _cue = None
    _title = None
    _artist = None

    def __init__(self, master, width, data_callback):
        """Construct a Meter.

        :param master
        :param width
        :param data_callback: function to retrieve meter data
        :param end_callback: function to call upon completion
        """
        Canvas.__init__(self, master, bg=COLOR_METER_BG, borderwidth=2, relief=tkinter.GROOVE, width=width,
                        height=METER_HEIGHT)

        self._data_callback = data_callback

        self._width = int(self.cget("width"))
        self._x0 = 0
        self._y0 = METER_HEIGHT - 25
        self._x1 = self._width + 5
        self._y1 = METER_HEIGHT

        self.create_text(10, 60, anchor=tkinter.W, font=FONT_SMALL, text=TEXT_POSITION, fill=COLOR_METER_TEXT)
        self.create_text(140, 60, anchor=tkinter.W, font=FONT_SMALL, text=TEXT_LENGTH, fill=COLOR_METER_TEXT)
        self.create_text(270, 60, anchor=tkinter.W, font=FONT_SMALL, text=TEXT_CUE, fill=COLOR_METER_TEXT)

        self._position = self.create_text(10, 85, anchor=tkinter.W, font=FONT_NUM, fill=COLOR_METER_TEXT)
        self._length = self.create_text(140, 85, anchor=tkinter.W, font=FONT_NUM, fill=COLOR_METER_TEXT)
        self._cue = self.create_text(270, 85, anchor=tkinter.W, font=FONT_NUM, fill=COLOR_METER_TEXT)
        self._title = self.create_text(10, 20, anchor=tkinter.W, font=FONT_HEAD, fill=COLOR_METER_TEXT)
        self._artist = self.create_text(self._width, 20, anchor=tkinter.E, font=FONT_HEAD, fill=COLOR_METER_TEXT)

        self._bar_bg = self.create_rectangle(self._x0, self._y0, self._x1, self._y1, fill=COLOR_BAR_BG)
        self._bar_fg = self.create_rectangle(self._x0, self._y0, self._x0, self._y1, fill=COLOR_BAR_FG)

        self.reset()

    def _run(self):
        """Run the meter in a separate thread."""
        while self._is_playing:
            data = self._data_callback()
            if data is None:
                data = (0, 0, "--", "--")

            if data[0] >= data[1]:
                break

            if data[1] is not 0:
                value = float(data[0]) / float(data[1])
            else:
                value = 0.0

            position = int(data[0]) / 1000
            length = int(data[1]) / 1000
            cue = length - position
            title = data[2]
            artist = data[3]

            self.itemconfigure(self._position, text=get_fmt_time(position))
            self.itemconfigure(self._length, text=get_fmt_time(length))
            self.itemconfigure(self._cue, text=get_fmt_time(cue))
            self.itemconfigure(self._title, text=title)
            self.itemconfigure(self._artist, text=artist)
            self.coords(self._bar_fg, self._x0, self._y0, int(self._width * value), self._y1)

            time.sleep(METER_INTERVAL)

    def start(self):
        """Start the meter."""
        self._is_playing = True
        thread = threading.Thread(target=self._run, daemon=True)  # Set daemon=True
        thread.start()

    def reset(self):
        """Reset the meter."""
        self._is_playing = False

        self.itemconfigure(self._position, text=get_fmt_time(0))
        self.itemconfigure(self._length, text=get_fmt_time(0))
        self.itemconfigure(self._cue, text=get_fmt_time(0))
        self.itemconfigure(self._title, text="--")
        self.itemconfigure(self._artist, text="--")
        self.coords(self._bar_fg, self._x0, self._y0, self._x0, self._y1)
