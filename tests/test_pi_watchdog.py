"""Tests for the Pi-side watchdog (pi/). It runs against a pretend Control object:
it has NOT been tried on the real robot."""

import importlib.util
import threading
import time
from pathlib import Path

import pytest

PI_DIR = Path(__file__).resolve().parent.parent / "pi"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PI_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wd = _load("connection_watchdog")
installer = _load("install_watchdog")

WALK = ["CMD_MOVE", "1", "0", "25", "5", "0"]
IDLE = ["", "", "", "", "", ""]


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeControl:
    """Same two attributes the stock Freenove Control object uses."""

    def __init__(self, queue=None, timeout=0):
        self.command_queue = list(queue or IDLE)
        self.timeout = timeout


def make(control, clock, **kw):
    return wd.ConnectionWatchdog(control, stale_seconds=1.0, clock=clock, log=lambda *_: None, **kw)


# ---- the decision ---------------------------------------------------------


def test_walking_mode_only_for_continuous_moves():
    assert wd.walking_mode(WALK) == "1"
    assert wd.walking_mode(["CMD_MOVE", "2", "-25", "0", "5", "0"]) == "2"
    assert wd.walking_mode(["CMD_MOVE", "1", "0", "0", "5", "-10"]) is None  # turn: one step
    assert wd.walking_mode(["CMD_MOVE", "1", "0", "0", "0", "0"]) is None  # stop
    assert wd.walking_mode(IDLE) is None
    assert wd.walking_mode(["CMD_POSITION", "0", "0", "0"]) is None
    assert wd.walking_mode(["CMD_MOVE", "1", "x", "0", "5", "0"]) is None
    assert wd.walking_mode(None) is None


def test_halts_a_walk_that_went_silent():
    clock = FakeClock()
    ctl = FakeControl(WALK, timeout=clock.now)
    dog = make(ctl, clock)
    clock.now += 0.5
    assert not dog.check()  # still fresh
    clock.now += 1.0
    assert not dog.check()  # stale, first sighting only
    assert ctl.command_queue == WALK
    assert dog.check()  # same stale command seen again: halt
    assert ctl.command_queue == ["CMD_MOVE", "1", "0", "0", "0", "0"]  # the stock stop
    assert ctl.timeout == clock.now
    assert dog.halts == 1
    assert not dog.check()  # now standing: nothing more to do
    assert not dog.check()
    assert dog.halts == 1


def test_stop_keeps_the_gait_mode():
    clock = FakeClock()
    ctl = FakeControl(["CMD_MOVE", "2", "25", "0", "5", "0"], timeout=clock.now - 5)
    dog = make(ctl, clock)
    dog.check()
    dog.check()
    assert ctl.command_queue == ["CMD_MOVE", "2", "0", "0", "0", "0"]


def test_a_fresh_command_cancels_the_halt():
    clock = FakeClock()
    ctl = FakeControl(WALK, timeout=clock.now - 5)
    dog = make(ctl, clock)
    assert not dog.check()  # stale, first sighting
    # the app's repeat arrives: a new list and a new time
    ctl.command_queue = list(WALK)
    ctl.timeout = clock.now
    assert not dog.check()
    assert not dog.check()
    assert dog.halts == 0 and ctl.command_queue == WALK


def test_command_stored_but_time_not_yet_updated_is_not_a_false_stop():
    # the server stores the command, THEN the time: a poll in between must not halt
    clock = FakeClock()
    ctl = FakeControl(WALK, timeout=clock.now - 5)
    dog = make(ctl, clock)
    assert not dog.check()  # old command, stale
    ctl.command_queue = list(WALK)  # new command stored, time still old
    assert not dog.check()  # different list object: starts over
    ctl.timeout = clock.now  # time catches up
    assert not dog.check()
    assert dog.halts == 0


@pytest.mark.parametrize(
    "queue",
    [
        IDLE,
        ["CMD_MOVE", "1", "0", "0", "5", "-10"],  # turn
        ["CMD_MOVE", "1", "0", "0", "0", "0"],  # stop
        ["CMD_CALIBRATION", "one", "1", "2", "3"],
        ["CMD_ATTITUDE", "1", "2", "3"],
    ],
)
def test_never_touches_anything_that_is_not_a_continuous_walk(queue):
    clock = FakeClock()
    ctl = FakeControl(queue, timeout=clock.now - 100)
    before = list(ctl.command_queue)
    dog = make(ctl, clock)
    for _ in range(5):
        assert not dog.check()
    assert ctl.command_queue == before and dog.halts == 0


def test_walk_with_no_timestamp_is_treated_as_stale():
    clock = FakeClock()
    ctl = FakeControl(WALK, timeout=0)
    dog = make(ctl, clock)
    dog.check()
    assert dog.check()


# ---- running as a thread, next to something that behaves like the stock server


