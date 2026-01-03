#!/usr/bin/env python
"""
Run the Strategy Overlay for poker tables.

This overlay provides real-time decision recommendations based on
the proven 2NL 9-max TAG strategy.

Usage:
    python scripts/run_strategy.py

Features:
    - Position detection from dealer button
    - Hand categorization (Premium, Strong, Playable, Marginal, Weak)
    - Preflop opening ranges by position
    - 3-bet and calling ranges
    - Postflop c-bet decisions
    - Check-raise recommendations
    - Pot odds and equity estimates
    - Color-coded action recommendations

Controls:
    Ctrl+C - Stop the overlay
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.capture.strategy_overlay import main  # noqa: E402

if __name__ == "__main__":
    print("=" * 50)
    print("  2NL 9-Max Strategy Overlay")
    print("=" * 50)
    print()
    print("Strategy: Tight-Aggressive (TAG) Exploitative")
    print()
    print("Legend:")
    print("  Position colors:")
    print("    Green  = Late (CO, BTN) - Wide range")
    print("    Yellow = Middle (MP) - Moderate range")
    print("    Red    = Early (UTG) - Tight range")
    print("    Blue   = Blinds (SB, BB) - Defense")
    print()
    print("  Action colors:")
    print("    Green  = RAISE/BET (aggressive)")
    print("    Blue   = CALL (continue)")
    print("    Red    = FOLD (release)")
    print("    Gray   = CHECK (passive)")
    print()
    print("Starting overlay...")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
