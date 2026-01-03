"""
Multi-street planning for poker strategy.

Instead of making isolated decisions each street, this module helps plan
the entire hand from flop to river. Key concepts:

- Hand type: Determines how we approach the hand (value, draw, bluff, marginal)
- Line planning: What we intend to do across multiple streets
- Geometric sizing: Building the pot to get stacks in by river
- Contingency planning: What to do if opponent plays back

All sizings mapped to available buttons: 33%, 66%, 80%, 100%
"""

from dataclasses import dataclass
from enum import Enum

from .game_state import Street
from .hand_evaluator import HandStrength, PairType

# Available postflop bet sizes
SIZING_33 = 0.33
SIZING_66 = 0.66
SIZING_80 = 0.80
SIZING_100 = 1.00


def _snap_to_button(sizing: float) -> tuple[float, str]:
    """Snap sizing fraction to nearest available button."""
    if sizing <= 0.50:
        return SIZING_33, "33%"
    elif sizing <= 0.73:
        return SIZING_66, "66%"
    elif sizing <= 0.90:
        return SIZING_80, "80%"
    else:
        return SIZING_100, "100%"


class HandType(Enum):
    """Classification of our hand for planning purposes."""

    MONSTER = "monster"  # Sets+, straights, flushes - want to get stacks in
    VALUE = "value"  # Strong made hands - two pair, overpair, TPTK
    MARGINAL = "marginal"  # Medium strength - second pair, weak top pair
    DRAW = "draw"  # Drawing hands - want to see more cards
    AIR = "air"  # Nothing - bluff or give up


class BetLine(Enum):
    """Planned betting line across streets."""

    VALUE_3_STREETS = "bet_bet_bet"  # Bet flop, turn, river
    VALUE_2_STREETS = "bet_bet_check"  # Bet flop and turn, check river
    DELAYED_CBET = "check_bet_bet"  # Check flop, bet turn and river
    CHECK_CALL_LINE = "check_call"  # Check and call opponent bets
    GIVE_UP = "give_up"  # Stop putting money in
    POT_CONTROL = "pot_control"  # Keep pot small, get to showdown


@dataclass
class StreetPlan:
    """
    Plan for a single street.

    Contains the intended action and contingencies.
    """

    street: Street
    primary_action: str  # 'bet', 'check', 'call', 'fold'
    sizing: float | None  # Bet/raise size as fraction of pot
    sizing_reason: str  # Why this sizing
    button: str  # Which button to click (e.g., "66%", "80%")

    # Contingency plans
    if_raised: str  # What to do if opponent raises ('call', 'fold', 'reraise')
    if_bet_into: str  # What to do if opponent bets first ('call', 'raise', 'fold')

    # Confidence
    confidence: float  # 0-1, how confident in this plan


@dataclass
class HandPlan:
    """
    Complete hand plan from flop to river.

    Provides a coherent strategy across all streets instead of
    making isolated decisions.
    """

    hand_type: HandType
    overall_line: BetLine
    target_pot_size: float  # What we want pot to be by river
    willing_to_stack_off: bool  # Ready to commit entire stack?

    # Street-by-street plans
    flop_plan: StreetPlan
    turn_plan: StreetPlan | None  # May be None if planning to give up
    river_plan: StreetPlan | None

    # Key decision points
    stop_if: list[str]  # Conditions to abandon plan (e.g., "opponent raises flop")
    escalate_if: list[str]  # Conditions to bet bigger (e.g., "action river")

    # Summary
    plan_summary: str  # Human-readable plan description


def classify_hand_type(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    has_draw: bool,
    draw_outs: int,
) -> HandType:
    """
    Classify hand into a planning category.

    Args:
        hand_strength: Current made hand strength
        pair_type: Type of pair if applicable
        has_draw: Whether we have a draw
        draw_outs: Number of outs if drawing

    Returns:
        HandType classification
    """
    # Monster hands
    if hand_strength >= HandStrength.THREE_OF_KIND:
        return HandType.MONSTER

    if hand_strength == HandStrength.TWO_PAIR:
        return HandType.VALUE

    # One pair hands - classify by pair type
    if hand_strength == HandStrength.PAIR:
        if pair_type == PairType.OVERPAIR:
            return HandType.VALUE
        elif pair_type == PairType.TOP_PAIR:
            return HandType.VALUE  # Could be marginal with weak kicker
        elif pair_type in (PairType.SECOND_PAIR, PairType.UNDERPAIR):
            return HandType.MARGINAL
        else:
            return HandType.MARGINAL

    # Drawing hands
    if has_draw and draw_outs >= 8:
        return HandType.DRAW

    # Air
    return HandType.AIR


