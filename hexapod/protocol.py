"""Freenove TCP command builders (newline-terminated UTF-8).

Source of truth:
https://github.com/Freenove/Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi/blob/master/Code/robot_control_communication_protocol.md
"""

from __future__ import annotations

CMD_PORT = 5002
VIDEO_PORT = 8002

# Typical Freenove walk step length used by the stock client (~25 of -35..35).
DEFAULT_STEP = 25
DEFAULT_SPEED = 5


def _line(*parts: object) -> str:
    return "#".join(str(p) for p in parts) + "\n"


def cmd_move(mode: int, x: int, y: int, speed: int, angle: int = 0) -> str:
    """mode 1 = motion, 2 = gait. x/y -35..35, speed 2..10, angle -10..10."""
    return _line("CMD_MOVE", mode, x, y, speed, angle)


def cmd_stop(mode: int = 1) -> str:
    return cmd_move(mode, 0, 0, 0, 0)


def cmd_walk(direction: str, speed: int = DEFAULT_SPEED, mode: int = 1) -> str:
    """direction: forward|backward|left|right|stop."""
    s = max(2, min(10, int(speed)))
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
    if d == "stop":
        return cmd_stop(mode)
    raise ValueError(f"unknown direction: {direction}")


def cmd_head(axis: int, angle: int) -> str:
    """axis 0 = horizontal, 1 = vertical; angle -90..90."""
    return _line("CMD_HEAD", axis, angle)


def cmd_camera(x: int, y: int) -> str:
    return _line("CMD_CAMERA", x, y)


def cmd_servo_power(on: bool) -> str:
    return _line("CMD_SERVOPOWER", 1 if on else 0)


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
