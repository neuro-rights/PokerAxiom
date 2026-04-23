"""
Game state model for poker strategy decisions.

Aggregates all detected values into a structured object for strategy analysis.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from .dynamic_ranges import StackDepth, get_stack_depth_category
from .hand_evaluator import (
    BoardDanger,
    Draw,
    HandStrength,
    PairType,
    PreflopCategory,
    assess_board_danger,
    categorize_preflop,
    classify_pair_strength,
    detect_draws,
    evaluate_made_hand,
    get_hand_notation,
)
from .positions import Position, get_hero_position
from .spr_strategy import SPRCategory, get_spr_category


class Street(Enum):
    """Current betting street."""

    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


class ActionContext(Enum):
    """Context of current betting action."""

    UNOPENED = "unopened"  # First to act or only blinds posted
    FACING_LIMPERS = "limpers"  # One or more limpers in pot
    FACING_RAISE = "raised"  # Someone has raised
    FACING_3BET = "3bet"  # Facing a re-raise
    FACING_ALLIN = "allin"  # Someone is all-in


# Big blind amount for 2NL
BB_AMOUNT = 0.02
SB_AMOUNT = 0.01


@dataclass
class GameState:
    """
    Complete game state for strategy decision-making.

    All monetary values are in dollars (float).
    """

    # Detected values
    hero_cards: list[str] = field(default_factory=list)
    board_cards: list[str] = field(default_factory=list)
    pot: float = 0.0
    stacks: dict[int, float | None] = field(default_factory=dict)
    bets: dict[int, float | None] = field(default_factory=dict)
    dealer_seat: int = 0
    active_seats: dict[int, bool] = field(default_factory=dict)  # Seats with visible card backs

    # Fixed values
    hero_seat: int = 1  # Hero always at seat 1 (bottom center)
    bb: float = BB_AMOUNT
    sb: float = SB_AMOUNT

    # Derived values (computed on creation)
    street: Street = Street.PREFLOP
    position: Position = Position.UTG
    action_context: ActionContext = ActionContext.UNOPENED

    # Hand analysis cache
    _preflop_category: PreflopCategory | None = field(default=None, repr=False)
    _hand_notation: str | None = field(default=None, repr=False)
    _hand_strength: HandStrength | None = field(default=None, repr=False)
    _hand_description: str | None = field(default=None, repr=False)
    _draws: list[Draw] | None = field(default=None, repr=False)
    _pair_type: PairType | None = field(default=None, repr=False)
    _board_danger: BoardDanger | None = field(default=None, repr=False)

    def __post_init__(self):
        """Compute derived values after initialization."""
        self._compute_derived_values()

    def _compute_derived_values(self):
        """Compute street, position, and action context."""
        # Compute street based on board cards
        valid_board = [c for c in self.board_cards if c and c != "--"]
        if len(valid_board) == 0:
            self.street = Street.PREFLOP
        elif len(valid_board) == 3:
            self.street = Street.FLOP
        elif len(valid_board) == 4:
            self.street = Street.TURN
        else:
            self.street = Street.RIVER

        # Compute position
        if self.dealer_seat > 0:
            self.position = get_hero_position(self.dealer_seat, self.hero_seat)

        # Compute action context
        self.action_context = self._detect_action_context()

    def _get_blind_seats(self) -> tuple[int, int]:
        """
        Find actual SB/BB seats, skipping empty/folded seats.

        Uses card back detection (active_seats) when available as it's most accurate.
        Falls back to stack/bet detection otherwise.

        Returns:
            Tuple of (sb_seat, bb_seat), or (0, 0) if not enough players
        """
        # Build set of occupied seats
        occupied = {self.hero_seat}  # Hero is always occupied

        if self.active_seats:
            # Prefer card back detection (most accurate for who's in the hand)
            for seat, is_active in self.active_seats.items():
                if is_active:
                    occupied.add(seat)
        else:
            # Fallback: use stacks and bets
            for s in range(1, 11):
                if self.stacks.get(s) and self.stacks[s] > 0:
                    occupied.add(s)
                elif self.bets.get(s) and self.bets[s] > 0:
                    occupied.add(s)

        if len(occupied) < 2:
            return 0, 0

        # Find next occupied seat after dealer (wrapping around 1-10)
        def next_occupied(start: int) -> int:
            for i in range(1, 11):
                seat = ((start - 1 + i) % 10) + 1  # Wrap 1-10
                if seat in occupied:
                    return seat
            return 0

        sb_seat = next_occupied(self.dealer_seat)
        bb_seat = next_occupied(sb_seat)

        return sb_seat, bb_seat

    def _detect_action_context(self) -> ActionContext:
        """
        Analyze betting pattern to determine action context.

        Logic:
        - No bets or only blinds → UNOPENED
        - Non-blind players bet BB amount (limps) → FACING_LIMPERS
        - Bets >= 2.5x BB → FACING_RAISE
        - Multiple raises → FACING_3BET
        """
        active_bets = {k: v for k, v in self.bets.items() if v and v > 0}

        if not active_bets:
            return ActionContext.UNOPENED

        # Get max bet (excluding hero's bet if any)
        other_bets = {k: v for k, v in active_bets.items() if k != self.hero_seat}

        if not other_bets:
            return ActionContext.UNOPENED

        max_bet = max(other_bets.values())
        hero_bet = active_bets.get(self.hero_seat, 0) or 0

        # Check for all-in (bet >= 90% of any stack)
        for seat, bet in other_bets.items():
            stack = self.stacks.get(seat) or 0
            if stack > 0 and bet >= stack * 0.9:
                return ActionContext.FACING_ALLIN

        # Calculate blind positions (skipping empty seats)
        sb_seat, bb_seat = self._get_blind_seats()

        # Count limpers: non-blind players who bet approximately BB
        limpers = 0
        for seat, bet in other_bets.items():
            if seat in (sb_seat, bb_seat):
                continue  # Skip blinds
            # Limper = bet approximately equals BB (0.02 +/- tolerance)
            if bet and abs(bet - self.bb) < 0.008:
                limpers += 1

        # Determine context based on bet sizes and limper count
        # A raise is > 1.5bb (min-raise is 2bb at most sites)
        # This catches min-raises at $0.04 (2bb) for 2NL
        if max_bet >= self.bb * 1.5:
            # Someone raised
            if hero_bet >= self.bb * 1.5:
                # Hero already raised, this is a 3-bet
                return ActionContext.FACING_3BET
            return ActionContext.FACING_RAISE
        elif limpers > 0:
            # One or more limpers
            return ActionContext.FACING_LIMPERS
        elif max_bet <= self.bb * 1.1:
            # Only blinds posted
            return ActionContext.UNOPENED

        return ActionContext.FACING_LIMPERS

    @classmethod
    def from_detection(
        cls,
        hero_cards: list[str],
        board_cards: list[str],
        pot: float,
        stacks: dict[int, float | None],
        bets: dict[int, float | None],
        dealer_seat: int,
        active_seats: dict[int, bool] | None = None,
    ) -> "GameState":
        """
        Factory method to create GameState from detection results.

        Args:
            hero_cards: Detected hero hole cards ['As', 'Kh']
            board_cards: Detected board cards ['2h', '7c', 'Jh']
            pot: Detected pot size
            stacks: Stack sizes by seat {1: 3.97, 2: 1.50, ...}
            bets: Current bets by seat {1: 0.02, 2: None, ...}
            dealer_seat: Seat with dealer button (1-10)
            active_seats: Seats with visible card backs (still in hand) {2: True, 3: False, ...}

        Returns:
            GameState instance
        """
        return cls(
            hero_cards=hero_cards,
            board_cards=board_cards,
            pot=pot or 0.0,
            stacks=stacks or {},
            bets=bets or {},
            dealer_seat=dealer_seat,
            active_seats=active_seats or {},
        )

    def is_valid(self) -> bool:
        """
        Check if game state has enough data for decision-making.

        Returns:
            True if we have hero cards and dealer position
        """
        valid_hero = len(self.hero_cards) == 2 and all(c and c != "--" for c in self.hero_cards)
        valid_dealer = 1 <= self.dealer_seat <= 10
        return valid_hero and valid_dealer

    def is_preflop(self) -> bool:
        """Check if currently preflop."""
        return self.street == Street.PREFLOP

    @property
    def preflop_category(self) -> PreflopCategory:
        """Get preflop hand category (cached)."""
        if self._preflop_category is None and len(self.hero_cards) >= 2:
            self._preflop_category = categorize_preflop(self.hero_cards[0], self.hero_cards[1])
        return self._preflop_category or PreflopCategory.WEAK

    @property
    def hand_notation(self) -> str:
        """Get standard hand notation (cached)."""
        if self._hand_notation is None and len(self.hero_cards) >= 2:
            self._hand_notation = get_hand_notation(self.hero_cards[0], self.hero_cards[1])
        return self._hand_notation or "??"

    @property
    def hand_strength(self) -> HandStrength:
        """Get current made hand strength (cached)."""
        if self._hand_strength is None:
            strength, desc = evaluate_made_hand(self.hero_cards, self.board_cards)
            self._hand_strength = strength
            self._hand_description = desc
        return self._hand_strength or HandStrength.NOTHING

    @property
    def hand_description(self) -> str:
        """Get hand description string."""
        if self._hand_description is None:
            _, desc = evaluate_made_hand(self.hero_cards, self.board_cards)
            self._hand_description = desc
        return self._hand_description or ""

    @property
    def draws(self) -> list[Draw]:
        """Get current draws (cached)."""
        if self._draws is None:
            self._draws = detect_draws(self.hero_cards, self.board_cards)
        return self._draws or []

    @property
    def pair_type(self) -> PairType | None:
        """
        Get pair type classification relative to board (cached).

        Returns None if hand is not a pair.
        """
        if self._pair_type is None:
            # Only compute if we have a pair
            if self.hand_strength == HandStrength.PAIR and self.hand_description:
                # Extract pair rank from description like "Pair of 8s (pocket or hit)"
                match = re.search(r"Pair of (\w)s", self.hand_description)
                if match:
                    pair_rank = match.group(1)
                    self._pair_type = classify_pair_strength(
                        self.hero_cards, self.board_cards, pair_rank
                    )
        return self._pair_type

    @property
    def board_danger(self) -> BoardDanger:
        """Get board danger assessment (cached)."""
        if self._board_danger is None:
            self._board_danger = assess_board_danger(self.hero_cards, self.board_cards)
        return self._board_danger

    @property
    def effective_stack_bb(self) -> float:
        """
        Get effective stack in big blinds.

        Useful for stack depth based decisions.

        Returns:
            Effective stack size in big blinds
        """
        return self.effective_stack() / self.bb if self.bb > 0 else 0

    @property
    def spr_category(self) -> SPRCategory:
        """
        Get SPR category for strategic adjustments.

        Returns:
            SPRCategory (LOW, MEDIUM, or HIGH)
        """
        spr = self.stack_to_pot_ratio()
        return get_spr_category(spr)

    @property
    def stack_depth(self) -> StackDepth:
        """
        Get stack depth category for range adjustments.

        Returns:
            StackDepth category
        """
        return get_stack_depth_category(self.effective_stack_bb)

    def to_call(self) -> float:
        """
        Calculate amount needed to call.

        Returns:
            Amount to call in dollars
        """
        hero_bet = self.bets.get(self.hero_seat) or 0
        other_bets = [v for k, v in self.bets.items() if k != self.hero_seat and v and v > 0]

        if not other_bets:
            return 0

        max_bet = max(other_bets)
        return max(0, max_bet - hero_bet)

    def pot_odds(self) -> float:
        """
        Calculate pot odds as a percentage.

        Returns:
            Pot odds as float (e.g., 0.25 for 25%)
        """
        call_amount = self.to_call()
        if call_amount <= 0:
            return 1.0  # No call needed, infinite odds

        total_pot = self.pot + call_amount
        if total_pot <= 0:
            return 0.0

        return call_amount / total_pot

    def active_opponent_count(self) -> int:
        """
        Count opponents still in the hand.

        Uses card back detection if available (most accurate).
        Falls back to bet/stack based counting for preflop or if not calibrated.

        Returns:
            Number of active opponents
        """
        # If we have card back detection data, use it (most accurate)
        if self.active_seats:
            return sum(
                1
                for seat, is_active in self.active_seats.items()
                if seat != self.hero_seat and is_active
            )

        # Fallback: On preflop, count players with bets or stacks
        # On postflop without card back detection, we can't reliably tell who folded
        count = 0
        for seat in range(1, 10):
            if seat == self.hero_seat:
                continue
            stack = self.stacks.get(seat)
            bet = self.bets.get(seat)
            if (stack and stack > 0) or (bet and bet > 0):
                count += 1
        return count

    def limper_count(self) -> int:
        """
        Count limpers (players who called BB without raising).

        Returns:
            Number of limpers
        """
        if self.street != Street.PREFLOP:
            return 0

        # Calculate blind positions (skipping empty seats)
        sb_seat, bb_seat = self._get_blind_seats()

        count = 0
        for seat, bet in self.bets.items():
            if seat == self.hero_seat:
                continue
            if seat in (sb_seat, bb_seat):
                continue  # Skip blinds - they're not limpers
            # Limper = bet roughly equals BB (not a raise)
            if bet and abs(bet - self.bb) < 0.008:
                count += 1

        return count

    def hero_stack(self) -> float:
        """Get hero's current stack size."""
        return self.stacks.get(self.hero_seat) or 0

    def effective_stack(self) -> float:
        """
        Get effective stack (minimum of hero and villain stacks).

        Returns:
            Effective stack in dollars
        """
        hero_stack = self.hero_stack()
        if hero_stack <= 0:
            return 0

        villain_stacks = [
            s for seat, s in self.stacks.items() if seat != self.hero_seat and s and s > 0
        ]

        if not villain_stacks:
            return hero_stack

        return min(hero_stack, max(villain_stacks))

    def stack_to_pot_ratio(self) -> float:
        """
        Calculate stack-to-pot ratio (SPR).

        Returns:
            SPR value
        """
        if self.pot <= 0:
            return float("inf")
        return self.effective_stack() / self.pot

    def get_street_name(self) -> str:
        """Get display name for current street."""
        return self.street.value.upper()

    def get_context_description(self) -> str:
        """Get human-readable action context description."""
        descriptions = {
            ActionContext.UNOPENED: "Unopened pot",
            ActionContext.FACING_LIMPERS: f"{self.limper_count()} limper(s)",
            ActionContext.FACING_RAISE: "Facing raise",
            ActionContext.FACING_3BET: "Facing 3-bet",
            ActionContext.FACING_ALLIN: "Facing all-in",
        }
        return descriptions.get(self.action_context, "Unknown")

    def get_raiser_position(self) -> Position | None:
        """
        Determine the position of the player who raised.

        Used for adjusting calling/folding ranges based on raiser's position.
        For example, fold AQo to raises from early position.

        Returns:
            Position of the raiser, or None if not facing a raise
        """
        if self.action_context not in (ActionContext.FACING_RAISE, ActionContext.FACING_3BET):
            return None

        # Find the player with the largest bet (excluding hero)
        max_bet = 0
        raiser_seat = None

        for seat, bet in self.bets.items():
            if seat == self.hero_seat:
                continue
            if bet and bet > max_bet and bet >= self.bb * 2.5:
                max_bet = bet
                raiser_seat = seat

        if raiser_seat is None:
            return None

        # Calculate raiser's position
        return get_hero_position(self.dealer_seat, raiser_seat)
