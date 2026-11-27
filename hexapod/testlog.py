"""A simple test log: one JSON object per line in a local file ("JSON lines").

Each entry records the date and time, what ran (commands and mode), the battery
voltages and a short result / note. Open the file in any text editor, or use the
Test log section of the app.

Default location: ``~/.big-hexapod-gui/test-log.jsonl``
(change it with the ``HEXAPOD_TEST_LOG`` environment variable).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MAX_COMMANDS_PER_ENTRY = 100


def default_path() -> Path:
    override = os.environ.get("HEXAPOD_TEST_LOG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".big-hexapod-gui" / "test-log.jsonl"


def _now() -> datetime:
    return datetime.now().astimezone()


class RunLog:
    """Collects the commands of a run, then writes one entry when it ends."""

    def __init__(
        self,
        path: Optional[Path] = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.path = Path(path) if path is not None else default_path()
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: List[str] = []

    # ---- recording -------------------------------------------------------

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def record_command(self, command: str) -> None:
        """Remember a command that was sent (repeats in a row are kept once)."""
        text = command.strip()
        if not text:
            return
        with self._lock:
            if self._pending and self._pending[-1] == text:
                return
            if len(self._pending) < MAX_COMMANDS_PER_ENTRY:
                self._pending.append(text)

    def finish(
        self,
        result: str,
        *,
        mode: str,
        gait_mode: Optional[int] = None,
        battery: Optional[Tuple[float, float]] = None,
        note: str = "",
    ) -> Optional[Dict[str, object]]:
        """Write an entry for the pending run. Returns it, or None if there was
        nothing to log (no commands and no note)."""
        note = note.strip()
        with self._lock:
            commands = self._pending
            self._pending = []
        if not commands and not note:
            return None
        entry: Dict[str, object] = {
            "time": self._clock().isoformat(timespec="seconds"),
            "mode": mode,  # "robot" or "practice"
            "gait_mode": gait_mode,
            "commands": commands,
            "battery": (
                {"pack1": battery[0], "pack2": battery[1]} if battery else None
            ),
            "result": result.strip(),
            "note": note,
        }
        self.append(entry)
        return entry

    # ---- the file --------------------------------------------------------

    def ensure_exists(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        return self.path

    def append(self, entry: Dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read_entries(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        """Entries oldest-first. Unreadable lines are skipped, never fatal."""
        if not self.path.exists():
            return []
        entries: List[Dict[str, object]] = []
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
        return entries[-limit:] if limit else entries


def _shorten(text: str, width: int = 90) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def summarize(entry: Dict[str, object]) -> Dict[str, str]:
    """Short text fields for showing an entry in a table."""
    commands = entry.get("commands") or []
    battery = entry.get("battery") or {}
    if isinstance(battery, dict) and battery:
        volts = f"{battery.get('pack1', '?')} / {battery.get('pack2', '?')} V"
    else:
        volts = "—"
    return {
        "time": str(entry.get("time", "")).replace("T", " "),
        "mode": str(entry.get("mode", "")),
        "ran": _shorten(", ".join(str(c) for c in commands)) if commands else "—",
        "battery": volts,
        "result": str(entry.get("result", "")),
        "note": str(entry.get("note", "")),
    }
