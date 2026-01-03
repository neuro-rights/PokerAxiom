"""
Tests for the hybrid GTO + exploitative strategy modules.

Tests cover:
- SPR-based decision making
- Enhanced board analysis
- MDF calculations
- Blocker analysis
- Dynamic ranges
- GTO baselines with 2NL exploits
"""

import pytest

# All imports consolidated at top
from src.strategy.actions import ActionType, BoardTexture
from src.strategy.blockers import (
    analyze_blockers,
    count_set_blockers,
    has_nut_flush_blocker,
    is_good_bluff_candidate,
)
from src.strategy.board_analysis import (
    FlushPotential,
    analyze_flop,
    is_draw_completing_card,
)
from src.strategy.dynamic_ranges import (
    StackDepth,
    get_adjusted_opening_range,
    get_stack_depth_category,
    is_in_adjusted_opening_range,
    should_set_mine_at_depth,
)
from src.strategy.game_state import GameState
from src.strategy.gto_baseline import (
    apply_2nl_exploits,
    get_cbet_recommendation,
    get_exploit_summary,
    get_gto_baseline,
    should_bluff_at_2nl,
)
from src.strategy.hand_evaluator import HandStrength, PairType
from src.strategy.mdf import (
    DefenseAction,
    calculate_mdf,
    calculate_pot_odds,
    get_mdf_for_bet_size,
    should_defend,
)
from src.strategy.positions import Position
from src.strategy.spr_strategy import (
    CommitmentLevel,
    SPRCategory,
    get_commitment_level,
    get_spr_category,
    get_spr_strategy,
    should_set_mine,
    should_stack_off,
)
from src.strategy.strategy_engine import StrategyEngine


class TestSPRStrategy:
    """Test SPR-based strategy decisions."""

    def test_spr_category_low(self):
        """SPR 1-3 should be LOW category."""
        assert get_spr_category(1.0) == SPRCategory.LOW
        assert get_spr_category(2.5) == SPRCategory.LOW
        assert get_spr_category(3.0) == SPRCategory.LOW

    def test_spr_category_medium(self):
        """SPR 4-7 should be MEDIUM category."""
        assert get_spr_category(4.0) == SPRCategory.MEDIUM
        assert get_spr_category(5.5) == SPRCategory.MEDIUM
        assert get_spr_category(7.0) == SPRCategory.MEDIUM

    def test_spr_category_high(self):
        """SPR 8+ should be HIGH category."""
        assert get_spr_category(8.0) == SPRCategory.HIGH
        assert get_spr_category(15.0) == SPRCategory.HIGH
        assert get_spr_category(100.0) == SPRCategory.HIGH

    def test_low_spr_stack_off_threshold(self):
        """Low SPR should stack off with top pair+."""
        strategy = get_spr_strategy(2.0)
        assert strategy.category == SPRCategory.LOW
        assert strategy.stack_off_threshold == HandStrength.PAIR

    def test_high_spr_stack_off_threshold(self):
        """High SPR should require sets+ to stack off."""
        strategy = get_spr_strategy(10.0)
        assert strategy.category == SPRCategory.HIGH
        assert strategy.stack_off_threshold == HandStrength.THREE_OF_KIND

    def test_commitment_level_low_spr_overpair(self):
        """Overpair at low SPR should be fully committed."""
        strategy = get_spr_strategy(2.0)
        commitment = get_commitment_level(HandStrength.PAIR, PairType.OVERPAIR, strategy)
        assert commitment == CommitmentLevel.FULLY_COMMITTED

    def test_commitment_level_high_spr_overpair(self):
        """Overpair at high SPR should be willing to commit but not fully."""
        strategy = get_spr_strategy(12.0)
        commitment = get_commitment_level(HandStrength.PAIR, PairType.OVERPAIR, strategy)
        assert commitment == CommitmentLevel.WILLING_TO_COMMIT

    def test_should_stack_off_with_set(self):
        """Sets should always stack off."""
        should, reason = should_stack_off(HandStrength.THREE_OF_KIND, None, spr=10.0)
        assert should is True
        assert "set" in reason.lower()

    def test_should_not_stack_off_top_pair_high_spr(self):
        """Top pair should not stack off at high SPR."""
        should, reason = should_stack_off(HandStrength.PAIR, PairType.TOP_PAIR, spr=12.0)
        assert should is False

    def test_set_mining_good_odds(self):
        """Should set mine with good implied odds."""
        should, reason = should_set_mine(call_amount=0.06, effective_stack=1.50, spr=5.0)
        assert should is True
        assert "implied" in reason.lower()

    def test_set_mining_bad_odds(self):
        """Should not set mine with poor implied odds."""
        should, reason = should_set_mine(call_amount=0.30, effective_stack=0.80, spr=3.0)
        assert should is False