def create_hand_plan(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    has_draw: bool,
    draw_outs: int,
    spr: float,
    pot: float,
    effective_stack: float,
    in_position: bool,
    opponent_count: int,
) -> HandPlan:
    """
    Create a multi-street plan for the hand.

    Args:
        hand_strength: Current made hand strength
        pair_type: Type of pair if applicable
        has_draw: Whether we have a draw
        draw_outs: Number of outs
        spr: Stack-to-pot ratio
        pot: Current pot size
        effective_stack: Effective stack size
        in_position: Whether we're in position
        opponent_count: Number of opponents

    Returns:
        HandPlan with street-by-street strategy
    """
    hand_type = classify_hand_type(hand_strength, pair_type, has_draw, draw_outs)

    # Plan based on hand type and SPR
    if hand_type == HandType.MONSTER:
        return _plan_monster(hand_strength, spr, pot, effective_stack, in_position)

    elif hand_type == HandType.VALUE:
        return _plan_value(
            hand_strength, pair_type, spr, pot, effective_stack, in_position, opponent_count
        )

    elif hand_type == HandType.DRAW:
        return _plan_draw(draw_outs, spr, pot, effective_stack, in_position, opponent_count)

    elif hand_type == HandType.MARGINAL:
        return _plan_marginal(hand_strength, pair_type, spr, pot, effective_stack, in_position)

    else:  # AIR
        return _plan_air(spr, pot, in_position, opponent_count)


def geometric_sizing(
    pot: float,
    effective_stack: float,
    streets_remaining: int,
) -> list[tuple[float, str]]:
    """
    Calculate geometric bet sizes mapped to available buttons.

    Geometric sizing means betting the same fraction of pot each street
    so that by the river, we've committed our stack.

    Args:
        pot: Current pot size
        effective_stack: Effective stack remaining
        streets_remaining: How many streets left (1-3)

    Returns:
        List of (bet_size, button_label) tuples for each street
    """
    if streets_remaining <= 0 or effective_stack <= 0:
        return []

    # Target: final pot = effective_stack + current pot
    target_pot = pot + effective_stack * 2

    # Solve for bet fraction
    multiplier = (target_pot / pot) ** (1 / streets_remaining)
    bet_fraction = (multiplier - 1) / 2

    # Cap at reasonable sizes
    bet_fraction = min(bet_fraction, 1.5)
    bet_fraction = max(bet_fraction, 0.25)

    # Snap to available button
    snapped_fraction, button = _snap_to_button(bet_fraction)

    # Calculate bets for each street using snapped size
    bets = []
    current_pot = pot
    remaining_stack = effective_stack

    for _ in range(streets_remaining):
        bet = current_pot * snapped_fraction
        bet = min(bet, remaining_stack)
        bets.append((round(bet, 2), button))
        current_pot = current_pot + bet * 2
        remaining_stack -= bet

    return bets


def update_plan_for_action(
    current_plan: HandPlan,
    opponent_action: str,
    current_street: Street,
) -> HandPlan:
    """
    Update the plan based on opponent's action.

    Args:
        current_plan: Our current hand plan
        opponent_action: What opponent did ('bet', 'raise', 'check', 'call')
        current_street: Current street

    Returns:
        Updated HandPlan
    """
    # Check if opponent action triggers a stop condition
    for stop_condition in current_plan.stop_if:
        if opponent_action in stop_condition:
            # Downgrade plan
            return _downgrade_plan(current_plan, opponent_action)

    # Check if opponent action triggers escalation
    for escalate_condition in current_plan.escalate_if:
        if opponent_action in escalate_condition:
            return _escalate_plan(current_plan, opponent_action)

    return current_plan


