# Get the robot talking — checklist (novice version)

Do these in order. Don’t skip ahead until the step works.

This guide is for Judson’s Freenove Big Hexapod (FNK0052) on a Raspberry Pi 5.  
Your easier control app lives in this repo (`big-hexapod-gui`) — but **only start that after Freenove’s official Wi‑Fi control already works.**

---

## Before you start

- Robot is fully assembled
- Batteries charged / power connected
- Raspberry Pi 5 has Raspberry Pi OS **with Desktop** installed
- Pi and your laptop are on the **same Wi‑Fi**
- You have a screen/keyboard for the Pi, or VNC remote desktop set up

---

## 1. Turn on the Pi’s “talk to the servo boards” setting

- Open Raspberry Pi settings → Interfaces
- Turn **I2C** ON
- (If your kit’s board is the newer V2.0 style, also turn **SPI** ON — if unsure, leave SPI for later)
- Reboot if it asks

**Tip:** Freenove recommends a faster I2C speed so the legs respond snappily. Their tutorial walks through adding that one line in a config file — follow their Chapter 1 wording exactly.

Official tutorial: https://docs.freenove.com/projects/fnk0052/en/latest/

---

## 2. Download Freenove’s robot software onto the Pi

- Open Terminal on the Pi
- Download their official kit folder from GitHub:  
  https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi
- Go into the `Code` folder
- Run their setup script once (`setup.py`)
- When it finishes, **reboot** the Pi

If setup fails, run it again (often a network hiccup), then reboot.

**Pi 5 note:** Older docs mention a `server-PI5` folder. In Freenove’s newer software (V1.1), that was folded into normal `Code/Server`. Use **`Code/Server`**.

---

## 3. Power the robot the right way for tests

- Batteries in / power switches ON as Freenove’s guide says (usually S1 and S2)
- Put the robot on a flat table
- Keep hands clear of the legs

---

## 4. Test the pieces one by one

From Freenove’s Server folder, run their module tests (their Chapter 3):

- Servos (legs twitch / move safely)
- Battery / power reading
- Ultrasonic distance sensor
- Camera
- Buzzer
- Skip fancy LED tests if they don’t work on your Pi 5 — that’s common

If a test fails, stop and fix that part before continuing.

---

## 5. Calibrate the six legs (one-time)

- Start Freenove’s official control program (their Client on a computer, or their phone app)
- Connect to the Pi’s Wi‑Fi address
- Open calibration
- Adjust until the robot stands level and square
- Save

Don’t skip this. An uncalibrated robot walks poorly or tips.

---

## 6. Start the robot “brain” on the Pi

- On the Pi, open Terminal
- Go to Freenove’s `Code/Server` folder
- Start their server in “Wi‑Fi control, no extra window” mode:

```bash
sudo python main.py -tn
```

Leave this running while you control the robot.

---

## 7. Connect a remote and prove it walks

- On your laptop or phone (same Wi‑Fi), open Freenove’s official Client / App
- Enter the Pi’s IP address → Connect
- Try: forward, back, turn, stop, relax

**Success looks like:** you press a button, the robot moves, then stops cleanly.

---

## 8. Only then: use (or build) the easier control screen

When steps 1–7 work, this repo’s simpler control screen can talk to that same robot brain.

See the main [README](../README.md) for how to run `big-hexapod-gui` once you’re ready.

---

## Quick “stuck?” guide

| Problem | Try this |
| --- | --- |
| Can’t connect | Same Wi‑Fi? Server running on Pi? Right IP address? |
| Legs look weird | Recalibrate (step 5) |
| Nothing moves | Batteries/switches; servo power / relax mode |
| Camera missing | Check the camera cable and Freenove’s cam0/cam1 choice during setup |

---

*Written for a non-programmer. Keep Freenove’s robot software as the brain; this project is the easier remote.*
