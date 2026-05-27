"""Pure grid helper functions shared by the GUI modules."""


def get_next_key(rows, cols, key):
    """Get the next cell to queue after a cell.

    - each cell queues the cell below
    - bottom cells queue the top cell in the next column
    - the bottom right cell queues the top left cell

    :param rows
    :param cols
    :param key
    """
    next_row = (int)(key[0])
    next_col = (int)(key[2])

    if next_row == rows:
        if next_col == cols:
            next_row = 1
            next_col = 1
        else:
            next_row = 1
            next_col += 1
    else:
        next_row += 1

    return (str)(next_row) + "x" + (str)(next_col)


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

    The progression begins at the corner and expands outward until every
    coordinate in the grid is included.

    :param rows: rows in the grid
    :param cols: columns in the grid
    :param corner: corner coordinate as a 2-tuple (row, col)
    """

    # append each radius of the progression
    array = []

    for radius in range(0, max(rows, cols)):
        array.extend(progression_radius(rows, cols, corner, radius))

    # temporary code to transform tuples into strings
    array = [(str)(elem[0]) + "x" + (str)(elem[1]) for elem in array]

    return array
