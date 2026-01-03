"""
Strategy Engine Demo

Demonstrates how to use the strategy engine programmatically
to get poker decision recommendations.
"""

from src.strategy.game_state import GameState, Street
from src.strategy.positions import Position
from src.strategy.strategy_engine import StrategyEngine


def demo_preflop():
    """Demonstrate preflop decision-making."""
    print("=" * 60)
    print("PREFLOP SCENARIO")
    print("=" * 60)

    # Scenario: Hero has AKo on the button, facing a raise
    state = GameState(
        hero_cards=["As", "Kd"],
        board=[],
        pot=3.5,  # Blinds + raise
        hero_stack=100.0,
        to_call=2.0,  # Facing 2BB raise
        street=Street.PREFLOP,
        hero_position=Position.BTN,
        num_players=3,
    )

    engine = StrategyEngine()
    action = engine.get_recommendation(state)

    print(f"Hero cards: {state.hero_cards}")
    print(f"Position: {state.hero_position.name}")
    print(f"Pot: ${state.pot}, To call: ${state.to_call}")
    print()
    print(f"Recommended action: {action.action_type.name}")
    if action.amount:
        print(f"Amount: ${action.amount:.2f}")
    if action.button:
        print(f"Button: {action.button}")
    if action.reasoning:
        print(f"Reasoning: {action.reasoning}")
    print()


def demo_flop():
    """Demonstrate flop decision-making."""
    print("=" * 60)
    print("FLOP SCENARIO")
    print("=" * 60)

    # Scenario: Hero has AK, flopped top pair on dry board
    state = GameState(
        hero_cards=["As", "Kd"],
        board=["Kh", "7c", "2s"],  # Dry board with top pair
        pot=10.0,
        hero_stack=95.0,
        to_call=0.0,  # Checked to us
        street=Street.FLOP,
        hero_position=Position.BTN,
        num_players=2,
    )

    engine = StrategyEngine()
    action = engine.get_recommendation(state)

    print(f"Hero cards: {state.hero_cards}")
    print(f"Board: {state.board}")
    print(f"Position: {state.hero_position.name}")
    print(f"Pot: ${state.pot}")
    print()
    print(f"Recommended action: {action.action_type.name}")
    if action.amount:
        print(f"Amount: ${action.amount:.2f}")
    if action.button:
        print(f"Button: {action.button}")
    if action.reasoning:
        print(f"Reasoning: {action.reasoning}")
    print()


def demo_river_decision():
    """Demonstrate river decision with MDF considerations."""
    print("=" * 60)
    print("RIVER SCENARIO - FACING A BET")
    print("=" * 60)

    # Scenario: Hero has top pair, facing a river bet
    state = GameState(
        hero_cards=["Ah", "Kc"],
        board=["Kd", "7s", "3h", "9c", "2d"],  # Safe runout
        pot=30.0,
        hero_stack=60.0,
        to_call=20.0,  # Facing 2/3 pot bet
        street=Street.RIVER,
        hero_position=Position.BB,
        num_players=2,
    )

    engine = StrategyEngine()
    action = engine.get_recommendation(state)

    print(f"Hero cards: {state.hero_cards}")
    print(f"Board: {state.board}")
    print(f"Pot: ${state.pot}, To call: ${state.to_call}")
    print()
    print(f"Recommended action: {action.action_type.name}")
    if action.reasoning:
        print(f"Reasoning: {action.reasoning}")
    print()


def demo_draw_situation():
    """Demonstrate decision with a drawing hand."""
    print("=" * 60)
    print("FLOP SCENARIO - FLUSH DRAW")
    print("=" * 60)

    # Scenario: Hero has flush draw
    state = GameState(
        hero_cards=["Ah", "Jh"],
        board=["Kh", "7h", "3c"],  # Flush draw
        pot=15.0,
        hero_stack=85.0,
        to_call=10.0,  # Facing bet
        street=Street.FLOP,
        hero_position=Position.CO,
        num_players=2,
    )

    engine = StrategyEngine()
    action = engine.get_recommendation(state)

    print(f"Hero cards: {state.hero_cards}")
    print(f"Board: {state.board}")
    print(f"Pot: ${state.pot}, To call: ${state.to_call}")
    print()
    print(f"Recommended action: {action.action_type.name}")
    if action.reasoning:
        print(f"Reasoning: {action.reasoning}")
    print()


def main():
    """Run all demo scenarios."""
    print("\n" + "=" * 60)
    print("  POKERAXIOM STRATEGY ENGINE DEMO")
    print("=" * 60 + "\n")

    demo_preflop()
    demo_flop()
    demo_river_decision()
    demo_draw_situation()

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
