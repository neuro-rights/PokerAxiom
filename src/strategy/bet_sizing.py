"""
Bet sizing module - Maps strategy recommendations to available buttons.

Available buttons: 1, 2, 3, 4 (smallest to largest)
- Button 1: 33% pot / 2bb
- Button 2: 66% pot / 3bb (standard)
- Button 3: 80% pot / 4bb
- Button 4: 100% pot / pot

This module ensures all recommendations map to clickable buttons.
"""

from dataclasses import dataclass
from enum import Enum

# Big blind size for 2NL
BB = 0.02


class BetSizing(Enum):
    """Available bet sizes mapped to buttons 1-4."""

    SMALL = "1"  # 33% / 2bb
    STANDARD = "2"  # 66% / 3bb
    LARGE = "3"  # 80% / 4bb
    POT = "4"  # 100% / pot


# Numeric values for sizing
PREFLOP_BB_VALUES = {
    BetSizing.SMALL: 2,
    BetSizing.STANDARD: 3,
    BetSizing.LARGE: 4,
    BetSizing.POT: 0,  # Pot calculated dynamically
}

POSTFLOP_POT_FRACTIONS = {
    BetSizing.SMALL: 0.33,
    BetSizing.STANDARD: 0.66,
    BetSizing.LARGE: 0.80,
    BetSizing.POT: 1.00,
}


@dataclass
class BetRecommendation:
    """
    A bet recommendation with button info.

    Attributes:
        amount: Dollar amount of the bet
        button: Which button to click ("1", "2", "3", "4")
        sizing_type: The sizing enum value
        reasoning: Why this size
    """

    amount: float
    button: str
    sizing_type: BetSizing
    reasoning: str


def snap_to_preflop_size(
    target_bb: float,
    pot_size_bb: float | None = None,
) -> tuple[BetSizing, str]:
    """
    Snap a target BB amount to the nearest available preflop button.

    Args:
        target_bb: Target raise size in big blinds
        pot_size_bb: Current pot in BBs (for pot-size button)

    Returns:
        Tuple of (BetSizing enum, reasoning)
    """
    # If target is very large (5bb+), use pot (button 4)
    if target_bb >= 5:
        return BetSizing.POT, "pot for large sizing"

    # Find nearest available size
    available = [2, 3, 4]
    nearest = min(available, key=lambda x: abs(x - target_bb))

    if nearest == 2:
        return BetSizing.SMALL, "2bb minraise"
    elif nearest == 3:
        return BetSizing.STANDARD, "3bb standard"
    else:
        return BetSizing.LARGE, "4bb value sizing"


def snap_to_postflop_size(target_pct: float) -> tuple[BetSizing, str]:
    """
    Snap a target pot percentage to the nearest available postflop button.

    Args:
        target_pct: Target bet as fraction of pot (0.33 = 33%)

    Returns:
        Tuple of (BetSizing enum, reasoning)
    """
    # Map target to available sizes
    # Thresholds: <50% -> 1, 50-73% -> 2, 73-90% -> 3, >90% -> 4

    if target_pct <= 0.50:
        return BetSizing.SMALL, "small sizing"
    elif target_pct <= 0.73:
        return BetSizing.STANDARD, "standard sizing"
    elif target_pct <= 0.90:
        return BetSizing.LARGE, "large sizing"
    else:
        return BetSizing.POT, "pot-size bet"


def get_preflop_raise_recommendation(
    limper_count: int = 0,
    vs_fish: bool = False,
    has_premium: bool = False,
    is_3bet: bool = False,
    open_amount_bb: float = 0,
    in_position: bool = True,
) -> BetRecommendation:
    """
    Get preflop raise recommendation mapped to available button (1-4).

    Strategy:
    - Standard open: 3bb -> button 2
    - With limpers: 4bb -> button 3, pot -> button 4
    - Premium vs fish: 4bb -> button 3
    - 3-bet IP: 3x open -> nearest button
    - 3-bet OOP: 4x open -> nearest button

    Args:
        limper_count: Number of limpers
        vs_fish: Targeting a fish
        has_premium: Holding premium hand (AA-TT, AK-AQ)
        is_3bet: Whether this is a 3-bet
        open_amount_bb: Original open size in BBs (for 3-bets)
        in_position: Whether we're in position

    Returns:
        BetRecommendation with button to click (1-4)
    """
    if is_3bet:
        # 3-bet sizing
        multiplier = 3.0 if in_position else 4.0
        target_bb = open_amount_bb * multiplier

        # 3-bets are typically larger, often use pot (button 4)
        if target_bb >= 10:
            return BetRecommendation(
                amount=0,  # Will be calculated from pot
                button="4",
                sizing_type=BetSizing.POT,
                reasoning=f"3-bet pot ({'IP' if in_position else 'OOP'})",
            )

        sizing, reason = snap_to_preflop_size(target_bb)
        bb_value = PREFLOP_BB_VALUES.get(sizing, 4)
        return BetRecommendation(
            amount=bb_value * BB,
            button=sizing.value,
            sizing_type=sizing,
            reasoning=f"3-bet {reason}",
        )

    # Open raise sizing
    if limper_count >= 2:
        # With 2+ limpers, use pot (button 4)
        return BetRecommendation(
            amount=0,
            button="4",
            sizing_type=BetSizing.POT,
            reasoning=f"pot iso vs {limper_count} limpers",
        )

    if limper_count == 1:
        # 3bb + 1 limper = 4bb (button 3)
        return BetRecommendation(
            amount=4 * BB,
            button="3",
            sizing_type=BetSizing.LARGE,
            reasoning="4bb iso vs limper",
        )

    if vs_fish and has_premium:
        # Size up vs fish with premium (button 3)
        return BetRecommendation(
            amount=4 * BB,
            button="3",
            sizing_type=BetSizing.LARGE,
            reasoning="4bb value vs fish",
        )

    # Standard open: 3bb (button 2)
    return BetRecommendation(
        amount=3 * BB,
        button="2",
        sizing_type=BetSizing.STANDARD,
        reasoning="3bb standard open",
    )


