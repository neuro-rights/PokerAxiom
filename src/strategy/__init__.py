"""
Strategy module for 2NL 10-max hybrid GTO + exploitative poker strategy.

Provides position calculation, hand evaluation, and action recommendations
using a balanced approach: GTO baseline with 2NL population exploits.

Key modules:
- spr_strategy: SPR-based commitment decisions
- board_analysis: Enhanced board texture analysis
- mdf: Minimum Defense Frequency calculations
- blockers: Blocker analysis for bluff selection
- dynamic_ranges: Stack depth adjusted ranges
- street_planning: Multi-street planning
- gto_baseline: GTO baselines with 2NL exploits
"""

from .actions import Action, ActionType
from .bet_sizing import (
    BetRecommendation,
    BetSizing,
    get_cbet_sizing,
    get_geometric_sizing,
    get_postflop_bet_recommendation,
    get_preflop_raise_recommendation,
    get_value_bet_sizing,
)
from .blockers import BlockerAnalysis, analyze_blockers
from .board_analysis import (
    BoardAnalysis,
    FlushPotential,
    StraightPotential,
    analyze_flop,
    is_safe_board_for_thin_value,
    is_safe_river_for_thin_value,
)
from .dynamic_ranges import StackDepth, get_adjusted_opening_range
from .game_state import ActionContext, GameState, Street
from .gto_baseline import GTOBaseline, apply_2nl_exploits, get_exploit_summary
from .hand_evaluator import (
    Draw,
    HandStrength,
    PreflopCategory,
    categorize_preflop,
    detect_draws,
    evaluate_made_hand,
)
from .mdf import MDFAnalysis, calculate_mdf, should_defend
from .positions import Position, get_hero_position, is_blind, is_late_position

# New hybrid strategy modules
from .spr_strategy import SPRCategory, SPRStrategy, get_spr_strategy
from .strategy_engine import StrategyEngine
from .street_planning import HandPlan, create_hand_plan, geometric_sizing

# Strategy version tracking for game history analysis correlation
# See CHANGELOG.md for detailed changes
STRATEGY_VERSION = "2.1.0"
STRATEGY_DATE = "2026-01-03T13:07:55Z"

__all__ = [
    # Core
    "Position",
    "get_hero_position",
    "is_late_position",
    "is_blind",
    "PreflopCategory",
    "HandStrength",
    "Draw",
    "categorize_preflop",
    "evaluate_made_hand",
    "detect_draws",
    "Action",
    "ActionType",
    "ActionContext",
    "GameState",
    "Street",
    "StrategyEngine",
    # SPR Strategy
    "SPRCategory",
    "SPRStrategy",
    "get_spr_strategy",
    # Board Analysis
    "BoardAnalysis",
    "analyze_flop",
    "FlushPotential",
    "StraightPotential",
    "is_safe_board_for_thin_value",
    "is_safe_river_for_thin_value",
    # Version Tracking
    "STRATEGY_VERSION",
    "STRATEGY_DATE",
    # MDF
    "MDFAnalysis",
    "calculate_mdf",
    "should_defend",
    # Blockers
    "BlockerAnalysis",
    "analyze_blockers",
    # Dynamic Ranges
    "StackDepth",
    "get_adjusted_opening_range",
    # Street Planning
    "HandPlan",
    "create_hand_plan",
    "geometric_sizing",
    # GTO Baseline
    "GTOBaseline",
    "apply_2nl_exploits",
    "get_exploit_summary",
    # Bet Sizing
    "BetSizing",
    "BetRecommendation",
    "get_preflop_raise_recommendation",
    "get_postflop_bet_recommendation",
    "get_cbet_sizing",
    "get_value_bet_sizing",
    "get_geometric_sizing",
]
