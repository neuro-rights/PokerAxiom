"""
Minimum Defense Frequency (MDF) calculations for poker strategy.

MDF determines how often we must defend (call or raise) to prevent
an opponent from profitably bluffing with any two cards.

Formula: MDF = 1 - (bet_size / (pot_size + bet_size))

At 2NL, we apply exploitative adjustments since opponents:
- Rarely bluff (we can fold more than MDF suggests)
- Call too much (we should value bet wider, bluff less)
"""

from dataclasses import dataclass
from enum import Enum

from .hand_evaluator import HandStrength, PairType


class DefenseAction(Enum):
    """Recommended defense action."""

    FOLD = "fold"
    CALL = "call"
    RAISE = "raise"


@dataclass
class MDFAnalysis:
    """
    MDF analysis for a betting situation.

    Provides both GTO MDF and exploitative adjustments for 2NL.
    """

    # Pure GTO values
    mdf: float  # Minimum defense frequency (0-1)
    pot_odds: float  # Pot odds as percentage (0-1)

    # Exploitative adjustments
    adjusted_mdf: float  # MDF adjusted for 2NL population
    exploit_factor: str  # What exploit is being applied

    # Strategic recommendation
    should_defend: bool  # Should we defend this hand?
    defense_action: DefenseAction  # Recommended action
    reasoning: str  # Explanation of decision


def calculate_mdf(bet_size: float, pot_size: float) -> float:
    """
    Calculate Minimum Defense Frequency.

    MDF = 1 - (bet / (pot + bet))

    This is the frequency we must defend to make opponent's
    bluffs with any two cards break even.

    Args:
        bet_size: Size of the bet we're facing
        pot_size: Current pot size (before the bet)

    Returns:
        MDF as float between 0 and 1
    """
    if bet_size <= 0:
        return 1.0  # No bet = defend everything

    total_pot = pot_size + bet_size
    return 1 - (bet_size / total_pot)


def calculate_pot_odds(call_amount: float, pot_size: float) -> float:
    """
    Calculate pot odds as a percentage.

    Pot odds = call / (pot + call)

    This tells us the equity we need to profitably call.

    Args:
        call_amount: Amount needed to call
        pot_size: Current pot size (including opponent's bet)

    Returns:
        Pot odds as float between 0 and 1
    """
    if call_amount <= 0:
        return 0.0  # Free to see, no equity needed

    total_pot = pot_size + call_amount
    return call_amount / total_pot


def get_mdf_for_bet_size(bet_pct: float) -> float:
    """
    Quick lookup for MDF at common bet sizes.

    Args:
        bet_pct: Bet size as fraction of pot (0.33, 0.5, 0.75, 1.0, etc.)

    Returns:
        MDF for that bet size
    """
    # MDF = 1 / (1 + bet_pct)
    return 1 / (1 + bet_pct)


# Common MDF values for reference:
# 25% pot bet: MDF = 80%
# 33% pot bet: MDF = 75%
# 50% pot bet: MDF = 67%
# 66% pot bet: MDF = 60%
# 75% pot bet: MDF = 57%
# 100% pot bet: MDF = 50%
# 150% pot bet: MDF = 40%
# 200% pot bet: MDF = 33%


def get_exploitative_mdf(
    base_mdf: float,
    street: str,
    facing_raise: bool = False,
) -> tuple[float, str]:
    """
    Adjust MDF for 2NL population tendencies.

    2NL players typically:
    - Under-bluff (we can fold more)
    - Over-call (we should value bet more)
    - Raise for value only (believe raises)

    Args:
        base_mdf: Pure GTO MDF
        street: Current street ('flop', 'turn', 'river')
        facing_raise: Whether we're facing a raise (vs a bet)

    Returns:
        Tuple of (adjusted_mdf, exploit_reason)
    """
    # Base adjustment: 2NL players under-bluff
    # We can fold ~10-15% more than MDF suggests
    adjustment = 0.10

    if street == "river":
        # River: 2NL players rarely bluff
        # "A raise on the river is ALWAYS the nuts"
        adjustment = 0.20
        exploit = "2NL rarely bluffs river"

    elif street == "turn":
        # Turn: Still under-bluffed but some semi-bluffs
        adjustment = 0.15
        exploit = "2NL under-bluffs turn"

    else:  # Flop
        # Flop: More c-bets and semi-bluffs, closer to GTO
        adjustment = 0.10
        exploit = "2NL slightly under-bluffs flop"

    # Extra adjustment for facing raises
    if facing_raise:
        adjustment += 0.10
        exploit = f"{exploit}, raises = value"

    adjusted_mdf = max(0.2, base_mdf - adjustment)
    return adjusted_mdf, exploit


