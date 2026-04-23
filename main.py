#!/usr/bin/env python
"""
Main entry point for the 2NL 10-Max Strategy Overlay.

Runs the live poker overlay with real-time decision recommendations
based on the proven 2NL 10-max TAG exploitative strategy.

Usage:
    python main.py

Controls:
    Ctrl+C - Stop the overlay
"""

import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.capture.strategy_overlay import main  # noqa: E402


def run():
    """Run the live strategy overlay."""
    print("=" * 60)
    print("  2NL 10-Max Strategy Overlay - Live Decision Support")
    print("=" * 60)
    print()
    print("Strategy: Tight-Aggressive (TAG) Exploitative")
    print()
    print("Preflop Ranges:")
    print("  UTG: 10%  |  UTG+1: 12%  |  UTG+2: 14%")
    print("  MP:  16%  |  HJ:    18%  |  CO:    25%")
    print("  BTN: 45%  |  SB:    30%  |  BB:    Defend")
    print()
    print("Key Rules:")
    print("  - 3-bet for value: QQ+, AK only")
    print("  - 4-bet range: AA, KK only")
    print("  - C-bet sizing by texture (dry 35%, medium 55%, wet 70%)")
    print("  - Overbet nuts on action rivers (1.5-2x pot)")
    print("  - Fold to turn/river raises (they have it)")
    print()
    print("Position Colors:")
    print("  Green  = Late (CO, BTN) - Wide range")
    print("  Yellow = Middle (MP, HJ) - Moderate range")
    print("  Red    = Early (UTG) - Tight range")
    print("  Blue   = Blinds (SB, BB) - Defense")
    print()
    print("Action Colors:")
    print("  Green  = RAISE/BET (aggressive)")
    print("  Blue   = CALL (continue)")
    print("  Red    = FOLD (release)")
    print("  Gray   = CHECK (passive)")
    print()
    print("Starting overlay... Press Ctrl+C to stop.")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\nOverlay stopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
