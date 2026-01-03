"""
Enhanced board texture analysis for poker strategy.

Provides comprehensive board analysis beyond simple DRY/MEDIUM/WET classification,
including connectedness, flush potential, straight potential, and c-bet guidance.
"""

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from .actions import BoardTexture
from .hand_evaluator import RANK_VALUES, get_rank_value, parse_card


class FlushPotential(Enum):
    """Flush draw potential on the board."""

    NONE = "none"  # Rainbow or no flush possible
    BACKDOOR = "backdoor"  # 2 of same suit (backdoor draw)
    DRAW = "draw"  # 3 of same suit (flush draw possible)
    COMPLETE = "complete"  # 4+ of same suit (flush likely made)


class StraightPotential(Enum):
    """Straight draw potential on the board."""

    NONE = "none"  # Disconnected, no straight possible
    BACKDOOR = "backdoor"  # Backdoor straight draw
    GUTSHOT = "gutshot"  # Gutshot straight draws possible
    OESD = "oesd"  # Open-ended straight draws possible
    COMPLETE = "complete"  # 4+ connected, straight likely made


@dataclass
class BoardAnalysis:
    """
    Comprehensive board texture analysis.

    Provides detailed information about board texture for strategic decisions.
    """

    # Basic texture (backwards compatible with existing code)
    texture_category: BoardTexture

    # Detailed metrics
    connectedness: float  # 0.0-1.0, how connected the board is
    flush_potential: FlushPotential
    straight_potential: StraightPotential

    # Card characteristics
    high_card_rank: str  # Highest card on board (A, K, Q, etc.)
    high_card_value: int  # Numeric value of highest card
    paired_board: bool  # Does board have a pair?
    pair_rank: str | None  # Which rank is paired (e.g., 'K' for K-K-7), None if not paired
    monotone: bool  # All same suit (flop only)
    rainbow: bool  # All different suits (flop only)
    broadway_count: int  # Count of broadway cards (T-A)

    # Strategic implications
    cbet_frequency: float  # Recommended c-bet frequency (0-1)
    cbet_sizing: float  # Recommended c-bet sizing (fraction of pot)
    check_raise_vulnerability: float  # 0-1, how vulnerable to check-raises

    # Dynamic evaluation
    scare_cards: list[str]  # Cards that complete draws
    brick_cards: list[str]  # Safe cards (blanks)


@dataclass
class TurnAnalysis:
    """Analysis of how the turn card changes the board."""

    turn_card: str
    is_scare_card: bool  # Does turn complete draws?
    completed_flush: bool  # Did turn complete a flush draw?
    completed_straight: bool  # Did turn complete a straight draw?
    brought_pair: bool  # Did turn pair the board?
    is_overcard: bool  # Is turn higher than flop high card?
    texture_change: str  # 'improved', 'neutral', 'dangerous'


@dataclass
class RiverAnalysis:
    """Analysis of how the river card changes the board."""

    river_card: str
    is_scare_card: bool
    completed_flush: bool
    completed_straight: bool
    brought_pair: bool
    is_action_river: bool  # Significant draw completing river
    texture_change: str


