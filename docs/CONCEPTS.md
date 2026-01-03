# Poker Strategy Concepts

This document explains the game theory and poker strategy concepts implemented in the strategy engine.

## GTO (Game Theory Optimal)

GTO strategy is a mathematically balanced approach that cannot be exploited by opponents. It represents the Nash equilibrium solution to poker.

**Key Principles:**
- Balanced ranges (mix of value and bluffs)
- Unexploitable but not necessarily most profitable
- Serves as a baseline before applying exploits

**Implementation:** `src/strategy/gto_baseline.py`

```python
# GTO c-bet frequencies by board texture
GTO_CBET_FREQUENCY = {
    "dry": 0.80,    # High frequency on dry boards
    "medium": 0.60, # Moderate on medium texture
    "wet": 0.40,    # Selective on wet boards
}
```

## MDF (Minimum Defense Frequency)

MDF determines how often you must defend (call or raise) to prevent opponents from profitably bluffing with any two cards.

**Formula:**
```
MDF = 1 - (bet_size / (pot_size + bet_size))
```

**Common MDF Values:**

| Bet Size | MDF |
|----------|-----|
| 25% pot | 80% |
| 33% pot | 75% |
| 50% pot | 67% |
| 75% pot | 57% |
| 100% pot | 50% |
| 150% pot | 40% |

**Implementation:** `src/strategy/mdf.py`

```python
def calculate_mdf(bet_size: float, pot_size: float) -> float:
    """
    MDF = 1 - (bet / (pot + bet))

    This is the frequency we must defend to make opponent's
    bluffs with any two cards break even.
    """
    if bet_size <= 0:
        return 1.0
    total_pot = pot_size + bet_size
    return 1 - (bet_size / total_pot)
```

**Exploitative Adjustments:**

At micro-stakes, players typically under-bluff, so we can fold more than pure MDF suggests:
- Flop: Fold ~10% more than MDF
- Turn: Fold ~15% more than MDF
- River: Fold ~20% more than MDF (raises are almost always value)

## SPR (Stack-to-Pot Ratio)

SPR determines commitment thresholds and affects hand values significantly.

**Formula:**
```
SPR = Effective Stack / Pot Size
```

**Categories:**

| SPR | Category | Strategy |
|-----|----------|----------|
| 1-3 | Low | Commitment mode - one pair hands very valuable |
| 4-7 | Medium | Flexibility - strong top pairs valuable |
| 8+ | High | Selectivity - favor nutted hands, draws valuable |

**Implementation:** `src/strategy/spr_strategy.py`

```python
class SPRCategory(Enum):
    LOW = "low"      # SPR 1-3
    MEDIUM = "medium" # SPR 4-7
    HIGH = "high"    # SPR 8+

def get_spr_strategy(spr: float) -> SPRStrategy:
    """Returns commitment thresholds and sizing guidance."""
    category = get_spr_category(spr)

    if category == SPRCategory.LOW:
        # Low SPR: One-pair hands can stack off
        return SPRStrategy(
            stack_off_threshold=HandStrength.PAIR,
            one_pair_value="high",
            draw_value="low",  # No implied odds
        )
```

**Strategic Implications:**
- **Low SPR (1-3):** Get stacks in with top pair+, draws lose value
- **Medium SPR (4-7):** Need two pair+ to comfortably stack off
- **High SPR (8+):** Draws gain value (implied odds), one pair should pot control

## Board Texture Analysis

Board texture affects optimal betting strategies.

**Classifications:**

| Texture | Characteristics | C-bet Frequency |
|---------|-----------------|-----------------|
| Dry | Unpaired, no draws (K72r) | High (70-80%) |
| Medium | Some connectivity (QT7) | Moderate (50-60%) |
| Wet | Flush/straight draws (JT9ss) | Selective (30-40%) |

**Implementation:** `src/strategy/board_analysis.py`

```python
@dataclass
class FlopAnalysis:
    texture: BoardTexture  # DRY, MEDIUM, WET
    flush_potential: FlushPotential
    straight_potential: StraightPotential
    is_paired: bool
    is_monotone: bool
    high_card: int
    connectedness: float  # 0.0 to 1.0
```

