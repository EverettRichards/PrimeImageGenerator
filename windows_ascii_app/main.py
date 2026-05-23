from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# When running as a PyInstaller one-file executable the runtime imports come
# from the bundled archive. Modifying sys.path in that case can break imports
# (the package is already embedded). Only add the repository root to sys.path
# when running in a normal (non-frozen) development environment.
if not getattr(sys, "frozen", False):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from shared_ascii_app.gui import launch_app


if __name__ == "__main__":
    launch_app("VADIM ASCII Generator - Windows")
