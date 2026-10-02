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

## How audio files are read

The music library is on a Samba share (`/media/Jemaine`). When the share
stalls, a read from it can block inside the kernel, where the process
can't be killed, and pymad may hold the GIL while it waits, which used to
freeze the whole program. So ZAutomate never reads the share itself:

- `cache.py` copies each file to local disk in a child process. A copy
  that takes longer than `ZA_COPY_TIMEOUT` is abandoned, and only that
  child is stuck.
- Carts and tracks only load and play local copies. Automation copies
  every queued track ahead of time, skips tracks that aren't copied yet
  and drops tracks that can't be copied.
- If nothing is ready for 15 seconds, Automation plays a random MP3 from
  `ZA_FALLBACK_DIR`, if it is set, instead of dead air.

The share's mount options decide how long a stalled read blocks. Mount it
read-only and `soft`, so a dead server returns an error instead of
blocking forever, and with a short `echo_interval` so a dead server is
noticed in seconds rather than minutes:

    //server/share  /media/Jemaine  cifs  ro,soft,echo_interval=10,...  0  0

## Configuration

Environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ZA_CACHE_DIR` | `~/.cache/zautomate` | local copies, one subdirectory per program |
| `ZA_COPY_TIMEOUT` | `90` | seconds before a copy from the share is abandoned |
| `ZA_CACHE_MAX_ENTRIES` | `300` | local copies kept per program |
| `ZA_FALLBACK_DIR` | unset | local directory of MP3s to play when nothing is ready |
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

Run the unit tests from the repository root (Python 2.7, no extra packages):

    python -m unittest discover -b -s test -p "test_*.py"

The tests use fakes instead of audio hardware, the music library share and
the server API, so they run anywhere. `test/manual/` has scripts that use the real audio device,
the real server API and a Tk window.

    pylint **/*.py > lint.log

## TODO

- separate Logbook_Log into log_cart and log_track
- create separate classes for carts and tracks
- clean up print statements, use `logging` module
- add hourly reload to Cart Machine
- Consider combining the three modules into one window
- replace pyao (startup prints a garbage libao channel matrix warning, probably uninitialized memory)
