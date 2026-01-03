#!/usr/bin/env python
"""Train and test the rank classifier."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.rank_classifier import main

if __name__ == "__main__":
    main()
