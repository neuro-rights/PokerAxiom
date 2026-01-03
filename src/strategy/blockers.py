"""
Blocker analysis for poker strategy.

Blockers affect the likelihood of opponents holding certain hands.
Key blocker concepts:

- Nut blockers: Having the Ace of a flush suit blocks nut flushes
- Set blockers: Having one card of a rank reduces opponent's set combos
- Straight blockers: Holding key cards for straights

Good bluff candidates often have:
- Blockers to opponent's value hands (nuts)
- Few blockers to opponent's bluffing hands (draws that missed)
"""

from collections import Counter
from dataclasses import dataclass

from .hand_evaluator import get_rank_value, parse_card


@dataclass
class BlockerAnalysis:
    """
    Analysis of how hero's cards block opponent's range.

    Used for:
    - Selecting bluff candidates
    - Evaluating call decisions
    - Understanding range interactions
    """

    # Nut blockers
    blocks_nut_flush: bool  # Hero has Ace of flush suit
    blocks_second_nut_flush: bool  # Hero has King of flush suit
    blocks_nut_straight: bool  # Hero blocks top straight
    flush_suit_blocked: str | None  # Which suit we're blocking

    # Value hand blockers
    blocks_sets: int  # How many set combos we block (0-3)
    blocks_top_pair: bool  # Do we block top pair combos?
    blocks_two_pair: int  # How many two pair combos we block

    # Bluff assessment
    bluff_candidate_score: float  # 0.0-1.0, how good this hand is for bluffing
    call_candidate_score: float  # 0.0-1.0, how good for bluff catching

    # Detailed blockers
    blocked_nut_combos: int  # Estimated nut combos we block
    blocked_value_combos: int  # Estimated value combos we block
    blocked_bluff_combos: int  # Estimated bluff combos we block


def analyze_blockers(hero_cards: list[str], board_cards: list[str]) -> BlockerAnalysis:
    """
    Analyze how hero's cards block opponent's ranges.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: List of board cards

    Returns:
        BlockerAnalysis with detailed blocker information
    """
    if not hero_cards or len(hero_cards) < 2:
        return _empty_blocker_analysis()

    valid_board = [c for c in board_cards if c and c != "--"]
    if len(valid_board) < 3:
        return _empty_blocker_analysis()

    # Parse cards
    hero_parsed = [parse_card(c) for c in hero_cards]
    hero_ranks = [r for r, _ in hero_parsed]
    hero_suits = [s for _, s in hero_parsed]

    board_parsed = [parse_card(c) for c in valid_board]
    board_ranks = [r for r, _ in board_parsed]
    board_suits = [s for _, s in board_parsed]
    board_values = sorted([get_rank_value(r) for r in board_ranks], reverse=True)

    # Analyze flush blockers
    flush_analysis = _analyze_flush_blockers(hero_suits, hero_ranks, board_suits)

    # Analyze straight blockers
    straight_analysis = _analyze_straight_blockers(hero_ranks, board_values)

    # Analyze set blockers
    set_blocks = _count_set_blockers(hero_ranks, board_ranks)

    # Analyze top pair blockers
    blocks_top = board_ranks[0] in hero_ranks if board_ranks else False

    # Analyze two pair blockers
    two_pair_blocks = _count_two_pair_blockers(hero_ranks, board_ranks)

    # Calculate combo estimates
    nut_combos = flush_analysis["nut_combos_blocked"] + straight_analysis["nut_combos_blocked"]
    value_combos = set_blocks * 3 + (4 if blocks_top else 0) + two_pair_blocks
    bluff_combos = _estimate_bluff_combos_blocked(hero_ranks, hero_suits, board_parsed)

    # Calculate bluff/call scores
    bluff_score = _calculate_bluff_score(
        flush_analysis["blocks_nut_flush"],
        straight_analysis["blocks_nut_straight"],
        nut_combos,
        bluff_combos,
    )

    call_score = _calculate_call_score(
        bluff_combos,
        nut_combos,
        value_combos,
    )

    return BlockerAnalysis(
        blocks_nut_flush=flush_analysis["blocks_nut_flush"],
        blocks_second_nut_flush=flush_analysis["blocks_second_nut_flush"],
        blocks_nut_straight=straight_analysis["blocks_nut_straight"],
        flush_suit_blocked=flush_analysis["blocked_suit"],
        blocks_sets=set_blocks,
        blocks_top_pair=blocks_top,
        blocks_two_pair=two_pair_blocks,
        bluff_candidate_score=bluff_score,
        call_candidate_score=call_score,
        blocked_nut_combos=nut_combos,
        blocked_value_combos=value_combos,
        blocked_bluff_combos=bluff_combos,
    )


