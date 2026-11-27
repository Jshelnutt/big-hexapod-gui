# big-hexapod-gui

Easy LAN control UI for the **Freenove Big Hexapod Robot Kit (FNK0052)** on a **Raspberry Pi 5**.

**New here / not a programmer?** Start with the plain-English checklist:  
**[Get the robot talking](docs/get-the-robot-talking.md)** — prove Freenove’s official Wi‑Fi control works first, then use this app.

This app is a **thin TCP client** to the stock Freenove `Code/Server`. It does **not** reimplement gait, kinematics, or servo timing.

## Architecture (v0)

| Piece | Role |
| --- | --- |
| Freenove `Code/Server` on Pi | Gait, servos, camera, ultrasonic (source of truth) |
| This NiceGUI app | Easy controls + video on any phone/laptop on the LAN |
| Official Freenove PyQt Client | **First-time leg calibration** (keep using it for that) |

- **CMD port:** `5002` (newline-terminated `CMD_*#...` UTF-8)
- **Video port:** `8002` (4-byte little-endian length + JPEG)
- Protocol: [`robot_control_communication_protocol.md`](https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/blob/master/Code/robot_control_communication_protocol.md)

### Pi 5 notes

- `server-PI5` was **merged into `Code/Server` in V1.1** — run Server, not a separate folder.
- Start headless TCP server: `sudo python main.py -t -n`
- LED only if PCB **V2.0** (SPI). V1.0 + Pi 5 → no LED.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m hexapod.app
```

Open `http://<this-machine>:8080`.

1. Enter the Pi's LAN IP → **Connect**
2. Or enable **Mock (no hardware)** to exercise the UI offline
3. Drive with the pad; use **Servos OFF** before working on the robot

### Mock TCP server (optional)

```bash
python -m hexapod.mock_server
```

Then connect the UI to `127.0.0.1` with Mock off.

## Must-have controls (v0)

- Connect / disconnect (Pi IP)
- Walk: forward / back / left / right / stop + speed
- Head pan/tilt
- Servo power on/off
- Battery (`CMD_POWER`) + ultrasonic (`CMD_SONIC`)
- Live JPEG preview
- Mock mode for development without hardware

## Safety features

### "Before you run it" checklist

After you connect, the app reads both battery packs (`CMD_POWER`) and shows them
above the controls. The walk and move controls (arrows, speed, gait mode, Servos ON,
head) stay **locked** until:

- the battery has been read and **both packs are above 6.6 V** (at 6.6 V or below,
  walking is blocked; below 7.0 V you get a low-battery warning but can still walk), and
- you tick all three boxes: **legs clear**, **robot lifted for first tests**,
  **someone watching**.

The **Stop** button, **Relax**, and **Buzz** always work. The boxes reset every time you
connect. The battery is re-read every 30 seconds; if it falls to 6.6 V or below while
you are walking, the app sends a stop and locks the controls again.
**Practice mode** works as before: it has no robot, so the boxes are optional there.
The thresholds are at the top of `hexapod/preflight.py`.

### Test log

Every run (from the first walk command until Stop, Relax, disconnect, a lost connection, or
a low battery) is saved as one line in a local file:
`~/.big-hexapod-gui/test-log.jsonl` (change it with the `HEXAPOD_TEST_LOG` environment
variable). Each entry has the date and time, the mode (robot or practice), the gait mode,
the commands that ran, both battery voltages, and a result plus your note.
Open the **Test log** section of the app to type a note, see the latest entries, or
download the file. The file is plain text — any editor opens it.

### Stop if the connection drops

- The app sends a **stop** when you press Stop, press Disconnect, close the page, or
  quit the app (this part already existed).
- **New:** while a walk is running, the app repeats the walk command about every 0.4 s
  (a "keep-alive"), and asks the operating system to notice a dead Wi‑Fi link within
  seconds. If the app, the computer or the Wi‑Fi goes away, the repeats just stop.
- **New, on the Pi:** a small watchdog halts the robot when no command has arrived for
  about 1 second. It is a separate add-on, not part of Freenove's code — see
  [`pi/README.md`](pi/README.md). **It is untested on the robot; test it with the robot
  lifted on a stand.** Without it, the stock Freenove server keeps repeating the last walk
  command if the connection dies without closing.

## Out of scope (v0)

- Replacing Freenove Server with ROS / custom gait
- Pure browser WebSocket protocol (Server speaks raw TCP)
- Streamlit as the drive UI
- Full calibration UI (use official PyQt Client)

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

(`pytest.ini` puts the repo folder on the import path, so plain `pytest -q` works.)

## Sources

- Freenove kit repo: https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi
- Docs: https://docs.freenove.com/projects/fnk0052/en/latest/
