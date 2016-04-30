#!/usr/bin/env python

import random
import Tkinter
from Tkinter import Frame, Label, Button
import ZAutomate_DBInterface as database
from ZAutomate_Gridder import Gridder
from ZAutomate_GridObj import GridObj
from ZAutomate_Meter import Meter

METER_WIDTH = 1000
GRID_ROWS = 8
GRID_COLS = 6

FONT_TITLE = ('Helvetica', 36, 'bold italic')
FONT_RELOAD = ('Helvetica', 24, 'bold')

COLOR_TITLE_BG = "#DDDDDD"
COLOR_TITLE_FG = "#000000"
COLOR_RELOAD_BG = "#FF0000"
COLOR_RELOAD_FG = "#000000"

TEXT_TITLE = "ZAutomate :: Cart Machine"
TEXT_RELOAD = "Reload"

class CartMachine(Frame):
    ###Master Window Variable
    Master = None
    ###Meter for counting down time left
    Meter = None

    ###Grid which holds the cart.
    Grid = None
    ###ActiveCart which is playing
    ActiveCart = None
    ###YATES_COMMENT: Not sure what this one is yet
    ActiveGrid = None
    ###Look to ensure we don't remove carts from the grid.  Included because
    ###The gridder/gridObject classes are also used in the DJ Studio
    AllowRightClick = False
    RewindOnPause = True

    ###Array which holds all the carts
    Carts = None

    def __init__(self): #width, height,
        Frame.__init__(self)
        self.Cols = GRID_COLS
        self.Rows = GRID_ROWS

        # make the window resizable
        top = self.winfo_toplevel()
        for row in range(2, self.Rows+2):
            for col in range(0, self.Cols):
                top.rowconfigure(row, weight=1)
                top.columnconfigure(col, weight=1)
                self.rowconfigure(row, weight=1)
                self.columnconfigure(col, weight=1)

        # initialize the title
        title = Label(self.Master, \
            bg=COLOR_TITLE_BG, fg=COLOR_TITLE_FG, \
            font=FONT_TITLE, text=TEXT_TITLE)
        title.grid(row=0, column=0, columnspan=self.Cols - 1, sticky=Tkinter.N)

        # initialize the reload button
        reload_button = Button(self.Master, \
            bg=COLOR_RELOAD_BG, fg=COLOR_RELOAD_FG, \
            font=FONT_RELOAD, text=TEXT_RELOAD, \
            command=self.reload)
        reload_button.grid(row=0, column=self.Cols - 1)

        # initialize the meter
        self.Meter = Meter(self.Master, METER_WIDTH, self.MeterFeeder, \
                     self.EndCallback)
        self.Meter.grid(row=1, column=0, columnspan=self.Cols) #, sticky=E+W
        ##self.Meter.grid_propagate(0)

        # initialize the grid
        self.Grid = {}
        for row in range(1, self.Rows + 1):
            for col in range(1, self.Cols + 1):
                key = (str)(row) + "x" + (str)(col)
                self.Grid[key] = GridObj(self)
                self.Grid[key].grid(row=row + 1, column=col - 1)

        self.Gridder = Gridder(self.Rows, self.Cols)

        self.load()

    def load(self):
        """Load the grid with carts.

        Since there are four cart types, each type is assigned
        to a corner of the grid, and the carts in that type expand
        from that corner. Carts are added one type at a time until
        the grid is full.

        Typically, since PSAs are the most numerous cart type, they
        fill middle space not covered by the other types.
        """

        # configuration for each cart type
        config = {
            # PSA
            0: {
                "corner": (1, 1),
                "limit": -1,
                "shuffle": True
            },
            # Underwriting
            1: {
                "corner": (self.Rows, self.Cols),
                "limit": -1,
                "shuffle": False
            },
            # Station ID
            2: {
                "corner": (1, self.Cols),
                "limit": 9,
                "shuffle": True
            },
            # Promotion
            3: {
                "corner": (self.Rows, 1),
                "limit": -1,
                "shuffle": False
            }
        }

        # generate a progression of cells for each corner
        progs = {}
        for t in config:
            progs[t] = self.Gridder.GridCorner(config[t]["corner"])

        # get a dictonary of carts for each cart type
        carts = database.get_carts()

        # apply limiting and shuffling to each cart type
        for t in carts:
            if config[t]["shuffle"] is True:
                random.shuffle(carts[t])

            limit = config[t]["limit"]
            if limit is not -1:
                carts[t] = carts[t][0:limit]

        # total number of carts inserted
        numinserted = 0

        # number of carts to insert next
        #
        # when iterating through the cart types,
        # each cart type attempts to insert enough
        # carts to fill the next layer (1 for the corner,
        # then 3 for around the corner, then 5, and so on)
        toinsert = 1

        ## keep iterating until the grid is full
        while numinserted <= self.Rows * self.Cols:
            numempty = 0
            for t in carts:
                for i in range(0, toinsert):

                    # load a cart from this cart type
                    if len(carts[t]) > 0:
                        # pop the first unused coordinate from the progression
                        key = progs[t].pop(0)
                        while self.Grid[key].HasCart():
                            if len(progs[t]) > 0:
                                key = progs[t].pop(0)
                            else:
                                return

                        # add the cart to the grid
                        self.Grid[key].AddCart(carts[t].pop(0))
                        numinserted += 1

                        ## extra control structure because we are 2 loops in
                        if numinserted == self.Rows * self.Cols:
                            return
                    else:
                        numempty += 1

            if numempty is len(carts):
                return

            toinsert += 2

    def reload(self):
        if self.ActiveCart is not None:
            return

        self.load()

    def EndCallback(self):
        self.ActiveCart.Stop()
        self.ActiveGrid.Reset()

    def SetActiveGridObj(self, grid_obj):
        self.ActiveGrid = grid_obj

    def SetActiveCart(self, cart):
        self.ActiveCart = cart

    def IsCartActive(self):
        return self.ActiveCart is not None

    def MeterFeeder(self):
        if self.ActiveCart is not None:
            return self.ActiveCart.MeterFeeder()
        else:
            return ("-:--", "-:--", "--", "--", None, None)

    def Bail(self):
        self.master.destroy()

cart_machine = CartMachine()
cart_machine.master.protocol("WM_DELETE_WINDOW", cart_machine.Bail)
cart_machine.master.title("ZAutomate :: Cart Machine")
cart_machine.mainloop()
