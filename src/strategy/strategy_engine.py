"""
Strategy Engine for 2NL 9-max TAG poker.

Implements the proven exploitative strategy from the research document.
Provides action recommendations based on position, hand strength, and game context.
"""

from collections import Counter
from typing import Any

from .actions import (
    Action,
    ActionType,
    BoardTexture,
    bet_action,
    calculate_3bet,
    calculate_check_raise,
    calculate_open_raise,
    calculate_overbet,
    calculate_value_bet,
    call_action,
    check_action,
    fold_action,
    raise_action,
)
from .board_analysis import (
    analyze_flop,
    is_safe_board_for_thin_value,
)
from .dynamic_ranges import (
    is_in_adjusted_opening_range,
)
from .game_state import ActionContext, GameState, Street
from .gto_baseline import (
    get_cbet_recommendation,
)
from .hand_evaluator import (
    HandStrength,
    PairType,
    PreflopCategory,
    count_outs,
    equity_estimate,
    get_rank_value,
    has_strong_draw,
    parse_card,
)
from .mdf import (
    calculate_mdf,
)
from .opponent_db import PlayerStats
from .positions import Position, is_early_position, is_late_position
from .ranges import (
    category_opens_from_position,
    is_in_3bet_call_range,
    is_in_3bet_range,
    is_in_bb_defend_range,
    is_in_opening_range,
)

# New hybrid strategy modules
from .spr_strategy import (
    CommitmentLevel,
    SPRCategory,
    get_commitment_level,
    get_spr_strategy,
)


class DecisionTrace:
    """
    Records step-by-step strategy decision process for debugging.

    Each step captures the method called and relevant decision details.
    """

    def __init__(self):
        self.steps: list[dict[str, Any]] = []

    def add(self, step: str, **details):
        """Add a trace step with optional details."""
        self.steps.append({"step": step, "details": details})

    def to_list(self) -> list[dict[str, Any]]:
        """Return trace as list of dicts."""
        return self.steps

    def format_text(self) -> str:
        """Format trace as human-readable text."""
        lines = []
        for i, entry in enumerate(self.steps, 1):
            step = entry["step"]
            details = entry.get("details", {})
            lines.append(f"[{i}] {step}")
            for key, value in details.items():
                lines.append(f"    - {key}: {value}")
        return "\n".join(lines)


def hero_has_backdoor_flush(hero_cards: list, board_cards: list) -> bool:
    """
    Check if hero has backdoor flush potential on the current board.

    Hero has backdoor flush if they have a card matching the dominant
    suit on the board (for monotone/two-tone boards).

    Args:
        hero_cards: Hero's hole cards
        board_cards: Board cards

    Returns:
        True if hero has backdoor flush potential
    """
    if not hero_cards or not board_cards:
        return False

    # Get board suits
    board_suits = []
    for c in board_cards[:3]:  # Only check flop
        if c and c != "--":
            parsed = parse_card(c)
            if parsed:
                board_suits.append(parsed[1])

    if len(board_suits) < 3:
        return False

    suit_counts = Counter(board_suits)

    # Find dominant suit (2+ cards)
    dominant_suit = None
    for suit, count in suit_counts.items():
        if count >= 2:
            dominant_suit = suit
            break

    if not dominant_suit:
        return True  # Rainbow board, no need for backdoor flush

    # Check if hero has a card of the dominant suit
    for card in hero_cards:
        if card and card != "--":
            parsed = parse_card(card)
            if parsed and parsed[1] == dominant_suit:
                return True

    return False


def hero_has_flush_draw(hero_cards: list, board_cards: list) -> bool:
    """
    Check if hero has a flush draw (4 to a flush).

    Args:
        hero_cards: Hero's hole cards
        board_cards: Board cards

    Returns:
        True if hero has flush draw
    """
    if not hero_cards or not board_cards:
        return False

    all_suits = []

    # Get hero suits
    for card in hero_cards:
        if card and card != "--":
            parsed = parse_card(card)
            if parsed:
                all_suits.append(parsed[1])

    # Get board suits
    for card in board_cards:
        if card and card != "--":
            parsed = parse_card(card)
            if parsed:
                all_suits.append(parsed[1])

    # Check for 4+ of same suit
    suit_counts = Counter(all_suits)
    return max(suit_counts.values()) >= 4 if suit_counts else False


def evaluate_board_texture(board_cards: list) -> BoardTexture:
    """
    Evaluate board texture for c-bet sizing.

    Dry: Rainbow, disconnected (K72r, Q83r) - 33-40% pot
    Wet: Flush draws, straight draws (JT9ss, QJ8ss) - 66-75% pot
    Medium: Everything else - 50-60% pot

    Args:
        board_cards: List of board card strings

    Returns:
        BoardTexture enum value
    """
    if len(board_cards) < 3:
        return BoardTexture.MEDIUM

    # Parse first 3 cards (flop)
    parsed = []
    for c in board_cards[:3]:
        if c and c != "--":
            parsed.append(parse_card(c))

    if len(parsed) < 3:
        return BoardTexture.MEDIUM

    ranks = [r for r, _ in parsed]
    suits = [s for _, s in parsed]

    # Check for flush draw potential (2+ same suit)
    suit_counts = Counter(suits)
    has_flush_draw = max(suit_counts.values()) >= 2

    # Check for straight draw potential (connected cards)
    values = sorted([get_rank_value(r) for r in ranks])
    gaps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    max_gap = max(gaps) if gaps else 0
    is_connected = max_gap <= 2

    # Classify
    if has_flush_draw and is_connected:
        return BoardTexture.WET
    elif not has_flush_draw and not is_connected and max_gap >= 4:
        return BoardTexture.DRY
    else:
        return BoardTexture.MEDIUM


def is_action_river(board_cards: list) -> bool:
    """
    Check if river completes obvious draws (action river).

    Action rivers = completing flush or straight draws.
    Fish cannot fold straights, flushes, sets on these boards.

    Args:
        board_cards: List of 5 board card strings

    Returns:
        True if river completes obvious draw
    """
    if len(board_cards) < 5:
        return False

    # Parse all cards
    parsed = []
    for c in board_cards:
        if c and c != "--":
            parsed.append(parse_card(c))

    if len(parsed) < 5:
        return False

    suits = [s for _, s in parsed]
    values = sorted([get_rank_value(r) for r, _ in parsed])

    # Check if flush completed (3+ of same suit with river)
    suit_counts = Counter(suits)
    if max(suit_counts.values()) >= 3:
        return True

    # Check if straight completed (5 cards within 4 gaps)
    unique_values = sorted(set(values))
    if len(unique_values) >= 5:
        # Check for any 5 consecutive values
        for i in range(len(unique_values) - 4):
            if unique_values[i + 4] - unique_values[i] == 4:
                return True

    return False


