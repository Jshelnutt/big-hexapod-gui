"""Freenove TCP command builders (newline-terminated UTF-8).

Checked against Freenove's official code:
https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi
(Code/Server/server.py, Code/Server/control.py, Code/Client/Main.py).

Head: the server's CMD_HEAD#<channel>#<angle> writes ``angle`` straight to servo
channel 0 or 1 with NO range check, so this module clamps every value:
  * channel 0 = head up/down,    Freenove app slider 50..180, centre 90
  * channel 1 = head left/right, Freenove app slider 0..180, centre 90,
    and the app sends ``180 - slider`` for this channel.
"""

from __future__ import annotations

CMD_PORT = 5002
VIDEO_PORT = 8002

# Typical Freenove walk step length used by the stock client (~25 of -35..35).
DEFAULT_STEP = 25
DEFAULT_SPEED = 5
# CMD_MOVE angle field range (-10..10); Freenove's app uses the full range to turn.
TURN_ANGLE = 10

HEAD_UP_DOWN = 0
HEAD_LEFT_RIGHT = 1
HEAD_CENTER = 90
HEAD_UP_DOWN_MIN, HEAD_UP_DOWN_MAX = 50, 180
HEAD_LEFT_RIGHT_MIN, HEAD_LEFT_RIGHT_MAX = 0, 180


def _clamp(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(float(value)))))


def _line(*parts: object) -> str:
    return "#".join(str(p) for p in parts) + "\n"


def cmd_move(mode: int, x: int, y: int, speed: int, angle: int = 0) -> str:
    """mode 1/2 = gait type. x/y -35..35, speed 2..10, angle -10..10 (clamped)."""
    return _line(
        "CMD_MOVE",
        1 if int(mode) != 2 else 2,
        _clamp(x, -35, 35),
        _clamp(y, -35, 35),
        _clamp(speed, 0, 10),
        _clamp(angle, -TURN_ANGLE, TURN_ANGLE),
    )


def cmd_stop(mode: int = 1) -> str:
    return cmd_move(mode, 0, 0, 0, 0)


def cmd_walk(direction: str, speed: int = DEFAULT_SPEED, mode: int = 1) -> str:
    """direction: forward|backward|left|right|turn_left|turn_right|stop."""
    s = _clamp(speed, 2, 10)
    step = DEFAULT_STEP
    d = direction.lower().strip()
    if d == "forward":
        return cmd_move(mode, 0, step, s, 0)
    if d == "backward":
        return cmd_move(mode, 0, -step, s, 0)
    if d == "left":
        return cmd_move(mode, -step, 0, s, 0)
    if d == "right":
        return cmd_move(mode, step, 0, s, 0)
    if d == "turn_left":
        return cmd_move(mode, 0, 0, s, -TURN_ANGLE)
    if d == "turn_right":
        return cmd_move(mode, 0, 0, s, TURN_ANGLE)
    if d == "stop":
        return cmd_stop(mode)
    raise ValueError(f"unknown direction: {direction}")


def cmd_head(axis: int, angle: int) -> str:
    """Raw servo angle. axis 0 = up/down (50..180), 1 = left/right (0..180).

    Values are clamped so an out-of-range angle can never reach the servo.
    """
    if axis == HEAD_UP_DOWN:
        return _line("CMD_HEAD", 0, _clamp(angle, HEAD_UP_DOWN_MIN, HEAD_UP_DOWN_MAX))
    if axis == HEAD_LEFT_RIGHT:
        return _line(
            "CMD_HEAD", 1, _clamp(angle, HEAD_LEFT_RIGHT_MIN, HEAD_LEFT_RIGHT_MAX)
        )
    raise ValueError(f"unknown head axis: {axis}")


def cmd_head_up_down(slider: int) -> str:
    """Same as Freenove's app: slider 50..180 sent as-is on channel 0."""
    return cmd_head(HEAD_UP_DOWN, slider)


def cmd_head_left_right(slider: int) -> str:
    """Same as Freenove's app: slider 0..180, sends ``180 - slider`` on channel 1."""
    s = _clamp(slider, HEAD_LEFT_RIGHT_MIN, HEAD_LEFT_RIGHT_MAX)
    return cmd_head(HEAD_LEFT_RIGHT, 180 - s)


def cmd_camera(x: int, y: int) -> str:
    return _line("CMD_CAMERA", _clamp(x, 50, 180), _clamp(y, 0, 180))


def cmd_servo_power(on: bool) -> str:
    return _line("CMD_SERVOPOWER", 1 if on else 0)


def cmd_relax() -> str:
    """Freenove's app 'Relax' button sends CMD_SERVOPOWER#0 (CMD_RELAX is a
    toggle the protocol doc says not to use)."""
    return cmd_servo_power(False)


def cmd_buzzer(on: bool) -> str:
    return _line("CMD_BUZZER", 1 if on else 0)


def cmd_sonic() -> str:
    return "CMD_SONIC\n"


def cmd_power() -> str:
    return "CMD_POWER\n"


def cmd_balance(on: bool) -> str:
    return _line("CMD_BALANCE", 1 if on else 0)


def cmd_attitude(roll: int, pitch: int, yaw: int) -> str:
    return _line("CMD_ATTITUDE", roll, pitch, yaw)


def cmd_position(x: int, y: int, z: int) -> str:
    return _line("CMD_POSITION", x, y, z)


def cmd_led_mode(mode: int) -> str:
    return _line("CMD_LED_MOD", mode)


def cmd_led_color(r: int, g: int, b: int) -> str:
    return _line("CMD_LED", r, g, b)


def mock_reply(line: str) -> str | None:
    """What the real Freenove server answers to ``line`` (None = no reply).

    Only CMD_SONIC and CMD_POWER produce replies on the real robot.
    """
    text = line.strip()
    head = text.split("#", 1)[0]
    if head == "CMD_SONIC":
        return "CMD_SONIC#42.0"
    if head == "CMD_POWER":
        return "CMD_POWER#8.1#8.05"
    return None
