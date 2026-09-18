"""Minimal Freenove-compatible TCP mock server for LAN UI testing without hardware.

Listens on CMD_PORT (5002) and VIDEO_PORT (8002). Video frames are length-prefixed
little-endian JPEG blobs matching the stock Client.py receiver.
"""

from __future__ import annotations

import argparse
import logging
import socket
import struct
import threading
import time
from . import protocol as proto
from .mock_frame import MOCK_JPEG

log = logging.getLogger(__name__)


def _handle_cmd(conn: socket.socket) -> None:
    buf = b""
    with conn:
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                log.info("CMD %s", text)
                if text.startswith("CMD_SONIC"):
                    conn.sendall(b"42.0\n")
                elif text.startswith("CMD_POWER"):
                    conn.sendall(b"CMD_POWER#8.10#8.05\n")


def _handle_video(conn: socket.socket, frame: bytes) -> None:
    with conn:
        while True:
            try:
                conn.sendall(struct.pack("<L", len(frame)) + frame)
            except OSError:
                break
            time.sleep(0.2)


def _serve(port: int, handler) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(5)
    log.info("listening on %s", port)
    while True:
        conn, addr = sock.accept()
        log.info("accept %s -> %s", addr, port)
        threading.Thread(target=handler, args=(conn,), daemon=True).start()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Mock Freenove hexapod server")
    parser.add_argument("--cmd-port", type=int, default=proto.CMD_PORT)
    parser.add_argument("--video-port", type=int, default=proto.VIDEO_PORT)
    args = parser.parse_args()
    frame = MOCK_JPEG

    def video_handler(conn: socket.socket) -> None:
        _handle_video(conn, frame)

    threading.Thread(
        target=_serve, args=(args.cmd_port, _handle_cmd), daemon=True
    ).start()
    threading.Thread(
        target=_serve, args=(args.video_port, video_handler), daemon=True
    ).start()
    log.info("mock Freenove server ready (cmd=%s video=%s)", args.cmd_port, args.video_port)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
