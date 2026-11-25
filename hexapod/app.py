"""NiceGUI control shell for Freenove Big Hexapod.

Talks to stock Freenove Code/Server over LAN TCP — does not reimplement gait.
Use the official PyQt Client for first-time leg calibration.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Union

from nicegui import app, ui

from .client import FreenoveClient, MockClient
from . import preflight
from . import protocol as proto
from .testlog import RunLog, summarize

log = logging.getLogger(__name__)

ClientType = Union[FreenoveClient, MockClient]

DEFAULT_HOST = "192.168.1.240"

POWER_POLL_SECONDS = 30  # how often the battery is re-read while connected
POWER_MAX_AGE = 120  # a battery reading older than this (seconds) no longer counts


def create_ui() -> None:
    state = {
        "client": FreenoveClient(),
        "speed": proto.DEFAULT_SPEED,
        "mode": 1,
        "status": "Disconnected",
        "reply": "",
        "mock": False,
        "lost": "",
        "power": None,  # (pack1, pack2) volts from the last CMD_POWER reply
        "power_time": 0.0,
        "unlocked": None,  # None = not checked yet, so the first check locks the controls
    }
    runlog = RunLog()
    runlog.ensure_exists()
    app.add_static_file(local_file=str(runlog.path), url_path="/test-log.jsonl")
    locked_controls: List[ui.element] = []  # walk / move controls behind the checklist
    check_boxes: Dict[str, ui.checkbox] = {}

    def active() -> ClientType:
        return state["client"]  # type: ignore[return-value]

    def set_status(text: str) -> None:
        state["status"] = text
        status_label.set_text(text)

    def on_reply(text: str) -> None:
        # Called from a background thread: only store it; the UI timer shows it.
        state["reply"] = text
        volts = preflight.parse_power_reply(text)
        if volts is not None:
            state["power"] = volts
            state["power_time"] = time.time()

    def current_power():
        """Latest battery reading, or None if there is none or it is too old."""
        if state["power"] is None or time.time() - state["power_time"] > POWER_MAX_AGE:
            return None
        return state["power"]

    def finish_run(result: str, note: str = "") -> None:
        """Write the test-log entry for whatever just ran (if anything did)."""
        try:
            runlog.finish(
                result,
                mode="practice" if state["mock"] else "robot",
                gait_mode=int(mode.value),
                battery=state["power"],
                note=note,
            )
        except Exception as exc:  # the log must never get in the way of stopping
            log.warning("could not write test log: %s", exc)

    def take_note() -> str:
        text = (note_input.value or "").strip()
        note_input.set_value("")
        return text

    def reset_checklist() -> None:
        for box in check_boxes.values():
            box.set_value(False)
        state["power"] = None

    def gate() -> preflight.Gate:
        ticks = {key: box.value for key, box in check_boxes.items()}
        return preflight.evaluate(
            current_power(),
            ticks,
            connected=active().connected,
            practice=bool(state["mock"]),
        )

    def request_power_quietly() -> None:
        try:
            if active().connected:
                active().request_power()
        except Exception:
            pass

    def update_gate() -> None:
        """Re-check the checklist; lock or unlock the walk and move controls."""
        g = gate()
        colors = {
            preflight.LEVEL_OK: "text-positive",
            preflight.LEVEL_WARN: "text-warning",
            preflight.LEVEL_BLOCKED: "text-negative",
            preflight.LEVEL_UNKNOWN: "text-grey",
        }
        power = current_power()
        power_label.set_text(
            f"Battery packs: {power[0]:.2f} V and {power[1]:.2f} V" if power else "Battery packs: no reading yet"
        )
        battery_label.set_text(g.battery.message)
        battery_label.classes(replace=f"text-body2 {colors[g.battery.level]}")
        if g.unlocked:
            unlocked_text = "Unlocked — walking and moving are allowed."
            if state["mock"]:
                unlocked_text += " (Practice mode: the boxes are optional.)"
            gate_label.set_text(unlocked_text)
        else:
            gate_label.set_text(f"Locked — {g.reason}")
        gate_label.classes(replace="text-body2 " + ("text-positive" if g.unlocked else "text-negative"))
        if g.unlocked != state["unlocked"]:
            if (
                not g.unlocked
                and state["unlocked"]
                and active().connected
                and g.battery.level == preflight.LEVEL_BLOCKED
            ):
                # The battery sank while unlocked: stop the robot right away.
                send_stop_quietly()
                finish_run("stopped: battery too low")
                ui.notify("Battery too low — robot stopped and walking is locked.", type="negative")
            state["unlocked"] = g.unlocked
            for control in locked_controls:
                control.set_enabled(g.unlocked)

    def require_unlocked() -> bool:
        g = gate()
        if not g.unlocked:
            ui.notify(f"Locked: {g.reason}", type="warning")
        return g.unlocked

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
                runlog.record_command(proto.cmd_stop(int(mode.value)))
        except Exception:
            pass

    def on_browser_closed() -> None:
        send_stop_quietly()
        finish_run("stopped: browser closed")

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
        reset_checklist()  # a fresh check every time you connect
        set_status("Connecting…")
        try:
            client.connect("mock" if use_mock else host)
            set_status("Practice mode connected" if use_mock else f"Connected to {host}")
            ui.notify(state["status"], type="positive")
            request_power_quietly()
        except Exception as exc:
            set_status(f"Connect failed: {exc}")
            ui.notify(str(exc), type="negative")

    def do_disconnect() -> None:
        try:
            finish_run("disconnected", note=take_note())
            active().disconnect()  # sends a stop first, then closes cleanly
        finally:
            state["lost"] = ""
            reset_checklist()
            set_status("Disconnected")

    def move(direction: str) -> None:
        if not require_unlocked():
            return
        line = proto.cmd_walk(direction, speed=int(speed.value), mode=int(mode.value))
        runlog.record_command(line)
        safe_send(lambda: active().walk(direction, speed=int(speed.value), mode=int(mode.value)))

    def stop() -> None:
        # Stop always works, whatever the checklist says.
        runlog.record_command(proto.cmd_stop(int(mode.value)))
        safe_send(lambda: active().stop(mode=int(mode.value)))
        finish_run("stopped with the Stop button", note=take_note())

    def servos_on() -> None:
        if not require_unlocked():
            return
        runlog.record_command(proto.cmd_servo_power(True))
        safe_send(lambda: active().servo_power(True))

    def relax() -> None:
        runlog.record_command(proto.cmd_stop(int(mode.value)))
        runlog.record_command(proto.cmd_relax())
        safe_send(lambda: active().relax(mode=int(mode.value)))
        finish_run("relaxed (servos off)", note=take_note())

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

    with ui.card().classes("w-full p-4"):
        ui.label("Before you run it").classes("text-subtitle1")
        ui.label(
            "Walking and moving stay locked until the battery looks OK and you tick all three boxes. "
            "The Stop button always works."
        ).classes("text-caption")
        power_label = ui.label("Battery packs: no reading yet")
        battery_label = ui.label("").classes("text-body2")
        ui.button("Read battery", on_click=lambda: safe_send(active().request_power)).props("flat dense")
        for key, text in preflight.CHECK_LABELS.items():
            check_boxes[key] = ui.checkbox(text, on_change=lambda _e: update_gate())
        gate_label = ui.label("").classes("text-body2")

    with ui.row().classes("w-full gap-6 flex-wrap"):
        with ui.card().classes("p-4"):
            ui.label("Drive").classes("text-subtitle1")
            speed = ui.slider(min=2, max=10, value=proto.DEFAULT_SPEED).props("label")
            locked_controls.append(speed)
            ui.label("Speed (2–10)")
            mode = ui.select({1: "Gait mode 1", 2: "Gait mode 2"}, value=1).classes("w-48")
            locked_controls.append(mode)
            with ui.grid(columns=3).classes("gap-2 mt-2"):
                locked_controls.append(
                    ui.button("⟲", on_click=lambda: move("turn_left")).props("unelevated").tooltip("Turn left")
                )
                locked_controls.append(ui.button("↑", on_click=lambda: move("forward")).props("unelevated"))
                locked_controls.append(
                    ui.button("⟳", on_click=lambda: move("turn_right")).props("unelevated").tooltip("Turn right")
                )
                locked_controls.append(ui.button("←", on_click=lambda: move("left")).props("unelevated"))
                ui.button("■", on_click=stop, color="negative").props("unelevated")
                locked_controls.append(ui.button("→", on_click=lambda: move("right")).props("unelevated"))
                ui.element("div")
                locked_controls.append(ui.button("↓", on_click=lambda: move("backward")).props("unelevated"))
            with ui.row().classes("mt-3 gap-2"):
                locked_controls.append(ui.button("Servos ON", on_click=servos_on))
                ui.button(
                    "Relax (servos off)",
                    on_click=relax,
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
            locked_controls.append(up_down)
            ui.label(f"Up / down ({proto.HEAD_UP_DOWN_MIN}–{proto.HEAD_UP_DOWN_MAX}, centre 90)")
            left_right = ui.slider(
                min=proto.HEAD_LEFT_RIGHT_MIN, max=proto.HEAD_LEFT_RIGHT_MAX, value=proto.HEAD_CENTER
            ).props("label")
            locked_controls.append(left_right)
            ui.label(f"Left / right ({proto.HEAD_LEFT_RIGHT_MIN}–{proto.HEAD_LEFT_RIGHT_MAX}, centre 90)")

            def apply_head() -> None:
                if not require_unlocked():
                    return
                runlog.record_command(proto.cmd_head_up_down(int(up_down.value)))
                runlog.record_command(proto.cmd_head_left_right(int(left_right.value)))
                safe_send(lambda: active().head_up_down(int(up_down.value)))
                safe_send(lambda: active().head_left_right(int(left_right.value)))

            def center_head() -> None:
                if not require_unlocked():
                    return
                up_down.set_value(proto.HEAD_CENTER)
                left_right.set_value(proto.HEAD_CENTER)
                runlog.record_command(proto.cmd_head_up_down(proto.HEAD_CENTER))
                runlog.record_command(proto.cmd_head_left_right(proto.HEAD_CENTER))
                safe_send(lambda: active().head_center())

            with ui.row().classes("gap-2"):
                locked_controls.append(ui.button("Apply head", on_click=apply_head))
                locked_controls.append(ui.button("Centre head", on_click=center_head))

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
                    finish_run(f"connection lost: {reason}", note=take_note())
                    reset_checklist()
                    set_status(f"Connection lost — press Connect to retry ({reason})")
                    ui.notify(f"Connection to robot lost: {reason}", type="negative")
                update_gate()

            ui.timer(0.2, refresh)
            ui.timer(POWER_POLL_SECONDS, request_power_quietly)

    with ui.expansion("Test log", icon="receipt_long").classes("w-full"):
        ui.label(f"Saved on this computer: {runlog.path}").classes("text-caption font-mono")
        note_input = ui.input("Result or note (saved with the next log entry)").classes("w-full")

        def save_note() -> None:
            text = take_note()
            if not text:
                ui.notify("Type a note first.", type="warning")
                return
            finish_run("note", note=text)
            show_log()
            ui.notify("Saved to the test log.", type="positive")

        def show_log() -> None:
            rows = []
            for index, entry in enumerate(reversed(runlog.read_entries(limit=50))):
                row = summarize(entry)
                row["id"] = str(index)
                rows.append(row)
            log_table.rows = rows
            log_table.update()

        with ui.row().classes("gap-2"):
            ui.button("Save note", on_click=save_note)
            ui.button("Show latest entries", on_click=show_log)
            ui.button(
                "Download log file",
                on_click=lambda: (runlog.ensure_exists(), ui.download("/test-log.jsonl", "test-log.jsonl")),
            )
        columns = [
            {"name": name, "label": label, "field": name, "align": "left"}
            for name, label in (
                ("time", "When"),
                ("mode", "Mode"),
                ("ran", "What ran"),
                ("battery", "Battery"),
                ("result", "Result"),
                ("note", "Note"),
            )
        ]
        log_table = ui.table(columns=columns, rows=[], row_key="id").classes("w-full")

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

    update_gate()  # start with the walk and move controls locked

    # Safety: if a browser tab closes, stop the robot walking.
    app.on_disconnect(on_browser_closed)

    def on_shutdown() -> None:
        try:
            finish_run("app closed")
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
