# API Reference

This document describes the public API for using PokerAxiom as a library.

## Strategy Engine

The strategy engine provides poker decision recommendations.

### Basic Usage

```python
from src.strategy import StrategyEngine, GameState, Street, Position

# Create game state
state = GameState(
    hero_cards=["As", "Kd"],
    board=["Qh", "Jc", "2s"],
    pot=10.0,
    hero_stack=100.0,
    to_call=0.0,
    street=Street.FLOP,
    hero_position=Position.BTN,
    num_players=3,
)

# Get recommendation
engine = StrategyEngine()
action = engine.get_recommendation(state)

print(f"Action: {action.action_type.name}")
print(f"Amount: {action.amount}")
print(f"Reasoning: {action.reasoning}")
```

### GameState

```python
@dataclass
class GameState:
    """Complete game state for strategy analysis."""

    # Cards
    hero_cards: list[str]  # ["As", "Kd"]
    board: list[str]       # ["Qh", "Jc", "2s"]

    # Pot info
    pot: float             # Current pot size
    to_call: float         # Amount to call (0 if no bet)

    # Stack info
    hero_stack: float      # Hero's remaining stack

    # Position
    hero_position: Position
    num_players: int       # Players still in hand

    # Street
    street: Street         # PREFLOP, FLOP, TURN, RIVER

    # Optional context
    villain_stats: PlayerStats = None
    is_3bet_pot: bool = False
```

### Action

```python
@dataclass
class Action:
    """Strategy recommendation."""

    action_type: ActionType  # FOLD, CHECK, CALL, BET, RAISE
    amount: float = 0.0      # Bet/raise amount
    button: str = ""         # Suggested button ("66%", "100%")
    reasoning: str = ""      # Explanation
```

## Hand Evaluation

Evaluate poker hands and calculate strength.

### Hand Strength

```python
from src.strategy.hand_evaluator import (
    evaluate_hand,
    HandStrength,
    PairType,
    get_preflop_category,
    count_outs,
    equity_estimate,
)

# Evaluate a hand
hero = ["As", "Kd"]
board = ["Qh", "Jc", "2s"]

strength, pair_type = evaluate_hand(hero, board)
print(f"Strength: {strength.name}")  # HIGH_CARD
print(f"Pair type: {pair_type}")     # None

# With a pair
hero = ["Kd", "Kc"]
board = ["Qh", "Jc", "2s"]
strength, pair_type = evaluate_hand(hero, board)
print(f"Strength: {strength.name}")  # PAIR
print(f"Pair type: {pair_type.name}")  # OVERPAIR
```

### Preflop Categories

```python
from src.strategy.hand_evaluator import get_preflop_category, PreflopCategory

category = get_preflop_category("As", "Kd")
print(category)  # PreflopCategory.PREMIUM

# Categories: PREMIUM, STRONG, PLAYABLE, MARGINAL, WEAK
```

### Draw Evaluation

```python
from src.strategy.hand_evaluator import count_outs, has_strong_draw

hero = ["Ah", "Kh"]
board = ["Qh", "Jh", "2s"]  # Flush draw + gutshot

outs = count_outs(hero, board)
print(f"Outs: {outs}")  # 12 (9 flush + 3 straight)

is_strong = has_strong_draw(hero, board)
print(f"Strong draw: {is_strong}")  # True
```

## Board Analysis

Analyze board texture and danger.

```python
from src.strategy.board_analysis import (
    analyze_flop,
    BoardTexture,
    FlushPotential,
    StraightPotential,
)

board = ["Qh", "Jh", "2s"]
analysis = analyze_flop(board)

print(f"Texture: {analysis.texture.name}")  # MEDIUM
print(f"Flush potential: {analysis.flush_potential.name}")  # DRAW
print(f"Straight potential: {analysis.straight_potential.name}")  # OESD
print(f"Is paired: {analysis.is_paired}")  # False
print(f"Connectedness: {analysis.connectedness}")  # 0.6
```

## MDF Calculations

Calculate Minimum Defense Frequency.

