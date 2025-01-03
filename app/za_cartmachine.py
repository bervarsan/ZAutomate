#!/usr/bin/env python

"""The CartMachine module provides a GUI for playing carts."""
import random
import tkinter
from tkinter import Frame, Label, Button
import database
from cartgrid import Grid
from meter import Meter

METER_WIDTH = 1000
GRID_ROWS = 8
GRID_COLS = 6

# configuration for each cart type
CONFIG_CARTS = {
    # PSA
    0: {
        "corner": (1, 1),
        "limit": -1
    },
    # Underwriting
    1: {
        "corner": (GRID_ROWS, GRID_COLS),
        "limit": -1
    },
    # Station ID
    2: {
        "corner": (1, GRID_COLS),
        "limit": 9
    },
    # Promotion
    3: {
        "corner": (GRID_ROWS, 1),
        "limit": -1
    }
}

COLOR_RELOAD_BG = "#FF0000"
COLOR_RELOAD_FG = "#000000"

FONT_TITLE = ('Helvetica', 36, 'bold italic')
FONT_RELOAD = ('Helvetica', 24, 'bold')

TEXT_TITLE = "ZAutomate :: Cart Machine"
TEXT_RELOAD = "Reload"


def progression_radius(rows, cols, corner, radius):
    """Generate a progression of coordinates at a given radius from a corner.

    Examples:
    - radius = 0 yields the corner
    - radius = 1 yields the 3 coordinates around the corner
    - radius = 2 yields the 5 coordinates around the previous 3, etc

    :param rows: rows in the grid
    :param cols: columns in the grid
    :param corner: corner coordinate as a 2-tuple (row, col)
    :param radius: number of diagonal cells from corner
    """

    # determine the directions from the corner
    if corner[0] == 1:
        dirR = 1
    elif corner[0] == rows:
        dirR = -1

    if corner[1] == 1:
        dirC = 1
    elif corner[1] == cols:
        dirC = -1

    # determine the pivot from the corner and radius
    pivot = (corner[0] + dirR * radius, corner[1] + dirC * radius)

    array = []

    # append coordinates along the same row
    for col in range(corner[1], pivot[1], dirC):
        array.append((pivot[0], col))

    # append coordinates along the same column
    for row in range(corner[0], pivot[0], dirR):
        array.append((row, pivot[1]))

    # append the pivot coordinate
    array.append(pivot)

    # filter valid coordinates
    array = [elem for elem in array if 0 < elem[0] <= rows and 0 < elem[1] <= cols]

    return array


def progression(rows, cols, corner):
    """Generate a progression of coordinates from a corner.

    The progression begins at the corner and expands outward
    until every coordinate in the grid is included.

    :param rows: rows in the grid
    :param cols: columns in the grid
    :param corner: corner coordinate as a 2-tuple (row, col)
    """

    # append each radius of the progression
    array = []

    for radius in range(0, max(rows, cols)):
        array.extend(progression_radius(rows, cols, corner, radius))

    # temporary code to transform tuples into strings
    array = [str(elem[0]) + "x" + str(elem[1]) for elem in array]

    return array


class CartMachine(Frame):
    """The CartMachine class is a GUI that provides a grid of carts."""
    _meter = None
    _grid = None

    def __init__(self):
        """Construct a CartMachine window."""
        Frame.__init__(self)

        # make the window resizable
        top = self.winfo_toplevel()
        for row in range(2, GRID_ROWS + 2):
            for col in range(0, GRID_COLS):
                top.rowconfigure(row, weight=1)
                top.columnconfigure(col, weight=1)
                self.rowconfigure(row, weight=1)
                self.columnconfigure(col, weight=1)

        # initialize the title
        title = Label(self.master, font=FONT_TITLE, text=TEXT_TITLE)
        title.grid(row=0, column=0, columnspan=GRID_COLS - 1, sticky=tkinter.N)

        # initialize the reload button
        reload_button = Button(self.master, \
                               bg=COLOR_RELOAD_BG, fg=COLOR_RELOAD_FG, \
                               font=FONT_RELOAD, text=TEXT_RELOAD, \
                               command=self.reload)
        reload_button.grid(row=0, column=GRID_COLS - 1)

        # initialize the meter
        self._meter = Meter(self.master, METER_WIDTH, self._get_meter_data)
        self._meter.grid(row=1, column=0, columnspan=GRID_COLS)
        # self._meter.grid_propagate(0)

        # initialize the grid
        self._grid = Grid(self, GRID_ROWS, GRID_COLS, False, self._cart_start, self._cart_stop, self._cart_end, None)
        self._load()

        # begin the event loop
        self.master.protocol("WM_DELETE_WINDOW", self.master.destroy)
        self.master.title(TEXT_TITLE)
        self.mainloop()

    def _load(self):
        """Load the grid with carts.

        Since there are four cart types, each type is assigned
        to a corner of the grid, and the carts in that type expand
        from that corner. Carts are added one type at a time until
        the grid is full.

        Typically, since PSAs are the most numerous cart type, they
        fill middle space not covered by the other types.
        """

        # generate a progression of cells for each corner
        progs = {}
        for cart_type in CONFIG_CARTS:
            progs[cart_type] = progression(GRID_ROWS, GRID_COLS, CONFIG_CARTS[cart_type]["corner"])

        # get a dictionary of carts for each cart type
        carts = database.get_carts()

        # apply shuffling and limiting to each cart type
        for cart_type in carts:
            random.shuffle(carts[cart_type])

            limit = CONFIG_CARTS[cart_type]["limit"]
            if limit is not -1:
                carts[cart_type] = carts[cart_type][0:limit]

        # insert carts until the grid is full or all carts are inserted
        num_inserted = 0

        for i in range(0, max(GRID_ROWS, GRID_COLS)):
            for cart_type in carts:
                # insert a layer for each cart type
                num_toinsert = 1 + 2 * i

                while len(carts[cart_type]) > 0 and num_toinsert > 0:
                    # pop the first empty coordinate from the progression
                    key = progs[cart_type].pop(0)
                    while self._grid.has_cart(key):
                        key = progs[cart_type].pop(0)

                    # add the cart to the grid
                    self._grid.set_cart(key, carts[cart_type].pop(0))
                    num_inserted += 1
                    num_toinsert -= 1

                    # exit if the grid is full
                    if num_inserted is GRID_ROWS * GRID_COLS:
                        return

                # exit if all carts are inserted
                if len([key for key in carts if len(carts[key]) > 0]) is 0:
                    break

    def reload(self):
        """Reload the cart machine."""

        if self._grid.is_playing():
            return

        print("Reloading the Cart Machine...")
        self._grid.clear()
        self._load()
        print("Cart Machine reloaded.")

    def _cart_start(self):
        """Start the meter when a cart starts."""
        self._meter.start()

    def _cart_stop(self):
        """Reset the meter when a cart stops."""
        self._meter.reset()

    def _cart_end(self, key):
        """Reset the meter when a cart ends."""
        self._meter.reset()

    def _get_meter_data(self):
        """Get meter data for the currently active cart."""
        return self._grid.get_active_cell().get_cart().get_meter_data()


CartMachine()