def has_nut_flush_blocker(hero_cards: list[str], board_cards: list[str]) -> bool:
    """
    Check if hero blocks the nut flush.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: Board cards

    Returns:
        True if hero has the Ace of the flush suit
    """
    valid_board = [c for c in board_cards if c and c != "--"]
    if len(valid_board) < 3:
        return False

    board_suits = [parse_card(c)[1] for c in valid_board]
    suit_counts = Counter(board_suits)

    # Find flush suit (3+ of same suit)
    for suit, count in suit_counts.items():
        if count >= 3:
            # Check if hero has Ace of this suit
            for card in hero_cards:
                rank, card_suit = parse_card(card)
                if card_suit == suit and rank == "A":
                    return True

    return False


def has_straight_blocker(hero_cards: list[str], board_cards: list[str]) -> bool:
    """
    Check if hero blocks key straight cards.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: Board cards

    Returns:
        True if hero blocks nut straight
    """
    analysis = analyze_blockers(hero_cards, board_cards)
    return analysis.blocks_nut_straight


def count_set_blockers(hero_cards: list[str], board_cards: list[str]) -> int:
    """
    Count how many set combos hero blocks.

    Having one card of a board rank removes 3 set combos for opponent.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: Board cards

    Returns:
        Number of board ranks we hold (0-3 typically)
    """
    hero_ranks = [parse_card(c)[0] for c in hero_cards]
    board_ranks = [parse_card(c)[0] for c in board_cards if c and c != "--"]

    blocks = 0
    for rank in set(board_ranks):
        if rank in hero_ranks:
            blocks += 1

    return blocks


def get_bluff_ev_adjustment(blocker_analysis: BlockerAnalysis) -> float:
    """
    Calculate EV adjustment for bluffing based on blockers.

    Blocking value hands increases bluff EV.
    Blocking bluffing hands decreases bluff EV.

    Args:
        blocker_analysis: BlockerAnalysis object

    Returns:
        EV adjustment multiplier (e.g., 1.2 = 20% better)
    """
    adjustment = 1.0

    # Blocking nuts is very good for bluffing
    if blocker_analysis.blocks_nut_flush:
        adjustment *= 1.3
    if blocker_analysis.blocks_second_nut_flush:
        adjustment *= 1.1
    if blocker_analysis.blocks_nut_straight:
        adjustment *= 1.2

    # Blocking many value combos is good
    if blocker_analysis.blocked_value_combos >= 10:
        adjustment *= 1.15
    elif blocker_analysis.blocked_value_combos >= 5:
        adjustment *= 1.08

    # Blocking bluff combos is bad (opponent more likely to have value)
    if blocker_analysis.blocked_bluff_combos >= 10:
        adjustment *= 0.85
    elif blocker_analysis.blocked_bluff_combos >= 5:
        adjustment *= 0.92

    return adjustment


