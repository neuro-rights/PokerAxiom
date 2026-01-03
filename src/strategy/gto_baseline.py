"""
GTO baselines with 2NL population exploits.

This module provides GTO-derived baseline frequencies and applies
exploitative adjustments for the 2NL player pool.

Philosophy:
- Start with GTO baseline frequencies
- Apply exploits based on known 2NL population tendencies
- The result is a hybrid strategy that is theoretically sound
  but exploits common leaks at 2NL

Key 2NL population tendencies:
1. Rarely bluff (especially river) - We can overfold to aggression
2. Call too much - We should value bet wider, bluff less
3. Limp too much - We should isolate wider
4. Don't fold made hands - Bet bigger for value
5. Raise for value only - Believe raises
"""

from dataclasses import dataclass
from enum import Enum

from .actions import BoardTexture


class ExploitType(Enum):
    """Types of exploits we apply."""

    SIZE_UP_VALUE = "size_up_value"  # Bet bigger for value (they call)
    REDUCE_BLUFFS = "reduce_bluffs"  # Bluff less (they call)
    OVERFOLD = "overfold"  # Fold more to aggression (they don't bluff)
    BELIEVE_RAISES = "believe_raises"  # Fold to raises (raises = value)
    ISO_WIDER = "iso_wider"  # Isolate limpers wider


@dataclass
class GTOBaseline:
    """
    GTO-derived baseline frequencies.

    These are theoretical frequencies before exploits are applied.
    """

    # C-betting
    cbet_frequency: float  # 0-1
    cbet_sizing: float  # Fraction of pot

    # Defense
    fold_to_cbet: float  # How often to fold vs c-bet
    fold_to_turn_bet: float
    fold_to_river_bet: float

    # Aggression
    check_raise_frequency: float  # XR frequency
    value_bet_frequency: float  # River value betting
    bluff_frequency: float  # River bluffing


@dataclass
class ExploitAdjustment:
    """
    Adjustment to baseline frequencies.

    Tracks what exploit is being applied and why.
    """

    exploit_type: ExploitType
    adjustment: float  # How much to adjust (positive or negative)
    applied_to: str  # What frequency it adjusts
    rationale: str  # Why this exploit


@dataclass
class AdjustedStrategy:
    """
    Final strategy after applying exploits.

    Combines GTO baseline with exploitative adjustments.
    """

    baseline: GTOBaseline
    exploits_applied: list[ExploitAdjustment]

    # Adjusted frequencies
    adj_cbet_frequency: float
    adj_cbet_sizing: float
    adj_fold_to_cbet: float
    adj_fold_to_turn: float
    adj_fold_to_river: float
    adj_xr_frequency: float
    adj_value_bet_freq: float
    adj_bluff_freq: float


# Available postflop bet sizes (buttons 1-4)
# Button 1: 33%, Button 2: 66%, Button 3: 80%, Button 4: 100%
SIZING_1 = 0.33
SIZING_2 = 0.66
SIZING_3 = 0.80
SIZING_4 = 1.00

# GTO Baseline frequencies by board texture
# Sizings mapped to available buttons
CBET_BASELINES = {
    BoardTexture.DRY: GTOBaseline(
        cbet_frequency=0.70,
        cbet_sizing=SIZING_1,  # Small c-bet on dry boards (button 1)
        fold_to_cbet=0.45,
        fold_to_turn_bet=0.40,
        fold_to_river_bet=0.35,
        check_raise_frequency=0.08,
        value_bet_frequency=0.55,
        bluff_frequency=0.25,
    ),
    BoardTexture.MEDIUM: GTOBaseline(
        cbet_frequency=0.55,
        cbet_sizing=SIZING_2,  # Standard c-bet (button 2)
        fold_to_cbet=0.40,
        fold_to_turn_bet=0.38,
        fold_to_river_bet=0.33,
        check_raise_frequency=0.10,
        value_bet_frequency=0.50,
        bluff_frequency=0.20,
    ),
    BoardTexture.WET: GTOBaseline(
        cbet_frequency=0.40,
        cbet_sizing=SIZING_3,  # Large c-bet to charge draws (button 3)
        fold_to_cbet=0.35,
        fold_to_turn_bet=0.35,
        fold_to_river_bet=0.30,
        check_raise_frequency=0.12,
        value_bet_frequency=0.45,
        bluff_frequency=0.15,
    ),
}

