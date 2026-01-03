#!/usr/bin/env python
"""Extract card images from samples using calibrated slots."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.card_extractor import main

if __name__ == "__main__":
    main()