def test_thread_stops_a_walk_when_the_commands_stop_but_not_while_they_repeat():
    ctl = FakeControl()
    walked = []
    running = threading.Event()
    running.set()

    def stock_monitor():  # mimics Control.condition_monitor's walk / stop handling
        while running.is_set():
            q = ctl.command_queue
            if q[0] == "CMD_MOVE":
                if q[2] == "0" and q[3] == "0":
                    walked.append("stand")
                    ctl.command_queue = list(IDLE)
                else:
                    walked.append("step")
            time.sleep(0.01)

    def receive(command):  # mimics Server.receive_commands
        ctl.command_queue = command
        ctl.timeout = time.time()

    dog = wd.ConnectionWatchdog(ctl, stale_seconds=0.3, poll_seconds=0.02, log=lambda *_: None)
    threading.Thread(target=stock_monitor, daemon=True).start()
    dog.start()
    try:
        end = time.time() + 0.8  # repeats arrive: it keeps walking
        while time.time() < end:
            receive(list(WALK))
            time.sleep(0.1)
        assert dog.halts == 0 and "stand" not in walked
        deadline = time.time() + 2  # the repeats stop: it must halt
        while time.time() < deadline and "stand" not in walked:
            time.sleep(0.02)
        assert "stand" in walked and dog.halts == 1
        assert ctl.command_queue == IDLE
    finally:
        dog.stop()
        running.clear()


def test_start_watchdog_refuses_an_unknown_control_object(capsys):
    assert wd.start_watchdog(object()) is None
    assert "NOT running" in capsys.readouterr().out


def test_start_watchdog_starts_a_daemon_thread(capsys):
    dog = wd.start_watchdog(FakeControl())
    try:
        assert dog.is_alive() and dog.daemon
        assert "running" in capsys.readouterr().out
    finally:
        dog.stop()


def test_an_error_inside_the_watchdog_does_not_kill_it():
    class Broken:
        timeout = 0

        @property
        def command_queue(self):
            raise RuntimeError("boom")

    messages = []
    dog = wd.ConnectionWatchdog(Broken(), poll_seconds=0.01, log=messages.append)
    dog.start()
    time.sleep(0.1)
    assert dog.is_alive() and messages
    dog.stop()


# ---- the installer --------------------------------------------------------

# The lines of Freenove's Code/Server/server.py that matter (master, V1.1+).
STOCK_SERVER = """# -*- coding: utf-8 -*-
import io
from command import COMMAND as cmd
from camera import Camera  

class Server:
    def __init__(self):
        self.is_tcp_active = False
        self.control_system = Control()
        self.camera_device = Camera()  
        self.control_system.condition_thread.start()

    def get_interface_ip(self):
        pass
"""


def test_patch_adds_exactly_two_lines():
    patched = installer.patch_source(STOCK_SERVER)
    added = [l for l in patched.split("\n") if l not in STOCK_SERVER.split("\n")]
    assert len(added) == 2
    assert any(l.startswith("from connection_watchdog import start_watchdog") for l in added)
    assert any(l == "        start_watchdog(self.control_system)" + installer.TAG for l in added)
    lines = patched.split("\n")
    start = next(i for i, l in enumerate(lines) if "condition_thread.start()" in l)
    assert "start_watchdog" in lines[start + 1]  # right after the thread starts
    compile(patched, "server.py", "exec")


def test_patch_is_safe_to_repeat_and_reversible():
    once = installer.patch_source(STOCK_SERVER)
    assert installer.patch_source(once) == once
    assert installer.unpatch_source(once) == STOCK_SERVER


def test_patch_refuses_unknown_or_half_patched_files():
    with pytest.raises(ValueError):
        installer.patch_source("print('a different server.py')\n")
    half = STOCK_SERVER.replace(
        "from camera import Camera  ", "from camera import Camera\nfrom connection_watchdog import start_watchdog"
    )
    with pytest.raises(ValueError):
        installer.patch_source(half)


def _fake_server_dir(tmp_path):
    folder = tmp_path / "Code" / "Server"
    folder.mkdir(parents=True)
    (folder / "server.py").write_text(STOCK_SERVER)
    return folder


def test_installer_end_to_end(tmp_path, capsys):
    folder = _fake_server_dir(tmp_path)
    assert installer.main([str(folder), "--dry-run"]) == 0
    assert (folder / "server.py").read_text() == STOCK_SERVER  # dry run changes nothing

    assert installer.main([str(folder)]) == 0
    patched = (folder / "server.py").read_text()
    assert "start_watchdog(self.control_system)" in patched
    assert (folder / "connection_watchdog.py").is_file()
    assert (folder / installer.BACKUP).read_text() == STOCK_SERVER

    assert installer.main([str(folder)]) == 0  # again: no change, backup kept
    assert (folder / "server.py").read_text() == patched
    assert (folder / installer.BACKUP).read_text() == STOCK_SERVER
    assert "Already installed" in capsys.readouterr().out

    assert installer.main([str(folder), "--remove"]) == 0
    assert (folder / "server.py").read_text() == STOCK_SERVER
    assert not (folder / "connection_watchdog.py").exists()


def test_installer_leaves_a_different_server_alone(tmp_path):
    folder = tmp_path / "Server"
    folder.mkdir()
    (folder / "server.py").write_text("print('hi')\n")
    assert installer.main([str(folder)]) == 1
    assert (folder / "server.py").read_text() == "print('hi')\n"
    assert not (folder / installer.BACKUP).exists()
    assert not (folder / "connection_watchdog.py").exists()


def test_installer_reports_a_wrong_folder(tmp_path):
    assert installer.main([str(tmp_path / "nope")]) == 1