def should_continue_line(
    plan: HandPlan,
    current_street: Street,
    board_changed: str,  # 'improved', 'neutral', 'dangerous'
) -> tuple[bool, str]:
    """
    Determine if we should continue with our planned line.

    Args:
        plan: Our hand plan
        current_street: Current street
        board_changed: How the board texture changed

    Returns:
        Tuple of (should_continue, reason)
    """
    if board_changed == "dangerous":
        if plan.hand_type in (HandType.MONSTER, HandType.VALUE):
            # Strong hands can continue but may need to reconsider sizing
            return True, "Continue with caution on dangerous board"
        else:
            return False, "Board got dangerous, abandon plan"

    if plan.hand_type == HandType.DRAW:
        if current_street == Street.RIVER:
            # Did we hit?
            return False, "Draw evaluation needed on river"

    return True, "Continue with plan"


# Private helper functions for creating plans


def _plan_monster(
    hand_strength: HandStrength,
    spr: float,
    pot: float,
    effective_stack: float,
    in_position: bool,
) -> HandPlan:
    """Create plan for monster hands (sets+)."""
    # Calculate geometric sizing with button mapping
    geo_sizes = geometric_sizing(pot, effective_stack, 3)

    # Default to 66% if no geometric sizes
    default_sizing, default_button = SIZING_66, "66%"

    flop_plan = StreetPlan(
        street=Street.FLOP,
        primary_action="bet",
        sizing=geo_sizes[0][0] if geo_sizes else default_sizing,
        sizing_reason="Geometric sizing for value",
        button=geo_sizes[0][1] if geo_sizes else default_button,
        if_raised="call",  # Happy to call with monster
        if_bet_into="raise",  # Raise for value
        confidence=0.9,
    )

    turn_plan = StreetPlan(
        street=Street.TURN,
        primary_action="bet",
        sizing=geo_sizes[1][0] if len(geo_sizes) > 1 else default_sizing,
        sizing_reason="Continue geometric sizing",
        button=geo_sizes[1][1] if len(geo_sizes) > 1 else default_button,
        if_raised="call",
        if_bet_into="raise",
        confidence=0.85,
    )

    river_plan = StreetPlan(
        street=Street.RIVER,
        primary_action="bet",
        sizing=geo_sizes[2][0] if len(geo_sizes) > 2 else SIZING_80,
        sizing_reason="Extract max value",
        button=geo_sizes[2][1] if len(geo_sizes) > 2 else "80%",
        if_raised="call",
        if_bet_into="raise",
        confidence=0.8,
    )

    return HandPlan(
        hand_type=HandType.MONSTER,
        overall_line=BetLine.VALUE_3_STREETS,
        target_pot_size=pot + effective_stack * 2,
        willing_to_stack_off=True,
        flop_plan=flop_plan,
        turn_plan=turn_plan,
        river_plan=river_plan,
        stop_if=[],  # Never stop with monster
        escalate_if=["action river"],  # Overbet on action rivers
        plan_summary=f"Get stacks in with {hand_strength.name}",
    )


