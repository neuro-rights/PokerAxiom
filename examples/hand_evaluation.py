"""
Hand Evaluation Demo

Demonstrates the hand evaluation system including:
- Made hand strength evaluation
- Pair type classification
- Draw detection and out counting
- Preflop hand categorization
"""

from src.strategy.hand_evaluator import (
    HandStrength,
    PairType,
    PreflopCategory,
    count_outs,
    equity_estimate,
    evaluate_hand,
    get_preflop_category,
    has_strong_draw,
)


def demo_hand_rankings():
    """Demonstrate hand strength evaluation."""
    print("=" * 60)
    print("HAND STRENGTH EVALUATION")
    print("=" * 60)

    # Test cases: (hero_cards, board, expected_description)
    test_cases = [
        (["As", "Kd"], ["Qh", "Jc", "2s"], "High card (Ace high)"),
        (["Kd", "Kc"], ["Qh", "Jc", "2s"], "Overpair (pocket Kings)"),
        (["As", "Ks"], ["Kh", "7c", "2s"], "Top pair top kicker"),
        (["Qd", "Qs"], ["Kh", "7c", "2s"], "Underpair to the King"),
        (["As", "7d"], ["Kh", "7c", "2s"], "Second pair"),
        (["Ah", "Kh"], ["Kd", "Kc", "2s"], "Three of a kind"),
        (["As", "Ks"], ["Kh", "Kc", "As", "2d", "7c"], "Full house"),
        (["Jh", "Th"], ["9h", "8h", "2h"], "Flush"),
        (["Jh", "Td"], ["9c", "8s", "7h"], "Straight"),
    ]

    for hero, board, description in test_cases:
        strength, pair_type = evaluate_hand(hero, board)
        print(f"\nHero: {hero}")
        print(f"Board: {board}")
        print(f"Expected: {description}")
        print(f"Detected: {strength.name}", end="")
        if pair_type:
            print(f" ({pair_type.name})")
        else:
            print()


def demo_preflop_categories():
    """Demonstrate preflop hand categorization."""
    print("\n" + "=" * 60)
    print("PREFLOP HAND CATEGORIES")
    print("=" * 60)

    # Representative hands for each category
    hands = [
        ("Ah", "As", "Pocket Aces"),
        ("Kd", "Kc", "Pocket Kings"),
        ("Ah", "Kh", "AK suited"),
        ("Ad", "Kc", "AK offsuit"),
        ("Jh", "Js", "Pocket Jacks"),
        ("Ah", "Qd", "AQ offsuit"),
        ("9h", "9d", "Pocket Nines"),
        ("Kd", "Jh", "KJ offsuit"),
        ("8h", "7h", "87 suited"),
        ("5d", "5c", "Pocket Fives"),
        ("Jd", "9h", "J9 offsuit"),
        ("7h", "2d", "72 offsuit"),
    ]

    for card1, card2, name in hands:
        category = get_preflop_category(card1, card2)
        print(f"{name:20} ({card1}{card2}): {category.name}")


def demo_draw_detection():
    """Demonstrate draw detection and equity estimation."""
    print("\n" + "=" * 60)
    print("DRAW DETECTION AND EQUITY")
    print("=" * 60)

    # Draw scenarios
    scenarios = [
        (["Ah", "Kh"], ["Qh", "7h", "2c"], "Nut flush draw"),
        (["Jd", "Td"], ["9c", "8s", "2h"], "Open-ended straight draw"),
        (["Ah", "Kd"], ["Qc", "Js", "2h"], "Gutshot straight draw"),
        (["Jh", "Th"], ["9h", "8c", "2h"], "Flush draw + OESD (combo draw)"),
        (["Ah", "5h"], ["Kh", "7h", "6c"], "Flush draw + gutshot"),
    ]

    for hero, board, description in scenarios:
        outs = count_outs(hero, board)
        flop_equity = equity_estimate(outs, "flop")
        turn_equity = equity_estimate(outs, "turn")
        is_strong = has_strong_draw(hero, board)

        print(f"\n{description}")
        print(f"Hero: {hero}")
        print(f"Board: {board}")
        print(f"Outs: {outs}")
        print(f"Flop equity: {flop_equity:.1%} (2 cards to come)")
        print(f"Turn equity: {turn_equity:.1%} (1 card to come)")
        print(f"Strong draw: {'Yes' if is_strong else 'No'}")


def demo_hand_comparison():
    """Compare hand strengths across different situations."""
    print("\n" + "=" * 60)
    print("HAND STRENGTH COMPARISON")
    print("=" * 60)

    # Same hand, different boards
    hero = ["Ad", "Kd"]

    boards = [
        (["Kh", "7c", "2s"], "Dry board - TPTK"),
        (["Kh", "Jh", "Th"], "Wet board - TPTK but vulnerable"),
        (["Qh", "Jh", "Tc"], "Missed flop - broadway draw"),
        (["Ad", "Kc", "7d"], "Two pair on board"),
        (["7h", "7c", "7s"], "Trips on board"),
    ]

    print(f"Hero: {hero}\n")

    for board, description in boards:
        strength, pair_type = evaluate_hand(hero, board)
        outs = count_outs(hero, board)

        print(f"Board: {board}")
        print(f"Situation: {description}")
        print(f"Strength: {strength.name}", end="")
        if pair_type:
            print(f" ({pair_type.name})")
        else:
            print()
        if outs > 0:
            print(f"Draw outs: {outs}")
        print()


def main():
    """Run all hand evaluation demos."""
    print("\n" + "=" * 60)
    print("  POKERAXIOM HAND EVALUATION DEMO")
    print("=" * 60)

    demo_hand_rankings()
    demo_preflop_categories()
    demo_draw_detection()
    demo_hand_comparison()

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
