import socket
import threading
import time

import pytest

from hexapod import mock_server
from hexapod import protocol as proto
from hexapod.client import KEEPALIVE_INTERVAL, FreenoveClient, MockClient

FORWARD = "CMD_MOVE#1#0#25#5#0"
STOP = "CMD_MOVE#1#0#0#0#0"


def _wait(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_is_continuous_move():
    assert proto.is_continuous_move(FORWARD)
    assert proto.is_continuous_move(proto.cmd_walk("left"))
    assert proto.is_continuous_move(proto.cmd_walk("backward") + "\n")
    # a stop or a turn is a single step on the stock server: nothing to repeat
    assert not proto.is_continuous_move(STOP)
    assert not proto.is_continuous_move(proto.cmd_walk("turn_left"))
    assert not proto.is_continuous_move("CMD_HEAD#0#90")
    assert not proto.is_continuous_move("CMD_MOVE#1#x#y#5#0")
    assert not proto.is_continuous_move("")


def test_keepalive_is_well_inside_the_pi_watchdog_timeout():
    assert KEEPALIVE_INTERVAL <= 0.5  # the Pi halts a walk after ~1 s of silence


def test_walk_is_repeated_until_stop():
    c = MockClient()
    c.keepalive_interval = 0.03
    c.connect()
    c.walk("forward")
    assert _wait(lambda: c.sent.count(FORWARD) >= 4)
    c.stop()
    n = len(c.sent)
    assert c.sent[-1] == STOP
    time.sleep(0.2)
    assert len(c.sent) == n  # nothing sent after the stop
    c.disconnect()


def test_idle_client_sends_nothing_extra():
    c = MockClient()
    c.keepalive_interval = 0.02
    c.connect()
    time.sleep(0.2)
    assert c.sent == []
    c.disconnect()


def test_turn_and_stop_are_not_repeated():
    c = MockClient()
    c.keepalive_interval = 0.02
    c.connect()
    c.walk("turn_left")
    time.sleep(0.2)
    assert c.sent == ["CMD_MOVE#1#0#0#5#-10"]
    c.disconnect()


def test_a_new_walk_replaces_the_old_one_and_stop_cancels_it():
    c = MockClient()
    c.keepalive_interval = 0.02
    c.connect()
    c.walk("forward")
    c.walk("backward")
    c.sent.clear()
    assert _wait(lambda: c.sent.count("CMD_MOVE#1#0#-25#5#0") >= 3)
    assert FORWARD not in c.sent
    c.walk("turn_right")  # a one-step command cancels the repeat
    c.sent.clear()
    time.sleep(0.15)
    assert c.sent == []
    c.disconnect()


def test_disconnect_sends_stop_and_ends_the_repeat():
    c = MockClient()
    c.keepalive_interval = 0.02
    c.connect()
    c.walk("forward")
    assert _wait(lambda: c.sent.count(FORWARD) >= 2)
    c.disconnect()
    assert c.sent[-1] == STOP
    n = len(c.sent)
    time.sleep(0.15)
    assert len(c.sent) == n


def test_relax_cancels_the_repeat():
    c = MockClient()
    c.keepalive_interval = 0.02
    c.connect()
    c.walk("forward")
    c.relax()
    n = len(c.sent)
    time.sleep(0.15)
    assert len(c.sent) == n
    assert c.sent[-2:] == [STOP, "CMD_SERVOPOWER#0"]
    c.disconnect()


def test_mock_power_override_for_practice_mode():
    c = MockClient()
    replies = []
    c.on_reply = replies.append
    c.mock_power = (6.5, 6.4)
    c.connect()
    c.request_power()
    assert replies == ["CMD_POWER#6.5#6.4"]
    c.disconnect()


@pytest.fixture
def fake_robot(monkeypatch):
    cmd_port, video_port = _free_port(), _free_port()
    monkeypatch.setattr(proto, "CMD_PORT", cmd_port)
    monkeypatch.setattr(proto, "VIDEO_PORT", video_port)
    received, conns = [], []

    def cmd_handler(conn):
        conns.append(conn)
        mock_server._handle_cmd(conn, received.append)

    def video_handler(conn):
        mock_server._handle_video(conn, mock_server.MOCK_JPEG)

    for port, handler in ((cmd_port, cmd_handler), (video_port, video_handler)):
        ready = threading.Event()
        threading.Thread(
            target=mock_server._serve, args=(port, handler, "127.0.0.1", ready), daemon=True
        ).start()
        assert ready.wait(2)
    return received, conns


def test_real_sockets_walk_is_repeated_then_stopped(fake_robot):
    received, _ = fake_robot
    c = FreenoveClient()
    c.keepalive_interval = 0.03
    c.connect("127.0.0.1")
    c.walk("forward")
    assert _wait(lambda: received.count(FORWARD) >= 4)
    c.stop()
    assert _wait(lambda: received and received[-1] == STOP)
    n = len(received)
    time.sleep(0.2)
    assert len(received) == n
    c.disconnect()


def test_repeat_stops_when_the_robot_drops_the_connection(fake_robot):
    received, conns = fake_robot
    c = FreenoveClient()
    c.keepalive_interval = 0.03
    lost = []
    c.on_connection_lost = lost.append
    c.connect("127.0.0.1")
    c.walk("forward")
    assert _wait(lambda: received.count(FORWARD) >= 2)
    conns[0].shutdown(socket.SHUT_RDWR)
    assert _wait(lambda: lost)
    assert not c.connected
    assert c._repeat_line is None
    c.disconnect()
