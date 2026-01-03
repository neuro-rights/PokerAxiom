"""
Dynamic range adjustments based on stack depth.

Stack depth significantly affects which hands are profitable to play:
- Short stacks (15-30bb): Value broadway hands, avoid speculative hands
- Standard (50-100bb): Baseline ranges apply
- Deep stacks (100bb+): Speculative hands gain value from implied odds

Key principles:
- Short stack: High card value matters, no implied odds for draws
- Deep stack: Suited connectors, small pairs gain value (set mining, straights)
"""

from dataclasses import dataclass
from enum import Enum

from .positions import Position
from .ranges import (
    get_opening_range,
)


class StackDepth(Enum):
    """Stack depth categories for range adjustments."""

    PUSH_FOLD = "push_fold"  # <15 BB - Push/fold territory
    SHORT = "short"  # 15-30 BB - Short stack play
    MEDIUM = "medium"  # 30-50 BB - Medium stack
    STANDARD = "standard"  # 50-100 BB - Standard cash game
    DEEP = "deep"  # 100-150 BB - Deep stack
    ULTRA_DEEP = "ultra_deep"  # 150+ BB - Very deep


@dataclass
class DynamicRange:
    """
    Stack-adjusted opening range.

    Shows the base range and adjustments made for stack depth.
    """

    base_range: set[str]  # Standard 100bb range
    adjusted_range: set[str]  # Stack-adjusted range
    hands_added: set[str]  # Hands added for this depth
    hands_removed: set[str]  # Hands removed for this depth
    adjustment_rationale: str  # Why adjustments were made


# Hands to ADD when deep stacked (implied odds value)
DEEP_STACK_ADDS = {
    # Small pairs for set mining
    "22",
    "33",
    "44",
    "55",
    "66",
    # Suited connectors (straight/flush potential)
    "54s",
    "65s",
    "76s",
    "87s",
    "98s",
    "T9s",
    # Suited gappers
    "53s",
    "64s",
    "75s",
    "86s",
    "97s",
    "T8s",
    # Suited aces (nut flush potential)
    "A2s",
    "A3s",
    "A4s",
    "A5s",
    "A6s",
    "A7s",
    "A8s",
    "A9s",
}

# Hands to REMOVE when short stacked (no implied odds)
SHORT_STACK_REMOVES = {
    # Small pairs don't set mine well
    "22",
    "33",
    "44",
    "55",
    # Low suited connectors
    "54s",
    "65s",
    "53s",
    "64s",
    # Weak suited gappers
    "75s",
    "86s",
    "97s",
    # Weak suited aces
    "A2s",
    "A3s",
    "A4s",
}

# Hands that are STRONGER short stacked (high card value)
SHORT_STACK_ADDS = {
    # Broadway hands play well short
    "AJo",
    "ATo",
    "KQo",
    "KJo",
    "QJo",
}

# Push/fold range (very short stacked, ~15bb)
# Based on push/fold charts - wider in late position
PUSH_FOLD_RANGES = {
    Position.UTG: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "ATs",
        "KQs",
    },
    Position.UTG1: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "KQs",
        "KQo",
        "KJs",
    },
    Position.UTG2: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "KQs",
        "KQo",
        "KJs",
        "KTs",
        "QJs",
    },
    Position.MP: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "44",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "A8s",
        "KQs",
        "KQo",
        "KJs",
        "KJo",
        "KTs",
        "QJs",
        "QTs",
        "JTs",
    },
    Position.MP1: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "44",
        "33",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "A8s",
        "A7s",
        "A9o",
        "KQs",
        "KQo",
        "KJs",
        "KJo",
        "KTs",
        "K9s",
        "QJs",
        "QTs",
        "JTs",
        "T9s",
    },
    Position.CO: {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "44",
        "33",
        "22",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A9o",
        "A8o",
        "A7o",
        "KQs",
        "KQo",
        "KJs",
        "KJo",
        "KTs",
        "KTo",
        "K9s",
        "K8s",
        "QJs",
        "QJo",
        "QTs",
        "Q9s",
        "JTs",
        "J9s",
        "T9s",
        "98s",
    },
    Position.BTN: {
        # Very wide - almost any two
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "44",
        "33",
        "22",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "A9o",
        "A8o",
        "A7o",
        "A6o",
        "A5o",
        "A4o",
        "A3o",
        "A2o",
        "KQs",
        "KQo",
        "KJs",
        "KJo",
        "KTs",
        "KTo",
        "K9s",
        "K9o",
        "K8s",
        "K7s",
        "K6s",
        "K5s",
        "K4s",
        "K3s",
        "K2s",
        "QJs",
        "QJo",
        "QTs",
        "QTo",
        "Q9s",
        "Q8s",
        "Q7s",
        "Q6s",
        "JTs",
        "JTo",
        "J9s",
        "J8s",
        "J7s",
        "T9s",
        "T8s",
        "T7s",
        "98s",
        "97s",
        "87s",
        "76s",
        "65s",
        "54s",
    },
    Position.SB: {
        # Wide vs BB only
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "55",
        "44",
        "33",
        "22",
        "AKs",
        "AKo",
        "AQs",
        "AQo",
        "AJs",
        "AJo",
        "ATs",
        "ATo",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "A9o",
        "A8o",
        "A7o",
        "A6o",
        "A5o",
        "KQs",
        "KQo",
        "KJs",
        "KJo",
        "KTs",
        "KTo",
        "K9s",
        "K8s",
        "K7s",
        "K6s",
        "K5s",
        "QJs",
        "QJo",
        "QTs",
        "Q9s",
        "Q8s",
        "JTs",
        "J9s",
        "J8s",
        "T9s",
        "T8s",
        "98s",
        "87s",
        "76s",
        "65s",
    },
    Position.BB: set(),  # BB doesn't open
}


