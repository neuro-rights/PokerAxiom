#!/usr/bin/env python
"""Verify model predictions on card samples."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.card_verifier import main

if __name__ == "__main__":
    main()
