import socket
import threading
import time

import pytest

from hexapod import mock_server
from hexapod import protocol as proto
from hexapod.client import FreenoveClient, MockClient


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_mock_client_replies_like_robot():
    c = MockClient()
    replies = []
    c.on_reply = replies.append
    c.connect()
    c.request_sonic()
    c.walk("forward")
    c.head_center()
    c.request_power()
    c.disconnect()
    assert replies[0] == "CMD_SONIC#42.0"
    assert replies[1].startswith("CMD_POWER#")
    assert len(replies) == 2  # no fake "OK" replies
    assert c.sent[-1] == "CMD_MOVE#1#0#0#0#0"  # stop sent on disconnect
    assert "CMD_HEAD#0#90" in c.sent and "CMD_HEAD#1#90" in c.sent


def test_mock_client_relax_stops_first():
    c = MockClient()
    c.connect()
    c.relax()
    assert c.sent[-2:] == ["CMD_MOVE#1#0#0#0#0", "CMD_SERVOPOWER#0"]
    c.disconnect()


def test_mock_client_not_connected_raises():
    with pytest.raises(RuntimeError):
        MockClient().walk("forward")


@pytest.fixture
def fake_robot(monkeypatch):
    """Real sockets against mock_server handlers on random local ports."""
    cmd_port, video_port = _free_port(), _free_port()
    monkeypatch.setattr(proto, "CMD_PORT", cmd_port)
    monkeypatch.setattr(proto, "VIDEO_PORT", video_port)
    received = []
    conns = []

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


def _wait(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_real_client_against_mock_server(fake_robot):
    received, _ = fake_robot
    c = FreenoveClient()
    c.connect("127.0.0.1")
    c.request_sonic()
    assert _wait(lambda: c.last_reply == "CMD_SONIC#42.0")
    c.turn("left")
    assert _wait(lambda: c.latest_jpeg is not None)
    c.disconnect()
    assert _wait(lambda: "CMD_MOVE#1#0#0#0#0" in received)
    assert "CMD_MOVE#1#0#0#5#-10" in received
    assert not c.connected
    assert c.lost_reason == ""  # clean disconnect is not a "lost" connection


def test_dropped_connection_is_detected(fake_robot):
    _, conns = fake_robot
    c = FreenoveClient()
    lost = []
    c.on_connection_lost = lost.append
    c.connect("127.0.0.1")
    assert _wait(lambda: conns)
    conns[0].shutdown(socket.SHUT_RDWR)  # robot side goes away
    assert _wait(lambda: lost)
    assert not c.connected
    assert c.lost_reason
    with pytest.raises(RuntimeError):
        c.stop()


def test_connect_retries_then_fails(monkeypatch):
    monkeypatch.setattr(proto, "CMD_PORT", _free_port())
    c = FreenoveClient()
    t0 = time.time()
    with pytest.raises(ConnectionError):
        c.connect("127.0.0.1", timeout=0.5, retries=3, retry_delay=0.1)
    assert time.time() - t0 >= 0.2  # waited between tries
    assert not c.connected
