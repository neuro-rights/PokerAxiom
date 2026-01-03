"""
Session tracker for opponent modeling.

Tracks player actions across hands to build opponent statistics
in real-time during a playing session.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..paths import DATA_DIR
from .game_state import GameState, Street
from .opponent_db import OpponentDatabase, PlayerStats

# Setup dedicated logger with rolling file handler
_logger = logging.getLogger("session_tracker")
_logger.setLevel(logging.DEBUG)

# Avoid duplicate handlers if module is reloaded
if not _logger.handlers:
    _log_file = DATA_DIR / "session_tracker.log"
    _handler = RotatingFileHandler(_log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
    )
    _logger.addHandler(_handler)


class DetectedAction(Enum):
    """Actions detected from state changes."""

    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"
    POST_BLIND = "post_blind"


@dataclass
class HandState:
    """Tracks state of a single hand for action detection."""

    hand_id: int = 0  # Unique ID for this hand
    street: Street = Street.PREFLOP
    is_active: bool = False
    hero_cards: list[str] = field(default_factory=list)

    # Per-seat tracking for this hand
    # seat -> list of detected actions
    seat_actions: dict[int, list[DetectedAction]] = field(default_factory=dict)

    # Track what we've already counted for stats (avoid double counting)
    vpip_counted: set[int] = field(default_factory=set)  # Seats where VPIP was counted
    pfr_counted: set[int] = field(default_factory=set)  # Seats where PFR was counted

    # Previous state for diff detection
    prev_bets: dict[int, float] = field(default_factory=dict)
    prev_active: dict[int, bool] = field(default_factory=dict)
    prev_stacks: dict[int, float] = field(default_factory=dict)


class SessionTracker:
    """
    Tracks opponent actions and builds stats during a session.

    Usage:
        tracker = SessionTracker()
        while playing:
            names = read_all_names(img, calibration, size)
            tracker.update(game_state, names)
            stats = tracker.get_seat_stats()  # For HUD display
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize session tracker.

        Args:
            db_path: Optional path to opponent database. Uses default if None.
        """
        self.db = OpponentDatabase(db_path)

        # Current seat -> player name mapping
        self.seat_names: dict[int, str] = {}

        # In-memory stats for current session (for quick HUD access)
        self.session_stats: dict[str, PlayerStats] = {}

        # Current hand state
        self.hand_state = HandState()
        self.hand_counter = 0

        # Tolerance for bet comparison (handles OCR errors)
        self.bet_tolerance = 0.005  # $0.005

    def update(self, game_state: GameState, names: dict[int, str | None] | None = None) -> None:
        """
        Update tracker with current game state.

        Call this on every frame to detect state changes.

        Args:
            game_state: Current detected GameState
            names: Optional seat -> name mapping from name OCR
        """
        # Update seat->name mapping
        if names:
            for seat, name in names.items():
                if name:
                    self._update_seat_name(seat, name)

        # Check for hand boundary
        if self._is_new_hand(game_state):
            self._start_new_hand(game_state)
        elif self._is_hand_complete(game_state):
            self._complete_hand()
            return

        # Detect actions from state changes
        self._detect_actions(game_state)

        # Update previous state for next comparison
        self._save_previous_state(game_state)

    def _update_seat_name(self, seat: int, name: str) -> None:
        """
        Update seat->name mapping and load stats if new player.

        Detects player changes at a seat and updates accordingly.
        """
        # Check if a different player is now at this seat
        if seat in self.seat_names:
            if self.seat_names[seat] == name:
                return  # Same player, no update needed
            # Different player at this seat - clear old mapping
            del self.seat_names[seat]

        # Set name for this seat
        self.seat_names[seat] = name

        # Load their stats from DB if not already in session
        if name not in self.session_stats:
            db_stats = self.db.get_or_create_player(name)
            self.session_stats[name] = db_stats

    def clear_seat(self, seat: int) -> None:
        """Clear a seat when player leaves (call when seat is empty)."""
        if seat in self.seat_names:
            del self.seat_names[seat]

    def _is_new_hand(self, game_state: GameState) -> bool:
        """Detect if a new hand has started."""
        # New hero cards dealt
        if not self.hand_state.hero_cards and game_state.hero_cards:
            valid_cards = [c for c in game_state.hero_cards if c and c != "--"]
            if len(valid_cards) == 2:
                return True

        # Cards changed (new hand after fold/completion)
        if self.hand_state.hero_cards and game_state.hero_cards:
            old_cards = set(self.hand_state.hero_cards)
            new_cards = set(c for c in game_state.hero_cards if c and c != "--")
            if len(new_cards) == 2 and new_cards != old_cards:
                return True

        return False

    def _is_hand_complete(self, game_state: GameState) -> bool:
        """Detect if the current hand has completed."""
        if not self.hand_state.is_active:
            return False

        # Hero folded (no cards)
        valid_hero = [c for c in game_state.hero_cards if c and c != "--"]
        if self.hand_state.hero_cards and len(valid_hero) == 0:
            return True

        # Pot went to 0 (hand finished)
        if game_state.pot <= 0 and self.hand_state.is_active:
            return True

        # Only one player left with cards
        active_count = sum(1 for v in game_state.active_seats.values() if v)
        if active_count <= 1 and self.hand_state.street != Street.PREFLOP:
            return True

        return False

    def _start_new_hand(self, game_state: GameState) -> None:
        """Initialize state for a new hand."""
        self.hand_counter += 1
        self.hand_state = HandState(
            hand_id=self.hand_counter,
            street=game_state.street,
            is_active=True,
            hero_cards=list(game_state.hero_cards),
        )

        # Initialize per-seat tracking
        for seat in range(1, 10):
            self.hand_state.seat_actions[seat] = []

        # Log new hand
        _logger.info(f"=== NEW HAND #{self.hand_counter} === Hero: {game_state.hero_cards}")
        _logger.debug(f"Seats mapped: {list(self.seat_names.keys())}")
        _logger.debug(f"Initial bets: {game_state.bets}")
        _logger.debug(f"Active seats: {game_state.active_seats}")

        # Increment hands_seen for all players at the table
        for seat, name in self.seat_names.items():
            if name and seat != 1:  # Not hero
                if name in self.session_stats:
                    self.session_stats[name].hands_seen += 1

        # Detect actions from initial bet state (actions that happened before we saw the hand)
        self._detect_initial_actions(game_state)

        # Record initial state AFTER detecting initial actions
        self._save_previous_state(game_state)

    def _detect_initial_actions(self, game_state: GameState) -> None:
        """
        Detect actions from initial bet state when hand is first seen.

        By the time we detect a new hand (hero cards visible), other players
        may have already acted. We infer their actions from the bet amounts.
        """
        if game_state.street != Street.PREFLOP:
            return  # Only analyze preflop initial state

        bb = game_state.bb

        # Find blind positions to exclude from action detection
        # Blinds are expected to have bet SB/BB amounts
        sb_seat, bb_seat = game_state._get_blind_seats()
        _logger.debug(f"Blind seats: SB={sb_seat}, BB={bb_seat}")

        # Collect all non-blind bets to analyze
        player_bets: list[tuple[int, float]] = []  # (seat, bet)
        for seat in range(2, 10):  # Skip hero (seat 1)
            name = self.seat_names.get(seat)
            if not name:
                continue

            bet = game_state.bets.get(seat) or 0
            is_active = game_state.active_seats.get(seat, False)

            # Skip if no bet or player already folded
            if bet <= 0 or not is_active:
                continue

            # Skip blind posts (SB with ~0.01, BB with ~0.02)
            if seat == sb_seat and abs(bet - game_state.sb) < self.bet_tolerance:
                continue
            if seat == bb_seat and abs(bet - bb) < self.bet_tolerance:
                continue

            player_bets.append((seat, bet))

        if not player_bets:
            return

        # Find the maximum bet - this is the raise amount
        max_bet = max(bet for _, bet in player_bets)

        # Track if we've already credited someone with the raise at max_bet level
        raise_credited = False

        # Process bets - only ONE player gets credit for a raise at each bet level
        for seat, bet in player_bets:
            if bet >= bb * 2.2:
                # This is raise territory
                if abs(bet - max_bet) < self.bet_tolerance and not raise_credited:
                    # First player at max bet level gets the raise credit
                    self._record_action(seat, DetectedAction.RAISE, game_state)
                    _logger.debug(f"INITIAL: Seat {seat} bet ${bet:.2f} → RAISE")
                    raise_credited = True
                else:
                    # Others at same bet level called the raise
                    self._record_action(seat, DetectedAction.CALL, game_state)
                    _logger.debug(f"INITIAL: Seat {seat} bet ${bet:.2f} → CALL (vs raise)")
            elif abs(bet - bb) < self.bet_tolerance:
                # Limp (called BB)
                self._record_action(seat, DetectedAction.CALL, game_state)
                _logger.debug(f"INITIAL: Seat {seat} bet ${bet:.2f} → CALL (limp)")
            elif bet > bb:
                # Bet more than BB but less than raise threshold - likely a call
                self._record_action(seat, DetectedAction.CALL, game_state)
                _logger.debug(f"INITIAL: Seat {seat} bet ${bet:.2f} → CALL (vs raise)")

    def _complete_hand(self) -> None:
        """Finalize hand and save stats to database."""
        if not self.hand_state.is_active:
            return

        self.hand_state.is_active = False

        # Log hand completion summary
        actions_summary = {
            seat: [a.value for a in actions]
            for seat, actions in self.hand_state.seat_actions.items()
            if actions
        }
        _logger.info(f"=== HAND #{self.hand_state.hand_id} COMPLETE ===")
        _logger.debug(f"Actions detected: {actions_summary}")

        # Save updated stats to database
        for name, stats in self.session_stats.items():
            self.db.update_player(stats)

    def _detect_actions(self, game_state: GameState) -> None:
        """Detect player actions from state changes."""
        if not self.hand_state.is_active:
            return

        # Detect street change
        if game_state.street != self.hand_state.street:
            self._on_street_change(game_state.street, game_state)
            self.hand_state.street = game_state.street

        # Check each seat for action changes
        for seat in range(2, 10):  # Skip hero (seat 1)
            self._detect_seat_action(seat, game_state)

    def _detect_seat_action(self, seat: int, game_state: GameState) -> None:
        """Detect action for a specific seat."""
        name = self.seat_names.get(seat)
        if not name:
            return

        prev_bet = self.hand_state.prev_bets.get(seat, 0) or 0
        curr_bet = game_state.bets.get(seat, 0) or 0
        prev_active = self.hand_state.prev_active.get(seat, False)
        curr_active = game_state.active_seats.get(seat, False)
        curr_stack = game_state.stacks.get(seat, 0) or 0

        # Detect FOLD: had cards, now doesn't
        if prev_active and not curr_active:
            self._record_action(seat, DetectedAction.FOLD, game_state)
            return

        # Detect bet changes
        if curr_bet > prev_bet + self.bet_tolerance:
            bet_increase = curr_bet - prev_bet

            # Calculate what "to call" would be for this seat
            other_bets = [
                b for s, b in self.hand_state.prev_bets.items() if s != seat and b and b > 0
            ]
            max_other_bet = max(other_bets) if other_bets else 0
            to_call = max(0, max_other_bet - prev_bet)

            # All-in detection
            is_all_in = curr_stack < self.bet_tolerance

            if is_all_in:
                self._record_action(seat, DetectedAction.ALL_IN, game_state)
            elif game_state.street == Street.PREFLOP:
                # Preflop actions
                if curr_bet >= game_state.bb * 2.2:
                    # This is a raise
                    self._record_action(seat, DetectedAction.RAISE, game_state)
                elif abs(curr_bet - game_state.bb) < self.bet_tolerance:
                    # Limp/call BB
                    self._record_action(seat, DetectedAction.CALL, game_state)
                elif to_call > 0 and abs(bet_increase - to_call) < self.bet_tolerance:
                    # Called a raise
                    self._record_action(seat, DetectedAction.CALL, game_state)
                else:
                    # Some other bet/raise
                    self._record_action(seat, DetectedAction.RAISE, game_state)
            else:
                # Postflop actions
                if to_call > 0:
                    if abs(bet_increase - to_call) < self.bet_tolerance:
                        self._record_action(seat, DetectedAction.CALL, game_state)
                    else:
                        self._record_action(seat, DetectedAction.RAISE, game_state)
                else:
                    # First to bet
                    self._record_action(seat, DetectedAction.BET, game_state)

    def _record_action(self, seat: int, action: DetectedAction, game_state: GameState) -> None:
        """Record an action and update stats."""
        name = self.seat_names.get(seat)
        if not name or name not in self.session_stats:
            _logger.warning(f"Seat {seat} action {action.value} ignored - no name mapping")
            return

        stats = self.session_stats[name]
        self.hand_state.seat_actions[seat].append(action)

        # Log the detected action
        bet_val = game_state.bets.get(seat) or 0
        _logger.info(
            f"ACTION: Seat {seat} [{name[:8]}] {action.value} "
            f"on {game_state.street.value} (bet=${bet_val:.2f})"
        )

        # Update stats based on action
        is_preflop = game_state.street == Street.PREFLOP

        if is_preflop:
            # VPIP: any voluntary action preflop (call, raise, bet, all-in)
            if action in (
                DetectedAction.CALL,
                DetectedAction.RAISE,
                DetectedAction.BET,
                DetectedAction.ALL_IN,
            ):
                if seat not in self.hand_state.vpip_counted:
                    stats.vpip_hands += 1
                    self.hand_state.vpip_counted.add(seat)
                    _logger.debug(
                        f"VPIP: Seat {seat} [{name[:8]}] vpip={stats.vpip_hands}/{stats.hands_seen}"
                    )

            # PFR: raise preflop
            if action in (DetectedAction.RAISE, DetectedAction.ALL_IN):
                if seat not in self.hand_state.pfr_counted:
                    stats.pfr_hands += 1
                    self.hand_state.pfr_counted.add(seat)
                    _logger.debug(
                        f"PFR: Seat {seat} [{name[:8]}] pfr={stats.pfr_hands}/{stats.hands_seen}"
                    )

            # 3-bet tracking: if there was already a raise, this is a 3-bet
            if action == DetectedAction.RAISE:
                # Check if there's already a raise in this hand
                prior_raises = sum(
                    1
                    for s in range(2, 10)
                    if s != seat
                    for a in self.hand_state.seat_actions.get(s, [])
                    if a == DetectedAction.RAISE
                )
                if prior_raises >= 1:
                    stats.three_bet_hands += 1
                    _logger.debug(f"3BET: Seat {seat} [{name[:8]}] 3bet detected")

                # Track 3-bet opportunity for all other active players
                for other_seat, other_name in self.seat_names.items():
                    if other_seat != seat and other_seat != 1:  # Not this player, not hero
                        if other_name in self.session_stats:
                            other_stats = self.session_stats[other_name]
                            other_stats.three_bet_opps += 1
        else:
            # Postflop aggression
            if action in (DetectedAction.BET, DetectedAction.RAISE, DetectedAction.ALL_IN):
                stats.postflop_bets += 1
                _logger.debug(f"POSTFLOP BET: Seat {seat} postflop_bets={stats.postflop_bets}")
            elif action == DetectedAction.CALL:
                stats.postflop_calls += 1
                _logger.debug(f"POSTFLOP CALL: Seat {seat} postflop_calls={stats.postflop_calls}")

    def _on_street_change(self, new_street: Street, game_state: GameState) -> None:
        """Handle street transitions and detect postflop actions."""
        old_street = self.hand_state.street
        _logger.info(f"STREET: {old_street.value} → {new_street.value}")

        # Detect postflop actions from current bet state
        # (actions that happened before we caught the street change)
        if new_street != Street.PREFLOP:
            self._detect_postflop_actions(game_state)

        # Reset previous state for the new street
        self._save_previous_state(game_state)

    def _detect_postflop_actions(self, game_state: GameState) -> None:
        """
        Detect postflop actions from bet state when street is first seen.

        On postflop streets, bets reset to 0. Any non-zero bets indicate
        actions that occurred before we captured the frame.
        """
        player_bets: list[tuple[int, float]] = []

        for seat in range(2, 10):
            name = self.seat_names.get(seat)
            if not name:
                continue

            bet = game_state.bets.get(seat) or 0
            is_active = game_state.active_seats.get(seat, False)

            if bet > 0 and is_active:
                player_bets.append((seat, bet))

        if not player_bets:
            return

        # Find the maximum bet level
        max_bet = max(bet for _, bet in player_bets)
        bet_credited = False

        for seat, bet in player_bets:
            if abs(bet - max_bet) < self.bet_tolerance and not bet_credited:
                # First player at max bet - either BET (if alone) or RAISE
                if len(player_bets) == 1 or all(
                    abs(b - max_bet) < self.bet_tolerance for _, b in player_bets
                ):
                    # Only one bet level - this is a BET, others called
                    self._record_action(seat, DetectedAction.BET, game_state)
                    _logger.debug(f"POSTFLOP INITIAL: Seat {seat} ${bet:.2f} → BET")
                else:
                    # Multiple bet levels - max is a RAISE
                    self._record_action(seat, DetectedAction.RAISE, game_state)
                    _logger.debug(f"POSTFLOP INITIAL: Seat {seat} ${bet:.2f} → RAISE")
                bet_credited = True
            elif abs(bet - max_bet) < self.bet_tolerance:
                # Same bet level as max, but not first - CALL
                self._record_action(seat, DetectedAction.CALL, game_state)
                _logger.debug(f"POSTFLOP INITIAL: Seat {seat} ${bet:.2f} → CALL")
            else:
                # Lower bet level - this was a bet that got raised, count as BET
                self._record_action(seat, DetectedAction.BET, game_state)
                _logger.debug(f"POSTFLOP INITIAL: Seat {seat} ${bet:.2f} → BET (raised)")

    def _save_previous_state(self, game_state: GameState) -> None:
        """Save current state as previous for next comparison."""
        self.hand_state.prev_bets = dict(game_state.bets)
        self.hand_state.prev_active = dict(game_state.active_seats)
        self.hand_state.prev_stacks = dict(game_state.stacks)

    def get_seat_stats(self) -> dict[int, PlayerStats]:
        """
        Get current stats for all seated players.

        Returns:
            Dict of seat -> PlayerStats for HUD display
        """
        result = {}
        for seat, name in self.seat_names.items():
            if name and name in self.session_stats:
                result[seat] = self.session_stats[name]
        return result

    def get_player_stats(self, name: str) -> PlayerStats | None:
        """Get stats for a specific player by name."""
        return self.session_stats.get(name)

    def get_session_summary(self) -> dict:
        """Get summary of current session."""
        return {
            "hands_tracked": self.hand_counter,
            "players_tracked": len(self.session_stats),
            "current_seats": dict(self.seat_names),
        }

    def save_all_stats(self) -> None:
        """Force save all session stats to database."""
        for name, stats in self.session_stats.items():
            self.db.update_player(stats)

    def clear_session(self) -> None:
        """Clear in-memory session data (stats remain in DB)."""
        self.seat_names.clear()
        self.session_stats.clear()
        self.hand_state = HandState()
        self.hand_counter = 0