# Standard 2NL population exploits
POPULATION_EXPLOITS = [
    ExploitAdjustment(
        exploit_type=ExploitType.SIZE_UP_VALUE,
        adjustment=0.15,  # 15% larger
        applied_to="cbet_sizing",
        rationale="2NL calls too much - size up for value",
    ),
    ExploitAdjustment(
        exploit_type=ExploitType.REDUCE_BLUFFS,
        adjustment=-0.15,  # 15% less bluffing
        applied_to="bluff_frequency",
        rationale="2NL calls too much - bluff less",
    ),
    ExploitAdjustment(
        exploit_type=ExploitType.OVERFOLD,
        adjustment=0.15,  # Fold 15% more
        applied_to="fold_to_river_bet",
        rationale="2NL rarely bluffs - fold more to river bets",
    ),
    ExploitAdjustment(
        exploit_type=ExploitType.BELIEVE_RAISES,
        adjustment=0.25,  # Fold 25% more to raises
        applied_to="fold_to_raises",
        rationale="2NL raises = value only",
    ),
]


def get_gto_baseline(texture: BoardTexture) -> GTOBaseline:
    """
    Get GTO baseline frequencies for a board texture.

    Args:
        texture: Board texture (DRY, MEDIUM, WET)

    Returns:
        GTOBaseline with theoretical frequencies
    """
    return CBET_BASELINES.get(texture, CBET_BASELINES[BoardTexture.MEDIUM])


def apply_2nl_exploits(baseline: GTOBaseline) -> AdjustedStrategy:
    """
    Apply 2NL population exploits to GTO baseline.

    Args:
        baseline: GTO baseline frequencies

    Returns:
        AdjustedStrategy with exploits applied
    """
    # Start with baseline values
    adj_cbet_freq = baseline.cbet_frequency
    adj_cbet_sizing = baseline.cbet_sizing
    adj_fold_cbet = baseline.fold_to_cbet
    adj_fold_turn = baseline.fold_to_turn_bet
    adj_fold_river = baseline.fold_to_river_bet
    adj_xr_freq = baseline.check_raise_frequency
    adj_value_freq = baseline.value_bet_frequency
    adj_bluff_freq = baseline.bluff_frequency

    # Apply each exploit
    for exploit in POPULATION_EXPLOITS:
        if exploit.applied_to == "cbet_sizing":
            adj_cbet_sizing *= 1 + exploit.adjustment
        elif exploit.applied_to == "bluff_frequency":
            adj_bluff_freq = max(0, adj_bluff_freq + exploit.adjustment)
        elif exploit.applied_to == "fold_to_river_bet":
            adj_fold_river = min(0.7, adj_fold_river + exploit.adjustment)

    # Cap values at reasonable ranges
    adj_cbet_sizing = min(1.0, max(0.25, adj_cbet_sizing))
    adj_bluff_freq = min(0.2, max(0.02, adj_bluff_freq))

    return AdjustedStrategy(
        baseline=baseline,
        exploits_applied=POPULATION_EXPLOITS,
        adj_cbet_frequency=adj_cbet_freq,
        adj_cbet_sizing=adj_cbet_sizing,
        adj_fold_to_cbet=adj_fold_cbet,
        adj_fold_to_turn=adj_fold_turn,
        adj_fold_to_river=adj_fold_river,
        adj_xr_frequency=adj_xr_freq,
        adj_value_bet_freq=adj_value_freq,
        adj_bluff_freq=adj_bluff_freq,
    )


