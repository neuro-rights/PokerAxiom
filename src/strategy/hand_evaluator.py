"""
Hand evaluation for poker strategy decisions.

Provides preflop hand categorization and postflop hand strength evaluation.
"""

from collections import Counter
from dataclasses import dataclass
from enum import Enum, IntEnum


class PreflopCategory(Enum):
    """Preflop hand strength categories for opening ranges."""

    PREMIUM = "premium"  # AA, KK, QQ, AKs, AKo
    STRONG = "strong"  # JJ, TT, AQs, AQo, AJs, KQs
    PLAYABLE = "playable"  # 99-77, ATs-A9s, KJs, QJs, JTs, T9s
    MARGINAL = "marginal"  # 66-22, A8s-A2s, suited connectors, suited gappers
    WEAK = "weak"  # Everything else


class HandStrength(IntEnum):
    """Made hand strength ranking (IntEnum for comparisons)."""

    NOTHING = 0
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_KIND = 8
    STRAIGHT_FLUSH = 9


class PairType(Enum):
    """Pair strength classification relative to board."""

    OVERPAIR = "overpair"  # Pocket pair > all board cards (QQ on J-7-2)
    TOP_PAIR = "top_pair"  # Paired highest board card (AK on K-7-2)
    SECOND_PAIR = "second_pair"  # Paired 2nd highest (KJ on A-J-5)
    UNDERPAIR = "underpair"  # Pocket pair < highest board card (88 on Q-J-T)
    BOTTOM_PAIR = "bottom_pair"  # Paired lowest board card
    BOARD_PAIR = "board_pair"  # Pair entirely on board (no hole card)


@dataclass
class Draw:
    """Represents a drawing hand."""

    draw_type: str  # 'flush_draw', 'oesd', 'gutshot', 'backdoor_flush'
    outs: int  # Number of outs
    cards_needed: int  # Cards needed to complete (1 or 2)
    description: str  # Human readable description


@dataclass
class BoardDanger:
    """Board danger assessment for strategy decisions."""

    four_flush: bool = False  # 4+ cards of same suit on board
    four_straight: bool = False  # 4+ cards to a straight on board
    hero_has_blocker: bool = False  # Hero has a card of the flush suit
    danger_level: str = "low"  # "low", "medium", "high", "extreme"


# Rank ordering for comparisons (A=14 for high, but also 1 for low straight)
RANK_VALUES = {
    "A": 14,
    "K": 13,
    "Q": 12,
    "J": 11,
    "T": 10,
    "9": 9,
    "8": 8,
    "7": 7,
    "6": 6,
    "5": 5,
    "4": 4,
    "3": 3,
    "2": 2,
}

# Broadway ranks (T through A)
BROADWAY_RANKS = {"A", "K", "Q", "J", "T"}


def parse_card(card: str) -> tuple[str, str]:
    """
    Parse a card string into rank and suit.

    Args:
        card: Card string like 'As', 'Kh', '2d', 'Tc'

    Returns:
        Tuple of (rank, suit)
    """
    if len(card) != 2:
        return ("?", "?")
    return card[0].upper(), card[1].lower()


def get_rank_value(rank: str) -> int:
    """Get numeric value for a rank."""
    return RANK_VALUES.get(rank.upper(), 0)


def is_suited(card1: str, card2: str) -> bool:
    """Check if two cards are suited."""
    _, suit1 = parse_card(card1)
    _, suit2 = parse_card(card2)
    return suit1 == suit2


def is_pair(card1: str, card2: str) -> bool:
    """Check if two cards form a pocket pair."""
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    return rank1 == rank2


def is_broadway(card1: str, card2: str) -> bool:
    """Check if both cards are broadway (T-A)."""
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    return rank1 in BROADWAY_RANKS and rank2 in BROADWAY_RANKS


def is_connector(card1: str, card2: str) -> bool:
    """Check if cards are connected (adjacent ranks)."""
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    v1, v2 = get_rank_value(rank1), get_rank_value(rank2)
    gap = abs(v1 - v2)
    # Also check A-2 as connected
    if {rank1, rank2} == {"A", "2"}:
        return True
    return gap == 1


def is_one_gapper(card1: str, card2: str) -> bool:
    """Check if cards are one-gappers (one rank between)."""
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    v1, v2 = get_rank_value(rank1), get_rank_value(rank2)
    gap = abs(v1 - v2)
    return gap == 2


