"""
SPR (Stack-to-Pot Ratio) based strategy framework.

SPR drives commitment decisions and helps determine when to stack off,
value bet, or exercise pot control.

SPR Categories:
- LOW (1-3): Commitment mode - one pair hands gain significant value
- MEDIUM (4-7): Flexibility mode - strong top pairs valuable but not automatic stack-offs
- HIGH (8+): Selectivity mode - favor nutted hands, one pair holdings less valuable
"""

from dataclasses import dataclass
from enum import Enum

from .hand_evaluator import HandStrength, PairType


class SPRCategory(Enum):
    """SPR category for strategic adjustments."""

    LOW = "low"  # SPR 1-3
    MEDIUM = "medium"  # SPR 4-7
    HIGH = "high"  # SPR 8+


class CommitmentLevel(Enum):
    """How committed we should be with our hand."""

    FULLY_COMMITTED = "fully_committed"  # Ready to get stacks in
    WILLING_TO_COMMIT = "willing_to_commit"  # Can commit if pushed
    POT_CONTROL = "pot_control"  # Control pot size, avoid big pots
    FOLD_TO_PRESSURE = "fold_to_pressure"  # Fold to significant aggression


@dataclass
class SPRStrategy:
    """
    SPR-based strategy recommendations.

    Provides thresholds and guidance based on stack-to-pot ratio.
    """

    spr: float
    category: SPRCategory

    # Commitment thresholds
    stack_off_threshold: HandStrength  # Minimum hand strength to stack off
    value_bet_threshold: HandStrength  # Minimum hand strength for value betting

    # Strategic guidance
    one_pair_value: str  # 'high', 'medium', 'low' - how valuable one-pair hands are
    draw_value: str  # 'high', 'medium', 'low' - how valuable draws are
    implied_odds_matter: bool  # Whether implied odds are significant

    # Sizing guidance
    preferred_sizing: str  # 'small', 'medium', 'large', 'geometric'
    bet_size_multiplier: float  # Adjust standard sizing by this factor

    # Set mining threshold (call raise with pocket pair if getting X:1 implied)
    set_mine_ratio: float  # Need this implied odds ratio to set mine


def get_spr_category(spr: float) -> SPRCategory:
    """
    Categorize SPR into strategic zones.

    Args:
        spr: Stack-to-pot ratio

    Returns:
        SPRCategory enum
    """
    if spr <= 3:
        return SPRCategory.LOW
    elif spr <= 7:
        return SPRCategory.MEDIUM
    return SPRCategory.HIGH


def get_spr_strategy(spr: float) -> SPRStrategy:
    """
    Get strategy recommendations based on SPR.

    Args:
        spr: Stack-to-pot ratio

    Returns:
        SPRStrategy with thresholds and guidance
    """
    category = get_spr_category(spr)

    if category == SPRCategory.LOW:
        # Low SPR (1-3): Commitment mode
        # One-pair hands very valuable, draws less so (no room for implied odds)
        # Easy to get stacks in with strong top pairs
        return SPRStrategy(
            spr=spr,
            category=category,
            stack_off_threshold=HandStrength.PAIR,  # TPTK+ can stack off
            value_bet_threshold=HandStrength.PAIR,  # Any pair has value
            one_pair_value="high",
            draw_value="low",  # No implied odds
            implied_odds_matter=False,
            preferred_sizing="large",  # Bigger bets relative to pot
            bet_size_multiplier=1.2,
            set_mine_ratio=0,  # Don't need implied odds at low SPR
        )

    elif category == SPRCategory.MEDIUM:
        # Medium SPR (4-7): Flexibility mode
        # Strong top pairs valuable but need to evaluate carefully
        # Draws have some implied odds value
        return SPRStrategy(
            spr=spr,
            category=category,
            stack_off_threshold=HandStrength.TWO_PAIR,  # Need 2pair+ to stack off
            value_bet_threshold=HandStrength.PAIR,  # Top pair+ for value
            one_pair_value="medium",
            draw_value="medium",
            implied_odds_matter=True,
            preferred_sizing="medium",
            bet_size_multiplier=1.0,
            set_mine_ratio=10,  # Need 10:1 implied to set mine
        )

    else:
        # High SPR (8+): Selectivity mode
        # Favor nutted hands (sets, straights, flushes)
        # One-pair hands much less valuable
        # Draws excellent due to implied odds
        return SPRStrategy(
            spr=spr,
            category=category,
            stack_off_threshold=HandStrength.THREE_OF_KIND,  # Need sets+ to stack off
            value_bet_threshold=HandStrength.TWO_PAIR,  # 2pair+ for value
            one_pair_value="low",
            draw_value="high",  # Excellent implied odds
            implied_odds_matter=True,
            preferred_sizing="geometric",  # Build pot over multiple streets
            bet_size_multiplier=0.8,  # Smaller bets to build pot
            set_mine_ratio=15,  # Need 15:1 implied to set mine
        )


