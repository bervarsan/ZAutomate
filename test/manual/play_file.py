#!/usr/bin/env python

"""Play a file with the real audio device. Run from the repository root."""
import sys
import time

sys.path.insert(0, 'app')
from player_madao import Player

if len(sys.argv) != 2:
    print "usage: test/manual/play_file.py [mp3-file]"
    sys.exit(1)

FILENAME = sys.argv[1]

def end_callback():
    print "Player finished."

player = Player(FILENAME)
player.play(end_callback)

while player.is_playing():
    print player.is_playing()
    time.sleep(1.0)