def get_high_card(card1: str, card2: str) -> str:
    """Get the higher card."""
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    v1, v2 = get_rank_value(rank1), get_rank_value(rank2)
    return card1 if v1 >= v2 else card2


def categorize_preflop(card1: str, card2: str) -> PreflopCategory:
    """
    Categorize a preflop hand based on the 2NL TAG strategy.

    Categories based on the strategy research:
    - PREMIUM: AA, KK, QQ, AKs, AKo (always 3-bet, always play)
    - STRONG: JJ, TT, AQs, AQo, AJs, KQs (open all positions, 3-bet some)
    - PLAYABLE: 99-77, ATs-A9s, KJs, QJs, JTs, T9s (open MP+)
    - MARGINAL: 66-22, A8s-A2s, suited connectors/gappers (open CO/BTN)
    - WEAK: Everything else (fold)

    Args:
        card1: First hole card (e.g., 'As')
        card2: Second hole card (e.g., 'Kh')

    Returns:
        PreflopCategory enum value
    """
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    suited = is_suited(card1, card2)

    # Sort ranks by value (high to low)
    v1, v2 = get_rank_value(rank1), get_rank_value(rank2)
    if v1 < v2:
        rank1, rank2 = rank2, rank1
        v1, v2 = v2, v1

    # Premium: AA, KK, QQ, AKs, AKo
    if rank1 == rank2 and rank1 in ("A", "K", "Q"):
        return PreflopCategory.PREMIUM
    if rank1 == "A" and rank2 == "K":
        return PreflopCategory.PREMIUM

    # Strong: JJ, TT, AQ, AJs, KQs
    if rank1 == rank2 and rank1 in ("J", "T"):
        return PreflopCategory.STRONG
    if rank1 == "A" and rank2 == "Q":
        return PreflopCategory.STRONG
    if rank1 == "A" and rank2 == "J" and suited:
        return PreflopCategory.STRONG
    if rank1 == "K" and rank2 == "Q" and suited:
        return PreflopCategory.STRONG

    # Playable: 99-77, ATs-A9s, KJs, QJs, JTs, T9s
    if rank1 == rank2 and v1 >= 7 and v1 <= 9:
        return PreflopCategory.PLAYABLE
    if rank1 == "A" and v2 >= 9 and v2 <= 10 and suited:
        return PreflopCategory.PLAYABLE
    if rank1 == "K" and rank2 == "J" and suited:
        return PreflopCategory.PLAYABLE
    if rank1 == "Q" and rank2 == "J" and suited:
        return PreflopCategory.PLAYABLE
    if rank1 == "J" and rank2 == "T" and suited:
        return PreflopCategory.PLAYABLE
    if rank1 == "T" and rank2 == "9" and suited:
        return PreflopCategory.PLAYABLE
    # KQo, AJo also playable
    if rank1 == "K" and rank2 == "Q":
        return PreflopCategory.PLAYABLE
    if rank1 == "A" and rank2 == "J":
        return PreflopCategory.PLAYABLE

    # Marginal: 66-22, A8s-A2s, suited connectors, suited one-gappers
    if rank1 == rank2 and v1 >= 2 and v1 <= 6:
        return PreflopCategory.MARGINAL
    if rank1 == "A" and v2 >= 2 and v2 <= 8 and suited:
        return PreflopCategory.MARGINAL
    # Suited connectors 98s-54s
    if suited and is_connector(card1, card2) and v1 <= 9 and v2 >= 4:
        return PreflopCategory.MARGINAL
    # Suited one-gappers K9s, Q9s, J9s, T8s, 97s, 86s, 75s
    if suited and is_one_gapper(card1, card2) and v1 <= 13 and v2 >= 5:
        return PreflopCategory.MARGINAL
    # ATo, KJo
    if rank1 == "A" and rank2 == "T":
        return PreflopCategory.MARGINAL
    if rank1 == "K" and rank2 == "J":
        return PreflopCategory.MARGINAL

    # Everything else is weak
    return PreflopCategory.WEAK


