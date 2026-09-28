"""Backward-compatible launcher: `python main.py` still works.

The real entry point is the installed package (`fall-detector` or
`python -m fall_detector`). This file only adds `src/` to the import path
so the project also runs without `pip install -e .`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fall_detector.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
