import pytest

from hexapod import preflight as pf

ALL_TICKED = {pf.CHECK_LEGS_CLEAR: True, pf.CHECK_LIFTED: True, pf.CHECK_WATCHING: True}


def test_parse_power_reply():
    assert pf.parse_power_reply("CMD_POWER#8.1#8.05") == (8.1, 8.05)
    assert pf.parse_power_reply("CMD_POWER#7#6.5\n") == (7.0, 6.5)


@pytest.mark.parametrize(
    "text",
    ["", "CMD_SONIC#42.0", "CMD_POWER", "CMD_POWER#8.1", "CMD_POWER#a#b", "CMD_POWER#nan#8", "CMD_POWER#inf#8", "CMD_POWER#1#2#3"],
)
def test_parse_power_reply_rejects_garbage(text):
    assert pf.parse_power_reply(text) is None


def test_thresholds():
    assert pf.battery_status((8.1, 8.05)).level == pf.LEVEL_OK
    assert pf.battery_status((7.0, 7.0)).level == pf.LEVEL_OK  # warn is *below* 7.0
    assert pf.battery_status((7.5, 6.99)).level == pf.LEVEL_WARN
    assert pf.battery_status((6.61, 8.0)).level == pf.LEVEL_WARN
    assert pf.battery_status((6.6, 8.0)).level == pf.LEVEL_BLOCKED  # 6.6 V or below blocks
    assert pf.battery_status((8.0, 6.0)).level == pf.LEVEL_BLOCKED  # either pack counts
    assert pf.battery_status(None).level == pf.LEVEL_UNKNOWN


def test_unlocks_only_with_good_battery_and_all_three_ticks():
    assert pf.evaluate((8.1, 8.05), ALL_TICKED).unlocked
    for key in ALL_TICKED:
        ticks = dict(ALL_TICKED, **{key: False})
        gate = pf.evaluate((8.1, 8.05), ticks)
        assert not gate.unlocked
        assert gate.missing == [key]
    assert not pf.evaluate((8.1, 8.05), {}).unlocked


def test_low_battery_warns_but_still_allows_walking():
    gate = pf.evaluate((6.8, 6.9), ALL_TICKED)
    assert gate.unlocked
    assert gate.battery.level == pf.LEVEL_WARN


def test_blocked_battery_blocks_even_with_all_ticks():
    gate = pf.evaluate((6.6, 8.0), ALL_TICKED)
    assert not gate.unlocked
    assert "too low" in gate.reason


def test_no_reading_or_no_connection_stays_locked():
    assert not pf.evaluate(None, ALL_TICKED).unlocked
    gate = pf.evaluate((8.1, 8.05), ALL_TICKED, connected=False)
    assert not gate.unlocked
    assert "Connect" in gate.reason


def test_practice_mode_does_not_need_the_boxes_but_still_checks_battery():
    assert pf.evaluate((8.1, 8.05), {}, practice=True).unlocked
    assert not pf.evaluate((6.5, 6.4), {}, practice=True).unlocked
    assert not pf.evaluate(None, {}, practice=True).unlocked


def test_mock_server_reply_is_readable_by_the_checklist():
    from hexapod import protocol as proto

    volts = pf.parse_power_reply(proto.mock_reply("CMD_POWER"))
    assert pf.evaluate(volts, {}, practice=True).unlocked
