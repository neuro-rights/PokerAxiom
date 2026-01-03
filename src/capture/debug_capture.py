"""
Debug capture module for strategy debugging.

Captures snapshots of game state, screenshots, and strategy decisions
when triggered by hotkey (Shift+S).
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from src.paths import DEBUG_SESSIONS_DIR


def serialize_game_state(game_state) -> dict[str, Any]:
    """
    Serialize GameState to JSON-compatible dictionary.

    Includes all detected values and computed properties.
    """
    # Basic detected values
    data = {
        "hero_cards": game_state.hero_cards,
        "board_cards": game_state.board_cards,
        "pot": game_state.pot,
        "stacks": {str(k): v for k, v in game_state.stacks.items()},
        "bets": {str(k): v for k, v in game_state.bets.items()},
        "dealer_seat": game_state.dealer_seat,
        "hero_seat": game_state.hero_seat,
        "bb": game_state.bb,
        "sb": game_state.sb,
    }

    # Computed values
    data["computed"] = {
        "street": game_state.street.value,
        "position": game_state.position.value,
        "action_context": game_state.action_context.value,
        "hand_notation": game_state.hand_notation,
        "preflop_category": game_state.preflop_category.value,
        "hand_strength": game_state.hand_strength.name,
        "hand_description": game_state.hand_description,
        "draws": [
            {
                "type": d.draw_type,
                "outs": d.outs,
                "cards_needed": d.cards_needed,
                "description": d.description,
            }
            for d in game_state.draws
        ],
        "to_call": game_state.to_call(),
        "pot_odds": game_state.pot_odds(),
        "hero_stack": game_state.hero_stack(),
        "effective_stack": game_state.effective_stack(),
        "spr": game_state.stack_to_pot_ratio(),
        "limper_count": game_state.limper_count(),
        "active_opponents": game_state.active_opponent_count(),
        "active_seats": {k: bool(v) for k, v in game_state.active_seats.items()},
        "is_valid": game_state.is_valid(),
        "context_description": game_state.get_context_description(),
    }

    return data


def serialize_action(action, trace=None) -> dict[str, Any]:
    """Serialize Action to JSON-compatible dictionary."""
    data = {
        "action_type": action.action_type.value,
        "amount": action.amount,
        "confidence": action.confidence,
        "reasoning": action.reasoning,
        "sizing_note": action.sizing_note,
        # Separated for automation
        "action_text": action.get_display_text(),  # e.g. "RAISE $0.08"
        "button": action.button,  # Raw: "4"
        "button_display": action.get_button_display(),  # Formatted: "[4]"
        "color": action.get_color(),
        "is_aggressive": action.is_aggressive(),
    }
    if trace:
        data["decision_trace"] = trace.to_list()
    return data


class DebugSession:
    """
    Manages a debug capture session.

    Creates session folder on initialization and handles
    per-capture subfolder creation with counter.
    """

    def __init__(self):
        """Initialize a new debug session with timestamped folder."""
        self.session_start = datetime.now()
        self.session_id = self.session_start.strftime("%Y%m%d_%H%M%S")
        self.session_dir = DEBUG_SESSIONS_DIR / self.session_id
        self.capture_counter = 0
        self._lock = threading.Lock()

        # Create session directory
        self.session_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Debug] Session started: {self.session_dir}")

    def get_next_capture_dir(self) -> Path:
        """
        Get the next capture directory with incremented counter.

        Returns:
            Path to capture_NNN subfolder
        """
        with self._lock:
            self.capture_counter += 1
            capture_dir = self.session_dir / f"capture_{self.capture_counter:03d}"
            capture_dir.mkdir(parents=True, exist_ok=True)
            return capture_dir


class DebugCapture:
    """Handles saving debug capture data to disk."""

    def __init__(self, session: DebugSession):
        self.session = session

    def save_capture(
        self,
        screenshot: Image.Image,
        game_state,
        action,
        table_title: str = "",
        trace=None,
        extra_info: dict[str, Any] | None = None,
    ) -> Path:
        """
        Save a complete debug capture.

        Args:
            screenshot: PIL Image of the table
            game_state: GameState object
            action: Action recommendation
            table_title: Window title of the table
            trace: Optional DecisionTrace from strategy engine
            extra_info: Optional additional info to include

        Returns:
            Path to the capture directory
        """
        capture_dir = self.session.get_next_capture_dir()

        # Save screenshot
        screenshot_path = capture_dir / "screenshot.png"
        screenshot.save(screenshot_path)

        # Save table state JSON
        state_data = {
            "capture_time": datetime.now().isoformat(),
            "table_title": table_title,
            "game_state": serialize_game_state(game_state),
            "action": serialize_action(action, trace),
        }
        if extra_info:
            state_data["extra"] = extra_info

        state_path = capture_dir / "table_state.json"
        with open(state_path, "w") as f:
            json.dump(state_data, f, indent=2)

        # Save strategy log
        log_path = capture_dir / "strategy_log.txt"
        self._write_strategy_log(log_path, game_state, action, trace)

        print(f"[Debug] Capture saved: {capture_dir.name}")
        return capture_dir

    def _write_strategy_log(self, path: Path, game_state, action, trace=None):
        """Write human-readable strategy log."""
        lines = [
            "=" * 60,
            "STRATEGY DEBUG LOG",
            "=" * 60,
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--- GAME STATE ---",
            f"Hero Cards: {' '.join(game_state.hero_cards)}",
            f"Board: {' '.join(c for c in game_state.board_cards if c and c != '--')}",
            f"Street: {game_state.street.value.upper()}",
            f"Position: {game_state.position.value}",
            f"Hand: {game_state.hand_notation} ({game_state.preflop_category.value})",
            "",
            f"Pot: ${game_state.pot:.2f}",
            f"To Call: ${game_state.to_call():.2f}",
            f"Pot Odds: {game_state.pot_odds() * 100:.1f}%",
            f"Hero Stack: ${game_state.hero_stack():.2f}",
            f"SPR: {game_state.stack_to_pot_ratio():.1f}",
            "",
            f"Context: {game_state.get_context_description()}",
            f"Opponents: {game_state.active_opponent_count()}",
            f"Limpers: {game_state.limper_count()}",
            "",
        ]

        # Active seats from card back detection
        if game_state.active_seats:
            active_list = [str(s) for s, a in game_state.active_seats.items() if a]
            folded_list = [str(s) for s, a in game_state.active_seats.items() if not a]
            lines.append(f"Active Seats: {', '.join(active_list) if active_list else 'none'}")
            lines.append(f"Folded Seats: {', '.join(folded_list) if folded_list else 'none'}")
            lines.append("")

        # Stacks and bets detail
        lines.append("--- STACKS & BETS ---")
        for seat in range(1, 10):
            stack = game_state.stacks.get(seat)
            bet = game_state.bets.get(seat)
            if stack or bet:
                stack_str = f"${stack:.2f}" if stack else "-"
                bet_str = f"${bet:.2f}" if bet else "-"
                marker = " (HERO)" if seat == game_state.hero_seat else ""
                marker += " (D)" if seat == game_state.dealer_seat else ""
                # Add active/folded indicator
                if seat in game_state.active_seats:
                    marker += " [IN]" if game_state.active_seats[seat] else " [FOLD]"
                lines.append(f"  Seat {seat}: Stack={stack_str}, Bet={bet_str}{marker}")
        lines.append("")

        # Postflop info
        if not game_state.is_preflop():
            lines.extend(
                [
                    "--- HAND ANALYSIS ---",
                    f"Made Hand: {game_state.hand_strength.name}",
                    f"Description: {game_state.hand_description}",
                ]
            )
            if game_state.draws:
                lines.append("Draws:")
                for draw in game_state.draws:
                    lines.append(f"  - {draw.description} ({draw.outs} outs)")
            lines.append("")

        lines.extend(
            [
                "--- RECOMMENDED ACTION ---",
                f"Action: {action.get_display_text()}",
            ]
        )

        # Show button on its own line if present
        if action.button:
            lines.append(f"Button: {action.get_button_display()}")

        lines.extend(
            [
                f"Confidence: {action.confidence * 100:.0f}%",
                f"Reasoning: {action.reasoning}",
            ]
        )

        if action.sizing_note:
            lines.append(f"Sizing: {action.sizing_note}")

        # Decision trace section
        if trace:
            lines.extend(
                [
                    "",
                    "--- DECISION TRACE ---",
                ]
            )
            lines.append(trace.format_text())

        lines.extend(
            [
                "",
                "=" * 60,
            ]
        )

        with open(path, "w") as f:
            f.write("\n".join(lines))