def get_stack_depth_category(effective_stack_bb: float) -> StackDepth:
    """
    Categorize effective stack into strategic zones.

    Args:
        effective_stack_bb: Effective stack in big blinds

    Returns:
        StackDepth category
    """
    if effective_stack_bb < 15:
        return StackDepth.PUSH_FOLD
    elif effective_stack_bb < 30:
        return StackDepth.SHORT
    elif effective_stack_bb < 50:
        return StackDepth.MEDIUM
    elif effective_stack_bb < 100:
        return StackDepth.STANDARD
    elif effective_stack_bb < 150:
        return StackDepth.DEEP
    else:
        return StackDepth.ULTRA_DEEP


def get_adjusted_opening_range(
    position: Position,
    effective_stack_bb: float,
) -> DynamicRange:
    """
    Get stack-adjusted opening range for a position.

    Args:
        position: Position at the table
        effective_stack_bb: Effective stack in big blinds

    Returns:
        DynamicRange with adjusted range and rationale
    """
    stack_depth = get_stack_depth_category(effective_stack_bb)
    base_range = get_opening_range(position)

    # Push/fold mode
    if stack_depth == StackDepth.PUSH_FOLD:
        push_range = PUSH_FOLD_RANGES.get(position, set())
        return DynamicRange(
            base_range=base_range,
            adjusted_range=push_range,
            hands_added=push_range - base_range,
            hands_removed=base_range - push_range,
            adjustment_rationale=f"Push/fold mode at {effective_stack_bb:.0f}bb",
        )

    # Short stack adjustments
    if stack_depth == StackDepth.SHORT:
        adjusted = (base_range - SHORT_STACK_REMOVES) | (
            SHORT_STACK_ADDS & _get_position_viable_adds(position)
        )
        return DynamicRange(
            base_range=base_range,
            adjusted_range=adjusted,
            hands_added=adjusted - base_range,
            hands_removed=base_range - adjusted,
            adjustment_rationale=f"Short stack ({effective_stack_bb:.0f}bb): Remove speculative hands",
        )

    # Medium stack - slightly tighter than standard
    if stack_depth == StackDepth.MEDIUM:
        # Remove just the worst speculative hands
        remove = {"22", "33", "54s", "53s"}
        adjusted = base_range - remove
        return DynamicRange(
            base_range=base_range,
            adjusted_range=adjusted,
            hands_added=set(),
            hands_removed=remove & base_range,
            adjustment_rationale=f"Medium stack ({effective_stack_bb:.0f}bb): Slightly tighter",
        )

    # Standard stack - use base ranges
    if stack_depth == StackDepth.STANDARD:
        return DynamicRange(
            base_range=base_range,
            adjusted_range=base_range,
            hands_added=set(),
            hands_removed=set(),
            adjustment_rationale=f"Standard stack ({effective_stack_bb:.0f}bb): Baseline ranges",
        )

    # Deep stack adjustments
    if stack_depth in (StackDepth.DEEP, StackDepth.ULTRA_DEEP):
        # Add speculative hands that aren't in base range
        position_adds = _get_deep_stack_adds(position)
        adjusted = base_range | position_adds
        return DynamicRange(
            base_range=base_range,
            adjusted_range=adjusted,
            hands_added=position_adds - base_range,
            hands_removed=set(),
            adjustment_rationale=f"Deep stack ({effective_stack_bb:.0f}bb): Add speculative hands",
        )

    # Default to base range
    return DynamicRange(
        base_range=base_range,
        adjusted_range=base_range,
        hands_added=set(),
        hands_removed=set(),
        adjustment_rationale="Default baseline ranges",
    )


def is_in_adjusted_opening_range(
    hand_notation: str,
    position: Position,
    effective_stack_bb: float,
) -> bool:
    """
    Check if hand is in stack-adjusted opening range.

    Args:
        hand_notation: Hand in standard notation (e.g., 'AKs')
        position: Position at table
        effective_stack_bb: Effective stack in big blinds

    Returns:
        True if hand should be opened at this stack depth
    """
    dynamic_range = get_adjusted_opening_range(position, effective_stack_bb)
    return hand_notation in dynamic_range.adjusted_range