def get_commitment_level(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    spr_strategy: SPRStrategy,
) -> CommitmentLevel:
    """
    Determine commitment level for a hand given SPR.

    Args:
        hand_strength: Current made hand strength
        pair_type: Type of pair if applicable
        spr_strategy: SPR strategy recommendations

    Returns:
        CommitmentLevel indicating how committed to be
    """
    # Strong hands (two pair+) always at least willing to commit
    if hand_strength >= HandStrength.TWO_PAIR:
        if hand_strength >= spr_strategy.stack_off_threshold:
            return CommitmentLevel.FULLY_COMMITTED
        return CommitmentLevel.WILLING_TO_COMMIT

    # One pair hands - depends on SPR and pair type
    if hand_strength == HandStrength.PAIR:
        if spr_strategy.category == SPRCategory.LOW:
            # Low SPR: Top pair+ can stack off
            if pair_type in (PairType.OVERPAIR, PairType.TOP_PAIR):
                return CommitmentLevel.FULLY_COMMITTED
            return CommitmentLevel.WILLING_TO_COMMIT

        elif spr_strategy.category == SPRCategory.MEDIUM:
            # Medium SPR: Top pair willing to commit, but pot control
            if pair_type in (PairType.OVERPAIR, PairType.TOP_PAIR):
                return CommitmentLevel.WILLING_TO_COMMIT
            return CommitmentLevel.POT_CONTROL

        else:  # HIGH SPR
            # High SPR: One pair is pot control territory
            if pair_type == PairType.OVERPAIR:
                return CommitmentLevel.WILLING_TO_COMMIT
            return CommitmentLevel.POT_CONTROL

    # Weak hands
    return CommitmentLevel.FOLD_TO_PRESSURE


def should_stack_off(
    hand_strength: HandStrength,
    pair_type: PairType | None,
    spr: float,
    facing_all_in: bool = False,
) -> tuple[bool, str]:
    """
    Determine if we should commit our stack with this hand.

    Args:
        hand_strength: Current made hand strength
        pair_type: Type of pair if applicable
        spr: Current stack-to-pot ratio
        facing_all_in: Whether we're facing an all-in

    Returns:
        Tuple of (should_stack_off, reasoning)
    """
    strategy = get_spr_strategy(spr)

    # Always stack off with very strong hands
    if hand_strength >= HandStrength.STRAIGHT:
        return True, f"Stack off with {hand_strength.name} at any SPR"

    if hand_strength >= HandStrength.THREE_OF_KIND:
        return True, "Stack off with set"

    if hand_strength >= HandStrength.TWO_PAIR:
        if strategy.category == SPRCategory.LOW:
            return True, "Stack off with two pair at low SPR"
        elif strategy.category == SPRCategory.MEDIUM:
            return True, "Stack off with two pair at medium SPR"
        else:
            # High SPR - two pair is borderline
            if facing_all_in:
                return False, "Two pair not strong enough vs all-in at high SPR"
            return True, "Value bet two pair at high SPR but avoid massive pots"

    # One pair hands
    if hand_strength == HandStrength.PAIR:
        if strategy.category == SPRCategory.LOW:
            if pair_type in (PairType.OVERPAIR, PairType.TOP_PAIR):
                return True, f"Stack off with {pair_type.value} at low SPR"
            return (
                False,
                f"{pair_type.value if pair_type else 'weak pair'} not strong enough even at low SPR",
            )

        elif strategy.category == SPRCategory.MEDIUM:
            if pair_type == PairType.OVERPAIR:
                if facing_all_in:
                    return False, "Overpair not strong enough vs all-in at medium SPR"
                return True, "Willing to commit with overpair at medium SPR"
            return False, "One pair needs pot control at medium SPR"

        else:  # HIGH SPR
            return False, "One pair hands should not stack off at high SPR"

    return False, "Hand too weak to stack off"


