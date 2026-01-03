"""SQLite database for opponent statistics persistence.

Stores opponent stats across sessions, allowing stats to accumulate
over time as we encounter the same players repeatedly.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..paths import DATA_DIR

# Default database path
OPPONENT_DB_FILE = DATA_DIR / "opponent_stats.db"


@dataclass
class PlayerStats:
    """Statistics for a tracked opponent."""

    name: str
    hands_seen: int = 0
    vpip_hands: int = 0  # Voluntarily put money in pot
    pfr_hands: int = 0  # Preflop raise
    three_bet_opps: int = 0  # Opportunities to 3-bet
    three_bet_hands: int = 0  # Actually 3-bet
    postflop_bets: int = 0  # Bets + raises postflop
    postflop_calls: int = 0  # Calls postflop
    first_seen: str | None = None
    last_seen: str | None = None

    @property
    def vpip(self) -> float:
        """Voluntarily Put money In Pot percentage."""
        if self.hands_seen == 0:
            return 0.0
        return (self.vpip_hands / self.hands_seen) * 100

    @property
    def pfr(self) -> float:
        """PreFlop Raise percentage."""
        if self.hands_seen == 0:
            return 0.0
        return (self.pfr_hands / self.hands_seen) * 100

    @property
    def three_bet(self) -> float:
        """3-bet percentage."""
        if self.three_bet_opps == 0:
            return 0.0
        return (self.three_bet_hands / self.three_bet_opps) * 100

    @property
    def aggression_factor(self) -> float:
        """Aggression Factor (bets+raises / calls)."""
        if self.postflop_calls == 0:
            if self.postflop_bets > 0:
                return 99.0  # Very aggressive (capped)
            return 0.0
        return self.postflop_bets / self.postflop_calls

    @property
    def player_type(self) -> str:
        """
        Classify player type based on stats.

        Returns one of: 'unknown', 'fish', 'nit', 'TAG', 'LAG', 'maniac'
        """
        if self.hands_seen < 15:
            return "unknown"

        vpip = self.vpip
        pfr = self.pfr
        af = self.aggression_factor

        # Fish: Very loose passive (high VPIP, low PFR, low aggression)
        if vpip > 40 and pfr < 15 and af < 1.5:
            return "fish"

        # Nit: Very tight (low VPIP)
        if vpip < 15:
            return "nit"

        # Maniac: Very loose aggressive
        if vpip > 35 and pfr > 25 and af > 2.5:
            return "maniac"

        # LAG: Loose aggressive
        if vpip > 28 and pfr > 20 and af > 1.5:
            return "LAG"

        # TAG: Tight aggressive
        if 18 <= vpip <= 28 and pfr > 15 and af > 1.2:
            return "TAG"

        # Default to fish if loose but doesn't fit other categories
        if vpip > 30:
            return "fish"

        return "unknown"

    def to_hud_string(self) -> str:
        """Format stats for HUD display: VPIP/PFR/AF (hands)"""
        return f"{self.vpip:.0f}/{self.pfr:.0f}/{self.aggression_factor:.1f} ({self.hands_seen})"


class OpponentDatabase:
    """Database interface for opponent statistics."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS opponent_stats (
        name TEXT PRIMARY KEY,
        hands_seen INTEGER DEFAULT 0,
        vpip_hands INTEGER DEFAULT 0,
        pfr_hands INTEGER DEFAULT 0,
        three_bet_opps INTEGER DEFAULT 0,
        three_bet_hands INTEGER DEFAULT 0,
        postflop_bets INTEGER DEFAULT 0,
        postflop_calls INTEGER DEFAULT 0,
        first_seen TEXT,
        last_seen TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_opponent_hands ON opponent_stats(hands_seen);
    CREATE INDEX IF NOT EXISTS idx_opponent_last_seen ON opponent_stats(last_seen);
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or OPPONENT_DB_FILE
        self._ensure_schema()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(self.SCHEMA)

    def get_player(self, name: str) -> PlayerStats | None:
        """
        Get stats for a player by name.

        Args:
            name: Player's screen name

        Returns:
            PlayerStats if found, None otherwise
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT name, hands_seen, vpip_hands, pfr_hands,
                       three_bet_opps, three_bet_hands,
                       postflop_bets, postflop_calls,
                       first_seen, last_seen
                FROM opponent_stats WHERE name = ?
                """,
                (name,),
            )
            row = cursor.fetchone()
            if row:
                return PlayerStats(
                    name=row["name"],
                    hands_seen=row["hands_seen"],
                    vpip_hands=row["vpip_hands"],
                    pfr_hands=row["pfr_hands"],
                    three_bet_opps=row["three_bet_opps"],
                    three_bet_hands=row["three_bet_hands"],
                    postflop_bets=row["postflop_bets"],
                    postflop_calls=row["postflop_calls"],
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
            return None

    def get_or_create_player(self, name: str) -> PlayerStats:
        """
        Get existing player or create new one.

        Args:
            name: Player's screen name

        Returns:
            PlayerStats (new or existing)
        """
        existing = self.get_player(name)
        if existing:
            return existing

        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO opponent_stats (name, first_seen, last_seen)
                VALUES (?, ?, ?)
                """,
                (name, now, now),
            )

        return PlayerStats(name=name, first_seen=now, last_seen=now)

    def update_player(self, stats: PlayerStats) -> None:
        """
        Update player stats in database.

        Args:
            stats: PlayerStats to save
        """
        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO opponent_stats (
                    name, hands_seen, vpip_hands, pfr_hands,
                    three_bet_opps, three_bet_hands,
                    postflop_bets, postflop_calls,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    hands_seen = excluded.hands_seen,
                    vpip_hands = excluded.vpip_hands,
                    pfr_hands = excluded.pfr_hands,
                    three_bet_opps = excluded.three_bet_opps,
                    three_bet_hands = excluded.three_bet_hands,
                    postflop_bets = excluded.postflop_bets,
                    postflop_calls = excluded.postflop_calls,
                    last_seen = excluded.last_seen
                """,
                (
                    stats.name,
                    stats.hands_seen,
                    stats.vpip_hands,
                    stats.pfr_hands,
                    stats.three_bet_opps,
                    stats.three_bet_hands,
                    stats.postflop_bets,
                    stats.postflop_calls,
                    stats.first_seen or now,
                    now,
                ),
            )

    def increment_stats(
        self,
        name: str,
        hands: int = 0,
        vpip: int = 0,
        pfr: int = 0,
        three_bet_opp: int = 0,
        three_bet: int = 0,
        bets: int = 0,
        calls: int = 0,
    ) -> PlayerStats:
        """
        Increment player stats atomically.

        Args:
            name: Player's screen name
            hands: Hands to add
            vpip: VPIP hands to add
            pfr: PFR hands to add
            three_bet_opp: 3-bet opportunities to add
            three_bet: 3-bet hands to add
            bets: Postflop bets/raises to add
            calls: Postflop calls to add

        Returns:
            Updated PlayerStats
        """
        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO opponent_stats (
                    name, hands_seen, vpip_hands, pfr_hands,
                    three_bet_opps, three_bet_hands,
                    postflop_bets, postflop_calls,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    hands_seen = hands_seen + excluded.hands_seen,
                    vpip_hands = vpip_hands + excluded.vpip_hands,
                    pfr_hands = pfr_hands + excluded.pfr_hands,
                    three_bet_opps = three_bet_opps + excluded.three_bet_opps,
                    three_bet_hands = three_bet_hands + excluded.three_bet_hands,
                    postflop_bets = postflop_bets + excluded.postflop_bets,
                    postflop_calls = postflop_calls + excluded.postflop_calls,
                    last_seen = excluded.last_seen
                """,
                (name, hands, vpip, pfr, three_bet_opp, three_bet, bets, calls, now, now),
            )

        return self.get_player(name)

    def get_all_players(self, min_hands: int = 0) -> list[PlayerStats]:
        """
        Get all players with minimum hand count.

        Args:
            min_hands: Minimum hands to include

        Returns:
            List of PlayerStats sorted by hands_seen descending
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT name, hands_seen, vpip_hands, pfr_hands,
                       three_bet_opps, three_bet_hands,
                       postflop_bets, postflop_calls,
                       first_seen, last_seen
                FROM opponent_stats
                WHERE hands_seen >= ?
                ORDER BY hands_seen DESC
                """,
                (min_hands,),
            )
            return [
                PlayerStats(
                    name=row["name"],
                    hands_seen=row["hands_seen"],
                    vpip_hands=row["vpip_hands"],
                    pfr_hands=row["pfr_hands"],
                    three_bet_opps=row["three_bet_opps"],
                    three_bet_hands=row["three_bet_hands"],
                    postflop_bets=row["postflop_bets"],
                    postflop_calls=row["postflop_calls"],
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
                for row in cursor.fetchall()
            ]

    def get_player_count(self) -> int:
        """Get total number of tracked players."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM opponent_stats")
            return cursor.fetchone()[0]

    def get_total_hands(self) -> int:
        """Get total hands observed across all players."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT SUM(hands_seen) FROM opponent_stats")
            result = cursor.fetchone()[0]
            return result or 0