def is_good_bluff_candidate(
    hero_cards: list[str],
    board_cards: list[str],
    threshold: float = 0.5,
) -> tuple[bool, str]:
    """
    Determine if this hand is a good bluffing candidate.

    Good bluffs have:
    - Blockers to opponent's value hands
    - Few blockers to opponent's bluffs/missed draws

    Args:
        hero_cards: List of 2 hole cards
        board_cards: Board cards
        threshold: Minimum score to be considered good (0-1)

    Returns:
        Tuple of (is_good_bluff, reasoning)
    """
    analysis = analyze_blockers(hero_cards, board_cards)

    if analysis.bluff_candidate_score >= threshold:
        reasons = []
        if analysis.blocks_nut_flush:
            reasons.append("blocks nut flush")
        if analysis.blocks_nut_straight:
            reasons.append("blocks nut straight")
        if analysis.blocks_sets >= 2:
            reasons.append(f"blocks {analysis.blocks_sets} set combos")

        reason_str = ", ".join(reasons) if reasons else "good blocker profile"
        return True, f"Good bluff candidate: {reason_str}"

    return False, "Poor bluff candidate: doesn't block enough value"


def is_good_call_candidate(
    hero_cards: list[str],
    board_cards: list[str],
    threshold: float = 0.5,
) -> tuple[bool, str]:
    """
    Determine if this hand is good for bluff catching.

    Good bluff catchers:
    - Block opponent's bluffs/missed draws
    - Don't block opponent's value (so opponent more likely bluffing)

    Args:
        hero_cards: List of 2 hole cards
        board_cards: Board cards
        threshold: Minimum score to be considered good (0-1)

    Returns:
        Tuple of (is_good_call, reasoning)
    """
    analysis = analyze_blockers(hero_cards, board_cards)

    if analysis.call_candidate_score >= threshold:
        return True, "Good bluff catcher: blocks opponent's bluffs"

    if analysis.blocked_bluff_combos > analysis.blocked_nut_combos:
        return True, "Decent bluff catcher: blocks more bluffs than value"

    return False, "Poor bluff catcher: blocks too much value"


# Private helper functions


def _empty_blocker_analysis() -> BlockerAnalysis:
    """Return empty blocker analysis for incomplete data."""
    return BlockerAnalysis(
        blocks_nut_flush=False,
        blocks_second_nut_flush=False,
        blocks_nut_straight=False,
        flush_suit_blocked=None,
        blocks_sets=0,
        blocks_top_pair=False,
        blocks_two_pair=0,
        bluff_candidate_score=0.0,
        call_candidate_score=0.0,
        blocked_nut_combos=0,
        blocked_value_combos=0,
        blocked_bluff_combos=0,
    )


def _analyze_flush_blockers(
    hero_suits: list[str],
    hero_ranks: list[str],
    board_suits: list[str],
) -> dict:
    """Analyze flush blocker effects."""
    result = {
        "blocks_nut_flush": False,
        "blocks_second_nut_flush": False,
        "blocked_suit": None,
        "nut_combos_blocked": 0,
    }

    suit_counts = Counter(board_suits)

    for suit, count in suit_counts.items():
        if count >= 3:
            result["blocked_suit"] = suit

            # Check if hero has A or K of this suit
            for rank, card_suit in zip(hero_ranks, hero_suits):
                if card_suit == suit:
                    if rank == "A":
                        result["blocks_nut_flush"] = True
                        result["nut_combos_blocked"] += 4  # Blocks Ax flush combos
                    elif rank == "K":
                        result["blocks_second_nut_flush"] = True
                        result["nut_combos_blocked"] += 2

            break  # Only one flush suit matters

    return result


def _analyze_straight_blockers(hero_ranks: list[str], board_values: list[int]) -> dict:
    """Analyze straight blocker effects."""
    result = {
        "blocks_nut_straight": False,
        "nut_combos_blocked": 0,
    }

    if len(board_values) < 3:
        return result

    # Find highest possible straight
    # Add ace-low for wheel check
    all_values = sorted(board_values)
    if 14 in all_values:
        all_values = [1] + all_values

    # Check for 3+ connected cards
    for i in range(len(all_values) - 2):
        window = all_values[i : i + 3]
        if window[-1] - window[0] <= 4:
            # Straight possible, find nut straight cards
            nut_cards = _get_nut_straight_cards(window)

            hero_values = [get_rank_value(r) for r in hero_ranks]
            for nut_val in nut_cards:
                if nut_val in hero_values:
                    result["blocks_nut_straight"] = True
                    result["nut_combos_blocked"] += 4
                    break

            break

    return result


