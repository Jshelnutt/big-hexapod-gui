import pytest

from hexapod import protocol as proto


def test_cmd_move_format():
    assert proto.cmd_move(1, 0, 25, 5, 0) == "CMD_MOVE#1#0#25#5#0\n"


def test_cmd_move_clamps():
    assert proto.cmd_move(1, 99, -99, 50, 40) == "CMD_MOVE#1#35#-35#10#10\n"


def test_cmd_walk_directions():
    assert proto.cmd_walk("forward", 5) == "CMD_MOVE#1#0#25#5#0\n"
    assert proto.cmd_walk("backward", 5) == "CMD_MOVE#1#0#-25#5#0\n"
    assert proto.cmd_walk("left", 5) == "CMD_MOVE#1#-25#0#5#0\n"
    assert proto.cmd_walk("right", 5) == "CMD_MOVE#1#25#0#5#0\n"
    assert proto.cmd_walk("stop") == "CMD_MOVE#1#0#0#0#0\n"


def test_turns_use_angle_field():
    assert proto.cmd_walk("turn_left", 5) == "CMD_MOVE#1#0#0#5#-10\n"
    assert proto.cmd_walk("turn_right", 5, mode=2) == "CMD_MOVE#2#0#0#5#10\n"


def test_cmd_speed_clamped():
    assert proto.cmd_walk("forward", 99) == "CMD_MOVE#1#0#25#10#0\n"
    assert proto.cmd_walk("forward", 1) == "CMD_MOVE#1#0#25#2#0\n"


def test_head_channels_and_clamps():
    # channel 0 = up/down, 50..180
    assert proto.cmd_head(0, 30) == "CMD_HEAD#0#50\n"
    assert proto.cmd_head(0, 200) == "CMD_HEAD#0#180\n"
    assert proto.cmd_head(0, -90) == "CMD_HEAD#0#50\n"
    # channel 1 = left/right, 0..180
    assert proto.cmd_head(1, -90) == "CMD_HEAD#1#0\n"
    assert proto.cmd_head(1, 999) == "CMD_HEAD#1#180\n"
    with pytest.raises(ValueError):
        proto.cmd_head(2, 90)


def test_head_like_freenove_app():
    assert proto.cmd_head_up_down(90) == "CMD_HEAD#0#90\n"
    assert proto.cmd_head_left_right(90) == "CMD_HEAD#1#90\n"
    assert proto.cmd_head_left_right(0) == "CMD_HEAD#1#180\n"
    assert proto.cmd_head_left_right(180) == "CMD_HEAD#1#0\n"
    assert proto.cmd_head_left_right(-50) == "CMD_HEAD#1#180\n"


def test_other_commands():
    assert proto.cmd_servo_power(False) == "CMD_SERVOPOWER#0\n"
    assert proto.cmd_relax() == "CMD_SERVOPOWER#0\n"
    assert proto.cmd_power() == "CMD_POWER\n"
    assert proto.cmd_sonic() == "CMD_SONIC\n"


def test_mock_replies_match_real_server():
    assert proto.mock_reply("CMD_SONIC") == "CMD_SONIC#42.0"
    assert proto.mock_reply("CMD_POWER").startswith("CMD_POWER#")
    assert proto.mock_reply("CMD_MOVE#1#0#25#5#0") is None
    assert proto.mock_reply("CMD_HEAD#0#90") is None