def _plan_value(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    spr: float,
    pot: float,
    effective_stack: float,
    in_position: bool,
    opponent_count: int,
) -> HandPlan:
    """Create plan for value hands (two pair, overpair, TPTK)."""
    # Value hands: bet 2 streets typically
    multiway = opponent_count > 1

    if spr <= 3:
        # Low SPR: Can bet all 3 streets
        line = BetLine.VALUE_3_STREETS
        stack_off = True
    elif spr <= 7:
        # Medium SPR: Bet 2 streets, evaluate river
        line = BetLine.VALUE_2_STREETS
        stack_off = hand_strength >= HandStrength.TWO_PAIR
    else:
        # High SPR: Pot control unless two pair+
        if hand_strength >= HandStrength.TWO_PAIR:
            line = BetLine.VALUE_2_STREETS
            stack_off = True
        else:
            line = BetLine.POT_CONTROL
            stack_off = False

    # Flop sizing - use available buttons
    if multiway:
        flop_sizing, flop_button = SIZING_80, "80%"  # Size up multiway
    else:
        flop_sizing, flop_button = SIZING_66, "66%"  # Standard

    flop_plan = StreetPlan(
        street=Street.FLOP,
        primary_action="bet",
        sizing=flop_sizing,
        sizing_reason="Value bet for protection" if multiway else "Standard c-bet",
        button=flop_button,
        if_raised="call" if stack_off else "fold",
        if_bet_into="raise" if stack_off else "call",
        confidence=0.8,
    )

    turn_plan = StreetPlan(
        street=Street.TURN,
        primary_action="bet" if line != BetLine.POT_CONTROL else "check",
        sizing=SIZING_66 if line != BetLine.POT_CONTROL else None,
        sizing_reason="Continue value" if line != BetLine.POT_CONTROL else "Pot control",
        button="66%" if line != BetLine.POT_CONTROL else "",
        if_raised="fold" if spr > 5 else "call",
        if_bet_into="call",
        confidence=0.7,
    )

    river_plan = StreetPlan(
        street=Street.RIVER,
        primary_action="check" if line == BetLine.VALUE_2_STREETS else "bet",
        sizing=SIZING_66 if line == BetLine.VALUE_3_STREETS else None,
        sizing_reason="Thin value" if line == BetLine.VALUE_3_STREETS else "Showdown",
        button="66%" if line == BetLine.VALUE_3_STREETS else "",
        if_raised="fold",  # Believe river raises at 2NL
        if_bet_into="call",
        confidence=0.6,
    )

    return HandPlan(
        hand_type=HandType.VALUE,
        overall_line=line,
        target_pot_size=pot * 3 if line == BetLine.VALUE_2_STREETS else pot * 5,
        willing_to_stack_off=stack_off,
        flop_plan=flop_plan,
        turn_plan=turn_plan,
        river_plan=river_plan,
        stop_if=["opponent raises turn", "opponent raises river"],
        escalate_if=["action river"] if hand_strength >= HandStrength.TWO_PAIR else [],
        plan_summary=f"Value bet {hand_strength.name}, stack off = {stack_off}",
    )


def _plan_draw(
    draw_outs: int,
    spr: float,
    pot: float,
    effective_stack: float,
    in_position: bool,
    opponent_count: int,
) -> HandPlan:
    """Create plan for drawing hands."""
    strong_draw = draw_outs >= 12  # Combo draw

    # Draws want to see cards cheaply or semi-bluff
    if in_position:
        # IP: Can take free cards
        line = BetLine.CHECK_CALL_LINE
    else:
        # OOP: Semi-bluff or check-call
        if strong_draw and opponent_count == 1:
            line = BetLine.VALUE_2_STREETS  # Semi-bluff
        else:
            line = BetLine.CHECK_CALL_LINE

    flop_action = "bet" if strong_draw and opponent_count == 1 else "check"

    flop_plan = StreetPlan(
        street=Street.FLOP,
        primary_action=flop_action,
        sizing=SIZING_66 if flop_action == "bet" else None,
        sizing_reason="Semi-bluff with strong draw"
        if flop_action == "bet"
        else "Check to see turn",
        button="66%" if flop_action == "bet" else "",
        if_raised="call" if draw_outs >= 9 else "fold",
        if_bet_into="call",
        confidence=0.7,
    )

    turn_plan = StreetPlan(
        street=Street.TURN,
        primary_action="check",
        sizing=None,
        sizing_reason="See river",
        button="",
        if_raised="fold",
        if_bet_into="call" if draw_outs >= 8 else "fold",
        confidence=0.6,
    )

    river_plan = StreetPlan(
        street=Street.RIVER,
        primary_action="check",  # Re-evaluate if we hit
        sizing=None,
        sizing_reason="Evaluate if hit",
        button="",
        if_raised="fold",
        if_bet_into="fold",
        confidence=0.5,
    )

    return HandPlan(
        hand_type=HandType.DRAW,
        overall_line=line,
        target_pot_size=pot * 2,  # Don't want pot to get huge
        willing_to_stack_off=strong_draw,
        flop_plan=flop_plan,
        turn_plan=turn_plan,
        river_plan=river_plan,
        stop_if=["opponent raises twice"],
        escalate_if=["draw completes"],
        plan_summary=f"Draw with {draw_outs} outs, play passively",
    )