def _snap_to_button(sizing: float) -> tuple[float, str]:
    """Snap sizing to nearest available button (1-4)."""
    if sizing <= 0.50:
        return SIZING_1, "1"
    elif sizing <= 0.73:
        return SIZING_2, "2"
    elif sizing <= 0.90:
        return SIZING_3, "3"
    else:
        return SIZING_4, "4"


def get_cbet_recommendation(
    texture: BoardTexture,
    in_position: bool,
    opponent_count: int,
    has_value: bool,
) -> tuple[bool, float, str, str]:
    """
    Get c-bet recommendation with exploits applied, mapped to button.

    Args:
        texture: Board texture
        in_position: Whether we're in position
        opponent_count: Number of opponents
        has_value: Whether we have value (pair+)

    Returns:
        Tuple of (should_cbet, sizing, reason, button_label)
    """
    baseline = get_gto_baseline(texture)
    adjusted = apply_2nl_exploits(baseline)

    # Adjust frequency for multiway
    if opponent_count > 1:
        freq_mult = 0.7 if opponent_count == 2 else 0.5
        cbet_freq = adjusted.adj_cbet_frequency * freq_mult
    else:
        cbet_freq = adjusted.adj_cbet_frequency

    # Adjust for position
    if not in_position:
        cbet_freq *= 0.85  # C-bet less OOP

    # With value, c-bet more often and size up one level
    if has_value:
        cbet_freq = min(0.95, cbet_freq * 1.2)
        # Size up: 1 -> 2, 2 -> 3, 3 -> 4
        if adjusted.adj_cbet_sizing <= SIZING_1:
            target_sizing = SIZING_2
        elif adjusted.adj_cbet_sizing <= SIZING_2:
            target_sizing = SIZING_3
        else:
            target_sizing = SIZING_4
        sizing, button = _snap_to_button(target_sizing)
        reason = f"Value c-bet on {texture.value} board"
    else:
        sizing, button = _snap_to_button(adjusted.adj_cbet_sizing)
        reason = f"GTO c-bet on {texture.value} board"

    # Multiway: size up for protection
    if opponent_count > 1 and has_value:
        if sizing < SIZING_3:
            sizing, button = SIZING_3, "3"
            reason = "Size up multiway"

    # Should we c-bet?
    should_cbet = has_value or (cbet_freq > 0.5 and opponent_count == 1)

    return should_cbet, sizing, reason, button


def get_defense_recommendation(
    texture: BoardTexture,
    street: str,
    bet_size_pct: float,
    hand_strength: str,  # 'strong', 'medium', 'weak'
    facing_raise: bool = False,
) -> tuple[str, str]:
    """
    Get defense recommendation against a bet.

    Args:
        texture: Board texture
        street: Current street ('flop', 'turn', 'river')
        bet_size_pct: Bet size as % of pot
        hand_strength: How strong our hand is
        facing_raise: Whether facing a raise (vs bet)

    Returns:
        Tuple of (action, reason)
    """
    # River special case - 2NL rarely bluffs
    if street == "river":
        if facing_raise:
            # "A raise on the river is ALWAYS the nuts"
            if hand_strength == "strong":
                return "call", "Call strong hand vs river raise (cautious)"
            return "fold", "Fold to river raise - 2NL always has it"

        if hand_strength == "strong":
            return "call", "Call with strong hand"
        elif hand_strength == "medium":
            if bet_size_pct <= 0.5:
                return "call", "Call medium hand vs small river bet"
            return "fold", "Fold medium to large river bet at 2NL"
        else:
            return "fold", "Fold weak to river bet - they have it"

    # Turn
    if street == "turn":
        if facing_raise:
            if hand_strength == "strong":
                return "call", "Call strong hand vs turn raise"
            return "fold", "Fold to turn raise - they have two pair+"

        if hand_strength in ("strong", "medium"):
            return "call", f"Continue with {hand_strength} on turn"
        return "fold", "Give up weak on turn"

    # Flop
    if hand_strength == "strong":
        return "raise", "Raise for value on flop"
    elif hand_strength == "medium":
        return "call", "Continue with medium on flop"
    else:
        if bet_size_pct <= 0.35:
            return "call", "Float small flop bet"
        return "fold", "Fold weak to flop bet"


