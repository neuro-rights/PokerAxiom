"""
Action recommendations for poker strategy.

Defines action types, sizing calculations, and recommendation formatting.
All bet sizes are mapped to buttons 1-4 (smallest to largest).
"""

from dataclasses import dataclass
from enum import Enum

from .bet_sizing import (
    POSTFLOP_POT_FRACTIONS,
    BetSizing,
    get_preflop_raise_recommendation,
)


class ActionType(Enum):
    """Types of poker actions."""

    FOLD = "FOLD"
    CHECK = "CHECK"
    CALL = "CALL"
    BET = "BET"
    RAISE = "RAISE"
    ALLIN = "ALL-IN"


class BoardTexture(Enum):
    """Board texture categories for c-bet sizing decisions."""

    DRY = "dry"  # K72r, Q83r - 33% pot
    MEDIUM = "medium"  # Mixed boards - 66% pot
    WET = "wet"  # JT9ss, QJ8ss - 80% pot


# Display colors for action types
ACTION_COLORS = {
    ActionType.FOLD: "#cc5555",  # Red
    ActionType.CHECK: "#888888",  # Gray
    ActionType.CALL: "#5588cc",  # Blue
    ActionType.BET: "#55cc55",  # Green
    ActionType.RAISE: "#55cc55",  # Green
    ActionType.ALLIN: "#ffcc00",  # Gold
}


@dataclass
class Action:
    """
    Recommended poker action with sizing and reasoning.

    Attributes:
        action_type: The type of action (FOLD, CHECK, CALL, BET, RAISE)
        amount: Bet/raise amount in dollars (None for FOLD/CHECK)
        confidence: Confidence level 0.0-1.0
        reasoning: Brief explanation for the recommendation
        sizing_note: Optional note about bet sizing
        button: Which button to click ("1", "2", "3", "4")
    """

    action_type: ActionType
    amount: float | None = None
    confidence: float = 0.8
    reasoning: str = ""
    sizing_note: str = ""
    button: str = ""  # Button label for overlay (1-4)

    def get_display_text(self, street: str = "") -> str:
        """
        Get formatted display text for the action (without button).

        Args:
            street: Current street ('preflop', 'flop', 'turn', 'river')

        Returns:
            Formatted string like "RAISE $0.08" or "BET $0.12" (no button)
        """
        if self.amount and self.amount > 0:
            return f"{self.action_type.value} ${self.amount:.2f}"
        return self.action_type.value

    def get_button_display(self) -> str:
        """
        Get formatted button display text.

        Returns:
            Formatted string like "[2]" or "[4]", or "" if no button
        """
        if self.button:
            return f"[{self.button}]"
        return ""

    def get_color(self) -> str:
        """Get display color for this action type."""
        return ACTION_COLORS.get(self.action_type, "#888888")

    def is_aggressive(self) -> bool:
        """Check if this is an aggressive action (bet/raise)."""
        return self.action_type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN)

    def is_passive(self) -> bool:
        """Check if this is a passive action (check/call/fold)."""
        return self.action_type in (ActionType.FOLD, ActionType.CHECK, ActionType.CALL)


# Sizing constants (in big blinds)
BB = 0.02  # 2NL big blind


def calculate_open_raise(
    limper_count: int = 0, vs_fish: bool = False, has_value_hand: bool = False
) -> tuple[float, str]:
    """
    Calculate standard open raise sizing mapped to button 1-4.

    Strategy:
    - Standard open: 3bb -> button 2
    - With 1 limper: 4bb -> button 3
    - With 2+ limpers: pot -> button 4
    - Premium vs fish: 4bb -> button 3

    Args:
        limper_count: Number of limpers in pot
        vs_fish: True if targeting a fish at the table
        has_value_hand: True if holding a premium/strong hand

    Returns:
        Tuple of (raise_amount, button_label)
    """
    rec = get_preflop_raise_recommendation(
        limper_count=limper_count,
        vs_fish=vs_fish,
        has_premium=has_value_hand,
    )
    return rec.amount, rec.button


def calculate_3bet(open_amount: float, in_position: bool = True) -> tuple[float, str]:
    """
    Calculate 3-bet sizing mapped to button 1-4.

    Strategy:
    - IP: 3x the open -> nearest button
    - OOP: 4x the open -> nearest button or pot (button 4)

    Args:
        open_amount: Original raise amount
        in_position: True if we're in position

    Returns:
        Tuple of (3bet_amount, button_label)
    """
    open_bb = open_amount / BB
    rec = get_preflop_raise_recommendation(
        is_3bet=True,
        open_amount_bb=open_bb,
        in_position=in_position,
    )
    # For 3-bets, amount may need to be calculated if pot-sized
    if rec.amount == 0:  # Pot-sized
        return 0, "4"
    return rec.amount, rec.button


