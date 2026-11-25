"""The "before you run it" checklist: pure logic, no UI and no network.

The app shows the two pack voltages reported by ``CMD_POWER`` and three tick
boxes. Walking and moving controls stay locked until:

* a battery reading has arrived,
* neither pack is at or below ``BLOCK_AT_OR_BELOW`` volts, and
* all three boxes are ticked (practice mode has no robot, so it skips the boxes).

Below ``WARN_BELOW`` volts the app warns but still allows walking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

WARN_BELOW = 7.0  # volts: warn, but walking is still allowed
BLOCK_AT_OR_BELOW = 6.6  # volts: walking is blocked

CHECK_LEGS_CLEAR = "legs_clear"
CHECK_LIFTED = "lifted"
CHECK_WATCHING = "watching"

CHECK_LABELS = {
    CHECK_LEGS_CLEAR: "The legs are clear (nothing in the way, no fingers near the joints)",
    CHECK_LIFTED: "The robot is lifted off the ground for first tests",
    CHECK_WATCHING: "Someone is watching the robot",
}

LEVEL_UNKNOWN = "unknown"
LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_BLOCKED = "blocked"

Voltages = Tuple[float, float]


def parse_power_reply(text: str) -> Optional[Voltages]:
    """Turn ``CMD_POWER#8.1#8.05`` into ``(8.1, 8.05)``; anything odd gives None."""
    parts = text.strip().split("#")
    if len(parts) != 3 or parts[0] != "CMD_POWER":
        return None
    try:
        first, second = float(parts[1]), float(parts[2])
    except ValueError:
        return None
    if not (math.isfinite(first) and math.isfinite(second)):
        return None
    return first, second


@dataclass
class BatteryStatus:
    level: str
    message: str


def battery_status(volts: Optional[Voltages]) -> BatteryStatus:
    """Judge the lower of the two packs."""
    if volts is None:
        return BatteryStatus(LEVEL_UNKNOWN, "No battery reading yet — press Battery.")
    low = min(volts)
    if low <= BLOCK_AT_OR_BELOW:
        return BatteryStatus(
            LEVEL_BLOCKED,
            f"Battery too low to walk ({low:.2f} V). Charge the pack first "
            f"(walking is blocked at {BLOCK_AT_OR_BELOW:.1f} V or below).",
        )
    if low < WARN_BELOW:
        return BatteryStatus(
            LEVEL_WARN,
            f"Battery is getting low ({low:.2f} V, under {WARN_BELOW:.1f} V). "
            "Keep runs short and charge soon.",
        )
    return BatteryStatus(LEVEL_OK, f"Battery looks fine ({low:.2f} V on the lower pack).")


@dataclass
class Gate:
    """Result of checking the checklist."""

    unlocked: bool
    battery: BatteryStatus
    missing: List[str] = field(default_factory=list)  # check keys not ticked
    reason: str = ""


def evaluate(
    volts: Optional[Voltages],
    ticks: dict,
    *,
    connected: bool = True,
    practice: bool = False,
) -> Gate:
    """Decide whether walk/move controls may be used right now."""
    battery = battery_status(volts)
    missing = [key for key in CHECK_LABELS if not ticks.get(key)]
    if not connected:
        return Gate(False, battery, missing, "Connect to the robot first.")
    if battery.level == LEVEL_UNKNOWN:
        return Gate(False, battery, missing, battery.message)
    if battery.level == LEVEL_BLOCKED:
        return Gate(False, battery, missing, battery.message)
    if missing and not practice:
        return Gate(False, battery, missing, "Tick all three boxes to unlock walking.")
    return Gate(True, battery, [] if practice else missing, "Unlocked.")
