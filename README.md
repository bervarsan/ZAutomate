ZAutomate
=========

WSBF's radio automation system, vintage 2011.

## Installation

Ubuntu:

    sudo apt-get install python python-tk python-tksnack python-pymad python-pyao pylint
    pip install faulthandler    # optional, enables the hang watchdog
    git clone https://github.com/wsbf/ZAutomate.git

Start everything with `init.sh`. It appends to `za_*.log` with unbuffered
output, so after a hang the log ends where the program actually stopped.

## Configuration

Environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ZA_STALL_SECONDS` | `30` | seconds of frozen GUI before thread stacks are dumped |
| `ZA_AO_DRIVER`, `ZA_AO_BITS`, ... | | audio device settings, see `app/config.py` |

## Diagnosing hangs

With `faulthandler` installed, the stack of every thread is written to the
log whenever the GUI stops responding for `ZA_STALL_SECONDS`, and on demand
with:

    kill -USR1 <pid>

Each program prints its pid at startup. To see whether a hung process is
stuck in the kernel (state `D`) and where:

    ps -eLo pid,tid,stat,wchan:32,cmd | grep za_

## Development

    pylint **/*.py > lint.log

## TODO

- review cartqueue for design flaws, possible infinite loop?
- separate Logbook_Log into log_cart and log_track
- create separate classes for carts and tracks
- clean up print statements, use `logging` module
- add hourly reload to Cart Machine
- Large queries in DJ Studio interrupt audio streaming (use multiprocess)
- Consider combining the three modules into one window
