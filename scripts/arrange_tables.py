#!/usr/bin/env python
"""Resize and tile poker table windows to standard size."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.capture.window_manager import main

if __name__ == "__main__":
    main()
