"""
Opening range definitions for 2NL 9-max TAG strategy.

Based on position-based VPIP targets from the 2NL strategy guide:
- UTG: ~10% (77+, ATs+, KQs, AJo+)
- UTG+1: ~12% (66+, ATs+, KJs+, QJs, AJo+, KQo)
- UTG+2: ~14% (55+, A9s+, KTs+, QTs+, JTs, ATo+, KQo)
- MP (LJ): ~16% (44+, A8s+, K9s+, Q9s+, J9s+, T9s, ATo+, KJo+)
- MP+1 (HJ): ~18% (33+, A5s+, K8s+, Q9s+, J9s+, T8s+, 98s, A9o+, KTo+, QJo)
- CO: ~25% (22+, A2s+, K5s+, Q8s+, J8s+, T7s+, 97s+, 87s, 76s, A7o+, K9o+, QTo+, JTo)
- BTN: ~40-50% (All pairs, all suited aces, most suited kings, suited connectors 54s+)
- SB: ~30% (Tighter than BTN due to OOP)
- BB: Defend vs steals
"""

from .hand_evaluator import PreflopCategory
from .positions import Position

# Opening ranges by position
# Format: Set of hand notations (e.g., 'AA', 'AKs', 'AKo', 'T9s')

# UTG: ~10% - Premium hands (77+, ATs+, KQs, AJo+)
UTG_OPEN_RANGE: set[str] = {
    # Pairs 77+
    "AA",
    "KK",
    "QQ",
    "JJ",
    "TT",
    "99",
    "88",
    "77",
    # Suited broadways
    "AKs",
    "AQs",
    "AJs",
    "ATs",
    "KQs",
    # Offsuit broadways
    "AKo",
    "AQo",
    "AJo",
}

# UTG+1: ~12% - Add 66, KJs, QJs
UTG1_OPEN_RANGE: set[str] = UTG_OPEN_RANGE | {
    "66",
    "KJs",
    "QJs",
    "KQo",
}

# UTG+2: ~14% - Add 55, A9s, KTs, QTs, JTs, ATo
UTG2_OPEN_RANGE: set[str] = UTG1_OPEN_RANGE | {
    "55",
    "A9s",
    "KTs",
    "QTs",
    "JTs",
    "ATo",
}

# MP (LJ): ~16% - Add 44, A8s, K9s, Q9s, J9s, T9s, KJo
MP_OPEN_RANGE: set[str] = UTG2_OPEN_RANGE | {
    "44",
    "A8s",
    "K9s",
    "Q9s",
    "J9s",
    "T9s",
    "KJo",
}

# MP+1 (HJ): ~18% - Add 33, A5s-A7s, K8s, T8s, 98s, A9o, KTo, QJo
MP1_OPEN_RANGE: set[str] = MP_OPEN_RANGE | {
    "33",
    "A7s",
    "A6s",
    "A5s",
    "K8s",
    "T8s",
    "98s",
    "A9o",
    "KTo",
    "QJo",
}

# CO: ~25% - 22+, A2s+, K5s+, Q8s+, J8s+, T7s+, 97s+, 87s, 76s, A7o+, K9o+, QTo+, JTo
CO_OPEN_RANGE: set[str] = MP1_OPEN_RANGE | {
    "22",  # All remaining pairs
    "A4s",
    "A3s",
    "A2s",  # Remaining suited aces
    "K7s",
    "K6s",
    "K5s",  # Suited kings down to K5s
    "Q8s",  # Suited queens
    "J8s",  # Suited jacks
    "T7s",
    "97s",
    "87s",
    "76s",  # Suited connectors
    "A8o",
    "A7o",  # Offsuit aces
    "K9o",  # Offsuit kings
    "QTo",
    "JTo",  # Offsuit broadway connectors
}

# BTN: ~40-50% - All pairs, all suited aces, most suited kings, suited connectors down to 54s
BTN_OPEN_RANGE: set[str] = CO_OPEN_RANGE | {
    # Suited kings (remaining)
    "K4s",
    "K3s",
    "K2s",
    # Suited queens
    "Q7s",
    "Q6s",
    "Q5s",
    "Q4s",
    # Suited jacks
    "J7s",
    # Suited connectors/gappers
    "86s",
    "75s",
    "65s",
    "64s",
    "54s",
    "53s",
    # Offsuit broadways
    "A6o",
    "A5o",
    "A4o",
    "K8o",
    "Q9o",
    "J9o",
    "T9o",
    # Offsuit connectors
    "98o",
    "87o",
}

# SB: ~30% steal range (wider than CO, tighter than BTN due to OOP)
SB_STEAL_RANGE: set[str] = CO_OPEN_RANGE | {
    # Add more suited connectors
    "86s",
    "75s",
    "65s",
    "54s",
    # Suited queens/jacks
    "Q7s",
    "Q6s",
    "J7s",
    # More suited kings
    "K4s",
    "K3s",
    # Offsuit broadways
    "A6o",
    "A5o",
    "K8o",
    "Q9o",
    "J9o",
    "T9o",
}

# 3-bet range (for facing opens): QQ+, AK only at 2NL (value only)
THREEBET_RANGE: set[str] = {
    "AA",
    "KK",
    "QQ",
    "AKs",
    "AKo",
}

# 3-bet calling range (vs 3-bet when we opened): JJ, TT, AQs
# Note: QQ 4-bets or flats, AK is in 3-bet range, fold AQo to tight 3-bets
THREEBET_CALL_RANGE: set[str] = {
    "JJ",
    "TT",
    "AQs",
}

