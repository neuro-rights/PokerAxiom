# Strategy Changelog

All strategy modifications are logged here with timestamps.
Use these dates to filter game history analysis for evaluating changes.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v2.1.0] - 2026-01-03T13:07:55Z

### Added
- Thin value betting with second pair on safe rivers (no flush/straight/pair possible)
- Paired board c-betting with high frequency (80%+) and small sizing (33% pot)
- Larger bet sizing vs identified fish (80% pot, up from 50%)
- `is_safe_river_for_thin_value()` helper function in board_analysis.py
- `pair_rank` field in BoardAnalysis dataclass
- `STRATEGY_VERSION` and `STRATEGY_DATE` constants in __init__.py

### Changed
- River value betting now includes second pair on safe boards (was top pair+ only)
- C-bet frequency on high paired boards (TT+) increased to 80%+
- Fish sizing increased from 50% to 80% pot

### Strategy Rationale
Based on established micro stakes poker literature:
- "Crushing the Microstakes" by Nathan Williams: Thin value bet because they call with anything
- "Applications of No-Limit Hold'em" by Matthew Janda: Paired boards favor PFR range
- Core principle: ABC poker crushes 2NL - don't get fancy

---

## [v2.0.0] - 2026-01-03 (Previous session - not tracked in detail)

Previous fixes implemented but not tracked with timestamps:
- Monotone board c-betting (check underpairs without backdoor flush)
- Float prevention (require 8+ outs to continue without pair)
- River calling logic (overpair/top pair/bluffcatcher thresholds)
- Donk betting fix (check to aggressor in 3-bet pots)
