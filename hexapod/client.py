"""TCP client for Freenove Big Hexapod Server (CMD 5002 + JPEG video 8002).

The stock server accepts ONE controller and only re-opens its ports after the
previous client disconnects cleanly, so this client always sends a stop and
closes both sockets on disconnect, and retries a connect a few times.
"""

from __future__ import annotations

import base64
import logging
import socket
import struct
import threading
import time
from typing import Callable, Optional

from . import protocol as proto
from .mock_frame import MOCK_JPEG

log = logging.getLogger(__name__)


class FreenoveClient:
    """Thin LAN client. Does not implement gait/servos — talks to stock Server."""

    def __init__(self) -> None:
        self._cmd: Optional[socket.socket] = None
        self._video: Optional[socket.socket] = None
        self._cmd_lock = threading.Lock()
        self._connected = False
        self._video_thread: Optional[threading.Thread] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_video = threading.Event()
        self._stop_reader = threading.Event()
        self.latest_jpeg: Optional[bytes] = None
        self.last_reply: str = ""
        self.lost_reason: str = ""
        self.on_video: Optional[Callable[[bytes], None]] = None
        self.on_reply: Optional[Callable[[str], None]] = None
        # Called with a reason when the robot drops the connection unexpectedly.
        self.on_connection_lost: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(
        self,
        host: str,
        timeout: float = 5.0,
        retries: int = 3,
        retry_delay: float = 1.5,
    ) -> None:
        """Connect, retrying a few times (the server needs a moment to re-open)."""
        self.disconnect()
        host = host.strip()
        last_exc: Optional[Exception] = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                self._open(host, timeout)
                return
            except OSError as exc:
                last_exc = exc
                log.warning("connect attempt %s/%s failed: %s", attempt, retries, exc)
                self._close_sockets()
                if attempt < retries:
                    time.sleep(retry_delay)
        raise ConnectionError(
            f"could not reach robot at {host} after {retries} tries: {last_exc}"
        )

    def _open(self, host: str, timeout: float) -> None:
        cmd = socket.create_connection((host, proto.CMD_PORT), timeout=timeout)
        self._cmd = cmd
        cmd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        video = socket.create_connection((host, proto.VIDEO_PORT), timeout=timeout)
        self._video = video
        # Blocking reads after connect; dead links are detected by recv/send errors.
        cmd.settimeout(None)
        video.settimeout(None)
        self.lost_reason = ""
        self._connected = True
        self._stop_video.clear()
        self._stop_reader.clear()
        self._video_thread = threading.Thread(
            target=self._video_loop, name="freenove-video", daemon=True
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="freenove-reader", daemon=True
        )
        self._video_thread.start()
        self._reader_thread.start()
        log.info("connected to %s:%s / :%s", host, proto.CMD_PORT, proto.VIDEO_PORT)

    def disconnect(self) -> None:
        """Clean disconnect: stop walking, then close both sockets."""
        if self._connected and self._cmd is not None:
            try:
                with self._cmd_lock:
                    self._cmd.sendall(proto.cmd_stop().encode("utf-8"))
            except OSError:
                pass
        self._connected = False
        self._stop_video.set()
        self._stop_reader.set()
        self._close_sockets()
        for t in (self._video_thread, self._reader_thread):
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=1.0)
        self._video_thread = None
        self._reader_thread = None

    def _close_sockets(self) -> None:
        for sock in (self._cmd, self._video):
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._cmd = None
        self._video = None

    def _mark_lost(self, reason: str) -> None:
        """Robot went away without us asking: flag it and tell the UI once."""
        if not self._connected or self._stop_reader.is_set():
            return
        self._connected = False
        self.lost_reason = reason
        log.warning("connection lost: %s", reason)
        self._stop_video.set()
        self._stop_reader.set()
        self._close_sockets()
        if self.on_connection_lost:
            try:
                self.on_connection_lost(reason)
            except Exception:  # pragma: no cover - UI callback
                log.exception("on_connection_lost failed")

    def send(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        with self._cmd_lock:
            if not self._cmd or not self._connected:
                raise RuntimeError("not connected")
            sock = self._cmd
            try:
                sock.sendall(line.encode("utf-8"))
            except OSError as exc:
                err = exc
            else:
                return
        self._mark_lost(f"send failed: {err}")
        raise RuntimeError(f"connection lost: {err}")

    def walk(self, direction: str, speed: int = proto.DEFAULT_SPEED, mode: int = 1) -> None:
        self.send(proto.cmd_walk(direction, speed=speed, mode=mode))

    def turn(self, direction: str, speed: int = proto.DEFAULT_SPEED, mode: int = 1) -> None:
        """direction: 'left' or 'right' (uses CMD_MOVE's angle field)."""
        self.walk(f"turn_{direction}", speed=speed, mode=mode)

    def stop(self, mode: int = 1) -> None:
        self.send(proto.cmd_stop(mode))

    def head(self, axis: int, angle: int) -> None:
        """Raw, clamped servo angle (see protocol.cmd_head)."""
        self.send(proto.cmd_head(axis, angle))

    def head_up_down(self, value: int) -> None:
        self.send(proto.cmd_head_up_down(value))

    def head_left_right(self, value: int) -> None:
        self.send(proto.cmd_head_left_right(value))

    def head_center(self) -> None:
        self.head_up_down(proto.HEAD_CENTER)
        self.head_left_right(proto.HEAD_CENTER)

    def servo_power(self, on: bool) -> None:
        self.send(proto.cmd_servo_power(on))

    def relax(self, mode: int = 1) -> None:
        """Stop walking, then let the legs go limp (Freenove app's Relax)."""
        self.stop(mode)
        self.send(proto.cmd_relax())

    def buzzer(self, on: bool) -> None:
        self.send(proto.cmd_buzzer(on))

    def request_sonic(self) -> None:
        self.send(proto.cmd_sonic())

    def request_power(self) -> None:
        self.send(proto.cmd_power())

    def latest_jpeg_data_url(self) -> Optional[str]:
        if not self.latest_jpeg:
            return None
        b64 = base64.b64encode(self.latest_jpeg).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _handle_reply(self, text: str) -> None:
        self.last_reply = text
        if self.on_reply:
            self.on_reply(text)

    def _reader_loop(self) -> None:
        sock = self._cmd
        buf = b""
        reason = "robot closed the connection"
        while not self._stop_reader.is_set() and sock is not None:
            try:
                chunk = sock.recv(1024)
            except OSError as exc:
                reason = f"read failed: {exc}"
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self._handle_reply(text)
        self._mark_lost(reason)

    def _video_loop(self) -> None:
        sock = self._video
        if sock is None:
            return
        try:
            while not self._stop_video.is_set():
                header = self._recv_exact(sock, 4)
                if header is None:
                    break
                (length,) = struct.unpack("<L", header)
                if length <= 0 or length > 5_000_000:
                    log.warning("invalid jpeg length %s", length)
                    break
                jpg = self._recv_exact(sock, length)
                if jpg is None:
                    break
                if not (jpg.startswith(b"\xff\xd8") and jpg.endswith(b"\xff\xd9")):
                    continue
                self.latest_jpeg = jpg
                if self.on_video:
                    self.on_video(jpg)
        except OSError as exc:
            log.debug("video loop ended: %s", exc)

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
        chunks: list[bytes] = []
        got = 0
        while got < n:
            try:
                part = sock.recv(n - got)
            except OSError:
                return None
            if not part:
                return None
            chunks.append(part)
            got += len(part)
        return b"".join(chunks)


class MockClient(FreenoveClient):
    """In-process practice mode: no sockets; replies exactly like the real server
    (only CMD_SONIC and CMD_POWER answer; everything else is silent)."""

    def __init__(self) -> None:
        super().__init__()
        self._mock_thread: Optional[threading.Thread] = None
        self._stop_mock = threading.Event()
        self._frame = MOCK_JPEG
        self.sent: list[str] = []

    def connect(self, host: str = "mock", timeout: float = 5.0, **_: object) -> None:  # noqa: ARG002
        self.disconnect()
        self.lost_reason = ""
        self._connected = True
        self._stop_mock.clear()
        self._mock_thread = threading.Thread(
            target=self._mock_loop, name="freenove-mock", daemon=True
        )
        self._mock_thread.start()
        log.info("mock client connected (%s)", host)

    def disconnect(self) -> None:
        if self._connected:
            self.sent.append(proto.cmd_stop().strip())
        self._connected = False
        self._stop_mock.set()
        if self._mock_thread and self._mock_thread.is_alive():
            self._mock_thread.join(timeout=1.0)
        self._mock_thread = None
        self._cmd = None
        self._video = None

    def send(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        if not self._connected:
            raise RuntimeError("not connected")
        text = line.strip()
        self.sent.append(text)
        log.info("mock TX %s", text)
        reply = proto.mock_reply(text)
        if reply is not None:
            self._handle_reply(reply)

    def _mock_loop(self) -> None:
        while not self._stop_mock.is_set():
            if self._frame:
                self.latest_jpeg = self._frame
                if self.on_video:
                    self.on_video(self._frame)
            time.sleep(0.25)