def get_adjusted_3bet_range(
    effective_stack_bb: float,
    in_position: bool = True,
) -> set[str]:
    """
    Get stack-adjusted 3-bet range.

    Short stacks: Tighter, more value-heavy
    Deep stacks: Can add some speculative 3-bets

    Args:
        effective_stack_bb: Effective stack in big blinds
        in_position: Whether we're in position

    Returns:
        Set of hands to 3-bet
    """
    stack_depth = get_stack_depth_category(effective_stack_bb)

    # Base 3-bet range (value only at 2NL)
    base_3bet = {"AA", "KK", "QQ", "AKs", "AKo"}

    if stack_depth == StackDepth.PUSH_FOLD:
        # Very short: Just premium pairs
        return {"AA", "KK", "QQ", "AKs", "AKo"}

    if stack_depth == StackDepth.SHORT:
        # Short stack: Value only, tighter
        return {"AA", "KK", "QQ", "AKs", "AKo"}

    if stack_depth == StackDepth.MEDIUM:
        # Medium: Standard value
        return base_3bet

    if stack_depth in (StackDepth.STANDARD, StackDepth.DEEP, StackDepth.ULTRA_DEEP):
        # Standard/Deep: Can expand slightly
        if in_position:
            # IP: Can 3-bet JJ for value too
            return base_3bet | {"JJ"}
        return base_3bet

    return base_3bet


def get_adjusted_call_range(
    position: Position,
    effective_stack_bb: float,
    raiser_position: Position | None = None,
) -> set[str]:
    """
    Get stack-adjusted calling range vs opens.

    Args:
        position: Our position
        effective_stack_bb: Effective stack in big blinds
        raiser_position: Position of the raiser (for adjustments)

    Returns:
        Set of hands to call with
    """
    stack_depth = get_stack_depth_category(effective_stack_bb)

    # Base calling range (hands that don't 3-bet but can call)
    base_call = {
        "JJ",
        "TT",
        "99",
        "88",
        "77",  # Pairs for set mining
        "AQs",
        "AJs",
        "ATs",  # Suited broadways
        "KQs",
        "KJs",
        "QJs",  # Suited broadways
    }

    if stack_depth == StackDepth.PUSH_FOLD:
        # No calling, push or fold
        return set()

    if stack_depth == StackDepth.SHORT:
        # Short stack: Can't set mine profitably
        # Only call with hands that play well short
        return {"JJ", "TT", "AQs", "AQo", "AJs"}

    if stack_depth == StackDepth.MEDIUM:
        # Medium: Reduced set mining
        return {"JJ", "TT", "99", "AQs", "AJs", "ATs", "KQs"}

    if stack_depth in (StackDepth.STANDARD, StackDepth.DEEP, StackDepth.ULTRA_DEEP):
        # Deep: Full set mining range
        if stack_depth in (StackDepth.DEEP, StackDepth.ULTRA_DEEP):
            # Add small pairs and suited connectors for implied odds
            base_call |= {"66", "55", "44", "33", "22", "T9s", "98s", "87s"}
        return base_call

    return base_call


def should_set_mine_at_depth(
    effective_stack_bb: float,
    call_bb: float,
) -> tuple[bool, str]:
    """
    Determine if set mining is profitable at this stack depth.

    Rule of thumb: Need ~10:1 implied odds to set mine
    We hit sets ~12% (7.5:1 against)

    Args:
        effective_stack_bb: Effective stack in big blinds
        call_bb: Amount to call in big blinds

    Returns:
        Tuple of (profitable, reasoning)
    """
    if call_bb <= 0:
        return True, "Free to see flop"

    implied_ratio = effective_stack_bb / call_bb

    if implied_ratio >= 15:
        return True, f"Excellent implied odds ({implied_ratio:.0f}:1)"
    elif implied_ratio >= 10:
        return True, f"Good implied odds ({implied_ratio:.0f}:1)"
    elif implied_ratio >= 7:
        return False, f"Borderline implied odds ({implied_ratio:.0f}:1) - fold small pairs"
    else:
        return False, f"Poor implied odds ({implied_ratio:.0f}:1) - don't set mine"


# Helper functions


def _get_position_viable_adds(position: Position) -> set[str]:
    """Get hands that can be added in this position (SHORT stack adds that make sense)."""
    # Late positions can add more broadway hands
    late_positions = {Position.CO, Position.BTN, Position.SB}
    middle_positions = {Position.MP, Position.MP1}

    if position in late_positions:
        return SHORT_STACK_ADDS
    elif position in middle_positions:
        return {"AJo", "ATo", "KQo"}
    else:
        return {"AJo"}  # Only AJo in early position


def _get_deep_stack_adds(position: Position) -> set[str]:
    """Get speculative hands to add when deep stacked."""
    # More hands from late position
    late_positions = {Position.CO, Position.BTN, Position.SB}
    middle_positions = {Position.MP, Position.MP1}

    if position in late_positions:
        return DEEP_STACK_ADDS
    elif position in middle_positions:
        # Add some suited connectors and small pairs
        return {
            "22",
            "33",
            "44",
            "55",
            "66",
            "T9s",
            "98s",
            "87s",
            "76s",
            "A2s",
            "A3s",
            "A4s",
            "A5s",
        }
    else:
        # Early position: Only small pairs for set mining
        return {"22", "33", "44", "55", "66"}