def _get_nut_straight_cards(connected_values: list[int]) -> list[int]:
    """Get the card values needed for the nut straight."""
    max_val = max(connected_values)

    nut_cards = []

    # Cards that complete highest straight
    for needed in range(max_val + 1, min(max_val + 3, 15)):
        if needed not in connected_values:
            nut_cards.append(needed)

    return nut_cards


def _count_set_blockers(hero_ranks: list[str], board_ranks: list[str]) -> int:
    """Count how many set combos hero blocks."""
    blocks = 0
    board_unique = set(board_ranks)

    for rank in board_unique:
        if rank in hero_ranks:
            blocks += 1

    return blocks


def _count_two_pair_blockers(hero_ranks: list[str], board_ranks: list[str]) -> int:
    """Estimate two pair combos blocked."""
    blocks = 0

    # For each board rank we hold, we block some two pair combos
    for rank in hero_ranks:
        if rank in board_ranks:
            # Blocking top 2 is more significant
            if board_ranks and rank == board_ranks[0]:
                blocks += 6  # More combos for top pair
            else:
                blocks += 3

    return blocks


def _estimate_bluff_combos_blocked(
    hero_ranks: list[str],
    hero_suits: list[str],
    board_parsed: list[tuple[str, str]],
) -> int:
    """Estimate how many bluff/draw combos we block."""
    blocked = 0

    board_suits = [s for _, s in board_parsed]
    suit_counts = Counter(board_suits)

    # If we have cards of the flush suit, we block missed flush draws
    for suit, count in suit_counts.items():
        if count >= 3:
            for card_suit in hero_suits:
                if card_suit == suit:
                    blocked += 3  # Block some missed flush draw combos

    # If we hold cards that would be part of missed straight draws
    # This is approximate
    for rank in hero_ranks:
        val = get_rank_value(rank)
        if 6 <= val <= 10:  # Middle connectors block draws
            blocked += 2

    return blocked


def _calculate_bluff_score(
    blocks_nut_flush: bool,
    blocks_nut_straight: bool,
    nut_combos_blocked: int,
    bluff_combos_blocked: int,
) -> float:
    """Calculate bluff candidate score (0-1)."""
    score = 0.3  # Base score

    if blocks_nut_flush:
        score += 0.25
    if blocks_nut_straight:
        score += 0.15

    # Bonus for blocking many nut combos
    score += min(nut_combos_blocked * 0.02, 0.2)

    # Penalty for blocking bluff combos
    score -= min(bluff_combos_blocked * 0.015, 0.15)

    return max(0.0, min(1.0, score))


def _calculate_call_score(
    bluff_combos_blocked: int,
    nut_combos_blocked: int,
    value_combos_blocked: int,
) -> float:
    """Calculate call/bluff catcher score (0-1)."""
    score = 0.4  # Base score

    # Good: blocking bluff combos (opponent less likely to be bluffing)
    score += min(bluff_combos_blocked * 0.03, 0.25)

    # Bad: blocking value combos (opponent more likely to be bluffing)
    # Wait - this is actually GOOD for bluff catching
    # If we block value, opponent is more likely bluffing when they bet
    # But actually no - if we block their bluffs, they're more likely to have value
    # This is confusing, let's simplify:

    # For bluff catching: we want to NOT block their value
    # Because if they have value despite us not blocking it, we're beat
    # And if they're bluffing, we can catch it

    # Penalty for blocking nuts (they're less likely to have it)
    score -= min(nut_combos_blocked * 0.02, 0.15)

    return max(0.0, min(1.0, score))