def _plan_marginal(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    spr: float,
    pot: float,
    effective_stack: float,
    in_position: bool,
) -> HandPlan:
    """Create plan for marginal hands (second pair, weak TP)."""
    # Marginal hands: Check, call, showdown
    line = BetLine.CHECK_CALL_LINE

    flop_plan = StreetPlan(
        street=Street.FLOP,
        primary_action="check",
        sizing=None,
        sizing_reason="Pot control with marginal",
        button="",
        if_raised="fold",
        if_bet_into="call",
        confidence=0.6,
    )

    turn_plan = StreetPlan(
        street=Street.TURN,
        primary_action="check",
        sizing=None,
        sizing_reason="Continue pot control",
        button="",
        if_raised="fold",
        if_bet_into="call" if spr <= 5 else "fold",
        confidence=0.5,
    )

    river_plan = StreetPlan(
        street=Street.RIVER,
        primary_action="check",
        sizing=None,
        sizing_reason="Get to showdown",
        button="",
        if_raised="fold",
        if_bet_into="fold",  # Don't pay off rivers at 2NL
        confidence=0.5,
    )

    return HandPlan(
        hand_type=HandType.MARGINAL,
        overall_line=line,
        target_pot_size=pot,  # Keep pot small
        willing_to_stack_off=False,
        flop_plan=flop_plan,
        turn_plan=turn_plan,
        river_plan=river_plan,
        stop_if=["opponent bets twice", "opponent raises"],
        escalate_if=[],
        plan_summary="Check-call with marginal, avoid big pots",
    )


def _plan_air(
    spr: float,
    pot: float,
    in_position: bool,
    opponent_count: int,
) -> HandPlan:
    """Create plan for air (no made hand or draw)."""
    # Air: C-bet once on dry boards, give up otherwise
    # At 2NL, bluffing is generally -EV

    if opponent_count == 1:
        line = BetLine.GIVE_UP  # One c-bet then done
        flop_action = "bet"  # Small c-bet on dry boards
    else:
        line = BetLine.GIVE_UP
        flop_action = "check"

    flop_plan = StreetPlan(
        street=Street.FLOP,
        primary_action=flop_action,
        sizing=SIZING_33 if flop_action == "bet" else None,
        sizing_reason="Small c-bet bluff" if flop_action == "bet" else "Give up multiway",
        button="33%" if flop_action == "bet" else "",
        if_raised="fold",
        if_bet_into="fold",
        confidence=0.4,
    )

    turn_plan = StreetPlan(
        street=Street.TURN,
        primary_action="check",
        sizing=None,
        sizing_reason="Give up",
        button="",
        if_raised="fold",
        if_bet_into="fold",
        confidence=0.3,
    )

    river_plan = StreetPlan(
        street=Street.RIVER,
        primary_action="check",
        sizing=None,
        sizing_reason="Give up - never bluff river at 2NL",
        button="",
        if_raised="fold",
        if_bet_into="fold",
        confidence=0.3,
    )

    return HandPlan(
        hand_type=HandType.AIR,
        overall_line=line,
        target_pot_size=pot,
        willing_to_stack_off=False,
        flop_plan=flop_plan,
        turn_plan=turn_plan,
        river_plan=river_plan,
        stop_if=["any resistance"],
        escalate_if=[],
        plan_summary="One and done c-bet, don't bluff",
    )


def _downgrade_plan(plan: HandPlan, trigger: str) -> HandPlan:
    """Downgrade plan due to opponent action."""
    # Shift to more passive line
    plan.overall_line = BetLine.GIVE_UP
    plan.willing_to_stack_off = False
    plan.plan_summary = f"Downgraded: {trigger}"
    return plan


def _escalate_plan(plan: HandPlan, trigger: str) -> HandPlan:
    """Escalate plan due to favorable conditions."""
    plan.overall_line = BetLine.VALUE_3_STREETS
    plan.willing_to_stack_off = True
    plan.plan_summary = f"Escalated: {trigger}"
    return plan