def get_hand_notation(card1: str, card2: str) -> str:
    """
    Get standard poker notation for a hand (e.g., 'AKs', 'QQ', 'T9o').

    Args:
        card1: First hole card
        card2: Second hole card

    Returns:
        Standard notation string
    """
    rank1, _ = parse_card(card1)
    rank2, _ = parse_card(card2)
    suited = is_suited(card1, card2)

    v1, v2 = get_rank_value(rank1), get_rank_value(rank2)
    if v1 < v2:
        rank1, rank2 = rank2, rank1

    if rank1 == rank2:
        return f"{rank1}{rank2}"
    elif suited:
        return f"{rank1}{rank2}s"
    else:
        return f"{rank1}{rank2}o"


def classify_pair_strength(
    hero_cards: list[str], board_cards: list[str], pair_rank: str
) -> PairType:
    """
    Classify pair type relative to board.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: List of board cards
        pair_rank: The rank of the pair (e.g., 'Q', '8')

    Returns:
        PairType enum indicating pair strength relative to board
    """
    board_ranks = [parse_card(c)[0] for c in board_cards if c and c != "--"]
    board_values = sorted([get_rank_value(r) for r in board_ranks], reverse=True)
    hero_ranks = [parse_card(c)[0] for c in hero_cards]
    pair_value = get_rank_value(pair_rank)

    # Check if pocket pair (both hole cards are the pair)
    if len(hero_ranks) == 2 and hero_ranks[0] == hero_ranks[1] == pair_rank:
        if not board_values or pair_value > board_values[0]:
            return PairType.OVERPAIR
        return PairType.UNDERPAIR

    # Hit board with one hole card
    if pair_rank in hero_ranks:
        if board_values and pair_value == board_values[0]:
            return PairType.TOP_PAIR
        elif len(board_values) > 1 and pair_value == board_values[1]:
            return PairType.SECOND_PAIR
        return PairType.BOTTOM_PAIR

    # Pair is entirely on the board
    return PairType.BOARD_PAIR


def assess_board_danger(hero_cards: list[str], board_cards: list[str]) -> BoardDanger:
    """
    Assess board danger for hero's hand.

    Identifies dangerous board textures like 4-flush or 4-straight
    that significantly devalue weak made hands.

    Args:
        hero_cards: List of 2 hole cards
        board_cards: List of board cards

    Returns:
        BoardDanger with flags and danger level
    """
    valid_board = [c for c in board_cards if c and c != "--"]
    if len(valid_board) < 3:
        return BoardDanger()

    # Check for 4-flush
    board_suits = [parse_card(c)[1] for c in valid_board]
    suit_counts = Counter(board_suits)
    max_suit, max_count = suit_counts.most_common(1)[0]

    four_flush = max_count >= 4
    hero_suits = [parse_card(c)[1] for c in hero_cards]
    hero_has_flush_card = max_suit in hero_suits if four_flush else False

    # Check for 4-straight (4+ cards within span of 5 ranks)
    board_values = sorted([get_rank_value(parse_card(c)[0]) for c in valid_board])
    four_straight = False
    if len(board_values) >= 4:
        # Check if any 4 consecutive cards span <= 4 ranks (making a straight possible)
        for i in range(len(board_values) - 3):
            if board_values[i + 3] - board_values[i] <= 4:
                four_straight = True
                break

    # Determine danger level
    if four_flush and not hero_has_flush_card:
        danger_level = "extreme"
    elif four_flush or four_straight:
        danger_level = "high"
    elif max_count >= 3:
        danger_level = "medium"
    else:
        danger_level = "low"

    return BoardDanger(
        four_flush=four_flush,
        four_straight=four_straight,
        hero_has_blocker=hero_has_flush_card,
        danger_level=danger_level,
    )


