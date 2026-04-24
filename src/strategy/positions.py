"""
Position calculation for 10-max poker tables.

Determines hero's position relative to the dealer button.
"""

from enum import Enum


class Position(Enum):
    """Poker table positions for 10-max."""

    UTG = "UTG"  # Under the gun (first to act preflop)
    UTG1 = "UTG+1"  # Second early position
    UTG2 = "UTG+2"  # Third early position
    MP = "MP"  # Middle position
    MP1 = "MP+1"  # Second middle position
    MP2 = "MP+2"  # Second middle position
    CO = "CO"  # Cutoff (one before button)
    BTN = "BTN"  # Button (dealer position)
    SB = "SB"  # Small blind
    BB = "BB"  # Big blind


# Position order for range comparisons (higher = later position = wider range)
POSITION_ORDER = {
    Position.UTG: 0,
    Position.UTG1: 1,
    Position.UTG2: 2,
    Position.MP: 3,
    Position.MP1: 4,
    Position.MP2: 5,
    Position.CO: 6,
    Position.BTN: 7,
    Position.SB: 8,  # SB acts first postflop but defends preflop
    Position.BB: 9,  # BB acts last preflop
}


def get_hero_position(dealer_seat: int, hero_seat: int = 1, num_players: int = 10) -> Position:
    """
    Calculate hero's position based on dealer button location.

    In 10-max:
    - Dealer (BTN) = dealer_seat
    - SB = dealer_seat + 1
    - BB = dealer_seat + 2
    - UTG = dealer_seat + 3
    - ... continuing around the table
    - CO = dealer_seat - 1

    Args:
        dealer_seat: Seat number with dealer button (1-10)
        hero_seat: Hero's seat number (default 1, bottom center)
        num_players: Number of seats at table (default 10)

    Returns:
        Position enum value
    """
    if not 1 <= dealer_seat <= num_players:
        return Position.UTG  # Default fallback

    # Calculate hero's offset from dealer (clockwise)
    # Offset 0 = BTN, 1 = SB, 2 = BB, 3 = UTG, etc.
    offset = (hero_seat - dealer_seat) % num_players

    # Map offset to position
    position_map = {
        0: Position.BTN,
        1: Position.SB,
        2: Position.BB,
        3: Position.UTG,
        4: Position.UTG1,
        5: Position.UTG2,
        6: Position.MP,
        7: Position.MP1,
        8: Position.MP2,
        9: Position.CO,
    }

    return position_map.get(offset, Position.UTG)


def position_order(position: Position) -> int:
    """
    Get numeric order for position comparison.

    Higher number = later position = typically wider range.

    Args:
        position: Position enum value

    Returns:
        Integer order (0-9)
    """
    return POSITION_ORDER.get(position, 0)


def is_late_position(position: Position) -> bool:
    """
    Check if position is considered late (CO or BTN).

    Late positions can profitably open wider ranges.

    Args:
        position: Position enum value

    Returns:
        True if CO or BTN
    """
    return position in (Position.CO, Position.BTN)


def is_middle_position(position: Position) -> bool:
    """
    Check if position is middle position.

    Args:
        position: Position enum value

    Returns:
        True if MP or MP+1
    """
    return position in (Position.MP, Position.MP1, Position.MP2)


def is_early_position(position: Position) -> bool:
    """
    Check if position is early (UTG, UTG+1, UTG+2).

    Early positions require tighter ranges.

    Args:
        position: Position enum value

    Returns:
        True if UTG, UTG+1, or UTG+2
    """
    return position in (Position.UTG, Position.UTG1, Position.UTG2)


def is_blind(position: Position) -> bool:
    """
    Check if position is a blind (SB or BB).

    Blinds have different strategies (defending vs opening).

    Args:
        position: Position enum value

    Returns:
        True if SB or BB
    """
    return position in (Position.SB, Position.BB)


def get_position_color(position: Position) -> str:
    """
    Get display color for position badge.

    Args:
        position: Position enum value

    Returns:
        Hex color code
    """
    if is_late_position(position):
        return "#55cc55"  # Green - favorable
    elif is_middle_position(position):
        return "#cccc55"  # Yellow - moderate
    elif is_early_position(position):
        return "#cc5555"  # Red - tight
    else:  # Blinds
        return "#5588cc"  # Blue - defensive
