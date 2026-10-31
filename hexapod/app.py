"""NiceGUI control shell for Freenove Big Hexapod.

Talks to stock Freenove Code/Server over LAN TCP — does not reimplement gait.
Use the official PyQt Client for first-time leg calibration.
"""

from __future__ import annotations

import logging
from typing import Union

from nicegui import app, ui

from .client import FreenoveClient, MockClient
from . import protocol as proto

log = logging.getLogger(__name__)

ClientType = Union[FreenoveClient, MockClient]

DEFAULT_HOST = "192.168.1.240"


def create_ui() -> None:
    state = {
        "client": FreenoveClient(),
        "speed": proto.DEFAULT_SPEED,
        "mode": 1,
        "status": "Disconnected",
        "reply": "",
        "mock": False,
        "lost": "",
    }

    def active() -> ClientType:
        return state["client"]  # type: ignore[return-value]

    def set_status(text: str) -> None:
        state["status"] = text
        status_label.set_text(text)

    def on_reply(text: str) -> None:
        # Called from a background thread: only store it; the UI timer shows it.
        state["reply"] = text

    def on_connection_lost(reason: str) -> None:
        # Background thread: the UI timer turns this into a visible status.
        state["lost"] = reason

    def safe_send(fn) -> None:
        try:
            fn()
        except Exception as exc:
            set_status(f"Error: {exc}")
            ui.notify(str(exc), type="negative")

    def send_stop_quietly() -> None:
        try:
            if active().connected:
                active().stop(mode=int(mode.value))
        except Exception:
            pass

    def do_connect() -> None:
        host = ip_input.value.strip() or DEFAULT_HOST
        use_mock = mock_switch.value
        try:
            active().disconnect()
        except Exception:
            pass
        client: ClientType = MockClient() if use_mock else FreenoveClient()
        client.on_reply = on_reply
        client.on_connection_lost = on_connection_lost
        state["client"] = client
        state["mock"] = use_mock
        state["lost"] = ""
        set_status("Connecting…")
        try:
            client.connect("mock" if use_mock else host)
            set_status("Practice mode connected" if use_mock else f"Connected to {host}")
            ui.notify(state["status"], type="positive")
        except Exception as exc:
            set_status(f"Connect failed: {exc}")
            ui.notify(str(exc), type="negative")

    def do_disconnect() -> None:
        try:
            active().disconnect()  # sends a stop first, then closes cleanly
        finally:
            state["lost"] = ""
            set_status("Disconnected")

    def move(direction: str) -> None:
        safe_send(lambda: active().walk(direction, speed=int(speed.value), mode=int(mode.value)))

    def stop() -> None:
        safe_send(lambda: active().stop(mode=int(mode.value)))

    ui.page_title("Big Hexapod GUI")
    with ui.header().classes("items-center justify-between"):
        ui.label("Freenove Big Hexapod — Easy Control").classes("text-h6")
        status_label = ui.label("Disconnected").classes("text-caption")

    with ui.row().classes("w-full items-end gap-4 flex-wrap"):
        ip_input = ui.input("Pi IP", value=DEFAULT_HOST).classes("w-48")
        mock_switch = ui.switch("Practice mode (no robot)", value=False)
        ui.button("Connect", on_click=do_connect, color="primary")
        ui.button("Disconnect", on_click=do_disconnect)
        ui.button("Battery", on_click=lambda: safe_send(active().request_power))
        ui.button("Distance", on_click=lambda: safe_send(active().request_sonic))

    with ui.row().classes("w-full gap-6 flex-wrap"):
        with ui.card().classes("p-4"):
            ui.label("Drive").classes("text-subtitle1")
            speed = ui.slider(min=2, max=10, value=proto.DEFAULT_SPEED).props("label")
            ui.label("Speed (2–10)")
            mode = ui.select({1: "Gait mode 1", 2: "Gait mode 2"}, value=1).classes("w-48")
            with ui.grid(columns=3).classes("gap-2 mt-2"):
                ui.button("⟲", on_click=lambda: move("turn_left")).props("unelevated").tooltip("Turn left")
                ui.button("↑", on_click=lambda: move("forward")).props("unelevated")
                ui.button("⟳", on_click=lambda: move("turn_right")).props("unelevated").tooltip("Turn right")
                ui.button("←", on_click=lambda: move("left")).props("unelevated")
                ui.button("■", on_click=stop, color="negative").props("unelevated")
                ui.button("→", on_click=lambda: move("right")).props("unelevated")
                ui.element("div")
                ui.button("↓", on_click=lambda: move("backward")).props("unelevated")
            with ui.row().classes("mt-3 gap-2"):
                ui.button(
                    "Servos ON",
                    on_click=lambda: safe_send(lambda: active().servo_power(True)),
                )
                ui.button(
                    "Relax (servos off)",
                    on_click=lambda: safe_send(lambda: active().relax(mode=int(mode.value))),
                    color="warning",
                ).tooltip("Stops, then lets the legs go limp — the body will sink")
                ui.button(
                    "Buzz",
                    on_click=lambda: safe_send(lambda: active().buzzer(True)),
                )

        with ui.card().classes("p-4"):
            ui.label("Head").classes("text-subtitle1")
            up_down = ui.slider(
                min=proto.HEAD_UP_DOWN_MIN, max=proto.HEAD_UP_DOWN_MAX, value=proto.HEAD_CENTER
            ).props("label")
            ui.label(f"Up / down ({proto.HEAD_UP_DOWN_MIN}–{proto.HEAD_UP_DOWN_MAX}, centre 90)")
            left_right = ui.slider(
                min=proto.HEAD_LEFT_RIGHT_MIN, max=proto.HEAD_LEFT_RIGHT_MAX, value=proto.HEAD_CENTER
            ).props("label")
            ui.label(f"Left / right ({proto.HEAD_LEFT_RIGHT_MIN}–{proto.HEAD_LEFT_RIGHT_MAX}, centre 90)")

            def apply_head() -> None:
                safe_send(lambda: active().head_up_down(int(up_down.value)))
                safe_send(lambda: active().head_left_right(int(left_right.value)))

            def center_head() -> None:
                up_down.set_value(proto.HEAD_CENTER)
                left_right.set_value(proto.HEAD_CENTER)
                safe_send(lambda: active().head_center())

            with ui.row().classes("gap-2"):
                ui.button("Apply head", on_click=apply_head)
                ui.button("Centre head", on_click=center_head)

        with ui.card().classes("p-4 grow"):
            ui.label("Camera").classes("text-subtitle1")
            video = ui.image("").classes("w-full max-w-xl rounded")
            reply_label = ui.label("").classes("text-caption font-mono")

            def refresh() -> None:
                url = active().latest_jpeg_data_url()
                if url:
                    video.set_source(url)
                if reply_label.text != state["reply"]:
                    reply_label.set_text(state["reply"])
                if state["lost"]:
                    reason = state["lost"]
                    state["lost"] = ""
                    set_status(f"Connection lost — press Connect to retry ({reason})")
                    ui.notify(f"Connection to robot lost: {reason}", type="negative")

            ui.timer(0.2, refresh)

    with ui.expansion("Notes / Pi 5", icon="info").classes("w-full"):
        ui.markdown(
            """
- On the Pi run stock Freenove **`Code/Server`**: `sudo python main.py -t -n`
  (`server-PI5` was merged into `Server` in V1.1).
- CMD port **5002**, JPEG video **8002** (length-prefixed little-endian).
- The robot accepts **one** controller at a time; always use **Disconnect**
  (or close the page) so it can accept the next connection.
- First calibration: use the official Freenove **PyQt Client**.
- LED: only PCB **V2.0** (SPI) on Pi 5; V1.0 has no LED path.
- Protocol: Freenove `Code/robot_control_communication_protocol.md`
            """
        )

    # Safety: if a browser tab closes, stop the robot walking.
    app.on_disconnect(send_stop_quietly)

    def on_shutdown() -> None:
        try:
            active().disconnect()  # sends stop, then closes cleanly
        except Exception:
            pass

    app.on_shutdown(on_shutdown)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_ui()
    ui.run(title="Big Hexapod GUI", host="0.0.0.0", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