def evaluate_made_hand(hero_cards: list[str], board_cards: list[str]) -> tuple[HandStrength, str]:
    """
    Evaluate the best 5-card hand from hero cards + board.

    Args:
        hero_cards: List of 2 hole cards ['As', 'Kh']
        board_cards: List of 0-5 board cards ['2h', '7c', 'Jh']

    Returns:
        Tuple of (HandStrength enum, description string)
    """
    if not hero_cards or len(hero_cards) < 2:
        return HandStrength.NOTHING, "No cards"

    all_cards = hero_cards + [c for c in board_cards if c and c != "--"]

    if len(all_cards) < 2:
        return HandStrength.HIGH_CARD, "High card only"

    # Parse all cards
    parsed = [parse_card(c) for c in all_cards]
    ranks = [r for r, _ in parsed]
    suits = [s for _, s in parsed]

    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    # Check for flush
    flush_suit = None
    for suit, count in suit_counts.items():
        if count >= 5:
            flush_suit = suit
            break

    # Check for straight
    rank_values = sorted(set(get_rank_value(r) for r in ranks), reverse=True)
    # Add low ace for wheel straight check
    if 14 in rank_values:
        rank_values.append(1)

    straight_high = None
    for i in range(len(rank_values) - 4):
        if rank_values[i] - rank_values[i + 4] == 4:
            straight_high = rank_values[i]
            break

    # Check for straight flush
    if flush_suit and straight_high:
        flush_ranks = [get_rank_value(r) for r, s in parsed if s == flush_suit]
        if 14 in flush_ranks:
            flush_ranks.append(1)
        flush_ranks = sorted(set(flush_ranks), reverse=True)
        for i in range(len(flush_ranks) - 4):
            if flush_ranks[i] - flush_ranks[i + 4] == 4:
                return HandStrength.STRAIGHT_FLUSH, f"Straight flush, {flush_ranks[i]} high"

    # Four of a kind
    for rank, count in rank_counts.items():
        if count >= 4:
            return HandStrength.FOUR_OF_KIND, f"Four {rank}s"

    # Full house
    three_kind = [r for r, c in rank_counts.items() if c >= 3]
    pairs = [r for r, c in rank_counts.items() if c >= 2]
    if three_kind and len(pairs) >= 2:
        return HandStrength.FULL_HOUSE, f"Full house, {three_kind[0]}s full"

    # Flush
    if flush_suit:
        return HandStrength.FLUSH, f"Flush in {flush_suit}"

    # Straight
    if straight_high:
        return HandStrength.STRAIGHT, f"Straight, {straight_high} high"

    # Three of a kind
    if three_kind:
        return HandStrength.THREE_OF_KIND, f"Three {three_kind[0]}s"

    # Two pair
    pair_ranks = [r for r, c in rank_counts.items() if c >= 2]
    if len(pair_ranks) >= 2:
        pair_ranks_sorted = sorted(pair_ranks, key=get_rank_value, reverse=True)
        return (
            HandStrength.TWO_PAIR,
            f"Two pair, {pair_ranks_sorted[0]}s and {pair_ranks_sorted[1]}s",
        )

    # One pair
    if pair_ranks:
        # Check if pair uses hole cards (stronger)
        hero_ranks = [parse_card(c)[0] for c in hero_cards]
        pair_rank = pair_ranks[0]
        if pair_rank in hero_ranks:
            return HandStrength.PAIR, f"Pair of {pair_rank}s (pocket or hit)"
        else:
            return HandStrength.PAIR, f"Pair of {pair_rank}s (board)"

    # High card
    high = max(ranks, key=get_rank_value)
    return HandStrength.HIGH_CARD, f"High card {high}"


def detect_draws(hero_cards: list[str], board_cards: list[str]) -> list[Draw]:
    """
    Detect drawing hands (flush draws, straight draws).

    Args:
        hero_cards: List of 2 hole cards
        board_cards: List of 3-5 board cards

    Returns:
        List of Draw objects
    """
    draws = []

    if not hero_cards or len(hero_cards) < 2:
        return draws

    all_cards = hero_cards + [c for c in board_cards if c and c != "--"]
    parsed = [parse_card(c) for c in all_cards]
    hero_parsed = [parse_card(c) for c in hero_cards]

    suits = [s for _, s in parsed]
    hero_suits = [s for _, s in hero_parsed]
    suit_counts = Counter(suits)

    # Flush draw: 4 to a flush with at least one hole card contributing
    for suit, count in suit_counts.items():
        if count == 4 and suit in hero_suits:
            draws.append(
                Draw(draw_type="flush_draw", outs=9, cards_needed=1, description="Flush draw")
            )
            break

    # Backdoor flush: 3 to a flush on flop
    if len(board_cards) == 3:
        for suit, count in suit_counts.items():
            if count == 3 and suit in hero_suits:
                draws.append(
                    Draw(
                        draw_type="backdoor_flush",
                        outs=0,  # Not direct outs
                        cards_needed=2,
                        description="Backdoor flush",
                    )
                )
                break

    # Straight draws
    rank_values = sorted(set(get_rank_value(r) for r, _ in parsed))
    hero_values = [get_rank_value(r) for r, _ in hero_parsed]

    # Add low ace
    if 14 in rank_values:
        rank_values = [1] + rank_values

    # Check for OESD (open-ended straight draw) - 8 outs
    # Need 4 consecutive cards with gaps at both ends
    for i in range(len(rank_values) - 3):
        window = rank_values[i : i + 4]
        if window[-1] - window[0] == 3:  # 4 consecutive
            # Check if hole cards contribute
            if any(v in hero_values or v == 14 and 1 in hero_values for v in window):
                # Check if open-ended (can complete on both ends)
                low_needed = window[0] - 1
                high_needed = window[-1] + 1
                if low_needed >= 1 and high_needed <= 14:
                    draws.append(
                        Draw(
                            draw_type="oesd",
                            outs=8,
                            cards_needed=1,
                            description="Open-ended straight draw",
                        )
                    )
                    break

    # Check for gutshot (inside straight draw) - 4 outs
    # Need 4 cards within a span of 5 with one gap
    for start in range(1, 11):
        window_range = set(range(start, start + 5))
        matching = set(rank_values) & window_range
        if len(matching) == 4:
            # Has a gutshot
            if any(v in hero_values for v in matching):
                missing = window_range - matching
                draws.append(
                    Draw(
                        draw_type="gutshot",
                        outs=4,
                        cards_needed=1,
                        description=f"Gutshot straight draw (need {list(missing)[0]})",
                    )
                )
                break

    return draws


