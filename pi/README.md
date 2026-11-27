# Pi-side stop-if-the-connection-drops watchdog

> **UNTESTED ON THE ROBOT.** The code is covered by automated tests that use a
> pretend robot, but it has never run on the real hexapod. **First test it with
> the robot lifted on a stand, legs in the air.**

## Why this exists

Freenove's server keeps repeating the last walk command until it is told to stop.
If the Wi-Fi drops and the connection does not close cleanly, the robot would
keep walking with nobody in control.

This small add-on runs on the Pi next to Freenove's server. If the robot is walking
and **no command has arrived for about 1 second**, it sends the robot the same
"stop" that the Stop button sends.

The app (this repo) now repeats its walk command about every 0.4 seconds while the
robot is walking, so a normal walk is never interrupted. If the app, the computer
or the Wi-Fi goes away, the repeats stop and the Pi stops the robot.

It does not change Freenove's walking, servo or calibration code. It does nothing
while the robot is standing, turning or being calibrated.

**One thing to know:** Freenove's own PyQt client appears to send a walk command
once and not repeat it. With the watchdog installed, walking from that client stops
after about a second. Use this app for walking. (Calibrating with the Freenove
client is fine, because the watchdog ignores calibration.)

## Install (on the Pi, about 2 minutes)

1. Copy the `pi` folder from this repo to the Pi (a USB stick, `scp`, or
   `git clone` on the Pi).
2. In a terminal on the Pi, go into that `pi` folder and run:

   ```bash
   python3 install_watchdog.py --dry-run     # optional: just shows what it would do
   python3 install_watchdog.py
   ```

   It expects Freenove's code at
   `~/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/Code/Server`. If yours is
   somewhere else, add the folder at the end:
   `python3 install_watchdog.py /path/to/Code/Server`.
3. It copies `connection_watchdog.py` into that folder, adds **two lines** to
   `server.py`, and saves the original as `server.py.before-watchdog`.
   If it says it cannot find the expected lines, it changes nothing — stop there and
   ask for help; your Freenove version is different.
4. Restart the Freenove server as usual:

   ```bash
   cd ~/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/Code/Server
   sudo python main.py -tn
   ```

   You should see the line `connection watchdog: running (halts a walk after 1.0s of silence)`.
   If you do not see it, the watchdog is not running.

## Test it (robot lifted on a stand)

Do this with **someone watching, legs clear, robot lifted so the feet are in the air.**

1. Connect from the app and finish the "before you run it" checklist.
2. Press **Forward**. The legs should keep walking. (If they stop after about a second, the
   app's repeat is not arriving — stop here and ask for help.)
3. While it walks, **turn off the Wi-Fi** on the computer running the app (or unplug the
   router), or close the app's terminal window.
4. Within about 1–2 seconds the legs should stop walking and stand still.
   The Pi's terminal should show `connection watchdog: no command for 1.0s while walking -> stop`.
5. Turn Wi-Fi back on, reconnect, and check the robot walks again.
6. If anything looks wrong at any point: press **Stop** in the app, or switch off the
   robot's power switch.

Please note in the app's **Test log** what happened.

## Remove it

```bash
python3 install_watchdog.py --remove
```

This takes the two lines back out and deletes the watchdog file. (Or copy
`server.py.before-watchdog` back over `server.py`.)

## Doing it by hand instead

Copy `connection_watchdog.py` into `Code/Server`, then edit `server.py`:

```python
from camera import Camera
from connection_watchdog import start_watchdog        # add this line below the other imports
...
        self.control_system.condition_thread.start()
        start_watchdog(self.control_system)           # add this line, same indentation
```

## How it decides (for the curious)

- The server notes the time of every movement command in `control.timeout`.
- Walking means `control.command_queue` holds a `CMD_MOVE` with a non-zero x or y.
- If that has been silent for more than 1 second on two checks in a row, the watchdog
  puts the stock stop command, `CMD_MOVE#<mode>#0#0#0#0`, into the queue.
- The limit is the `STALE_SECONDS` value at the top of `connection_watchdog.py`.
- Written against Freenove's `Code/Server` on `master` (V1.1+, the merged Pi 5 server).