def analyze_flop(board_cards: list[str]) -> BoardAnalysis:
    """
    Analyze flop texture for strategic decisions.

    Args:
        board_cards: List of 3-5 board cards

    Returns:
        BoardAnalysis with comprehensive texture information
    """
    # Filter valid cards (first 3 for flop)
    valid_cards = [c for c in board_cards if c and c != "--"][:3]

    if len(valid_cards) < 3:
        # Return default analysis for incomplete boards
        return BoardAnalysis(
            texture_category=BoardTexture.MEDIUM,
            connectedness=0.0,
            flush_potential=FlushPotential.NONE,
            straight_potential=StraightPotential.NONE,
            high_card_rank="?",
            high_card_value=0,
            paired_board=False,
            pair_rank=None,
            monotone=False,
            rainbow=False,
            broadway_count=0,
            cbet_frequency=0.5,
            cbet_sizing=0.5,
            check_raise_vulnerability=0.3,
            scare_cards=[],
            brick_cards=[],
        )

    # Parse cards
    parsed = [parse_card(c) for c in valid_cards]
    ranks = [r for r, _ in parsed]
    suits = [s for _, s in parsed]
    values = sorted([get_rank_value(r) for r in ranks], reverse=True)

    # Basic card analysis
    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    paired_board = max(rank_counts.values()) >= 2
    # Find which rank is paired (if any)
    pair_rank = None
    if paired_board:
        for rank, count in rank_counts.items():
            if count >= 2:
                pair_rank = rank
                break
    monotone = len(set(suits)) == 1
    rainbow = len(set(suits)) == 3

    high_card_rank = max(ranks, key=get_rank_value)
    high_card_value = get_rank_value(high_card_rank)

    broadway_ranks = {"A", "K", "Q", "J", "T"}
    broadway_count = sum(1 for r in ranks if r in broadway_ranks)

    # Flush potential
    max_suit_count = max(suit_counts.values())
    if max_suit_count >= 3:
        flush_potential = FlushPotential.DRAW
    elif max_suit_count == 2:
        flush_potential = FlushPotential.BACKDOOR
    else:
        flush_potential = FlushPotential.NONE

    # Straight potential (connectedness)
    connectedness, straight_potential = _calculate_connectedness(values)

    # Texture category (backwards compatible)
    texture_category = _categorize_texture(
        flush_potential, straight_potential, connectedness, paired_board
    )

    # C-bet guidance based on texture
    cbet_frequency, cbet_sizing = _calculate_cbet_guidance(
        texture_category, high_card_value, paired_board, broadway_count
    )

    # Check-raise vulnerability
    xr_vulnerability = _calculate_xr_vulnerability(
        flush_potential, straight_potential, paired_board
    )

    # Scare and brick cards
    scare_cards, brick_cards = _calculate_dynamic_cards(
        values, suits, flush_potential, straight_potential
    )

    return BoardAnalysis(
        texture_category=texture_category,
        connectedness=connectedness,
        flush_potential=flush_potential,
        straight_potential=straight_potential,
        high_card_rank=high_card_rank,
        high_card_value=high_card_value,
        paired_board=paired_board,
        pair_rank=pair_rank,
        monotone=monotone,
        rainbow=rainbow,
        broadway_count=broadway_count,
        cbet_frequency=cbet_frequency,
        cbet_sizing=cbet_sizing,
        check_raise_vulnerability=xr_vulnerability,
        scare_cards=scare_cards,
        brick_cards=brick_cards,
    )


def analyze_turn_change(
    flop_analysis: BoardAnalysis,
    board_cards: list[str],
) -> TurnAnalysis:
    """
    Analyze how the turn card changes the board texture.

    Args:
        flop_analysis: Analysis of the flop
        board_cards: All 4 board cards including turn

    Returns:
        TurnAnalysis with turn-specific information
    """
    valid_cards = [c for c in board_cards if c and c != "--"]
    if len(valid_cards) < 4:
        return TurnAnalysis(
            turn_card="?",
            is_scare_card=False,
            completed_flush=False,
            completed_straight=False,
            brought_pair=False,
            is_overcard=False,
            texture_change="neutral",
        )

    turn_card = valid_cards[3]
    turn_rank, turn_suit = parse_card(turn_card)
    turn_value = get_rank_value(turn_rank)

    # Check if turn completes flush
    all_suits = [parse_card(c)[1] for c in valid_cards]
    suit_counts = Counter(all_suits)
    completed_flush = max(suit_counts.values()) >= 4

    # Check if turn completes straight
    all_values = sorted([get_rank_value(parse_card(c)[0]) for c in valid_cards])
    completed_straight = _check_straight_possible(all_values)

    # Check if turn pairs the board
    all_ranks = [parse_card(c)[0] for c in valid_cards]
    rank_counts = Counter(all_ranks)
    brought_pair = not flop_analysis.paired_board and max(rank_counts.values()) >= 2

    # Check if overcard
    is_overcard = turn_value > flop_analysis.high_card_value

    # Is this a scare card?
    is_scare_card = (
        completed_flush
        or completed_straight
        or is_overcard
        or turn_rank in flop_analysis.scare_cards
    )

    # Texture change assessment
    if completed_flush or completed_straight:
        texture_change = "dangerous"
    elif is_scare_card:
        texture_change = "improved"  # For draws
    else:
        texture_change = "neutral"

    return TurnAnalysis(
        turn_card=turn_card,
        is_scare_card=is_scare_card,
        completed_flush=completed_flush,
        completed_straight=completed_straight,
        brought_pair=brought_pair,
        is_overcard=is_overcard,
        texture_change=texture_change,
    )