def get_tptk_turn_sizing(board_cards: list, pot: float) -> tuple[float, str, str, BoardTexture]:
    """
    Get turn sizing for TPTK based on board texture.

    At 2NL, always bet TPTK for value - opponents call too light.
    Sizing varies by texture:
    - WET: 80% pot (protection + value from draws)
    - MEDIUM: 66% pot (standard value)
    - DRY: 66% pot (thin value)

    Args:
        board_cards: Current board cards (4 cards on turn)
        pot: Current pot size

    Returns:
        Tuple of (bet_amount, button_label, reasoning, texture)
    """
    # Analyze full turn board (4 cards) for draws, not just flop
    # The turn card may have added flush/straight draws
    valid_cards = [c for c in board_cards[:4] if c and c != "--"]

    # Check for flush draw (2+ of same suit)
    suits = [c[-1] for c in valid_cards]
    suit_counts = Counter(suits)
    has_flush_draw = max(suit_counts.values()) >= 2

    # Check for straight draw (connected cards)
    values = sorted([get_rank_value(c[:-1]) for c in valid_cards])
    gaps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    max_gap = max(gaps) if gaps else 99
    has_straight_draw = max_gap <= 2 or (len(values) >= 3 and values[-1] - values[0] <= 5)

    # Determine texture from full board
    if has_flush_draw or has_straight_draw:
        texture = BoardTexture.WET
    elif max_gap >= 4 and not has_flush_draw:
        texture = BoardTexture.DRY
    else:
        texture = BoardTexture.MEDIUM

    if texture == BoardTexture.WET:
        sizing_pct, button = 0.80, "80%"
        reason = "Value bet TPTK on wet board (charge draws, 2NL calls light)"
    elif texture == BoardTexture.DRY:
        sizing_pct, button = 0.66, "66%"
        reason = "Value bet TPTK on dry board (thin value, 2NL calls light)"
    else:  # MEDIUM
        sizing_pct, button = 0.66, "66%"
        reason = "Value bet TPTK (2NL calls too light to check)"

    return round(pot * sizing_pct, 2), button, reason, texture


