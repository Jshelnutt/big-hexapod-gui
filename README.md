# big-hexapod-gui

Easy LAN control UI for the **Freenove Big Hexapod Robot Kit (FNK0052)** on a **Raspberry Pi 5**.

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

## Sources

- Freenove kit repo: https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi
- Docs: https://docs.freenove.com/projects/fnk0052/en/latest/
