"""
paths.py — single source of truth for where persistent data lives.

Every other module in this codebase used to independently compute
DATA_DIR as `Path(__file__).parent.parent / "data"`. That's correct
for normal `python app.py` execution, but breaks silently and
seriously when running as a PyInstaller --onefile executable:
`__file__` then resolves inside PyInstaller's temporary extraction
directory (sys._MEIPASS), which is deleted the moment the process
exits. Every write — portfolio trades, price history, recommendation
log — would appear to succeed, then vanish on the next run. This was
caught by actually running the built executable and diffing what got
written, not by inspection.

The fix: resolve the data directory relative to the actual executable
file's location when frozen (which persists across runs, since it's
the real .exe on disk, not a temp extraction), and relative to the
source tree otherwise. Every module that needs DATA_DIR should import
it from here instead of redefining it.
"""

import sys
from pathlib import Path


def get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        # sys.executable is the real, persistent .exe/binary on disk —
        # NOT the ephemeral PyInstaller extraction temp dir. Data next
        # to it survives process exit and future runs.
        base = Path(sys.executable).parent
    else:
        # Normal source execution: backend/services/paths.py -> backend/ -> data/
        base = Path(__file__).parent.parent

    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


DATA_DIR = get_data_dir()
