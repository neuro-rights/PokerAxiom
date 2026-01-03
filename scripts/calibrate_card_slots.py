#!/usr/bin/env python
"""Run card slot calibrator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.card_slot_calibrator import main

if __name__ == "__main__":
    main()