def analyze_river_change(
    board_cards: list[str],
) -> RiverAnalysis:
    """
    Analyze how the river card affects the final board.

    Args:
        board_cards: All 5 board cards

    Returns:
        RiverAnalysis with river-specific information
    """
    valid_cards = [c for c in board_cards if c and c != "--"]
    if len(valid_cards) < 5:
        return RiverAnalysis(
            river_card="?",
            is_scare_card=False,
            completed_flush=False,
            completed_straight=False,
            brought_pair=False,
            is_action_river=False,
            texture_change="neutral",
        )

    river_card = valid_cards[4]
    turn_cards = valid_cards[:4]

    river_rank, river_suit = parse_card(river_card)

    # Check flush completion
    all_suits = [parse_card(c)[1] for c in valid_cards]
    turn_suits = [parse_card(c)[1] for c in turn_cards]
    suit_counts = Counter(all_suits)
    turn_suit_counts = Counter(turn_suits)

    completed_flush = max(suit_counts.values()) >= 4 and max(turn_suit_counts.values()) < 4

    # Check straight completion
    all_values = sorted([get_rank_value(parse_card(c)[0]) for c in valid_cards])
    turn_values = sorted([get_rank_value(parse_card(c)[0]) for c in turn_cards])

    has_straight_now = _check_straight_possible(all_values)
    had_straight_before = _check_straight_possible(turn_values)
    completed_straight = has_straight_now and not had_straight_before

    # Check pair
    all_ranks = [parse_card(c)[0] for c in valid_cards]
    turn_ranks = [parse_card(c)[0] for c in turn_cards]
    rank_counts = Counter(all_ranks)
    turn_rank_counts = Counter(turn_ranks)

    brought_pair = max(rank_counts.values()) > max(turn_rank_counts.values())

    # Is this an action river? (draw completing)
    is_action_river = completed_flush or completed_straight

    is_scare_card = is_action_river or brought_pair

    if is_action_river:
        texture_change = "dangerous"
    elif is_scare_card:
        texture_change = "improved"
    else:
        texture_change = "neutral"

    return RiverAnalysis(
        river_card=river_card,
        is_scare_card=is_scare_card,
        completed_flush=completed_flush,
        completed_straight=completed_straight,
        brought_pair=brought_pair,
        is_action_river=is_action_river,
        texture_change=texture_change,
    )


def is_draw_completing_card(card: str, board_cards: list[str]) -> bool:
    """
    Check if a card completes obvious draws on the board.

    Args:
        card: The card to check
        board_cards: Current board cards (without the card)

    Returns:
        True if card completes a flush or straight draw
    """
    if not card or card == "--":
        return False

    test_board = [c for c in board_cards if c and c != "--"] + [card]
    if len(test_board) < 4:
        return False

    card_rank, card_suit = parse_card(card)
    current_board = [c for c in board_cards if c and c != "--"]

    # Check if completes flush
    current_suits = [parse_card(c)[1] for c in current_board]
    suit_counts = Counter(current_suits)

    for suit, count in suit_counts.items():
        if count >= 3 and card_suit == suit:
            return True

    # Check if completes straight
    current_values = [get_rank_value(parse_card(c)[0]) for c in current_board]
    card_value = get_rank_value(card_rank)

    all_values = sorted(current_values + [card_value])
    if _check_straight_possible(all_values):
        # Check if straight wasn't already there
        if not _check_straight_possible(sorted(current_values)):
            return True

    return False


def get_scare_cards(board_cards: list[str]) -> list[str]:
    """
    Get list of cards that would be scare cards on this board.

    Args:
        board_cards: Current board cards

    Returns:
        List of rank strings that are scare cards
    """
    analysis = analyze_flop(board_cards)
    return analysis.scare_cards