def get_postflop_bet_recommendation(
    pot: float,
    target_pct: float,
    context: str = "",
) -> BetRecommendation:
    """
    Get postflop bet recommendation mapped to available button.

    Args:
        pot: Current pot size in dollars
        target_pct: Target bet as fraction of pot
        context: Context for reasoning (e.g., "dry board c-bet")

    Returns:
        BetRecommendation with button to click
    """
    sizing, reason = snap_to_postflop_size(target_pct)
    pct_value = POSTFLOP_POT_FRACTIONS[sizing]
    amount = round(pot * pct_value, 2)

    full_reason = f"{reason}"
    if context:
        full_reason = f"{context} - {reason}"

    return BetRecommendation(
        amount=amount,
        button=sizing.value,
        sizing_type=sizing,
        reasoning=full_reason,
    )


# Strategy-specific sizing recommendations


def get_cbet_sizing(
    board_texture: str,  # 'dry', 'medium', 'wet'
    has_value: bool,
    multiway: bool,
) -> tuple[BetSizing, str]:
    """
    Get c-bet sizing based on board texture and situation.

    Strategy mapping:
    - Dry board: button 1 (high frequency, small size)
    - Medium board: button 2 (standard)
    - Wet board: button 3 (charge draws)
    - Multiway: Size up one level

    Args:
        board_texture: Board texture category
        has_value: Whether we have a made hand
        multiway: Whether facing multiple opponents

    Returns:
        Tuple of (BetSizing, reasoning)
    """
    base_sizings = {
        "dry": BetSizing.SMALL,
        "medium": BetSizing.STANDARD,
        "wet": BetSizing.LARGE,
    }

    base = base_sizings.get(board_texture, BetSizing.STANDARD)

    # Size up for multiway or strong value
    if multiway or (has_value and board_texture == "wet"):
        # Upgrade one level
        upgrades = {
            BetSizing.SMALL: BetSizing.STANDARD,
            BetSizing.STANDARD: BetSizing.LARGE,
            BetSizing.LARGE: BetSizing.POT,
            BetSizing.POT: BetSizing.POT,
        }
        base = upgrades[base]

    reasons = {
        BetSizing.SMALL: "small c-bet on dry",
        BetSizing.STANDARD: "standard c-bet",
        BetSizing.LARGE: "large sizing vs draws",
        BetSizing.POT: "pot-size for protection",
    }

    return base, reasons[base]


def get_value_bet_sizing(
    street: str,  # 'flop', 'turn', 'river'
    hand_strength: str,  # 'monster', 'strong', 'medium'
    action_board: bool = False,
) -> tuple[BetSizing, str]:
    """
    Get value bet sizing based on street and strength.

    Strategy:
    - Flop: button 2 standard value
    - Turn: button 2-3 continue value
    - River: button 3-4 extract max

    Args:
        street: Current street
        hand_strength: How strong our hand is
        action_board: Whether board completed draws (for river overbet)

    Returns:
        Tuple of (BetSizing, reasoning)
    """
    if street == "river":
        if action_board and hand_strength == "monster":
            # Overbet action rivers - 2NL can't fold made hands
            return BetSizing.POT, "pot on action river (they can't fold)"
        elif hand_strength in ("monster", "strong"):
            return BetSizing.LARGE, "thick value river"
        else:
            return BetSizing.STANDARD, "thin value river"

    if street == "turn":
        if hand_strength == "monster":
            return BetSizing.LARGE, "size up turn with monster"
        return BetSizing.STANDARD, "standard turn bet"

    # Flop
    if hand_strength == "monster":
        return BetSizing.LARGE, "build pot with monster"
    return BetSizing.STANDARD, "standard value flop"


def get_geometric_sizing(
    pot: float,
    effective_stack: float,
    streets_remaining: int,
) -> list[tuple[BetSizing, float]]:
    """
    Calculate geometric bet sizes snapped to available buttons (1-4).

    Args:
        pot: Current pot size
        effective_stack: Effective stack remaining
        streets_remaining: Streets left (1-3)

    Returns:
        List of (BetSizing, dollar_amount) for each street
    """
    if streets_remaining <= 0 or effective_stack <= 0:
        return []

    # Calculate geometric fraction
    target_pot = pot + effective_stack * 2
    multiplier = (target_pot / pot) ** (1 / streets_remaining)
    bet_fraction = (multiplier - 1) / 2
    bet_fraction = min(bet_fraction, 1.5)
    bet_fraction = max(bet_fraction, 0.25)

    # Generate bets and snap to buttons
    result = []
    current_pot = pot
    remaining_stack = effective_stack

    for _ in range(streets_remaining):
        # Snap to available size
        sizing, _ = snap_to_postflop_size(bet_fraction)
        pct = POSTFLOP_POT_FRACTIONS[sizing]

        bet = current_pot * pct
        bet = min(bet, remaining_stack)

        result.append((sizing, round(bet, 2)))

        current_pot = current_pot + bet * 2
        remaining_stack -= bet

    return result


def format_sizing_display(
    action_type: str,  # 'BET', 'RAISE'
    amount: float,
    button: str,
) -> str:
    """
    Format sizing for overlay display.

    Args:
        action_type: BET or RAISE
        amount: Dollar amount
        button: Button label ("1", "2", "3", "4")

    Returns:
        Formatted string like "BET $0.12 [2]"
    """
    return f"{action_type} ${amount:.2f} [{button}]"