class StrategyEngine:
    """
    Main strategy engine implementing 2NL TAG strategy.

    Rules implemented from research:
    - Rules 1-5: Position-based preflop ranges
    - Rule 6: 3-betting only for value
    - Rules 7-8: C-betting frequency by opponent count
    - Rules 9-11: Facing opposition decisions
    - Rule 12: Check-raise strategy
    - Rules 14-15: Turn/river play
    """

    def __init__(self):
        """Initialize the strategy engine."""
        self.last_recommendation: Action | None = None
        self.last_trace: DecisionTrace | None = None
        self._trace: DecisionTrace | None = None  # Current trace being built

    def recommend(
        self, game_state: GameState, villain_stats: dict[int, PlayerStats] | None = None
    ) -> Action:
        """
        Get action recommendation for current game state.

        Args:
            game_state: Current GameState object
            villain_stats: Optional dict of seat -> PlayerStats for villain adjustments

        Returns:
            Action recommendation
        """
        # Initialize new trace for this decision
        self._trace = DecisionTrace()

        if not game_state.is_valid():
            self._trace.add("recommend", result="INVALID", reason="Invalid game state")
            self.last_trace = self._trace
            return fold_action("Invalid game state")

        street = game_state.street.value
        self._trace.add("recommend", street=street, valid=True)

        if game_state.is_preflop():
            action = self._preflop_decision(game_state)
        else:
            action = self._postflop_decision(game_state)

        # Convert FOLD to CHECK when check is available (no bet to call)
        # Folding when you can check for free is always a mistake
        if action.action_type == ActionType.FOLD and game_state.to_call() == 0:
            action = check_action("Check (free option)")
            self._trace.add("fold_to_check", reason="Check available - never fold for free")

        # Apply villain-specific adjustments if stats available
        if villain_stats:
            action = self._apply_villain_adjustments(action, game_state, villain_stats)

        # Store final result in trace
        self._trace.add(
            "result",
            action=action.action_type.value,
            amount=action.amount,
            reasoning=action.reasoning,
        )

        self.last_recommendation = action
        self.last_trace = self._trace
        return action

    def _preflop_decision(self, gs: GameState) -> Action:
        """
        Preflop decision logic implementing Rules 1-6.

        Decision tree:
        1. Unopened → Check if in opening range → RAISE
        2. Facing limpers → Raise if in range, isolate
        3. Facing raise → 3-bet premium, call/fold others
        4. Facing 3-bet → Only continue with QQ+, AK
        """
        position = gs.position
        hand = gs.hand_notation
        category = gs.preflop_category
        context = gs.action_context

        self._trace.add(
            "_preflop_decision",
            hand=hand,
            category=category.value,
            position=position.value,
            context=context.value,
        )

        # Rule: Unopened pot - check opening range
        if context == ActionContext.UNOPENED:
            return self._unopened_decision(gs, position, hand, category)

        # Rule: Facing limpers - raise to isolate
        if context == ActionContext.FACING_LIMPERS:
            return self._facing_limpers_decision(gs, position, hand, category)

        # Rule: Facing raise - 3-bet or fold (minimal calling)
        if context == ActionContext.FACING_RAISE:
            return self._facing_raise_decision(gs, position, hand, category)

        # Rule: Facing 3-bet - only continue with monsters
        if context == ActionContext.FACING_3BET:
            return self._facing_3bet_decision(gs, hand, category)

        # Rule: Facing all-in - only call with premiums
        if context == ActionContext.FACING_ALLIN:
            return self._facing_allin_decision(gs, hand, category)

        return fold_action("Unknown preflop situation")

    def _unopened_decision(
        self, gs: GameState, position: Position, hand: str, category: PreflopCategory
    ) -> Action:
        """
        Decision when pot is unopened.

        Uses dynamic ranges that adjust for stack depth.
        """
        # Get effective stack in big blinds
        effective_bb = gs.effective_stack_bb
        stack_depth = gs.stack_depth

        # Check if hand is in stack-adjusted opening range
        in_dynamic_range = is_in_adjusted_opening_range(hand, position, effective_bb)

        # Fallback to static range for backwards compatibility
        in_static_range = is_in_opening_range(hand, position)
        category_opens = category_opens_from_position(category, position)

        # Use dynamic range if available, otherwise fall back
        in_range = in_dynamic_range or in_static_range or category_opens

        self._trace.add(
            "_unopened_decision",
            effective_bb=f"{effective_bb:.0f}bb",
            stack_depth=stack_depth.value,
            in_dynamic_range=in_dynamic_range,
            in_static_range=in_static_range,
            category_opens=category_opens,
            in_range=in_range,
        )

        if not in_range:
            return fold_action(f"{hand} not in {position.value} range at {effective_bb:.0f}bb")

        # Calculate raise sizing (3bb standard) mapped to button
        raise_amount, button = calculate_open_raise(limper_count=0)

        return raise_action(
            raise_amount,
            reasoning=f"Open {category.value} from {position.value} ({stack_depth.value} stack)",
            sizing_note=button,
            button=button,
        )

    def _facing_limpers_decision(
        self, gs: GameState, position: Position, hand: str, category: PreflopCategory
    ) -> Action:
        """
        Decision when facing limpers.

        Raise to isolate with hands in range, otherwise fold.
        """
        limper_count = gs.limper_count()
        is_late = is_late_position(position)
        is_early = is_early_position(position)

        self._trace.add(
            "_facing_limpers_decision",
            limper_count=limper_count,
            is_late=is_late,
            is_early=is_early,
        )

        # Tighten range slightly with limpers
        # Premium and Strong always raise
        # Playable raises from MP+
        # Marginal only from late position with 1 limper

        if category == PreflopCategory.PREMIUM:
            raise_amount, button = calculate_open_raise(limper_count)
            self._trace.add("isolate", reason="PREMIUM always raises")
            return raise_action(
                raise_amount,
                reasoning=f"Isolate {limper_count} limper(s) with premium",
                sizing_note=button,
                button=button,
            )

        if category == PreflopCategory.STRONG:
            raise_amount, button = calculate_open_raise(limper_count)
            self._trace.add("isolate", reason="STRONG always raises")
            return raise_action(
                raise_amount,
                reasoning="Isolate with strong hand",
                sizing_note=button,
                button=button,
            )

        if category == PreflopCategory.PLAYABLE:
            if not is_early:
                raise_amount, button = calculate_open_raise(limper_count)
                self._trace.add("isolate", reason="PLAYABLE raises from MP+")
                return raise_action(
                    raise_amount,
                    reasoning="Isolate with playable hand in position",
                    sizing_note=button,
                    button=button,
                )

        if category == PreflopCategory.MARGINAL:
            # Only raise from late position with 1 limper
            if is_late and limper_count <= 1:
                raise_amount, button = calculate_open_raise(limper_count)
                self._trace.add("isolate", reason="MARGINAL raises late with <=1 limper")
                return raise_action(
                    raise_amount,
                    reasoning="Isolate from late position",
                    sizing_note=button,
                    button=button,
                )

        self._trace.add("fold", reason=f"{category.value} too weak vs limpers")
        return fold_action(f"{hand} too weak vs limpers")

    def _facing_raise_decision(
        self, gs: GameState, position: Position, hand: str, category: PreflopCategory
    ) -> Action:
        """
        Decision when facing a raise.

        Rule: 3-bet for VALUE only with QQ+, AK (JJ removed from 3-bet range).
        JJ, TT can call in position. AQo should fold to EP raises.
        """
        call_amount = gs.to_call()
        is_late = is_late_position(position)
        in_3bet_range = is_in_3bet_range(hand)  # Now only QQ+, AK
        bb_defend = is_in_bb_defend_range(hand) if position == Position.BB else False
        raiser_position = gs.get_raiser_position()

        self._trace.add(
            "_facing_raise_decision",
            call_amount=call_amount,
            is_late=is_late,
            is_in_3bet_range=in_3bet_range,
            raiser_position=raiser_position.value if raiser_position else None,
            is_bb_defend_range=bb_defend,
        )

        # Check if hand is in 3-bet range (QQ+, AK only)
        if in_3bet_range:
            # 3-bet for value - use pot button for 3-bets
            threbet_amount, button = calculate_3bet(call_amount, is_late)
            self._trace.add("3bet", reason=f"{hand} in 3-bet value range (QQ+, AK)")
            return raise_action(
                threbet_amount,
                reasoning=f"3-bet {hand} for value",
                sizing_note=button,
                button=button,
            )

        # JJ, TT should always continue vs a single raise at 2NL
        # These are top 5% hands - too strong to fold to standard opens
        # Only fold to very large raises (8bb+) or 3-bets
        if hand in ("JJ", "TT"):
            bb = gs.bb or 0.02
            call_bb = call_amount / bb if bb > 0 else 0

            self._trace.add(
                "premium_pair_check",
                hand=hand,
                call_bb=f"{call_bb:.1f}bb",
                is_late=is_late,
            )

            # Fold only to very large raises (8bb+)
            if call_bb >= 8:
                self._trace.add("fold", reason=f"{hand} folds to large raise ({call_bb:.1f}bb)")
                return fold_action(f"Fold {hand} vs large raise")

            # Otherwise always call - great implied odds at 2NL
            if is_late:
                self._trace.add("call", reason=f"{hand} calls in position")
                return call_action(call_amount, reasoning=f"Call with {hand} in position")
            else:
                self._trace.add("call", reason=f"{hand} calls OOP (set mine + overpair value)")
                return call_action(call_amount, reasoning=f"Call with {hand} (set mine)")

        # AQs can call, AQo should fold to tight 3-bets (EP raises)
        if hand == "AQs":
            self._trace.add("call", reason="AQs calls raise")
            return call_action(call_amount, reasoning="Call with AQs")

        if hand == "AQo":
            # Fold AQo to raises from early positions
            if raiser_position and raiser_position in (Position.UTG, Position.UTG1, Position.UTG2):
                self._trace.add("fold", reason="Fold AQo to EP raise")
                return fold_action("Fold AQo vs early position raise")
            # Can call in position vs late position raises
            if is_late:
                self._trace.add("call", reason="AQo calls LP raise in position")
                return call_action(call_amount, reasoning="Call AQo in position vs LP")

        # Strong hands can call in position
        if category in (PreflopCategory.PREMIUM, PreflopCategory.STRONG):
            if is_late:
                self._trace.add("call", reason=f"{category.value} calls in late position")
                return call_action(call_amount, reasoning=f"Call with {hand} in position")
            self._trace.add("skip_call", reason=f"{category.value} but not in position")

        # Playable hands can call on button
        if category == PreflopCategory.PLAYABLE:
            if position == Position.BTN:
                self._trace.add("call", reason="PLAYABLE on BTN")
                return call_action(call_amount, reasoning="Call with playable on button")
            self._trace.add("skip_call", reason="PLAYABLE but not on BTN")

        # BB defense
        if position == Position.BB:
            if bb_defend:
                self._trace.add("call", reason="BB defense range")
                return call_action(call_amount, reasoning="Defend BB")
            self._trace.add("skip_bb_defend", reason=f"{hand} not in BB defend range")

        self._trace.add("fold", reason=f"{hand} ({category.value}) not strong enough vs raise")
        return fold_action(f"{hand} not strong enough vs raise")

    def _facing_3bet_decision(self, gs: GameState, hand: str, category: PreflopCategory) -> Action:
        """
        Decision when facing a 3-bet.

        4-bet range = AA, KK only (removed AKs unless maniac)
        Call range = QQ, JJ, TT, AKs, AKo, AQs
        Fold AQo to 3-bets.
        """
        call_amount = gs.to_call()
        in_call_range = is_in_3bet_call_range(hand)  # Now JJ, TT, AQs

        self._trace.add(
            "_facing_3bet_decision",
            call_amount=call_amount,
            is_4bet_hand=(hand in ("AA", "KK")),
            is_in_3bet_call_range=in_call_range,
        )

        # 4-bet with AA, KK only
        if hand in ("AA", "KK"):
            # 4-bet sizing roughly 2.2x the 3-bet
            fourbet_amount = round(call_amount * 2.2, 2)
            self._trace.add("4bet", reason=f"{hand} is 4-bet for value hand")
            return raise_action(fourbet_amount, reasoning=f"4-bet {hand} for value")

        # QQ can 4-bet or flat (default to calling, can 4-bet vs aggro)
        if hand == "QQ":
            self._trace.add("call", reason="QQ calls 3-bet (can 4-bet vs aggro)")
            return call_action(call_amount, reasoning="Call 3-bet with QQ")

        # AKs/AKo - call 3-bet (no longer 4-betting)
        if hand in ("AKs", "AKo"):
            self._trace.add("call", reason=f"{hand} calls 3-bet")
            return call_action(call_amount, reasoning=f"Call 3-bet with {hand}")

        # Call with JJ, TT, AQs (in_call_range)
        if in_call_range:
            self._trace.add("call", reason=f"{hand} in 3-bet call range")
            return call_action(call_amount, reasoning=f"Call 3-bet with {hand}")

        # Fold AQo to 3-bets
        if hand == "AQo":
            self._trace.add("fold", reason="Fold AQo to 3-bet")
            return fold_action("Fold AQo vs 3-bet at 2NL")

        self._trace.add("fold", reason="Not in 3-bet continue range at 2NL")
        return fold_action("Fold vs 3-bet at 2NL")

    def _facing_allin_decision(self, gs: GameState, hand: str, category: PreflopCategory) -> Action:
        """
        Decision when facing an all-in.

        Only call with AA, KK, QQ, AK.
        """
        call_amount = gs.to_call()

        self._trace.add("_facing_allin_decision", call_amount=call_amount)

        if hand in ("AA", "KK"):
            self._trace.add("call", reason=f"Snap call {hand} vs all-in")
            return call_action(call_amount, reasoning=f"Snap call with {hand}")

        if hand in ("QQ", "AKs", "AKo"):
            self._trace.add("call", reason=f"Call {hand} vs all-in")
            return call_action(call_amount, reasoning=f"Call all-in with {hand}")

        self._trace.add("fold", reason="Not premium hand vs all-in")
        return fold_action("Fold vs all-in without premium")

    def _postflop_decision(self, gs: GameState) -> Action:
        """
        Postflop decision logic implementing Rules 7-15.
        """
        street = gs.street
        hand_strength = gs.hand_strength
        draws = gs.draws

        self._trace.add(
            "_postflop_decision",
            street=street.value,
            hand_strength=hand_strength.name,
            draw_count=len(draws),
        )

        if street == Street.FLOP:
            return self._flop_decision(gs, hand_strength, draws)
        elif street == Street.TURN:
            return self._turn_decision(gs, hand_strength, draws)
        else:  # River
            return self._river_decision(gs, hand_strength)

    def _flop_decision(self, gs: GameState, strength: HandStrength, draws: list) -> Action:
        """
        Flop decision logic.

        Rules 7-8: C-bet frequency based on opponent count.
        Rule 12: Check-raise with sets/two-pair.
        """
        opponent_count = gs.active_opponent_count()
        pot = gs.pot
        call_amount = gs.to_call()

        self._trace.add(
            "_flop_decision",
            opponent_count=opponent_count,
            pot=pot,
            call_amount=call_amount,
            facing_bet=(call_amount > 0),
        )

        # If facing a bet
        if call_amount > 0:
            return self._facing_flop_bet(gs, strength, draws, call_amount)

        # We have betting lead - consider c-bet
        return self._flop_cbet_decision(gs, strength, draws, opponent_count, pot)

    def _flop_cbet_decision(
        self, gs: GameState, strength: HandStrength, draws: list, opponent_count: int, pot: float
    ) -> Action:
        """
        C-bet decision on flop using enhanced board analysis and GTO baseline.

        Uses:
        - Enhanced board texture analysis
        - GTO baseline frequencies with 2NL exploits
        - SPR-based sizing adjustments
        """
        has_draw = has_strong_draw(draws)
        has_value = strength >= HandStrength.PAIR

        # Get enhanced board analysis
        board_analysis = analyze_flop(gs.board_cards)
        texture = board_analysis.texture_category

        # Get SPR for sizing adjustments
        spr = gs.stack_to_pot_ratio()
        spr_category = gs.spr_category

        # Get GTO-based c-bet recommendation with 2NL exploits
        is_ip = is_late_position(gs.position)
        should_cbet, gto_sizing, cbet_reason, cbet_button = get_cbet_recommendation(
            texture=texture,
            in_position=is_ip,
            opponent_count=opponent_count,
            has_value=has_value,
        )

        # Check for monotone board - need special handling
        is_monotone = board_analysis.monotone
        has_backdoor = hero_has_backdoor_flush(gs.hero_cards, gs.board_cards)
        has_flush_draw_now = hero_has_flush_draw(gs.hero_cards, gs.board_cards)

        self._trace.add(
            "_flop_cbet_decision",
            has_draw=has_draw,
            has_value=has_value,
            strength=strength.name,
            opponent_count=opponent_count,
            board_texture=texture.value,
            spr=f"{spr:.1f}",
            spr_category=spr_category.value,
            gto_cbet_sizing=cbet_button,
            board_connectedness=f"{board_analysis.connectedness:.2f}",
            is_monotone=is_monotone,
            has_backdoor_flush=has_backdoor,
        )

        # 3-BET POT DETECTION: If pot is unusually large, this is likely a 3-bet pot
        # In a 3-bet pot, we should check to the aggressor with marginal hands
        # Standard open-call pot at 2NL: ~$0.12 (3bb + 3bb + blinds)
        # 3-bet pot at 2NL: ~$0.80+ (open + 3-bet + call)
        is_likely_3bet_pot = pot > 0.50

        # DONK BETTING FIX: In 3-bet pots, don't lead with marginal hands
        # Check to the 3-bettor unless we have strong value or a draw
        pair_type = gs.pair_type
        if is_likely_3bet_pot and opponent_count <= 1:
            # In 3-bet pots, only lead with very strong hands or draws
            if strength <= HandStrength.PAIR:
                # With pairs, only lead with top pair+ or strong draws
                if pair_type not in (PairType.OVERPAIR, PairType.TOP_PAIR):
                    if not has_draw:
                        self._trace.add(
                            "check",
                            reason="3-bet pot: check underpair/medium pair to aggressor",
                        )
                        return check_action("Check to aggressor in 3-bet pot (don't donk)")

        if is_monotone and not has_backdoor and not has_flush_draw_now:
            # Check if we have an underpair (pair below board high card)
            if strength == HandStrength.PAIR and pair_type in (
                PairType.UNDERPAIR,
                PairType.SECOND_PAIR,
                PairType.BOTTOM_PAIR,
            ):
                self._trace.add(
                    "check",
                    reason="Monotone board leak fix: check underpair without backdoor flush",
                )
                return check_action("Check underpair on monotone (no backdoor flush)")

            # Also check back with just overcards (no pair, no backdoor)
            if strength <= HandStrength.HIGH_CARD:
                self._trace.add(
                    "check",
                    reason="Monotone board: check air without backdoor flush",
                )
                return check_action("Check air on monotone (no backdoor flush)")

        # PAIRED BOARD C-BETTING: High frequency with small sizing
        # Source: "Applications of No-Limit Hold'em" by Janda - paired boards favor PFR range
        # High paired boards (TT+) - c-bet ~80% with small sizing
        if board_analysis.paired_board and opponent_count <= 1:
            pair_rank_value = (
                get_rank_value(board_analysis.pair_rank) if board_analysis.pair_rank else 0
            )
            # High paired boards (TT+ = value 10+) favor our range strongly
            if pair_rank_value >= 10:
                small_bet = round(pot * 0.33, 2)  # Button 1 - small sizing
                self._trace.add(
                    "bet",
                    reason=f"Paired board c-bet (range advantage): {board_analysis.pair_rank}{board_analysis.pair_rank}x",
                )
                return bet_action(
                    small_bet,
                    reasoning="C-bet paired board (range advantage, small sizing)",
                    sizing_note="1",
                    button="1",
                )
            # Lower paired boards (99 and below) - still bet with value, check without
            elif has_value or has_draw:
                small_bet = round(pot * 0.33, 2)
                self._trace.add("bet", reason="Paired board c-bet with value")
                return bet_action(
                    small_bet,
                    reasoning="Value c-bet on paired board",
                    sizing_note="1",
                    button="1",
                )

        # Calculate actual bet amount using GTO sizing
        bet_amount = round(pot * gto_sizing, 2)
        sizing_button = cbet_button

        # Heads-up - follow GTO c-bet recommendation
        if opponent_count <= 1:
            if has_value or has_draw:
                self._trace.add("bet", reason=f"GTO c-bet HU on {texture.value} board")
                return bet_action(
                    bet_amount,
                    reasoning=cbet_reason,
                    sizing_note=sizing_button,
                    button=sizing_button,
                )
            else:
                # Bluff c-bet only on dry boards
                if texture == BoardTexture.DRY and should_cbet:
                    small_bet = round(pot * 0.33, 2)
                    self._trace.add("bet", reason="Bluff c-bet HU on dry board (one and done)")
                    return bet_action(
                        small_bet,
                        reasoning="C-bet bluff on dry board",
                        sizing_note="1",
                        button="1",
                    )
                self._trace.add("check", reason="No equity - don't bluff at 2NL")
                return check_action("Check air (don't bluff wet boards at 2NL)")

        # Multiway - tighten up significantly
        if opponent_count == 2:
            if has_value:
                self._trace.add("bet", reason="Value c-bet vs 2 opponents")
                return bet_action(
                    bet_amount,
                    reasoning="Value c-bet multiway (2NL: size up for value)",
                    sizing_note=sizing_button,
                    button=sizing_button,
                )
            if has_draw:
                self._trace.add("bet", reason="Semi-bluff draw vs 2")
                return bet_action(
                    bet_amount,
                    reasoning="Semi-bluff strong draw",
                    sizing_note=sizing_button,
                    button=sizing_button,
                )
            self._trace.add("check", reason="No equity vs 2 opponents")
            return check_action("Check back air multiway")

        # 3+ opponents - tighten range but still bet strong made hands
        # At 2NL, top pair is often best even multiway
        pair_type = gs.pair_type

        self._trace.add(
            "_multiway_cbet_check",
            opponent_count=opponent_count,
            strength=strength.name,
            pair_type=pair_type.value if pair_type else None,
            board_texture=texture.value,
        )

        # Two pair+ always bets for value
        if strength >= HandStrength.TWO_PAIR:
            large_bet = round(pot * 0.80, 2)
            self._trace.add("bet", reason="Value bet strong hand multiway")
            return bet_action(
                large_bet,
                reasoning="Value bet multiway (size up for 2NL)",
                sizing_note="3",
                button="3",
            )

        # Top pair / overpair - bet for value AND protection on drawy boards
        if strength >= HandStrength.PAIR:
            if pair_type in (PairType.TOP_PAIR, PairType.OVERPAIR):
                # Size up on wet/medium boards to charge draws
                if texture in (BoardTexture.WET, BoardTexture.MEDIUM):
                    value_bet = round(pot * 0.80, 2)
                    self._trace.add("bet", reason="Value bet top pair multiway (charge draws)")
                    return bet_action(
                        value_bet,
                        reasoning="Value bet top pair (charge draws at 2NL)",
                        sizing_note="3",
                        button="3",
                    )
                else:
                    # Dry board - can bet smaller
                    value_bet = round(pot * 0.66, 2)
                    self._trace.add("bet", reason="Value bet top pair on dry board")
                    return bet_action(
                        value_bet,
                        reasoning="Value bet top pair (dry board)",
                        sizing_note="2",
                        button="2",
                    )

        self._trace.add("check", reason="Weak hand multiway - check back")
        return check_action("Check back weak hand multiway")

    def _facing_flop_bet(
        self, gs: GameState, strength: HandStrength, draws: list, call_amount: float
    ) -> Action:
        """
        Decision when facing a flop bet.

        Uses:
        - MDF calculations for defense frequency
        - SPR-based commitment decisions
        - 2NL exploitative adjustments
        - Monotone board handling (don't call with overcards, no backdoor)
        - Float prevention (require pair or draw to continue)
        """
        pot = gs.pot
        pot_odds = gs.pot_odds()
        outs = count_outs(draws)
        spr = gs.stack_to_pot_ratio()
        spr_category = gs.spr_category
        pair_type = gs.pair_type

        # Calculate MDF
        mdf = calculate_mdf(call_amount, pot - call_amount)

        # Get SPR-based commitment level
        commitment = get_commitment_level(strength, pair_type, get_spr_strategy(spr))

        # Check for monotone board
        board_analysis = analyze_flop(gs.board_cards)
        is_monotone = board_analysis.monotone
        has_backdoor = hero_has_backdoor_flush(gs.hero_cards, gs.board_cards)
        has_flush_draw_now = hero_has_flush_draw(gs.hero_cards, gs.board_cards)

        self._trace.add(
            "_facing_flop_bet",
            pot=pot,
            pot_odds=f"{pot_odds * 100:.1f}%",
            mdf=f"{mdf * 100:.0f}%",
            strength=strength.name,
            pair_type=pair_type.value if pair_type else None,
            spr=f"{spr:.1f}",
            commitment=commitment.value,
            outs=outs,
            is_monotone=is_monotone,
            has_backdoor_flush=has_backdoor,
        )

        # MONOTONE BOARD FIX: Fold overcards on monotone boards without backdoor flush
        if is_monotone and not has_backdoor and not has_flush_draw_now:
            # Only continue with a made hand (pair+) or strong draw
            if strength <= HandStrength.HIGH_CARD and outs < 8:
                self._trace.add(
                    "fold",
                    reason="Monotone board leak fix: fold overcards without backdoor flush",
                )
                return fold_action("Fold on monotone - no backdoor flush equity")

        # FLOAT PREVENTION: Fold high card hands without strong draws on ANY board
        # At 2NL, floating with just overcards burns money
        if strength <= HandStrength.HIGH_CARD:
            if outs < 8:  # Need at least 8 outs (OESD or flush draw) to continue
                self._trace.add(
                    "fold",
                    reason=f"Float prevention: high card with only {outs} outs on flop",
                )
                return fold_action("Fold high card on flop (don't float at 2NL)")

        # Monster hands - raise for value
        if strength >= HandStrength.THREE_OF_KIND:
            raise_amount, button = calculate_check_raise(call_amount, pot)
            self._trace.add("raise", reason="Check-raise set for value")
            return raise_action(
                raise_amount,
                reasoning="Check-raise set for value",
                sizing_note=button,
                button=button,
            )

        # Two pair - raise at low/medium SPR
        if strength >= HandStrength.TWO_PAIR:
            if spr_category in (SPRCategory.LOW, SPRCategory.MEDIUM):
                raise_amount, button = calculate_check_raise(call_amount, pot)
                self._trace.add("raise", reason="Check-raise two-pair at favorable SPR")
                return raise_action(
                    raise_amount,
                    reasoning="Check-raise two-pair",
                    sizing_note=button,
                    button=button,
                )
            # High SPR - just call to control pot
            self._trace.add("call", reason="Call two-pair at high SPR (pot control)")
            return call_action(call_amount, reasoning="Call two-pair (high SPR pot control)")

        # One pair hands - depends on pair type and SPR
        if strength == HandStrength.PAIR:
            if commitment == CommitmentLevel.FULLY_COMMITTED:
                # Low SPR with top pair+ - can even raise
                if pair_type in (PairType.OVERPAIR, PairType.TOP_PAIR):
                    self._trace.add("call", reason=f"Call {pair_type.value} (committed at low SPR)")
                    return call_action(call_amount, reasoning=f"Call {pair_type.value} (low SPR)")

            if commitment in (CommitmentLevel.WILLING_TO_COMMIT, CommitmentLevel.POT_CONTROL):
                # Check if it's a strong enough pair
                if pair_type in (PairType.OVERPAIR, PairType.TOP_PAIR, PairType.SECOND_PAIR):
                    self._trace.add("call", reason=f"Defend {pair_type.value} (above MDF)")
                    return call_action(call_amount, reasoning=f"Call {pair_type.value}")

        # Drawing hands - use equity vs pot odds
        if outs > 0:
            equity = equity_estimate(strength, draws, "flop")
            self._trace.add("draw_check", equity=f"{equity * 100:.1f}%", outs=outs)

            # Strong draws (8+ outs) - always continue
            if outs >= 8:
                self._trace.add("call", reason=f"Strong draw ({outs} outs) has equity")
                return call_action(call_amount, reasoning=f"Call strong draw ({outs} outs)")

            # Medium draws - need good pot odds
            if equity >= pot_odds:
                self._trace.add("call", reason=f"Draw has odds ({outs} outs)")
                return call_action(call_amount, reasoning=f"Call draw ({outs} outs)")

        # Weak hand - fold (2NL exploit: don't float without equity)
        self._trace.add("fold", reason="No equity to continue at 2NL")
        return fold_action("Fold weak hand (don't float at 2NL)")

    def _turn_decision(self, gs: GameState, strength: HandStrength, draws: list) -> Action:
        """
        Turn decision logic using SPR-based value betting.

        Uses:
        - SPR to determine value bet thresholds
        - Board danger assessment
        - Multi-street planning concepts
        """
        pot = gs.pot
        call_amount = gs.to_call()
        spr = gs.stack_to_pot_ratio()
        spr_category = gs.spr_category
        pair_type = gs.pair_type

        # Facing a bet
        if call_amount > 0:
            return self._facing_turn_bet(gs, strength, draws, call_amount)

        # Get SPR strategy for thresholds
        spr_strat = get_spr_strategy(spr)

        # Get board texture for TPTK sizing decisions
        board_analysis = analyze_flop(gs.board_cards)
        texture = board_analysis.texture_category

        self._trace.add(
            "_turn_decision",
            strength=strength.name,
            pair_type=pair_type.value if pair_type else None,
            spr=f"{spr:.1f}",
            spr_category=spr_category.value,
            value_threshold=spr_strat.value_bet_threshold.name,
            board_texture=texture.value,
        )

        # Check board danger first
        if gs.board_danger.danger_level == "extreme":
            self._trace.add("check", reason="Extreme board danger (4-flush)")
            return check_action("Check on dangerous board (4-flush)")

        # Monsters - always value bet
        if strength >= HandStrength.THREE_OF_KIND:
            bet_amount, button = calculate_value_bet(pot, "turn")
            self._trace.add("bet", reason="Value bet monster on turn")
            return bet_action(
                bet_amount, reasoning="Value bet set+", sizing_note=button, button=button
            )

        # Two pair - value bet unless extreme danger
        if strength >= HandStrength.TWO_PAIR:
            bet_amount, button = calculate_value_bet(pot, "turn")
            self._trace.add("bet", reason="Value bet two pair")
            return bet_action(
                bet_amount, reasoning="Value bet two pair", sizing_note=button, button=button
            )

        # One pair - depends on SPR and pair type
        if strength == HandStrength.PAIR:
            if pair_type == PairType.OVERPAIR:
                # Overpair: Value bet at all SPRs
                bet_amount, button = calculate_value_bet(pot, "turn")
                self._trace.add("bet", reason="Value bet overpair on turn")
                return bet_action(
                    bet_amount, reasoning="Value bet overpair", sizing_note=button, button=button
                )

            if pair_type == PairType.TOP_PAIR:
                # TPTK: Always bet for value at 2NL - opponents call too light
                # Use full turn board texture for sizing (may differ from flop texture)
                bet_amount, button, reason, turn_texture = get_tptk_turn_sizing(gs.board_cards, pot)

                self._trace.add(
                    "bet",
                    reason=f"Value bet TPTK ({turn_texture.value} board)",
                    board_texture=turn_texture.value,
                )
                return bet_action(bet_amount, reasoning=reason, sizing_note=button, button=button)

            # Weak pairs - check for showdown
            if pair_type in (PairType.UNDERPAIR, PairType.SECOND_PAIR, PairType.BOTTOM_PAIR):
                self._trace.add("check", reason=f"Check {pair_type.value} for showdown")
                return check_action(f"Check {pair_type.value} for showdown value")

        # Check draws for free river
        if has_strong_draw(draws):
            self._trace.add("check", reason="Check draw for free card")
            return check_action("Check draw for free card")

        self._trace.add("check", reason="Check back weak hand")
        return check_action("Check back weak hand")

    def _facing_turn_bet(
        self, gs: GameState, strength: HandStrength, draws: list, call_amount: float
    ) -> Action:
        """
        Decision when facing a turn bet.

        From guide: "A raise on the turn is usually the nuts"
        - If facing a RAISE (we bet, they raised), fold overpairs/TPTK
        - Only continue with sets+, or nut draws (12+ outs)
        """
        pot_odds = gs.pot_odds()

        # Check if this is a RAISE (we already bet and got raised)
        hero_bet = gs.bets.get(gs.hero_seat, 0) or 0
        is_facing_raise = hero_bet > 0 and call_amount > 0

        self._trace.add(
            "_facing_turn_bet",
            is_facing_raise=is_facing_raise,
            strength=strength.name,
            call_amount=call_amount,
        )

        if is_facing_raise:
            # "A raise on the turn is usually the nuts"
            # Only continue with sets, straights, flushes, or nut draws
            if strength >= HandStrength.THREE_OF_KIND:
                self._trace.add("call", reason="Continue vs turn raise with set+")
                return call_action(call_amount, reasoning="Call turn raise with set+")

            # Check for nut draws (combo draws, 12+ outs)
            outs = count_outs(draws)
            if outs >= 12:
                self._trace.add("call", reason="Continue vs turn raise with nut draw")
                return call_action(
                    call_amount, reasoning=f"Call turn raise with nut draw ({outs} outs)"
                )

            # Fold overpairs and TPTK to turn raises
            self._trace.add("fold", reason="Fold to turn raise (they have two pair+)")
            return fold_action("Fold to turn raise - they have it")

        # Standard turn facing bet logic (not a raise)
        opponent_count = gs.active_opponent_count()
        pair_type = gs.pair_type
        hero_stack = gs.hero_stack()
        is_all_in_call = call_amount >= hero_stack * 0.9  # Calling commits 90%+ of stack

        self._trace.add(
            "_facing_turn_bet_analysis",
            opponent_count=opponent_count,
            pair_type=pair_type.value if pair_type else None,
            is_all_in_call=is_all_in_call,
            pot_odds=f"{pot_odds * 100:.1f}%",
        )

        # FLOAT PREVENTION: Fold high card hands without strong draws on turn
        # At 2NL, floating with just overcards is burning money
        outs = count_outs(draws)
        if strength <= HandStrength.HIGH_CARD:
            if outs < 8:  # Need at least 8 outs (OESD or flush draw) to continue
                self._trace.add(
                    "fold",
                    reason=f"Float prevention: high card with only {outs} outs on turn",
                )
                return fold_action("Fold high card on turn (don't float at 2NL)")

        if strength >= HandStrength.TWO_PAIR:
            self._trace.add("call", reason="Two pair+ always continues")
            return call_action(call_amount, reasoning="Call with two pair+")

        if strength >= HandStrength.PAIR:
            # Use proper pair type classification instead of string matching
            if pair_type == PairType.OVERPAIR:
                self._trace.add("call", reason="Overpair continues on turn")
                return call_action(call_amount, reasoning="Call with overpair")

            if pair_type == PairType.TOP_PAIR:
                # Top pair: call heads-up, fold multiway or if all-in call
                if opponent_count <= 1 and not is_all_in_call:
                    self._trace.add("call", reason="Top pair continues HU")
                    return call_action(call_amount, reasoning="Call with top pair")
                elif opponent_count > 1:
                    self._trace.add("fold", reason="Top pair folds multiway on turn")
                    return fold_action("Fold top pair multiway (too many opponents)")
                else:
                    # All-in call with top pair - need good kicker
                    self._trace.add("fold", reason="Top pair folds to all-in on turn")
                    return fold_action("Fold top pair to all-in (marginal spot)")

            # Weaker pairs (second pair, bottom pair, underpair) - only with great odds
            if pair_type in (PairType.SECOND_PAIR, PairType.BOTTOM_PAIR, PairType.UNDERPAIR):
                # Need very good pot odds (< 20%) to continue with weak pairs
                if pot_odds <= 0.20 and opponent_count <= 1:
                    self._trace.add(
                        "call", reason=f"Weak pair with good odds ({pot_odds * 100:.0f}%)"
                    )
                    return call_action(call_amount, reasoning=f"Call {pair_type.value} (good odds)")
                self._trace.add("fold", reason=f"{pair_type.value} too weak on turn")
                return fold_action(f"Fold {pair_type.value} on turn")

            # Board pair or unknown pair type - very weak, fold
            if pair_type == PairType.BOARD_PAIR or pair_type is None:
                self._trace.add("fold", reason="Board pair only - no real hand")
                return fold_action("Fold board pair on turn")

        # Draws with odds
        outs = count_outs(draws)
        if outs > 0:
            equity = equity_estimate(strength, draws, "turn")
            if equity >= pot_odds:
                self._trace.add("call", reason=f"Draw has odds ({outs} outs)")
                return call_action(call_amount, reasoning=f"Call draw ({outs} outs)")

        self._trace.add("fold", reason="No equity to continue")
        return fold_action("Fold to turn bet")

    def _river_decision(self, gs: GameState, strength: HandStrength) -> Action:
        """
        River decision logic.

        From guide:
        - OVERBET SHOVE (1.5x-2x pot) with NUTS on action rivers
        - Action rivers = completing flush/straight draws
        - Fish cannot fold straights, flushes, sets
        - Never bluff at 2NL
        """
        pot = gs.pot
        call_amount = gs.to_call()
        hero_stack = gs.hero_stack()

        # Facing a bet
        if call_amount > 0:
            return self._facing_river_bet(gs, strength, call_amount)

        # Check for action river (completing draws)
        action_river = is_action_river(gs.board_cards)

        self._trace.add(
            "_river_decision", strength=strength.name, action_river=action_river, pot=pot
        )

        # Check board danger first - don't value bet weak hands into dangerous boards
        if gs.board_danger.danger_level == "extreme" and strength < HandStrength.FLUSH:
            self._trace.add("check", reason="Extreme board danger (4-flush)")
            return check_action("Check on dangerous board (4-flush)")

        # We have action - value bet or check
        if strength >= HandStrength.STRAIGHT:
            # OVERBET SHOVE with the nuts on action rivers - use 100% button
            if action_river:
                overbet_amount, button = calculate_overbet(pot, hero_stack)
                self._trace.add("overbet", reason="Overbet shove nuts on action river")
                return bet_action(
                    overbet_amount,
                    reasoning="POT on action river (fish can't fold)",
                    sizing_note=button,
                    button=button,
                )
            else:
                # Standard value bet with strong hands - use 80% on river
                bet_amount, button = calculate_value_bet(pot, "river")
                self._trace.add("bet", reason="Value bet strong hand")
                return bet_action(
                    bet_amount, reasoning="Value bet river", sizing_note=button, button=button
                )

        if strength >= HandStrength.TWO_PAIR:
            bet_amount, button = calculate_value_bet(pot, "river")
            return bet_action(
                bet_amount, reasoning="Value bet two pair+", sizing_note=button, button=button
            )

        # Thin value with pairs - use proper classification
        if strength >= HandStrength.PAIR:
            pair_type = gs.pair_type

            if pair_type == PairType.OVERPAIR:
                bet_amount, button = calculate_value_bet(pot, "river")
                return bet_action(
                    bet_amount,
                    reasoning="Thin value with overpair",
                    sizing_note=button,
                    button=button,
                )

            if pair_type == PairType.TOP_PAIR:
                bet_amount, button = calculate_value_bet(pot, "river")
                return bet_action(
                    bet_amount,
                    reasoning="Thin value with top pair",
                    sizing_note=button,
                    button=button,
                )

            # Second pair - thin value bet on SAFE boards at 2NL (they call with worse)
            # Source: "Crushing the Microstakes" - value bet thinly, they call with anything
            if pair_type == PairType.SECOND_PAIR:
                if is_safe_board_for_thin_value(gs.board_cards):
                    # Small sizing (33% pot) for thin value
                    small_bet = round(pot * 0.33, 2)
                    self._trace.add("thin_value", reason="Second pair on safe board")
                    return bet_action(
                        small_bet,
                        reasoning="Thin value second pair (safe board, 2NL calls light)",
                        sizing_note="1",
                        button="1",
                    )
                # Unsafe board - check for showdown
                return check_action("Check second pair (unsafe board)")

            # Underpair, bottom pair - check for showdown (too weak to value bet)
            if pair_type in (PairType.UNDERPAIR, PairType.BOTTOM_PAIR):
                return check_action(f"Check {pair_type.value} for showdown")

        # Rule: Never bluff river at 2NL
        return check_action("Don't bluff river at 2NL")

    def _facing_river_bet(
        self, gs: GameState, strength: HandStrength, call_amount: float
    ) -> Action:
        """
        Decision when facing a river bet.

        From guide: "A raise on the river is ALWAYS the nuts"
        - If facing a RAISE (we bet, they raised), fold everything except the nuts
        - Fold overpairs, two pair, even sets to river raises
        """
        pot_odds = gs.pot_odds()

        # Check if this is a RAISE (we already bet and got raised)
        hero_bet = gs.bets.get(gs.hero_seat, 0) or 0
        is_facing_raise = hero_bet > 0 and call_amount > 0

        self._trace.add(
            "_facing_river_bet",
            is_facing_raise=is_facing_raise,
            strength=strength.name,
            call_amount=call_amount,
        )

        if is_facing_raise:
            # "A raise on the river is ALWAYS the nuts"
            # Only call with the nuts (flush, straight, or better)
            if strength >= HandStrength.FLUSH:
                self._trace.add("call", reason="Call river raise with near-nuts")
                return call_action(call_amount, reasoning="Call river raise with strong flush+")

            # Fold overpairs, two pair, even sets to river raises
            self._trace.add("fold", reason="Fold to river raise (it's always the nuts)")
            return fold_action("Fold to river raise - believe them")

        # Standard river facing bet logic (not a raise)
        pair_type = gs.pair_type
        pot = gs.pot

        # Calculate MDF for bluffcatcher defense
        mdf = calculate_mdf(call_amount, pot - call_amount)

        self._trace.add(
            "_river_defense_analysis",
            pair_type=pair_type.value if pair_type else None,
            pot_odds=f"{pot_odds * 100:.1f}%",
            mdf=f"{mdf * 100:.0f}%",
        )

        # Two pair+ - always call standard river bets
        if strength >= HandStrength.TWO_PAIR:
            self._trace.add("call", reason="Two pair+ always calls river bet")
            return call_action(call_amount, reasoning="Call with strong hand")

        # Pair hands - defend based on pair type and pot odds
        if strength >= HandStrength.PAIR:
            # Overpair - always call standard river bets (it's a strong hand)
            if pair_type == PairType.OVERPAIR:
                self._trace.add("call", reason="Overpair calls river bet")
                return call_action(call_amount, reasoning="Call with overpair")

            # Top pair - call with reasonable pot odds
            if pair_type == PairType.TOP_PAIR:
                if pot_odds <= 0.35:  # Call if need 35% or less equity
                    self._trace.add("call", reason="Top pair calls river bet (good odds)")
                    return call_action(call_amount, reasoning="Call with top pair (good odds)")
                self._trace.add("fold", reason="Top pair folds to overbet")
                return fold_action("Fold top pair to large river bet")

            # Second pair / underpair - only call with very good odds (bluffcatcher)
            # At 2NL, 2nd pair can be a bluffcatcher if we're getting good odds
            if pair_type in (PairType.SECOND_PAIR, PairType.UNDERPAIR):
                if pot_odds <= 0.25:  # Need at least 4:1 odds
                    self._trace.add(
                        "call",
                        reason=f"Bluffcatcher call {pair_type.value} (pot odds {pot_odds:.0%})",
                    )
                    return call_action(
                        call_amount,
                        reasoning=f"Bluffcatcher call {pair_type.value} (good odds)",
                    )
                self._trace.add("fold", reason=f"{pair_type.value} folds to river bet")
                return fold_action(f"Fold {pair_type.value} to river bet")

        # Fold to river aggression with weak hands (high card or bottom pair)
        self._trace.add("fold", reason="Weak hand folds to river bet")
        return fold_action("Fold to river bet")

    def _apply_villain_adjustments(
        self,
        action: Action,
        gs: GameState,
        villain_stats: dict[int, PlayerStats],
    ) -> Action:
        """
        Apply villain-specific adjustments to the action.

        Modifies the action based on opponent tendencies:
        - vs Fish (VPIP > 40%): Value bet thinner, never bluff
        - vs Nit (VPIP < 15%): Respect their aggression, fold more
        - vs LAG (high VPIP + aggression): Call down lighter
        - vs Maniac: Trap more, call down very light

        Args:
            action: Base action from standard strategy
            gs: Current game state
            villain_stats: Dict of seat -> PlayerStats

        Returns:
            Adjusted action (may be same as input)
        """
        # Find the aggressor (if any)
        aggressor_seat = self._find_aggressor_seat(gs)
        if not aggressor_seat or aggressor_seat not in villain_stats:
            return action  # No villain data for aggressor

        villain = villain_stats[aggressor_seat]

        # Skip adjustment if not enough data (need 15+ hands)
        if villain.hands_seen < 15:
            return action

        player_type = villain.player_type
        self._trace.add(
            "villain_adjustment",
            seat=aggressor_seat,
            player_type=player_type,
            vpip=f"{villain.vpip:.0f}%",
            pfr=f"{villain.pfr:.0f}%",
            af=f"{villain.aggression_factor:.1f}",
            hands=villain.hands_seen,
        )

        # Apply type-specific adjustments
        if player_type == "fish":
            return self._adjust_vs_fish(action, gs, villain)
        elif player_type == "nit":
            return self._adjust_vs_nit(action, gs, villain)
        elif player_type == "LAG":
            return self._adjust_vs_lag(action, gs, villain)
        elif player_type == "maniac":
            return self._adjust_vs_maniac(action, gs, villain)

        return action

    def _find_aggressor_seat(self, gs: GameState) -> int | None:
        """Find the seat of the last aggressor (raiser/bettor)."""
        max_bet = 0
        aggressor = None

        for seat, bet in gs.bets.items():
            if seat == gs.hero_seat:
                continue
            if bet and bet > max_bet:
                max_bet = bet
                aggressor = seat

        return aggressor

    def _adjust_vs_fish(self, action: Action, gs: GameState, villain: PlayerStats) -> Action:
        """
        Adjust action vs fish (loose passive).

        Strategy (from "Crushing the Microstakes"):
        - Value bet thinner (they call too much)
        - Size up for value (75%+ pot recommended)
        - Never bluff (they don't fold)
        - Call wider on defense (they're bluffing less often than they seem)
        """
        # If we're bluffing, convert to check (fish don't fold)
        if action.action_type in (ActionType.BET, ActionType.RAISE):
            strength = gs.hand_strength
            if strength <= HandStrength.HIGH_CARD:
                self._trace.add("fish_adjust", change="bluff_to_check", reason="Fish don't fold")
                return check_action("Check vs fish (they don't fold bluffs)")

        # Widen value betting threshold with LARGER sizing
        # Source: "Crushing the Microstakes" - 75%+ pot vs recreational players
        if action.action_type == ActionType.CHECK:
            strength = gs.hand_strength
            pot = gs.pot or 0.03

            # Value bet medium pairs vs fish with larger sizing
            if strength >= HandStrength.PAIR:
                # River with two pair+ - go for pot (100%)
                if gs.street == Street.RIVER and strength >= HandStrength.TWO_PAIR:
                    bet_size = round(pot * 1.0, 2)  # Full pot - fish can't fold
                    self._trace.add(
                        "fish_adjust", change="pot_value", reason="Fish can't fold strong hands"
                    )
                    return bet_action(
                        bet_size,
                        reasoning="Pot vs fish (they can't fold)",
                        sizing_note="4",
                        button="4",
                    )
                # Standard value - 80% pot (up from 50%)
                bet_size = round(pot * 0.80, 2)
                self._trace.add(
                    "fish_adjust", change="large_value", reason="Fish call too light - size up"
                )
                return bet_action(
                    bet_size,
                    reasoning="Value vs fish (80% pot - they call anything)",
                    sizing_note="3",
                    button="3",
                )

        return action

    def _adjust_vs_nit(self, action: Action, gs: GameState, villain: PlayerStats) -> Action:
        """
        Adjust action vs nit (tight passive).

        Strategy:
        - Respect their aggression (they have it when they bet)
        - Fold more to their bets/raises
        - Bluff more when they check (high fold frequency)
        """
        to_call = gs.to_call()

        # If nit is betting, they have a strong hand
        if to_call > 0 and action.action_type == ActionType.CALL:
            strength = gs.hand_strength
            # Fold medium hands to nit aggression
            if strength < HandStrength.TWO_PAIR:
                self._trace.add("nit_adjust", change="tighten_defense", reason="Nit has it")
                return fold_action("Fold to nit aggression (they always have it)")

        # If nit checked to us, bluff more
        if to_call == 0 and action.action_type == ActionType.CHECK:
            # Bluff with overcards or backdoors
            draws = gs.draws
            if draws or gs.hand_strength == HandStrength.HIGH_CARD:
                pot = gs.pot or 0.03
                bet_size = pot * 0.5
                self._trace.add("nit_adjust", change="bluff_more", reason="Nit folds a lot")
                return bet_action(
                    bet_size, reasoning="Bluff vs nit (high fold equity)", sizing_note="50% pot"
                )

        return action

    def _adjust_vs_lag(self, action: Action, gs: GameState, villain: PlayerStats) -> Action:
        """
        Adjust action vs LAG (loose aggressive).

        Strategy:
        - Call down lighter (they bluff more)
        - Don't give up medium pairs
        - Trap more with monsters
        """
        to_call = gs.to_call()

        # Call down lighter vs LAG
        if to_call > 0 and action.action_type == ActionType.FOLD:
            strength = gs.hand_strength
            pot_odds = gs.pot_odds()

            # Call with pairs if pot odds are decent
            if strength >= HandStrength.PAIR and pot_odds <= 0.35:
                self._trace.add("lag_adjust", change="call_down_light", reason="LAG bluffs often")
                return call_action(to_call, reasoning="Call down vs LAG")

        return action

    def _adjust_vs_maniac(self, action: Action, gs: GameState, villain: PlayerStats) -> Action:
        """
        Adjust action vs maniac (very loose very aggressive).

        Strategy:
        - Trap with strong hands (they hang themselves)
        - Call down even lighter
        - Let them bluff into our strong hands
        """
        to_call = gs.to_call()
        strength = gs.hand_strength

        # Trap with strong hands instead of raising
        if action.action_type == ActionType.RAISE and strength >= HandStrength.TWO_PAIR:
            if to_call > 0:
                self._trace.add("maniac_adjust", change="trap", reason="Let maniac keep bluffing")
                return call_action(to_call, reasoning="Trap maniac (let them bluff)")

        # Call with any pair
        if to_call > 0 and action.action_type == ActionType.FOLD:
            if strength >= HandStrength.PAIR:
                self._trace.add(
                    "maniac_adjust", change="hero_call", reason="Maniac bluffs constantly"
                )
                return call_action(to_call, reasoning="Hero call vs maniac")

        return action