def _calculate_connectedness(values: list[int]) -> tuple[float, StraightPotential]:
    """Calculate how connected the board is for straight draws."""
    if len(values) < 3:
        return 0.0, StraightPotential.NONE

    values = sorted(values)

    # Calculate total span between lowest and highest cards
    total_span = values[-1] - values[0]

    # Perfect connectivity: 3 cards spanning 2 (like 7-8-9)
    # Low connectivity: 3 cards spanning 10+ (like 2-7-K)

    if total_span <= 2:
        # Very connected (consecutive or one gap)
        connectedness = 1.0
        straight_potential = StraightPotential.OESD
    elif total_span <= 4:
        # Somewhat connected
        connectedness = 0.7
        straight_potential = StraightPotential.GUTSHOT
    elif total_span <= 6:
        # Slightly connected
        connectedness = 0.4
        straight_potential = StraightPotential.BACKDOOR
    else:
        # Disconnected
        connectedness = 0.2
        straight_potential = StraightPotential.NONE

    # Check for wheel potential (A-2-3-4-5)
    if 14 in values:  # Ace present
        low_values = [v for v in values if v <= 5] + [1]  # Ace as 1
        if len(low_values) >= 3:
            connectedness = max(connectedness, 0.5)
            if straight_potential == StraightPotential.NONE:
                straight_potential = StraightPotential.BACKDOOR

    return connectedness, straight_potential


def _categorize_texture(
    flush_potential: FlushPotential,
    straight_potential: StraightPotential,
    connectedness: float,
    paired_board: bool,
) -> BoardTexture:
    """Categorize board into DRY/MEDIUM/WET."""
    wet_factors = 0

    if flush_potential == FlushPotential.DRAW:
        wet_factors += 2
    elif flush_potential == FlushPotential.BACKDOOR:
        wet_factors += 0.5

    if straight_potential == StraightPotential.OESD:
        wet_factors += 2
    elif straight_potential == StraightPotential.GUTSHOT:
        wet_factors += 1
    elif straight_potential == StraightPotential.BACKDOOR:
        wet_factors += 0.5

    if connectedness >= 0.7:
        wet_factors += 1

    # Paired boards are slightly dryer (fewer combos)
    if paired_board:
        wet_factors -= 0.5

    if wet_factors >= 3:
        return BoardTexture.WET
    elif wet_factors >= 1:
        return BoardTexture.MEDIUM
    return BoardTexture.DRY


def _calculate_cbet_guidance(
    texture: BoardTexture,
    high_card_value: int,
    paired_board: bool,
    broadway_count: int,
) -> tuple[float, float]:
    """Calculate c-bet frequency and sizing based on texture."""
    # Base frequencies by texture
    base_freq = {
        BoardTexture.DRY: 0.70,  # C-bet often on dry boards
        BoardTexture.MEDIUM: 0.55,
        BoardTexture.WET: 0.40,  # More selective on wet boards
    }

    base_sizing = {
        BoardTexture.DRY: 0.33,  # Small on dry
        BoardTexture.MEDIUM: 0.55,
        BoardTexture.WET: 0.70,  # Large on wet for protection
    }

    freq = base_freq[texture]
    sizing = base_sizing[texture]

    # Adjustments
    # High card boards favor preflop aggressor
    if high_card_value >= 12:  # Q or higher
        freq += 0.05

    # Paired boards favor preflop aggressor
    if paired_board:
        freq += 0.10
        sizing -= 0.10  # Size down on paired boards

    # Broadway heavy boards favor aggressor range
    if broadway_count >= 2:
        freq += 0.05

    return min(freq, 0.85), max(sizing, 0.25)


def _calculate_xr_vulnerability(
    flush_potential: FlushPotential,
    straight_potential: StraightPotential,
    paired_board: bool,
) -> float:
    """Calculate vulnerability to check-raises."""
    vulnerability = 0.2  # Base vulnerability

    # Wet boards have more check-raise opportunities
    if flush_potential == FlushPotential.DRAW:
        vulnerability += 0.2
    if straight_potential == StraightPotential.OESD:
        vulnerability += 0.2
    elif straight_potential == StraightPotential.GUTSHOT:
        vulnerability += 0.1

    # Paired boards have less XR (fewer combos)
    if paired_board:
        vulnerability -= 0.1

    return max(0.1, min(0.7, vulnerability))