def should_defend(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    bet_size: float,
    pot_size: float,
    street: str,
    facing_raise: bool = False,
    has_draw: bool = False,
    draw_outs: int = 0,
) -> MDFAnalysis:
    """
    Determine if we should defend with this hand.

    Combines MDF theory with hand strength evaluation and
    exploitative adjustments for 2NL.

    Args:
        hand_strength: Current made hand strength
        pair_type: Type of pair if applicable
        bet_size: Size of bet we're facing
        pot_size: Current pot size
        street: Current street
        facing_raise: Whether facing a raise
        has_draw: Whether we have a draw
        draw_outs: Number of outs if drawing

    Returns:
        MDFAnalysis with recommendation
    """
    # Calculate base MDF
    mdf = calculate_mdf(bet_size, pot_size)
    pot_odds = calculate_pot_odds(bet_size, pot_size + bet_size)

    # Get exploitative adjustment
    adjusted_mdf, exploit_factor = get_exploitative_mdf(mdf, street, facing_raise)

    # Evaluate hand
    should_def, action, reasoning = _evaluate_defense(
        hand_strength=hand_strength,
        pair_type=pair_type,
        pot_odds=pot_odds,
        street=street,
        facing_raise=facing_raise,
        has_draw=has_draw,
        draw_outs=draw_outs,
    )

    return MDFAnalysis(
        mdf=mdf,
        pot_odds=pot_odds,
        adjusted_mdf=adjusted_mdf,
        exploit_factor=exploit_factor,
        should_defend=should_def,
        defense_action=action,
        reasoning=reasoning,
    )


def _evaluate_defense(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    pot_odds: float,
    street: str,
    facing_raise: bool,
    has_draw: bool,
    draw_outs: int,
) -> tuple[bool, DefenseAction, str]:
    """
    Evaluate whether to defend based on hand strength and situation.

    Returns:
        Tuple of (should_defend, action, reasoning)
    """
    # Very strong hands - always defend, consider raising
    if hand_strength >= HandStrength.THREE_OF_KIND:
        if facing_raise:
            return True, DefenseAction.CALL, f"Strong hand ({hand_strength.name}) vs raise"
        return True, DefenseAction.RAISE, f"Raise for value with {hand_strength.name}"

    if hand_strength >= HandStrength.TWO_PAIR:
        if facing_raise and street == "river":
            # Be cautious of river raises at 2NL
            return True, DefenseAction.CALL, "Call two pair vs river raise (cautious)"
        return True, DefenseAction.CALL, "Defend with two pair"

    # One pair hands - depends on pair type and street
    if hand_strength == HandStrength.PAIR:
        if pair_type == PairType.OVERPAIR:
            if facing_raise and street in ("turn", "river"):
                return True, DefenseAction.CALL, "Call overpair vs aggression (cautious)"
            return True, DefenseAction.CALL, "Defend with overpair"

        if pair_type == PairType.TOP_PAIR:
            if facing_raise and street == "river":
                # 2NL river raises are almost always value
                return False, DefenseAction.FOLD, "Fold top pair to river raise at 2NL"
            return True, DefenseAction.CALL, "Defend with top pair"

        if pair_type == PairType.SECOND_PAIR:
            if street == "river" or facing_raise:
                return False, DefenseAction.FOLD, "Second pair too weak vs aggression"
            # Flop/turn - need good odds
            if pot_odds <= 0.25:
                return True, DefenseAction.CALL, "Call second pair with good odds"
            return False, DefenseAction.FOLD, "Second pair facing poor odds"

        # Underpair, bottom pair, board pair
        if pot_odds <= 0.20:
            return True, DefenseAction.CALL, "Call weak pair with excellent odds"
        return False, DefenseAction.FOLD, "Weak pair cannot defend"

    # Drawing hands
    if has_draw and draw_outs > 0:
        # Calculate equity needed vs pot odds
        if street == "flop":
            # Two cards to come, ~4% per out
            draw_equity = min(draw_outs * 0.04, 0.45)
        else:  # turn
            # One card to come, ~2% per out
            draw_equity = min(draw_outs * 0.02, 0.20)

        if draw_equity >= pot_odds:
            return True, DefenseAction.CALL, f"Call draw ({draw_outs} outs) with equity"

        # Check for implied odds with strong draws
        if draw_outs >= 9:  # Flush draw or combo draw
            return True, DefenseAction.CALL, f"Call strong draw ({draw_outs} outs) for implied odds"

    # High card / nothing
    return False, DefenseAction.FOLD, "Cannot defend without equity"


