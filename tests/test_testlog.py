import json
from datetime import datetime, timezone

from hexapod import testlog
from hexapod.testlog import RunLog, summarize


def make(tmp_path):
    fixed = datetime(2026, 11, 25, 10, 30, 0, tzinfo=timezone.utc)
    return RunLog(tmp_path / "logs" / "test-log.jsonl", clock=lambda: fixed)


def test_entry_has_time_commands_mode_battery_and_result(tmp_path):
    log = make(tmp_path)
    log.record_command("CMD_MOVE#1#0#25#5#0\n")
    log.record_command("CMD_MOVE#1#0#0#0#0")
    entry = log.finish("stopped", mode="robot", gait_mode=1, battery=(8.1, 8.05), note="legs fine")
    assert entry["time"] == "2026-11-25T10:30:00+00:00"
    assert entry["mode"] == "robot"
    assert entry["gait_mode"] == 1
    assert entry["commands"] == ["CMD_MOVE#1#0#25#5#0", "CMD_MOVE#1#0#0#0#0"]
    assert entry["battery"] == {"pack1": 8.1, "pack2": 8.05}
    assert entry["result"] == "stopped"
    assert entry["note"] == "legs fine"
    # one JSON object per line in the file
    lines = log.path.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0]) == entry


def test_nothing_to_log_writes_nothing(tmp_path):
    log = make(tmp_path)
    assert log.finish("stopped", mode="robot") is None
    assert log.read_entries() == []


def test_note_only_entry_and_missing_battery(tmp_path):
    log = make(tmp_path)
    entry = log.finish("note", mode="practice", note="  looks good ")
    assert entry["note"] == "looks good"
    assert entry["commands"] == [] and entry["battery"] is None


def test_pending_commands_are_cleared_after_an_entry(tmp_path):
    log = make(tmp_path)
    log.record_command("A")
    assert log.has_pending
    log.finish("one", mode="robot")
    assert not log.has_pending
    assert log.finish("two", mode="robot") is None
    assert len(log.read_entries()) == 1


def test_repeated_commands_are_kept_once_and_the_list_is_capped(tmp_path):
    log = make(tmp_path)
    for _ in range(5):
        log.record_command("CMD_MOVE#1#0#25#5#0")
    for i in range(500):
        log.record_command(f"CMD_HEAD#0#{i}")
    entry = log.finish("x", mode="robot")
    assert entry["commands"][0] == "CMD_MOVE#1#0#25#5#0"
    assert entry["commands"].count("CMD_MOVE#1#0#25#5#0") == 1
    assert len(entry["commands"]) == testlog.MAX_COMMANDS_PER_ENTRY


def test_read_entries_skips_damaged_lines_and_can_limit(tmp_path):
    log = make(tmp_path)
    for n in range(4):
        log.finish(f"r{n}", mode="robot", note=f"n{n}")
    with open(log.path, "a") as fh:
        fh.write("this is not json\n\n[1, 2]\n")
    assert [e["result"] for e in log.read_entries()] == ["r0", "r1", "r2", "r3"]
    assert [e["result"] for e in log.read_entries(limit=2)] == ["r2", "r3"]


def test_ensure_exists_creates_folder_and_empty_file(tmp_path):
    log = make(tmp_path)
    assert not log.path.exists()
    log.ensure_exists()
    assert log.path.is_file() and log.path.read_text() == ""
    assert log.read_entries() == []


def test_default_path_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("HEXAPOD_TEST_LOG", raising=False)
    assert testlog.default_path().name == "test-log.jsonl"
    monkeypatch.setenv("HEXAPOD_TEST_LOG", str(tmp_path / "mine.jsonl"))
    assert testlog.default_path() == tmp_path / "mine.jsonl"
    assert RunLog().path == tmp_path / "mine.jsonl"


def test_summarize_for_the_table(tmp_path):
    log = make(tmp_path)
    log.record_command("CMD_MOVE#1#0#25#5#0")
    row = summarize(log.finish("stopped", mode="robot", battery=(8.1, 8.05), note="ok"))
    assert row["time"] == "2026-11-25 10:30:00+00:00"
    assert row["ran"] == "CMD_MOVE#1#0#25#5#0"
    assert row["battery"] == "8.1 / 8.05 V"
    assert row["result"] == "stopped" and row["note"] == "ok"
    empty = summarize({})
    assert empty["ran"] == "—" and empty["battery"] == "—"
