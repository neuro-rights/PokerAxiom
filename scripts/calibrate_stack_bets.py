#!/usr/bin/env python
"""Run stack/bet region calibrator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.stack_bet_calibrator import main

if __name__ == "__main__":
    main()