**Metrics Tracked:**
- Connectedness score (how connected cards are for straight draws)
- Flush potential (NONE → BACKDOOR → DRAW → COMPLETE)
- Straight potential (NONE → GUTSHOT → OESD → COMPLETE)
- Scare cards (which future cards complete draws)
- Brick cards (safe cards for value betting)

## Hand Evaluation

Complete hand ranking and categorization system.

**Hand Rankings:**
1. Straight Flush
2. Four of a Kind
3. Full House
4. Flush
5. Straight
6. Three of a Kind
7. Two Pair
8. Pair
9. High Card

**Pair Classifications:**

| Type | Description |
|------|-------------|
| Overpair | Pair higher than all board cards |
| Top Pair | Pair with highest board card |
| Second Pair | Pair with second-highest board card |
| Underpair | Pair lower than all board cards |
| Bottom Pair | Pair with lowest board card |

**Implementation:** `src/strategy/hand_evaluator.py`

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

## Equity Estimation

Quick equity calculations for drawing hands.

**Rule of 4 and 2:**
- Flop: ~4% per out (two cards to come)
- Turn: ~2% per out (one card to come)

**Common Outs:**

| Draw | Outs | Flop Equity | Turn Equity |
|------|------|-------------|-------------|
| Flush draw | 9 | ~36% | ~18% |
| OESD | 8 | ~32% | ~16% |
| Gutshot | 4 | ~16% | ~8% |
| Flush + OESD | 15 | ~54% | ~30% |

**Implementation:**
```python
def equity_estimate(outs: int, street: str) -> float:
    """Simplified equity calculation."""
    if street == "flop":
        return min(outs * 0.04, 0.45)  # Cap at 45%
    else:  # turn
        return min(outs * 0.02, 0.20)  # Cap at 20%
```

## Pot Odds

Pot odds determine the equity needed to profitably call.

**Formula:**
```
Pot Odds = Call Amount / (Pot + Call Amount)
```

**Decision Rule:**
- If Equity > Pot Odds → Call is profitable
- If Equity < Pot Odds → Consider folding (unless implied odds)

**Example:**
```
Pot: $10, Opponent bets: $5
Pot Odds = 5 / (10 + 5 + 5) = 25%
Need 25% equity to call profitably
```

## Positional Awareness

Position significantly affects opening ranges and strategy.

**Positions (9-max):**

| Position | Abbreviation | Opening Range |
|----------|--------------|---------------|
| Under the Gun | UTG | Tight (10-12%) |
| UTG+1 | UTG+1 | Tight (12-14%) |
| UTG+2 | UTG+2 | Tight (14-16%) |
| Lojack | LJ | Moderate (16-18%) |
| Hijack | HJ | Wider (18-22%) |
| Cutoff | CO | Wide (25-28%) |
| Button | BTN | Widest (40-50%) |
| Small Blind | SB | Selective |
| Big Blind | BB | Defense range |

**Implementation:** `src/strategy/positions.py`

## Hybrid GTO-Exploitative Approach

The strategy engine combines GTO baseline with population-specific exploits.

**Philosophy:**
1. Start with GTO-inspired baseline frequencies
2. Apply exploits based on population tendencies
3. Track individual opponents for further adjustments

**Key Exploits (Micro-stakes):**

| GTO Principle | Micro-stakes Exploit |
|---------------|---------------------|
| Balanced bluffing | Reduce bluffs (they call too much) |
| Call down MDF | Fold more (they under-bluff) |
| Thin value bets | Size up value (they call too wide) |
| Raise for value/bluff | Respect raises (they only raise value) |

**Implementation:** `src/strategy/gto_baseline.py`

```python
# Exploitative adjustments
EXPLOIT_ADJUSTMENTS = {
    "value_bet_sizing": 1.25,  # Size up value bets 25%
    "bluff_frequency": 0.30,   # Only 30% of GTO bluffs
    "fold_to_raise": 1.20,     # Fold 20% more to raises
}
```

## Further Reading

- **Game Theory and Poker** - Mathematical foundations
- **The Mathematics of Poker** - Quantitative analysis
- **Modern Poker Theory** - GTO concepts explained
