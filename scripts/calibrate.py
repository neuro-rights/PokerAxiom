"""
Unified Calibration Tool - Single tool for all calibration needs.

Usage:
    python scripts/calibrate.py

All regions are visible on a single canvas with color-coded overlays:
- Red: Parent regions (hero_cards, board, pot, actions)
- Blue: Card slots
- Cyan: Stacks
- Orange: Bets
- Green: Buttons
- Pink: Card backs
- Yellow: Fold pixel

Keyboard shortcuts:
- H/B/T/A: Select parent regions
- L/R: Select hero left/right card
- 1-5: Select board cards (when in card slot mode)
- 1-9: Select stack
- Shift+1-9: Select bet
- Ctrl+1-9: Select button
- Alt+2-9: Select card back
- F: Select fold pixel
- Arrow keys: Nudge (Shift for 5px)
- N/P: Next/Previous sample
- S: Save
- Escape: Deselect
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibration.unified_calibrator import main

if __name__ == "__main__":
    main()
