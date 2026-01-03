"""
MDF Calculator Demo

Demonstrates Minimum Defense Frequency calculations including:
- Basic MDF formula
- Pot odds calculation
- Exploitative adjustments
- Defense decision framework
- Bluff frequency analysis
"""

from src.strategy.hand_evaluator import HandStrength, PairType
from src.strategy.mdf import (
    calculate_break_even_frequency,
    calculate_mdf,
    calculate_pot_odds,
    get_bluff_frequency,
    get_exploitative_mdf,
    get_mdf_for_bet_size,
    should_bluff,
    should_defend,
)


def demo_basic_mdf():
    """Demonstrate basic MDF calculation."""
    print("=" * 60)
    print("MINIMUM DEFENSE FREQUENCY (MDF)")
    print("=" * 60)

    print("\nMDF Formula: MDF = 1 - (bet / (pot + bet))")
    print("\nThis is how often you must defend to prevent opponents")
    print("from profitably bluffing any two cards.")
    print()

    # Common bet sizes
    bet_sizes = [0.25, 0.33, 0.50, 0.66, 0.75, 1.0, 1.5, 2.0]

    print(f"{'Bet Size':>12} {'MDF':>10}")
    print("-" * 24)

    for bet_pct in bet_sizes:
        mdf = get_mdf_for_bet_size(bet_pct)
        print(f"{bet_pct*100:>10.0f}% pot {mdf*100:>8.1f}%")


def demo_pot_odds():
    """Demonstrate pot odds calculation."""
    print("\n" + "=" * 60)
    print("POT ODDS CALCULATION")
    print("=" * 60)

    print("\nPot Odds Formula: call / (pot + call)")
    print("This tells you the equity needed to call profitably.")
    print()

    # Example scenarios
    scenarios = [
        (10, 30, "Pot $30, facing $10 bet"),
        (15, 20, "Pot $20, facing $15 bet"),
        (20, 20, "Pot $20, facing $20 bet (pot-sized)"),
        (30, 20, "Pot $20, facing $30 bet (overbet)"),
    ]

    print(f"{'Scenario':>35} {'Pot Odds':>12} {'Equity Needed':>15}")
    print("-" * 65)

    for call, pot, desc in scenarios:
        pot_odds = calculate_pot_odds(call, pot + call)
        print(f"{desc:>35} {pot_odds*100:>10.1f}% {pot_odds*100:>13.1f}%")


def demo_exploitative_adjustments():
    """Demonstrate exploitative MDF adjustments."""
    print("\n" + "=" * 60)
    print("EXPLOITATIVE ADJUSTMENTS")
    print("=" * 60)

    print("\nAt micro-stakes, opponents typically under-bluff,")
    print("so we can fold more than pure MDF suggests.")
    print()

    base_mdf = 0.67  # 50% pot bet

    streets = ["flop", "turn", "river"]

    print(f"Base MDF for 50% pot bet: {base_mdf*100:.1f}%\n")

    for street in streets:
        adj_mdf, reason = get_exploitative_mdf(base_mdf, street, facing_raise=False)
        print(f"{street.title():>6}: Adjusted MDF = {adj_mdf*100:.1f}%")
        print(f"        Reason: {reason}")
        print()

    print("With a raise on the river:")
    adj_mdf, reason = get_exploitative_mdf(base_mdf, "river", facing_raise=True)
    print(f"        Adjusted MDF = {adj_mdf*100:.1f}%")
    print(f"        Reason: {reason}")