def get_bluff_frequency(bet_size: float, pot_size: float) -> float:
    """
    Calculate how often we should be bluffing for balance.

    For a balanced range, bluff frequency = bet_size / (pot_size + 2*bet_size)

    At 2NL, we should bluff LESS than this since opponents over-call.

    Args:
        bet_size: Our bet size
        pot_size: Current pot

    Returns:
        Bluff frequency for balance (0-1)
    """
    if bet_size <= 0:
        return 0.0

    # GTO bluff frequency
    gto_bluff_freq = bet_size / (pot_size + 2 * bet_size)

    # At 2NL, reduce bluff frequency significantly
    # Opponents call too much, so bluffs are -EV
    exploit_bluff_freq = gto_bluff_freq * 0.3  # Only 30% of GTO bluffs

    return exploit_bluff_freq


def should_bluff(
    pot_size: float,
    bet_size: float,
    has_blockers: bool = False,
    street: str = "river",
    multiway: bool = False,
) -> tuple[bool, str]:
    """
    Determine if a bluff is profitable at 2NL.

    Generally, bluffs are unprofitable at 2NL because:
    - Opponents over-call
    - They don't fold made hands
    - They call to "keep you honest"

    Args:
        pot_size: Current pot
        bet_size: Proposed bet size
        has_blockers: Whether we have nut blockers
        street: Current street
        multiway: Whether multiway pot

    Returns:
        Tuple of (should_bluff, reasoning)
    """
    # Rule: Don't bluff river at 2NL
    if street == "river":
        if has_blockers:
            # With blockers, occasional bluff is okay
            return False, "Don't bluff river at 2NL (even with blockers, they call)"
        return False, "Never bluff river at 2NL - they call everything"

    # Multiway: Never bluff
    if multiway:
        return False, "Don't bluff multiway at 2NL"

    # Flop/Turn: Very selective semi-bluffs only
    if street == "flop":
        if has_blockers:
            return True, "Flop c-bet bluff acceptable with blockers"
        return False, "Avoid pure bluffs on flop at 2NL"

    if street == "turn":
        return False, "Avoid turn bluffs at 2NL"

    return False, "Default: no bluffing at 2NL"


def calculate_break_even_frequency(bet_size: float, pot_size: float) -> float:
    """
    Calculate how often our bluff needs to work to break even.

    Break-even % = bet_size / (pot_size + bet_size)

    Args:
        bet_size: Our bet size
        pot_size: Current pot

    Returns:
        Required fold frequency for break-even (0-1)
    """
    if bet_size <= 0:
        return 0.0

    return bet_size / (pot_size + bet_size)
