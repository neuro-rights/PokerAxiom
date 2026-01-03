#!/usr/bin/env python
"""Run fold button pixel picker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.pixel_picker import main

if __name__ == "__main__":
    main()
