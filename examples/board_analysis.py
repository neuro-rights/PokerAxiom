"""
Board Analysis Demo

Demonstrates board texture analysis including:
- Texture classification (dry, medium, wet)
- Flush and straight potential detection
- Connectedness scoring
- Scare card identification
"""

from src.strategy.board_analysis import (
    BoardTexture,
    FlushPotential,
    StraightPotential,
    analyze_flop,
    is_safe_board_for_thin_value,
)


def demo_board_textures():
    """Demonstrate board texture classification."""
    print("=" * 60)
    print("BOARD TEXTURE CLASSIFICATION")
    print("=" * 60)

    # Example boards for each texture type
    boards = [
        # Dry boards
        (["Kh", "7c", "2d"], "K72 rainbow - Very dry"),
        (["Ah", "8c", "3s"], "A83 rainbow - Dry"),
        (["Qd", "5s", "2h"], "Q52 rainbow - Dry"),

        # Medium boards
        (["Kh", "Jc", "7d"], "KJ7 rainbow - Medium (connected high cards)"),
        (["Th", "9c", "4s"], "T94 rainbow - Medium (some connectivity)"),
        (["Qd", "Qs", "6h"], "QQ6 - Medium (paired, but limited draws)"),

        # Wet boards
        (["Jh", "Th", "9c"], "JT9 two-tone - Very wet"),
        (["8h", "7h", "6h"], "876 monotone - Extremely wet"),
        (["Qh", "Jd", "Tc"], "QJT - Wet (coordinated broadway)"),
        (["9h", "8h", "7c"], "987 two-tone - Very wet"),
    ]

    for board, description in boards:
        analysis = analyze_flop(board)
        print(f"\nBoard: {board}")
        print(f"Description: {description}")
        print(f"Texture: {analysis.texture.name}")
        print(f"Connectedness: {analysis.connectedness:.2f}")


def demo_draw_potential():
    """Demonstrate flush and straight potential analysis."""
    print("\n" + "=" * 60)
    print("DRAW POTENTIAL ANALYSIS")
    print("=" * 60)

    boards = [
        (["Kh", "7c", "2d"], "Rainbow - no draws"),
        (["Kh", "7h", "2d"], "Two hearts - backdoor flush"),
        (["Kh", "7h", "2h"], "Three hearts - flush draw possible"),
        (["Kh", "Qh", "Jh", "Th"], "Four hearts - flush completed"),

        (["Kh", "7c", "2d"], "Disconnected - no straight draws"),
        (["Jh", "Tc", "4d"], "One gap - gutshot possible"),
        (["Jh", "Tc", "9d"], "Connected - OESD possible"),
        (["Jh", "Tc", "9d", "8c"], "Four connected - straight completed"),
    ]

    for board, description in boards:
        analysis = analyze_flop(board)
        print(f"\nBoard: {board}")
        print(f"Description: {description}")
        print(f"Flush potential: {analysis.flush_potential.name}")
        print(f"Straight potential: {analysis.straight_potential.name}")


def demo_board_features():
    """Demonstrate detailed board feature analysis."""
    print("\n" + "=" * 60)
    print("DETAILED BOARD FEATURES")
    print("=" * 60)

    boards = [
        ["Ah", "Kc", "Qd"],  # Broadway heavy
        ["7h", "6c", "5d"],  # Low connected
        ["Kd", "Kc", "7h"],  # Paired board
        ["As", "8s", "3s"],  # Monotone
        ["Qh", "Jc", "2s"],  # Mixed
    ]

    for board in boards:
        analysis = analyze_flop(board)
        safe_for_thin_value = is_safe_board_for_thin_value(board)

        print(f"\nBoard: {board}")
        print(f"├─ Texture: {analysis.texture.name}")
        print(f"├─ Is paired: {analysis.is_paired}")
        print(f"├─ Is monotone: {analysis.is_monotone}")
        print(f"├─ High card: {analysis.high_card}")
        print(f"├─ Flush potential: {analysis.flush_potential.name}")
        print(f"├─ Straight potential: {analysis.straight_potential.name}")
        print(f"├─ Connectedness: {analysis.connectedness:.2f}")
        print(f"└─ Safe for thin value: {'Yes' if safe_for_thin_value else 'No'}")


def demo_texture_strategy():
    """Show how board texture affects strategy."""
    print("\n" + "=" * 60)
    print("TEXTURE-BASED STRATEGY ADJUSTMENTS")
    print("=" * 60)

    strategies = {
        BoardTexture.DRY: {
            "cbet_freq": "High (70-80%)",
            "sizing": "Small (33% pot)",
            "reasoning": "Few draws, bluffs fold, value hands call",
        },
        BoardTexture.MEDIUM: {
            "cbet_freq": "Moderate (50-60%)",
            "sizing": "Medium (50-66% pot)",
            "reasoning": "Some draws exist, need protection",
        },
        BoardTexture.WET: {
            "cbet_freq": "Selective (30-40%)",
            "sizing": "Large (66-75% pot)",
            "reasoning": "Many draws, charge draws, protect equity",
        },
    }

    for texture, strategy in strategies.items():
        print(f"\n{texture.name} Board Strategy:")
        print(f"├─ C-bet frequency: {strategy['cbet_freq']}")
        print(f"├─ Sizing: {strategy['sizing']}")
        print(f"└─ Reasoning: {strategy['reasoning']}")


def demo_paired_boards():
    """Analyze paired board dynamics."""
    print("\n" + "=" * 60)
    print("PAIRED BOARD ANALYSIS")
    print("=" * 60)

    paired_boards = [
        (["Kh", "Kc", "7d"], "High pair - trips unlikely, top pair strong"),
        (["7h", "7c", "2d"], "Low pair - check-raise threat, float more"),
        (["Ah", "Ac", "Kd"], "Ace-high pair - polarized, AK is value"),
        (["Qh", "Qc", "Qs"], "Trips on board - everyone has quads fear"),
    ]

    for board, description in paired_boards:
        analysis = analyze_flop(board)
        print(f"\nBoard: {board}")
        print(f"Analysis: {description}")
        print(f"Texture: {analysis.texture.name}")
        print(f"Pair rank: {analysis.high_card}")


def main():
    """Run all board analysis demos."""
    print("\n" + "=" * 60)
    print("  POKERAXIOM BOARD ANALYSIS DEMO")
    print("=" * 60)

    demo_board_textures()
    demo_draw_potential()
    demo_board_features()
    demo_texture_strategy()
    demo_paired_boards()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