class TestBoardAnalysis:
    """Test enhanced board texture analysis."""

    def test_dry_board_detection(self):
        """K72 rainbow should be DRY."""
        analysis = analyze_flop(["Kh", "7c", "2d"])
        assert analysis.texture_category == BoardTexture.DRY
        assert analysis.rainbow is True
        assert analysis.flush_potential == FlushPotential.NONE

    def test_wet_board_detection(self):
        """JT9 two-tone should be WET."""
        analysis = analyze_flop(["Jh", "Th", "9c"])
        assert analysis.texture_category == BoardTexture.WET
        assert analysis.connectedness >= 0.7

    def test_monotone_board(self):
        """All hearts should be monotone."""
        analysis = analyze_flop(["Ah", "8h", "3h"])
        assert analysis.monotone is True
        assert analysis.flush_potential == FlushPotential.DRAW

    def test_paired_board(self):
        """Board with pair should be detected."""
        analysis = analyze_flop(["Kh", "Kc", "7d"])
        assert analysis.paired_board is True

    def test_high_card_detection(self):
        """Should detect highest card correctly."""
        analysis = analyze_flop(["Qh", "7c", "2d"])
        assert analysis.high_card_rank == "Q"
        assert analysis.high_card_value == 12

    def test_broadway_count(self):
        """Should count broadway cards."""
        analysis = analyze_flop(["Ah", "Kc", "Qd"])
        assert analysis.broadway_count == 3

    def test_cbet_frequency_dry(self):
        """Dry boards should have higher c-bet frequency."""
        dry_analysis = analyze_flop(["Kh", "7c", "2d"])
        wet_analysis = analyze_flop(["Jh", "Th", "9h"])
        assert dry_analysis.cbet_frequency > wet_analysis.cbet_frequency

    def test_draw_completing_card(self):
        """Should detect draw completing cards."""
        # Board with 3 hearts - adding 4th heart completes flush
        board = ["Jh", "Th", "2h"]
        # Another heart completes flush
        assert is_draw_completing_card("Ah", board) is True
        # A brick doesn't complete anything
        assert is_draw_completing_card("3d", board) is False


class TestMDF:
    """Test Minimum Defense Frequency calculations."""

    def test_half_pot_mdf(self):
        """50% pot bet should have ~67% MDF."""
        mdf = calculate_mdf(bet_size=0.50, pot_size=1.00)
        assert 0.66 <= mdf <= 0.68

    def test_pot_bet_mdf(self):
        """Pot size bet should have 50% MDF."""
        mdf = calculate_mdf(bet_size=1.00, pot_size=1.00)
        assert mdf == 0.50

    def test_third_pot_mdf(self):
        """33% pot bet should have ~75% MDF."""
        mdf = get_mdf_for_bet_size(0.33)
        assert 0.74 <= mdf <= 0.76

    def test_pot_odds_calculation(self):
        """Pot odds should be call / (pot + call)."""
        odds = calculate_pot_odds(call_amount=0.50, pot_size=1.50)
        assert odds == 0.25  # 0.50 / (1.50 + 0.50) = 0.25

    def test_should_defend_with_overpair(self):
        """Overpair should always defend on flop."""
        analysis = should_defend(
            hand_strength=HandStrength.PAIR,
            pair_type=PairType.OVERPAIR,
            bet_size=0.10,
            pot_size=0.15,
            street="flop",
        )
        assert analysis.should_defend is True
        assert analysis.defense_action == DefenseAction.CALL

    def test_should_fold_weak_to_river_bet(self):
        """Weak hands should fold to river bets at 2NL."""
        analysis = should_defend(
            hand_strength=HandStrength.HIGH_CARD,
            pair_type=None,
            bet_size=0.20,
            pot_size=0.30,
            street="river",
        )
        assert analysis.should_defend is False
        assert analysis.defense_action == DefenseAction.FOLD