def demo_defense_decisions():
    """Demonstrate defense decision framework."""
    print("\n" + "=" * 60)
    print("DEFENSE DECISIONS")
    print("=" * 60)

    # Various hand strength scenarios
    scenarios = [
        # (strength, pair_type, bet, pot, street, facing_raise, has_draw, outs)
        (HandStrength.PAIR, PairType.TOP_PAIR, 10, 20, "flop", False, False, 0),
        (HandStrength.PAIR, PairType.TOP_PAIR, 20, 20, "river", True, False, 0),
        (HandStrength.PAIR, PairType.SECOND_PAIR, 10, 20, "turn", False, False, 0),
        (HandStrength.HIGH_CARD, None, 10, 25, "flop", False, True, 9),  # Flush draw
        (HandStrength.TWO_PAIR, None, 20, 30, "river", False, False, 0),
    ]

    descriptions = [
        "Top pair on flop vs bet",
        "Top pair on river vs raise",
        "Second pair on turn vs bet",
        "Flush draw on flop vs bet",
        "Two pair on river vs bet",
    ]

    for (strength, pair_type, bet, pot, street, facing_raise, has_draw, outs), desc in zip(
        scenarios, descriptions
    ):
        analysis = should_defend(
            hand_strength=strength,
            pair_type=pair_type,
            bet_size=bet,
            pot_size=pot,
            street=street,
            facing_raise=facing_raise,
            has_draw=has_draw,
            draw_outs=outs,
        )

        print(f"\n{desc}:")
        print(f"├─ GTO MDF: {analysis.mdf*100:.1f}%")
        print(f"├─ Adjusted MDF: {analysis.adjusted_mdf*100:.1f}%")
        print(f"├─ Should defend: {'Yes' if analysis.should_defend else 'No'}")
        print(f"├─ Action: {analysis.defense_action.name}")
        print(f"└─ Reasoning: {analysis.reasoning}")


def demo_bluff_frequencies():
    """Demonstrate bluff frequency analysis."""
    print("\n" + "=" * 60)
    print("BLUFF FREQUENCIES")
    print("=" * 60)

    print("\nGTO bluff frequency ensures opponents can't exploit")
    print("by always calling or always folding.")
    print()

    pot = 100
    bet_sizes = [33, 50, 75, 100, 150]

    print(f"{'Bet Size':>10} {'Break-even':>12} {'GTO Bluff':>12} {'2NL Bluff':>12}")
    print("-" * 50)

    for bet in bet_sizes:
        break_even = calculate_break_even_frequency(bet, pot)
        gto_bluff = bet / (pot + 2 * bet)
        exploit_bluff = get_bluff_frequency(bet, pot)

        print(
            f"${bet:>8} {break_even*100:>10.1f}% {gto_bluff*100:>10.1f}% {exploit_bluff*100:>10.1f}%"
        )

    print("\nNote: At 2NL, we drastically reduce bluff frequency")
    print("because opponents call too often (bluffs are -EV).")


def demo_bluff_decisions():
    """Demonstrate when to bluff (or not) at micro-stakes."""
    print("\n" + "=" * 60)
    print("BLUFF DECISIONS AT MICRO-STAKES")
    print("=" * 60)

    scenarios = [
        (100, 66, True, "river", False, "River with blockers"),
        (100, 66, False, "river", False, "River without blockers"),
        (100, 50, True, "flop", False, "Flop c-bet with blockers"),
        (50, 33, False, "turn", False, "Turn barrel without blockers"),
        (100, 75, False, "flop", True, "Multiway flop"),
    ]

    for pot, bet, blockers, street, multiway, desc in scenarios:
        should, reason = should_bluff(pot, bet, blockers, street, multiway)
        print(f"\n{desc}:")
        print(f"├─ Pot: ${pot}, Bet: ${bet}")
        print(f"├─ Has blockers: {'Yes' if blockers else 'No'}")
        print(f"├─ Should bluff: {'Yes' if should else 'No'}")
        print(f"└─ Reason: {reason}")


def main():
    """Run all MDF demos."""
    print("\n" + "=" * 60)
    print("  POKERAXIOM MDF CALCULATOR DEMO")
    print("=" * 60)

    demo_basic_mdf()
    demo_pot_odds()
    demo_exploitative_adjustments()
    demo_defense_decisions()
    demo_bluff_frequencies()
    demo_bluff_decisions()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