# 4-bet range: AA, KK only (unless opponent is a maniac)
FOURBET_RANGE: set[str] = {
    "AA",
    "KK",
}

# Defend BB vs steal (vs BTN/SB open): Wider
BB_DEFEND_VS_STEAL: set[str] = {
    # All pairs
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
    # Strong broadways
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
    "KTs",
    "QJs",
    "QTs",
    "JTs",
    # Suited connectors
    "T9s",
    "98s",
    "87s",
    "76s",
    "65s",
    # Suited aces
    "A9s",
    "A8s",
    "A7s",
    "A6s",
    "A5s",
    "A4s",
    "A3s",
    "A2s",
}

# Limp-raise range (when limpers in pot): Same as open but raise larger
LIMP_RAISE_RANGE: set[str] = MP_OPEN_RANGE  # Tighten up with limpers


def get_opening_range(position: Position) -> set[str]:
    """
    Get the opening range for a given position.

    Args:
        position: Position enum

    Returns:
        Set of hand notations that should be opened
    """
    ranges = {
        Position.UTG: UTG_OPEN_RANGE,
        Position.UTG1: UTG1_OPEN_RANGE,
        Position.UTG2: UTG2_OPEN_RANGE,
        Position.MP: MP_OPEN_RANGE,
        Position.MP1: MP1_OPEN_RANGE,
        Position.CO: CO_OPEN_RANGE,
        Position.BTN: BTN_OPEN_RANGE,
        Position.SB: SB_STEAL_RANGE,
        Position.BB: set(),  # BB doesn't open, only defends
    }
    return ranges.get(position, set())


def is_in_opening_range(hand_notation: str, position: Position) -> bool:
    """
    Check if a hand is in the opening range for a position.

    Args:
        hand_notation: Hand in standard notation (e.g., 'AKs', 'QQ')
        position: Position enum

    Returns:
        True if hand should be opened from this position
    """
    opening_range = get_opening_range(position)
    return hand_notation in opening_range


def is_in_3bet_range(hand_notation: str) -> bool:
    """
    Check if a hand is in the value 3-bet range.

    At 2NL, we only 3-bet for value with premium hands.

    Args:
        hand_notation: Hand in standard notation

    Returns:
        True if hand should 3-bet
    """
    return hand_notation in THREEBET_RANGE


def is_in_3bet_call_range(hand_notation: str) -> bool:
    """
    Check if a hand can call a 3-bet.

    Args:
        hand_notation: Hand in standard notation

    Returns:
        True if hand can profitably call a 3-bet
    """
    return hand_notation in THREEBET_CALL_RANGE


def is_in_4bet_range(hand_notation: str) -> bool:
    """
    Check if a hand should 4-bet (facing a 3-bet).

    Args:
        hand_notation: Hand in standard notation

    Returns:
        True if hand should 4-bet
    """
    return hand_notation in FOURBET_RANGE


def is_in_bb_defend_range(hand_notation: str) -> bool:
    """
    Check if BB should defend this hand vs a steal.

    Args:
        hand_notation: Hand in standard notation

    Returns:
        True if BB should defend
    """
    return hand_notation in BB_DEFEND_VS_STEAL


def get_range_percentage(position: Position) -> float:
    """
    Get the approximate VPIP percentage for a position.

    Args:
        position: Position enum

    Returns:
        Percentage as float (e.g., 0.12 for 12%)
    """
    percentages = {
        Position.UTG: 0.10,  # 10% per guide
        Position.UTG1: 0.12,  # 12% per guide
        Position.UTG2: 0.14,  # 14% per guide
        Position.MP: 0.16,  # 16% (LJ) per guide
        Position.MP1: 0.18,  # 18% (HJ) per guide
        Position.CO: 0.25,  # 25% per guide
        Position.BTN: 0.45,  # 40-50% per guide
        Position.SB: 0.30,  # 30% per guide
        Position.BB: 0.35,  # Defense frequency
    }
    return percentages.get(position, 0.10)


# Category to positions mapping (which categories open from which positions)
CATEGORY_POSITION_MAP: dict[PreflopCategory, set[Position]] = {
    PreflopCategory.PREMIUM: {
        Position.UTG,
        Position.UTG1,
        Position.UTG2,
        Position.MP,
        Position.MP1,
        Position.CO,
        Position.BTN,
        Position.SB,
    },
    PreflopCategory.STRONG: {
        Position.UTG,
        Position.UTG1,
        Position.UTG2,
        Position.MP,
        Position.MP1,
        Position.CO,
        Position.BTN,
        Position.SB,
    },
    PreflopCategory.PLAYABLE: {
        Position.MP,
        Position.MP1,
        Position.CO,
        Position.BTN,
        Position.SB,
    },
    PreflopCategory.MARGINAL: {
        Position.CO,
        Position.BTN,
        Position.SB,
    },
    PreflopCategory.WEAK: set(),  # Never open
}


def category_opens_from_position(category: PreflopCategory, position: Position) -> bool:
    """
    Check if a hand category should open from a position.

    Simplified logic using category-based decisions.

    Args:
        category: PreflopCategory of the hand
        position: Current position

    Returns:
        True if this category opens from this position
    """
    valid_positions = CATEGORY_POSITION_MAP.get(category, set())
    return position in valid_positions
