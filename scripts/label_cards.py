#!/usr/bin/env python
"""Manual card labeling tool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.card_labeler import main

if __name__ == "__main__":
    main()
