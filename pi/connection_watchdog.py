"""Connection watchdog for the stock Freenove Big Hexapod server.  (Pi side)

UNTESTED ON THE ROBOT. Test it with the robot lifted on a stand first.
See pi/README.md in the big-hexapod-gui repo.

Problem: the stock server keeps repeating the last walk command until it gets a
stop. If Wi-Fi drops (or the controlling app dies) without the TCP connection
closing cleanly, the robot keeps walking.

What this does: a small background thread watches the server's Control object.
If a continuous walk is running and no new movement command has arrived for about
one second, it queues the same "stop" command the app's Stop button sends. It
does not touch the gait, servo or calibration code, and it does nothing at all
while the robot is standing still, turning, or being calibrated.

big-hexapod-gui repeats its walk command every ~0.4 s, so a normal walk never
trips it. As far as its code shows, Freenove's own PyQt client sends a walk
command once and does not repeat it, so with the watchdog installed a walk
started from that client stops after about one second. Use big-hexapod-gui for
walking, or remove the watchdog (see pi/README.md).

It only reads/writes two things on the Control object that the stock server
already uses: ``command_queue`` and ``timeout`` (set to time.time() by the server
every time a movement command arrives).
"""

import threading
import time

STALE_SECONDS = 1.0  # halt after this much silence while walking
POLL_SECONDS = 0.1  # how often to look
MOVE = "CMD_MOVE"


def walking_mode(command_queue):
    """Return the gait mode string if the queue holds a continuous walk, else None.

    The stock server repeats a CMD_MOVE forever when x or y is non-zero. A turn
    (x and y zero) or a stop is a single step and is cleared by the server.
    """
    try:
        queue = list(command_queue)
        if len(queue) != 6 or queue[0] != MOVE:
            return None
        if int(queue[2]) != 0 or int(queue[3]) != 0:
            return str(queue[1])
    except (TypeError, ValueError):
        return None
    return None


class ConnectionWatchdog(threading.Thread):
    def __init__(
        self,
        control,
        stale_seconds=STALE_SECONDS,
        poll_seconds=POLL_SECONDS,
        clock=time.time,
        log=print,
    ):
        super().__init__(name="connection-watchdog", daemon=True)
        self.control = control
        self.stale_seconds = stale_seconds
        self.poll_seconds = poll_seconds
        self.clock = clock
        self.log = log
        self.halts = 0  # how many times it has stopped the robot
        self._stop_event = threading.Event()
        self._candidate = None  # (queue object, timeout) seen stale last poll

    def stop(self):
        self._stop_event.set()

    def check(self):
        """One look. Returns True if it halted the robot on this call.

        A halt needs the same stale walk command to be seen on two polls in a row.
        That avoids a false stop while the server is half way through handling a
        brand-new command (it stores the command, then the time).
        """
        queue = self.control.command_queue
        mode = walking_mode(queue)
        if mode is None:
            self._candidate = None
            return False
        last = self.control.timeout
        if last and (self.clock() - last) <= self.stale_seconds:
            self._candidate = None
            return False
        if self._candidate is None or self._candidate[0] is not queue or self._candidate[1] != last:
            self._candidate = (queue, last)
            return False
        # Stale on two polls in a row with the same command: halt.
        self._candidate = None
        self.control.command_queue = [MOVE, mode, "0", "0", "0", "0"]  # the stock stop
        self.control.timeout = self.clock()
        self.halts += 1
        self.log("connection watchdog: no command for %.1fs while walking -> stop" % self.stale_seconds)
        return True

    def run(self):
        while not self._stop_event.wait(self.poll_seconds):
            try:
                self.check()
            except Exception as exc:  # never let the watchdog take the server down
                self.log("connection watchdog: error %r" % (exc,))


def start_watchdog(control, **kwargs):
    """Start the watchdog for a stock Freenove ``Control`` object."""
    if not (hasattr(control, "command_queue") and hasattr(control, "timeout")):
        print("connection watchdog: this Freenove version has no command_queue/timeout "
              "- watchdog NOT running")
        return None
    watchdog = ConnectionWatchdog(control, **kwargs)
    watchdog.start()
    print("connection watchdog: running (halts a walk after %.1fs of silence)" % watchdog.stale_seconds)
    return watchdog