def should_set_mine(
    call_amount: float,
    effective_stack: float,
    spr: float,
) -> tuple[bool, str]:
    """
    Determine if calling with a pocket pair for set value is profitable.

    Set mining is profitable when implied odds are good enough.
    We hit a set ~12% of the time (7.5:1 against).

    Args:
        call_amount: Amount to call
        effective_stack: Effective stack size
        spr: Current SPR (informational)

    Returns:
        Tuple of (should_set_mine, reasoning)
    """
    if call_amount <= 0:
        return True, "Free to see flop"

    # Calculate implied odds ratio
    implied_ratio = effective_stack / call_amount if call_amount > 0 else float("inf")

    # We need roughly 10:1 implied to break even on set mining
    # At 2NL, fish pay off sets well, so 8:1 is often enough
    min_ratio = 8.0

    if implied_ratio >= min_ratio:
        return True, f"Set mine with {implied_ratio:.1f}:1 implied odds"
    else:
        return False, f"Implied odds {implied_ratio:.1f}:1 not enough for set mining"


def get_value_bet_sizing(
    pot: float,
    spr: float,
    hand_strength: HandStrength,
    streets_remaining: int,
) -> float:
    """
    Calculate value bet sizing based on SPR and streets remaining.

    Uses geometric sizing to build pot over multiple streets.

    Args:
        pot: Current pot size
        spr: Stack-to-pot ratio
        hand_strength: Current hand strength
        streets_remaining: Number of betting streets left (1-3)

    Returns:
        Recommended bet size
    """
    strategy = get_spr_strategy(spr)

    # Base sizing percentages by SPR
    base_pct = {
        SPRCategory.LOW: 0.75,  # Larger bets at low SPR
        SPRCategory.MEDIUM: 0.66,  # Standard 2/3 pot
        SPRCategory.HIGH: 0.50,  # Smaller bets to build pot
    }

    base = base_pct[strategy.category]

    # Adjust for hand strength - bet bigger with stronger hands for value
    if hand_strength >= HandStrength.STRAIGHT:
        base *= 1.2
    elif hand_strength >= HandStrength.TWO_PAIR:
        base *= 1.1

    # For geometric sizing at high SPR, calculate to get stacks in by river
    if strategy.preferred_sizing == "geometric" and streets_remaining > 1:
        # Geometric formula: bet_size = pot * ((final_pot_ratio)^(1/streets) - 1)
        # Simplified: aim for roughly equal fractions of remaining stack each street
        target_final_pot = pot * (1 + base) ** streets_remaining
        geometric_pct = (target_final_pot / pot) ** (1 / streets_remaining) - 1
        base = min(base, geometric_pct)  # Don't exceed normal sizing

    bet_amount = pot * base
    return round(bet_amount, 2)


def adjust_cbet_for_spr(
    base_frequency: float,
    base_sizing: float,
    spr: float,
) -> tuple[float, float]:
    """
    Adjust c-bet frequency and sizing based on SPR.

    Args:
        base_frequency: Base c-bet frequency (0-1)
        base_sizing: Base c-bet sizing (fraction of pot)
        spr: Stack-to-pot ratio

    Returns:
        Tuple of (adjusted_frequency, adjusted_sizing)
    """
    strategy = get_spr_strategy(spr)

    if strategy.category == SPRCategory.LOW:
        # Low SPR: C-bet more often, size up for value
        freq = min(base_frequency * 1.15, 1.0)
        sizing = base_sizing * strategy.bet_size_multiplier
        return freq, sizing

    elif strategy.category == SPRCategory.MEDIUM:
        # Medium SPR: Standard frequencies
        return base_frequency, base_sizing

    else:  # HIGH SPR
        # High SPR: Slightly lower frequency, smaller sizing
        freq = base_frequency * 0.9
        sizing = base_sizing * strategy.bet_size_multiplier
        return freq, sizing