```python
from src.strategy.mdf import (
    calculate_mdf,
    calculate_pot_odds,
    should_defend,
    MDFAnalysis,
)

# Simple MDF calculation
bet = 10
pot = 20
mdf = calculate_mdf(bet, pot)
print(f"MDF: {mdf:.2%}")  # 66.67%

# Full defense analysis
from src.strategy.hand_evaluator import HandStrength, PairType

analysis = should_defend(
    hand_strength=HandStrength.PAIR,
    pair_type=PairType.TOP_PAIR,
    bet_size=10,
    pot_size=20,
    street="flop",
    facing_raise=False,
    has_draw=False,
    draw_outs=0,
)

print(f"Should defend: {analysis.should_defend}")
print(f"Action: {analysis.defense_action.name}")
print(f"Reasoning: {analysis.reasoning}")
```

## SPR Strategy

Get strategy based on Stack-to-Pot Ratio.

```python
from src.strategy.spr_strategy import (
    get_spr_strategy,
    get_spr_category,
    get_commitment_level,
    SPRCategory,
    CommitmentLevel,
)

# Get SPR category
spr = 5.0
category = get_spr_category(spr)
print(f"Category: {category.name}")  # MEDIUM

# Get full strategy
strategy = get_spr_strategy(spr)
print(f"Stack-off threshold: {strategy.stack_off_threshold.name}")
print(f"One pair value: {strategy.one_pair_value}")
print(f"Draw value: {strategy.draw_value}")

# Get commitment level for a hand
from src.strategy.hand_evaluator import HandStrength, PairType

level = get_commitment_level(
    spr=5.0,
    hand_strength=HandStrength.PAIR,
    pair_type=PairType.TOP_PAIR,
)
print(f"Commitment: {level.name}")  # WILLING_TO_COMMIT
```

## Position Utilities

Work with poker positions.

```python
from src.strategy.positions import (
    Position,
    get_position_from_seats,
    is_early_position,
    is_late_position,
    get_position_color,
)

# Get position
position = get_position_from_seats(
    hero_seat=5,
    button_seat=4,
    num_seats=9,
)
print(f"Position: {position.name}")  # CO (Cutoff)

# Check position type
print(f"Early: {is_early_position(position)}")  # False
print(f"Late: {is_late_position(position)}")    # True

# All positions
for pos in Position:
    print(pos.name)
# UTG, UTG1, UTG2, LJ, HJ, CO, BTN, SB, BB
```

## Window Capture

Capture poker table windows.

```python
from src.capture.window_capture import WindowCapture

capture = WindowCapture()

# Find all poker tables
tables = capture.find_all_windows("*NLHA*")
for hwnd, title in tables:
    print(f"Found: {title}")

# Capture a table
img = capture.grab("*NLHA*")
if img:
    img.save("table.png")

# Capture specific region
region_img = capture.grab_region("*NLHA*", x=100, y=100, width=200, height=150)
```

## Card Detection

Detect cards from images.

```python
from src.detection.card_detector import detect_card, CardResult
import cv2

# Load card image
img = cv2.imread("card.png")

# Detect card
result = detect_card(img)
if result:
    print(f"Card: {result.rank}{result.suit}")
    print(f"Confidence: {result.confidence:.2%}")
```

## Opponent Tracking

Track opponent statistics.

```python
from src.strategy.opponent_db import OpponentDB, PlayerStats

db = OpponentDB()

# Update opponent stats
db.update_stats(
    player_hash="abc123",
    vpip=True,
    pfr=False,
    three_bet=False,
)

# Get opponent profile
stats = db.get_stats("abc123")
if stats:
    print(f"VPIP: {stats.vpip:.1%}")
    print(f"Player type: {stats.player_type.name}")  # FISH, NIT, TAG, LAG, MANIAC
```

## Enums and Constants

### ActionType

```python
class ActionType(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
```

### Street

```python
class Street(Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
```

### Position

```python
class Position(Enum):
    UTG = "utg"
    UTG1 = "utg+1"
    UTG2 = "utg+2"
    LJ = "lj"     # Lojack
    HJ = "hj"     # Hijack
    CO = "co"     # Cutoff
    BTN = "btn"   # Button
    SB = "sb"     # Small Blind
    BB = "bb"     # Big Blind
```

### HandStrength

```python
class HandStrength(Enum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_KIND = 8
    STRAIGHT_FLUSH = 9
```

### BoardTexture

```python
class BoardTexture(Enum):
    DRY = "dry"
    MEDIUM = "medium"
    WET = "wet"
```