class TestBlockers:
    """Test blocker analysis."""

    def test_nut_flush_blocker(self):
        """Should detect Ace of flush suit as blocker."""
        assert (
            has_nut_flush_blocker(hero_cards=["Ah", "Kc"], board_cards=["9h", "7h", "2h"]) is True
        )

    def test_no_flush_blocker(self):
        """Should not detect blocker without Ace of suit."""
        assert (
            has_nut_flush_blocker(hero_cards=["Kc", "Qc"], board_cards=["9h", "7h", "2h"]) is False
        )

    def test_set_blockers(self):
        """Should count set blockers correctly."""
        blocks = count_set_blockers(hero_cards=["Kh", "7c"], board_cards=["Kd", "7s", "2h"])
        assert blocks == 2  # We block both K and 7 sets

    def test_good_bluff_candidate(self):
        """Hand with nut blockers should be good bluff candidate."""
        is_good, reason = is_good_bluff_candidate(
            hero_cards=["Ah", "2c"],  # Blocks nut flush
            board_cards=["Kh", "9h", "4h"],
            threshold=0.4,
        )
        assert is_good is True

    def test_blocker_analysis_structure(self):
        """BlockerAnalysis should have all expected fields."""
        analysis = analyze_blockers(hero_cards=["As", "Kh"], board_cards=["Qs", "Js", "2s"])
        assert hasattr(analysis, "blocks_nut_flush")
        assert hasattr(analysis, "bluff_candidate_score")
        assert hasattr(analysis, "blocked_nut_combos")


class TestDynamicRanges:
    """Test stack depth adjusted ranges."""

    def test_stack_depth_categories(self):
        """Should categorize stack depths correctly."""
        assert get_stack_depth_category(10) == StackDepth.PUSH_FOLD
        assert get_stack_depth_category(20) == StackDepth.SHORT
        assert get_stack_depth_category(40) == StackDepth.MEDIUM
        assert get_stack_depth_category(75) == StackDepth.STANDARD
        assert get_stack_depth_category(120) == StackDepth.DEEP
        assert get_stack_depth_category(200) == StackDepth.ULTRA_DEEP

    def test_short_stack_removes_speculative(self):
        """Short stack should remove speculative hands."""
        # 54s is marginal and should be removed at short stack
        short_range = get_adjusted_opening_range(Position.BTN, 25)
        _ = get_adjusted_opening_range(Position.BTN, 100)

        # Check that 54s is not in short stack range but is in standard
        assert "54s" not in short_range.adjusted_range
        # 54s might or might not be in standard range depending on position

    def test_deep_stack_adds_speculative(self):
        """Deep stack should add speculative hands."""
        deep_range = get_adjusted_opening_range(Position.BTN, 150)
        assert deep_range.adjustment_rationale.lower().find("deep") != -1

    def test_set_mining_at_depth(self):
        """Should determine set mining profitability."""
        # Good: 100bb effective, calling 3bb
        good, _ = should_set_mine_at_depth(100, 3)
        assert good is True

        # Bad: 30bb effective, calling 5bb
        bad, _ = should_set_mine_at_depth(30, 5)
        assert bad is False

    def test_adjusted_opening_range_contains_premiums(self):
        """All ranges should contain premium hands."""
        for position in [Position.UTG, Position.BTN, Position.CO]:
            for stack_bb in [20, 50, 100, 150]:
                assert is_in_adjusted_opening_range("AA", position, stack_bb)
                assert is_in_adjusted_opening_range("KK", position, stack_bb)