def calculate_cbet(pot: float, strength: str = "standard") -> tuple[float, str]:
    """
    Calculate continuation bet sizing mapped to button 1-4.

    Args:
        pot: Current pot size
        strength: 'small' (1), 'standard' (2), or 'large' (3)

    Returns:
        Tuple of (cbet_amount, button_label)
    """
    sizings = {
        "small": BetSizing.SMALL,
        "standard": BetSizing.STANDARD,
        "large": BetSizing.LARGE,
    }
    sizing = sizings.get(strength, BetSizing.STANDARD)
    pct = POSTFLOP_POT_FRACTIONS[sizing]
    return round(pot * pct, 2), sizing.value


def calculate_cbet_by_texture(
    pot: float, texture: "BoardTexture", vs_calling_station: bool = False
) -> tuple[float, str]:
    """
    Calculate c-bet sizing based on board texture, mapped to button 1-4.

    Button mapping:
    - Dry boards: button 1
    - Medium texture: button 2
    - Wet boards: button 3
    - Calling station: button 3

    Args:
        pot: Current pot size
        texture: BoardTexture enum value
        vs_calling_station: True if opponent is a calling station

    Returns:
        Tuple of (cbet_amount, button_label)
    """
    if vs_calling_station:
        return round(pot * 0.80, 2), "3"

    # Map texture to available buttons
    sizing_map = {
        BoardTexture.DRY: BetSizing.SMALL,  # button 1
        BoardTexture.MEDIUM: BetSizing.STANDARD,  # button 2
        BoardTexture.WET: BetSizing.LARGE,  # button 3
    }

    sizing = sizing_map.get(texture, BetSizing.STANDARD)
    pct = POSTFLOP_POT_FRACTIONS[sizing]
    return round(pot * pct, 2), sizing.value


def calculate_overbet(pot: float, stack: float) -> tuple[float, str]:
    """
    Calculate overbet sizing - use button 4 (pot).

    For river overbets with the nuts on action rivers.
    Fish cannot fold straights/flushes/sets.

    Args:
        pot: Current pot size
        stack: Hero's remaining stack

    Returns:
        Tuple of (bet_amount, button_label)
    """
    # Use button 4 (pot) for overbets
    amount = round(min(pot, stack), 2)
    return amount, "4"


def calculate_value_bet(pot: float, street: str = "flop") -> tuple[float, str]:
    """
    Calculate value bet sizing mapped to button 1-4.

    Strategy:
    - Flop: button 2 (standard)
    - Turn: button 2-3
    - River: button 3 for thick value

    Args:
        pot: Current pot size
        street: Current street ('flop', 'turn', 'river')

    Returns:
        Tuple of (bet_amount, button_label)
    """
    if street == "river":
        return round(pot * 0.80, 2), "3"
    return round(pot * 0.66, 2), "2"


def calculate_check_raise(opponent_bet: float, pot: float) -> tuple[float, str]:
    """
    Calculate check-raise sizing mapped to button 4 (pot).

    Strategy: Raise to pot since check-raises should be large.

    Args:
        opponent_bet: Amount opponent bet
        pot: Current pot size

    Returns:
        Tuple of (raise_amount, button_label)
    """
    # Check-raise to pot is standard (button 4)
    # Total pot after call = pot + opponent_bet
    # Pot-sized raise = (pot + opponent_bet) + opponent_bet
    return round(pot + opponent_bet * 2, 2), "4"


# Pre-built action factories for common situations


def fold_action(reasoning: str = "") -> Action:
    """Create a FOLD action."""
    return Action(
        action_type=ActionType.FOLD,
        reasoning=reasoning or "Hand not in range",
        confidence=0.9,
    )


def check_action(reasoning: str = "") -> Action:
    """Create a CHECK action."""
    return Action(
        action_type=ActionType.CHECK,
        reasoning=reasoning or "Check back",
        confidence=0.7,
    )


def call_action(amount: float, reasoning: str = "") -> Action:
    """Create a CALL action."""
    return Action(
        action_type=ActionType.CALL,
        amount=amount,
        reasoning=reasoning or "Call with odds",
        confidence=0.7,
    )


def bet_action(
    amount: float, reasoning: str = "", sizing_note: str = "", button: str = ""
) -> Action:
    """Create a BET action with button label."""
    return Action(
        action_type=ActionType.BET,
        amount=amount,
        reasoning=reasoning or "Value bet",
        confidence=0.8,
        sizing_note=sizing_note,
        button=button,
    )


def raise_action(
    amount: float, reasoning: str = "", sizing_note: str = "", button: str = ""
) -> Action:
    """Create a RAISE action with button label."""
    return Action(
        action_type=ActionType.RAISE,
        amount=amount,
        reasoning=reasoning or "Raise for value",
        confidence=0.8,
        sizing_note=sizing_note,
        button=button,
    )


def allin_action(amount: float, reasoning: str = "") -> Action:
    """Create an ALL-IN action."""
    return Action(
        action_type=ActionType.ALLIN,
        amount=amount,
        reasoning=reasoning or "All-in for value",
        confidence=0.85,
        button="A",  # All-in
    )
