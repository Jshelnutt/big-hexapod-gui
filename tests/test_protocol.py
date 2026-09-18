from hexapod import protocol as proto


def test_cmd_move_format():
    assert proto.cmd_move(1, 0, 25, 5, 0) == "CMD_MOVE#1#0#25#5#0\n"


def test_cmd_walk_directions():
    assert proto.cmd_walk("forward", 5) == "CMD_MOVE#1#0#25#5#0\n"
    assert proto.cmd_walk("backward", 5) == "CMD_MOVE#1#0#-25#5#0\n"
    assert proto.cmd_walk("left", 5) == "CMD_MOVE#1#-25#0#5#0\n"
    assert proto.cmd_walk("right", 5) == "CMD_MOVE#1#25#0#5#0\n"
    assert proto.cmd_walk("stop") == "CMD_MOVE#1#0#0#0#0\n"


def test_cmd_speed_clamped():
    assert proto.cmd_walk("forward", 99) == "CMD_MOVE#1#0#25#10#0\n"
    assert proto.cmd_walk("forward", 1) == "CMD_MOVE#1#0#25#2#0\n"


def test_other_commands():
    assert proto.cmd_servo_power(False) == "CMD_SERVOPOWER#0\n"
    assert proto.cmd_head(0, 30) == "CMD_HEAD#0#30\n"
    assert proto.cmd_power() == "CMD_POWER\n"
    assert proto.cmd_sonic() == "CMD_SONIC\n"