def count_outs(draws: list[Draw]) -> int:
    """
    Count total outs from draws (accounting for overlap).

    Args:
        draws: List of Draw objects

    Returns:
        Estimated out count
    """
    if not draws:
        return 0

    # Simple sum (could be more sophisticated for overlapping draws)
    direct_draws = [d for d in draws if d.cards_needed == 1]
    total = sum(d.outs for d in direct_draws)

    # Cap at reasonable maximum (accounting for some overlap)
    return min(total, 15)


def equity_estimate(hand_strength: HandStrength, draws: list[Draw], street: str = "flop") -> float:
    """
    Rough equity estimate based on hand strength and draws.

    This is a simplified estimate for decision-making, not precise equity calculation.

    Args:
        hand_strength: Current made hand strength
        draws: List of active draws
        street: Current street ('flop', 'turn', 'river')

    Returns:
        Estimated equity as float (0.0 to 1.0)
    """
    # Base equity from made hand
    base_equity = {
        HandStrength.NOTHING: 0.05,
        HandStrength.HIGH_CARD: 0.15,
        HandStrength.PAIR: 0.50,
        HandStrength.TWO_PAIR: 0.70,
        HandStrength.THREE_OF_KIND: 0.80,
        HandStrength.STRAIGHT: 0.85,
        HandStrength.FLUSH: 0.88,
        HandStrength.FULL_HOUSE: 0.95,
        HandStrength.FOUR_OF_KIND: 0.98,
        HandStrength.STRAIGHT_FLUSH: 0.99,
    }.get(hand_strength, 0.10)

    # Add draw equity if on flop/turn
    if street in ("flop", "turn"):
        outs = count_outs(draws)
        if street == "flop":
            # Roughly 4% per out with two cards to come, slightly less due to overlap
            draw_equity = min(outs * 0.035, 0.45)
        else:
            # Roughly 2% per out with one card to come
            draw_equity = min(outs * 0.02, 0.20)

        # Combine (not just add, as they can overlap)
        combined = base_equity + draw_equity * (1 - base_equity)
        return min(combined, 0.99)

    return base_equity


def has_strong_draw(draws: list[Draw]) -> bool:
    """
    Check if draws include a strong draw (flush draw or OESD).

    Args:
        draws: List of Draw objects

    Returns:
        True if has flush draw or OESD
    """
    for draw in draws:
        if draw.draw_type in ("flush_draw", "oesd"):
            return True
    return False


def get_category_color(category: PreflopCategory) -> str:
    """Get display color for hand category."""
    colors = {
        PreflopCategory.PREMIUM: "#ffcc00",  # Gold
        PreflopCategory.STRONG: "#55cc55",  # Green
        PreflopCategory.PLAYABLE: "#5588cc",  # Blue
        PreflopCategory.MARGINAL: "#cc8855",  # Orange
        PreflopCategory.WEAK: "#888888",  # Gray
    }
    return colors.get(category, "#888888")
