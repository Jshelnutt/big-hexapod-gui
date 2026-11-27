#!/usr/bin/env python3
"""Install (or remove) the connection watchdog in Freenove's Code/Server folder.

UNTESTED ON THE ROBOT. Run it on the Pi:

    python3 install_watchdog.py                 # install
    python3 install_watchdog.py --remove        # undo
    python3 install_watchdog.py --dry-run       # show what would change

It copies connection_watchdog.py next to server.py and adds exactly two lines to
server.py (after saving a backup called server.py.before-watchdog). Nothing else
in Freenove's code is changed. Running it twice is safe.
"""

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_SERVER_DIR = (
    Path.home() / "Freenove_Big_Hexapod_Robot_Kit_for_Raspberry_Pi" / "Code" / "Server"
)
MODULE = "connection_watchdog.py"
BACKUP = "server.py.before-watchdog"
TAG = "  # added by big-hexapod-gui (connection watchdog)"
IMPORT_LINE = "from connection_watchdog import start_watchdog"
START_LINE = "start_watchdog(self.control_system)"
IMPORT_ANCHOR = "from camera import Camera"
START_ANCHOR = "self.control_system.condition_thread.start()"


def patch_source(text):
    """Return the patched server.py text. Raises ValueError if it cannot."""
    if IMPORT_LINE in text and START_LINE in text:
        return text  # already installed
    if IMPORT_LINE in text or START_LINE in text:
        raise ValueError("server.py is only half patched; restore it with --remove first")
    lines = text.split("\n")
    out = []
    did_import = did_start = False
    for line in lines:
        out.append(line)
        stripped = line.strip()
        if not did_import and stripped == IMPORT_ANCHOR:
            out.append(IMPORT_LINE + TAG)
            did_import = True
        elif not did_start and stripped == START_ANCHOR:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + START_LINE + TAG)
            did_start = True
    if not (did_import and did_start):
        raise ValueError(
            "could not find the expected lines in server.py "
            "(this Freenove version looks different). Nothing was changed."
        )
    return "\n".join(out)


def unpatch_source(text):
    return "\n".join(line for line in text.split("\n") if TAG not in line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("server_dir", nargs="?", type=Path, default=DEFAULT_SERVER_DIR,
                        help="Freenove Code/Server folder (default: %(default)s)")
    parser.add_argument("--remove", action="store_true", help="undo the install")
    parser.add_argument("--dry-run", action="store_true", help="change nothing, just report")
    args = parser.parse_args(argv)

    server_py = args.server_dir / "server.py"
    if not server_py.is_file():
        print("Cannot find %s - is this the Code/Server folder?" % server_py)
        return 1
    original = server_py.read_text(encoding="utf-8")

    try:
        new_text = unpatch_source(original) if args.remove else patch_source(original)
    except ValueError as exc:
        print("Stopped: %s" % exc)
        return 1

    if new_text == original and not args.remove:
        print("Already installed. Nothing to do.")
        return 0
    if args.dry_run:
        print("Dry run: server.py would be %s." % ("restored" if args.remove else "patched"))
        return 0

    if args.remove:
        server_py.write_text(new_text, encoding="utf-8")
        (args.server_dir / MODULE).unlink(missing_ok=True)
        print("Removed the watchdog. Restart the server (sudo python main.py -tn).")
        return 0

    backup = args.server_dir / BACKUP
    if not backup.exists():
        shutil.copy2(server_py, backup)
    shutil.copy2(Path(__file__).with_name(MODULE), args.server_dir / MODULE)
    server_py.write_text(new_text, encoding="utf-8")
    print("Installed. Backup of the original: %s" % backup)
    print("Restart the server (sudo python main.py -tn) and test with the robot LIFTED on a stand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
