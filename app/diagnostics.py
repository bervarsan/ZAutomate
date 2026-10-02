"""The diagnostics module makes hangs leave evidence behind.

- stdout is made unbuffered. Python 2 buffers stdout in 4-8 KB blocks
  when it goes to a log file, and a killed process loses whatever was in
  the buffer, so the log used to stop well before the actual hang.
- If the faulthandler backport is installed (pip install faulthandler),
  a watchdog dumps the stack of every thread to stderr whenever the Tk
  main loop stops responding for ZA_STALL_SECONDS, and `kill -USR1 <pid>`
  dumps them on demand. The watchdog runs in a C thread, so it works even
  when Python is stuck inside a C call or a blocked system call.
"""
import os
import signal
import sys
import time
from config import za_config

def _unbuffer_stdout():
    """Write stdout straight to its file descriptor."""
    try:
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 0)
    except (AttributeError, IOError, OSError, ValueError):
        pass

def enable(widget, stall_seconds=None):
    """Enable unbuffered output and the hang watchdog.

    :param widget: Tk widget whose main loop is watched
    :param stall_seconds: seconds without a heartbeat before stacks are dumped
    :return: True if the watchdog is running
    """
    _unbuffer_stdout()

    try:
        import faulthandler
    except ImportError:
        print time.asctime() + " :=: Diagnostics :: faulthandler is not installed, hang watchdog disabled"
        return False

    stall_seconds = stall_seconds or za_config.stall_seconds
    heartbeat_ms = max(1, stall_seconds // 3) * 1000

    faulthandler.enable(file=sys.stderr, all_threads=True)

    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)

    def heartbeat():
        # re-arming cancels the previous timer, so stacks are only dumped
        # if the main loop misses heartbeats for stall_seconds
        faulthandler.dump_traceback_later(stall_seconds, repeat=True, file=sys.stderr)
        widget.after(heartbeat_ms, heartbeat)

    heartbeat()

    print time.asctime() + " :=: Diagnostics :: Hang watchdog armed (" + str(stall_seconds) + "s), pid " + str(os.getpid())
    return True