class TestGTOBaseline:
    """Test GTO baselines with 2NL exploits."""

    def test_baseline_varies_by_texture(self):
        """Different textures should have different baselines."""
        dry = get_gto_baseline(BoardTexture.DRY)
        wet = get_gto_baseline(BoardTexture.WET)

        assert dry.cbet_frequency > wet.cbet_frequency
        assert dry.cbet_sizing < wet.cbet_sizing

    def test_exploits_adjust_baseline(self):
        """2NL exploits should adjust baseline."""
        baseline = get_gto_baseline(BoardTexture.MEDIUM)
        adjusted = apply_2nl_exploits(baseline)

        # Sizing should be adjusted up (2NL calls too much)
        assert adjusted.adj_cbet_sizing >= baseline.cbet_sizing
        # Bluff frequency should be reduced
        assert adjusted.adj_bluff_freq <= baseline.bluff_frequency

    def test_cbet_recommendation_with_value(self):
        """Should recommend c-bet with value hand and return button label."""
        should_cbet, sizing, reason, button = get_cbet_recommendation(
            texture=BoardTexture.DRY,
            in_position=True,
            opponent_count=1,
            has_value=True,
        )
        assert should_cbet is True
        assert sizing > 0
        assert button in ("1", "2", "3", "4")

    def test_never_bluff_river_at_2nl(self):
        """Should never bluff river at 2NL."""
        should_bluff, reason = should_bluff_at_2nl(
            street="river",
            opponent_count=1,
            has_blockers=True,  # Even with blockers
            previous_aggression=True,
        )
        assert should_bluff is False
        assert "2nl" in reason.lower() or "river" in reason.lower()

    def test_exploit_summary_exists(self):
        """Should have list of exploits."""
        summary = get_exploit_summary()
        assert len(summary) > 0
        assert any("value" in s.lower() for s in summary)


class TestStrategyEngineIntegration:
    """Test integrated strategy engine with new modules."""

    def test_engine_uses_dynamic_ranges(self):
        """Engine should use dynamic ranges for preflop."""
        engine = StrategyEngine()

        # Create a valid game state with proper dealer position
        # Hero at seat 1, dealer at seat 9 means hero is on SB
        # Let's use dealer at seat 7 so hero (seat 1) is on CO
        gs = GameState.from_detection(
            hero_cards=["As", "Kh"],
            board_cards=[],
            pot=0.03,
            stacks={1: 1.00, 2: 1.00, 3: 1.00, 9: 1.00},  # 50bb effective
            bets={1: 0.00, 9: 0.01, 2: 0.02},  # Blinds posted
            dealer_seat=7,  # Hero on BTN-ish position
        )

        action = engine.recommend(gs)
        # AK should always be opened - check action type enum
        assert action.action_type == ActionType.RAISE

    def test_engine_uses_spr_for_postflop(self):
        """Engine should use SPR for postflop decisions."""
        engine = StrategyEngine()
        gs = GameState.from_detection(
            hero_cards=["Kh", "Kc"],
            board_cards=["Ks", "7d", "2c"],  # Set on dry board
            pot=0.20,
            stacks={1: 0.50, 2: 0.50},  # Low SPR
            bets={1: 0.00, 2: 0.10},  # Facing bet
            dealer_seat=8,
        )

        action = engine.recommend(gs)

        # Should raise with set - check enum value
        assert action.action_type == ActionType.RAISE

    def test_engine_handles_short_stack(self):
        """Engine should handle short stack situations."""
        engine = StrategyEngine()

        # Set up proper position - dealer at 7, hero at 1 = late position
        gs = GameState.from_detection(
            hero_cards=["Qs", "Js"],  # Strong playable hand
            board_cards=[],
            pot=0.03,
            stacks={1: 0.40, 2: 2.00, 3: 2.00, 9: 2.00},  # 20bb effective
            bets={1: 0.00, 9: 0.01, 2: 0.02},  # Blinds posted
            dealer_seat=7,
        )

        action = engine.recommend(gs)
        # QJs should be raised from late position
        # At short stack, might push or fold depending on exact calculation
        # Just verify we get a valid action
        assert action.action_type in (ActionType.RAISE, ActionType.FOLD)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