def _calculate_dynamic_cards(
    values: list[int],
    suits: list[str],
    flush_potential: FlushPotential,
    straight_potential: StraightPotential,
) -> tuple[list[str], list[str]]:
    """Calculate which cards are scare cards vs bricks."""
    scare_cards = []
    brick_cards = []

    # All possible ranks
    all_ranks = list(RANK_VALUES.keys())

    suit_counts = Counter(suits)
    flush_suit = None
    if flush_potential == FlushPotential.DRAW:
        flush_suit = max(suit_counts, key=suit_counts.get)

    for rank in all_ranks:
        rank_value = get_rank_value(rank)
        is_scare = False

        # Flush completing card (any card of flush suit)
        if flush_suit:
            is_scare = True

        # Straight completing cards
        if straight_potential in (StraightPotential.OESD, StraightPotential.GUTSHOT):
            # Cards that could complete a straight
            min_val = min(values)
            max_val = max(values)

            # Cards at edges of connected boards
            if rank_value == min_val - 1 or rank_value == max_val + 1:
                is_scare = True

            # Cards that fill gaps
            for v in values:
                if abs(rank_value - v) == 2 and rank_value not in values:
                    is_scare = True

        # Overcards to board
        if rank_value > max(values):
            is_scare = True

        if is_scare:
            scare_cards.append(rank)
        else:
            brick_cards.append(rank)

    return scare_cards, brick_cards


def _check_straight_possible(values: list[int]) -> bool:
    """Check if a straight is possible with these card values."""
    if len(values) < 4:
        return False

    # Add ace-low for wheel check
    if 14 in values:
        values = values + [1]

    unique_values = sorted(set(values))

    # Check for 4+ cards in a row or within span of 5
    for i in range(len(unique_values) - 3):
        window = unique_values[i : i + 4]
        if window[-1] - window[0] <= 4:
            return True

    return False


def is_safe_river_for_thin_value(river_analysis: RiverAnalysis) -> bool:
    """
    Check if river is 'safe' for thin value betting with marginal hands.

    A safe river is one where no obvious draws completed, making it more
    likely our second pair or weak top pair is still good.

    Based on micro stakes strategy: thin value bet on safe boards because
    opponents call too much with worse.

    Args:
        river_analysis: RiverAnalysis from analyze_river_change()

    Returns:
        True if river is safe for thin value betting
    """
    # Unsafe conditions - draws completed or board paired
    if river_analysis.completed_flush:
        return False
    if river_analysis.completed_straight:
        return False
    if river_analysis.brought_pair:
        return False  # Full house possible
    if river_analysis.is_action_river:
        return False

    return True


def is_safe_board_for_thin_value(board_cards: list[str]) -> bool:
    """
    Check if the final 5-card board is safe for thin value betting.

    This is a simpler check that doesn't require RiverAnalysis,
    useful when we just have the board cards.

    Args:
        board_cards: List of 5 board cards

    Returns:
        True if board is safe for thin value
    """
    valid_cards = [c for c in board_cards if c and c != "--"]
    if len(valid_cards) < 5:
        return False

    # Parse all cards
    parsed = [parse_card(c) for c in valid_cards]
    ranks = [r for r, _ in parsed]
    suits = [s for _, s in parsed]
    values = [get_rank_value(r) for r in ranks]

    # Check for flush (4+ of same suit)
    suit_counts = Counter(suits)
    if max(suit_counts.values()) >= 4:
        return False  # Flush possible

    # Check for 4-straight (4 cards within span of 4)
    unique_values = sorted(set(values))
    # Add ace-low for wheel
    if 14 in unique_values:
        unique_values = [1] + unique_values

    for i in range(len(unique_values) - 3):
        window = unique_values[i : i + 4]
        if window[-1] - window[0] <= 4:
            return False  # Straight possible

    # Check for paired board (full house possible)
    rank_counts = Counter(ranks)
    if max(rank_counts.values()) >= 2:
        return False  # Paired board - full house threat

    return True
