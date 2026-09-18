"""TCP client for Freenove Big Hexapod Server (CMD 5002 + JPEG video 8002)."""

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
        self.on_video: Optional[Callable[[bytes], None]] = None
        self.on_reply: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, timeout: float = 5.0) -> None:
        self.disconnect()
        host = host.strip()
        cmd = socket.create_connection((host, proto.CMD_PORT), timeout=timeout)
        cmd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        video = socket.create_connection((host, proto.VIDEO_PORT), timeout=timeout)
        self._cmd = cmd
        self._video = video
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
        self._connected = False
        self._stop_video.set()
        self._stop_reader.set()
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
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=1.0)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._video_thread = None
        self._reader_thread = None

    def send(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        with self._cmd_lock:
            if not self._cmd or not self._connected:
                raise RuntimeError("not connected")
            self._cmd.sendall(line.encode("utf-8"))

    def walk(self, direction: str, speed: int = proto.DEFAULT_SPEED, mode: int = 1) -> None:
        self.send(proto.cmd_walk(direction, speed=speed, mode=mode))

    def stop(self, mode: int = 1) -> None:
        self.send(proto.cmd_stop(mode))

    def head(self, axis: int, angle: int) -> None:
        self.send(proto.cmd_head(axis, angle))

    def servo_power(self, on: bool) -> None:
        self.send(proto.cmd_servo_power(on))

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

    def _reader_loop(self) -> None:
        buf = b""
        while not self._stop_reader.is_set() and self._cmd is not None:
            try:
                chunk = self._cmd.recv(1024)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    self.last_reply = text
                    if self.on_reply:
                        self.on_reply(text)
            except OSError:
                break
        self._connected = False

    def _video_loop(self) -> None:
        assert self._video is not None
        sock = self._video
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
    """In-process mock: no sockets; synthesizes JPEG frames and echoes commands."""

    def __init__(self) -> None:
        super().__init__()
        self._mock_thread: Optional[threading.Thread] = None
        self._stop_mock = threading.Event()
        self._frame = MOCK_JPEG

    def connect(self, host: str = "mock", timeout: float = 5.0) -> None:  # noqa: ARG002
        self.disconnect()
        self._connected = True
        self._stop_mock.clear()
        self._mock_thread = threading.Thread(
            target=self._mock_loop, name="freenove-mock", daemon=True
        )
        self._mock_thread.start()
        log.info("mock client connected (%s)", host)

    def disconnect(self) -> None:
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
        log.info("mock TX %s", text)
        if text.startswith("CMD_SONIC"):
            reply = "42.0"
        elif text.startswith("CMD_POWER"):
            reply = "CMD_POWER#8.10#8.05"
        else:
            reply = "OK"
        self.last_reply = reply
        if self.on_reply:
            self.on_reply(reply)

    def _mock_loop(self) -> None:
        while not self._stop_mock.is_set():
            if self._frame:
                self.latest_jpeg = self._frame
                if self.on_video:
                    self.on_video(self._frame)
            time.sleep(0.25)