def get_value_bet_recommendation(
    street: str,
    hand_strength: str,
    action_board: bool = False,
) -> tuple[bool, float, str, str]:
    """
    Get value betting recommendation mapped to button.

    Args:
        street: Current street
        hand_strength: Hand strength category
        action_board: Whether board is action (completed draws)

    Returns:
        Tuple of (should_bet, sizing_pct, reason, button_label)
    """
    # River value betting
    if street == "river":
        if hand_strength == "strong":
            if action_board:
                # Use pot on action rivers - fish can't fold
                return True, SIZING_4, "Pot on action river - 2NL can't fold", "4"
            return True, SIZING_3, "Thick value river", "3"
        elif hand_strength == "medium":
            return True, SIZING_2, "Thin value - 2NL calls light", "2"
        return False, 0, "No value bet with weak", ""

    # Turn value betting
    if street == "turn":
        if hand_strength in ("strong", "medium"):
            return True, SIZING_2, "Continue value on turn", "2"
        return False, 0, "Check back weak on turn", ""

    # Flop - use button 2 for value
    if hand_strength in ("strong", "medium"):
        return True, SIZING_2, "Value bet flop", "2"
    return False, 0, "Check flop without value", ""


def should_bluff_at_2nl(
    street: str,
    opponent_count: int,
    has_blockers: bool,
    previous_aggression: bool,
) -> tuple[bool, str]:
    """
    Determine if bluffing is advisable at 2NL.

    Generally: Don't bluff at 2NL, especially river.

    Args:
        street: Current street
        opponent_count: Number of opponents
        has_blockers: Whether we have nut blockers
        previous_aggression: Whether we were aggressive earlier

    Returns:
        Tuple of (should_bluff, reason)
    """
    # Never bluff river at 2NL
    if street == "river":
        return False, "Never bluff river at 2NL - they call everything"

    # Never bluff multiway
    if opponent_count > 1:
        return False, "Never bluff multiway at 2NL"

    # Flop c-bet bluff is okay
    if street == "flop":
        if has_blockers:
            return True, "Flop c-bet bluff okay with blockers"
        return True, "One and done flop c-bet bluff okay"

    # Turn - very selective
    if street == "turn":
        if has_blockers and previous_aggression:
            return True, "Selective turn barrel with blockers (rare)"
        return False, "Don't barrel turn without strong draw"

    return False, "Default: don't bluff at 2NL"


def get_exploit_summary() -> list[str]:
    """
    Get human-readable summary of exploits being applied.

    Returns:
        List of exploit descriptions
    """
    return [
        "Size up value bets - 2NL players call too much",
        "Reduce bluff frequency - 2NL doesn't fold",
        "Fold more to river aggression - 2NL rarely bluffs river",
        "Believe raises - 2NL raises are almost always value",
        "Isolate limpers wider - 2NL limps too much with weak hands",
        "Don't slow play - 2NL will check back made hands",
        "Value bet thin - 2NL calls with weak pairs",
        "Overbet action rivers - 2NL can't fold straights/flushes",
    ]


def get_position_adjustment(in_position: bool) -> dict[str, float]:
    """
    Get frequency adjustments based on position.

    Args:
        in_position: Whether we're in position

    Returns:
        Dict of frequency adjustments
    """
    if in_position:
        return {
            "cbet_frequency": 1.1,  # C-bet 10% more IP
            "bluff_frequency": 1.0,  # No change
            "call_frequency": 1.1,  # Can call wider IP
        }
    else:
        return {
            "cbet_frequency": 0.85,  # C-bet 15% less OOP
            "bluff_frequency": 0.7,  # Bluff 30% less OOP
            "call_frequency": 0.9,  # Tighter calling range OOP
        }
