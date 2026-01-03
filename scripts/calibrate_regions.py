#!/usr/bin/env python
"""Run region calibrator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.region_calibrator import main

if __name__ == "__main__":
    main()
