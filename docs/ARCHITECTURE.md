# Architecture

This document describes the system architecture of PokerAxiom, a real-time poker decision support system.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Strategy Overlay                          │
│                    (User Interface Layer)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Strategy Engine                             │
│              (Decision Logic & Recommendations)                   │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Hand         │  │ Board        │  │ MDF          │           │
│  │ Evaluator    │  │ Analysis     │  │ Calculator   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ SPR          │  │ GTO          │  │ Dynamic      │           │
│  │ Strategy     │  │ Baseline     │  │ Ranges       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Game State                                 │
│              (Structured Detection Results)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Detection Layer                              │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Card         │  │ Button       │  │ Value        │           │
│  │ Detector     │  │ Detector     │  │ Reader       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Capture Layer                               │
│                (Window Capture & Management)                      │
└─────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### 1. Capture Layer (`src/capture/`)

Handles window detection and screen capture.

| Module | Purpose |
|--------|---------|
| `window_capture.py` | Captures window content using Windows GDI PrintWindow API |
| `window_manager.py` | Finds and manages poker table windows |
| `strategy_overlay.py` | Creates transparent HUD overlays attached to tables |

**Key Features:**
- Captures windows regardless of z-order (works when covered by other windows)
- DPI-aware scaling for high-DPI displays
- Multi-table support with independent overlays

### 2. Detection Layer (`src/detection/`)

Computer vision for recognizing game elements.

| Module | Purpose |
|--------|---------|
| `card_detector.py` | Recognizes card ranks and suits using ML + HSV color |
| `button_detector.py` | Locates dealer button position |
| `card_back_detector.py` | Identifies which opponents still have cards |

**Card Detection Pipeline:**
```
Card Image → Preprocessing → MLP Classifier → Rank
           → HSV Analysis → Suit Color → Suit
           → Combine → Full Card (e.g., "As", "Kh")
```

### 3. ML Layer (`src/ml/`)

Machine learning classifiers for recognition.

| Module | Purpose |
|--------|---------|
| `rank_classifier.py` | MLP classifier for card ranks (A-K) |
| `digit_classifier.py` | Digit recognition for pot/stack values |

**Model Details:**
- OpenCV MLP classifier
- 99.4% accuracy on card ranks
- Trained on extracted game screenshots
- Lightweight for real-time inference

### 4. Strategy Layer (`src/strategy/`)

Core decision-making engine (1700+ lines).

| Module | Purpose |
|--------|---------|
| `strategy_engine.py` | Main decision coordinator |
| `game_state.py` | Structures game information |
| `hand_evaluator.py` | Evaluates hand strength and draws |
| `board_analysis.py` | Analyzes board texture |
| `mdf.py` | Minimum Defense Frequency calculations |
| `spr_strategy.py` | Stack-to-Pot Ratio strategies |
| `gto_baseline.py` | GTO baseline with exploitative adjustments |
| `dynamic_ranges.py` | Position-aware hand ranges |
| `actions.py` | Structured action recommendations |
| `positions.py` | Position calculations |
| `opponent_db.py` | Opponent statistics tracking |

**Decision Flow:**
```
GameState
    │
    ├─► HandEvaluator → Made Hand + Draws
    │
    ├─► BoardAnalysis → Texture Classification
    │
    ├─► SPR Strategy → Commitment Level
    │
    ├─► MDF Analysis → Defense Thresholds
    │
    └─► StrategyEngine → Action Recommendation
```

### 5. Calibration Layer (`src/calibration/`)

Interactive tools for configuring table regions.

| Module | Purpose |
|--------|---------|
| `unified_calibrator.py` | All-in-one calibration tool |
| `calibration_manager.py` | Loads and manages calibration data |

**Calibrated Regions:**
- Hero cards, community cards
- Stack amounts, bet amounts
- Dealer button positions (9 seats)
- Card back detection areas

## Data Flow

### Live Analysis Flow

```
1. WindowCapture.grab()
   └─► Capture table screenshot

2. Detection Phase
   ├─► CardDetector.detect_card() × 7 slots
   ├─► ButtonDetector.detect_dealer_button()
   ├─► ValueReader.read_value() for pot/stacks/bets
   └─► CardBackDetector.get_active_seats()

3. GameState Construction
   └─► Combine all detected values into structured state

4. Strategy Analysis
   ├─► HandEvaluator.evaluate()
   ├─► BoardAnalysis.analyze_flop()
   ├─► SPRStrategy.get_spr_strategy()
   └─► StrategyEngine.get_recommendation()

5. Overlay Display
   └─► Render action recommendation on transparent overlay
```

### Configuration

| File | Purpose |
|------|---------|
| `config/calibration.json` | All calibrated regions and positions |
| `config/overlay_settings.json` | Overlay positioning and scale |
| `models/rank_classifier.xml` | Trained card rank classifier |
| `models/digit_classifier.xml` | Trained digit classifier |

## Design Principles

1. **Modular Separation** - Each layer has clear responsibilities
2. **No External Poker Libraries** - All hand evaluation built from scratch
3. **Type Safety** - Comprehensive type hints throughout
4. **Dataclass Architecture** - Clean data containers with validation
5. **Enum State Machines** - Well-defined states for decision logic
6. **Trace Debugging** - Decision traces for understanding recommendations

## Technology Stack

- **Python 3.11+** with type hints
- **OpenCV (cv2)** - Image processing and MLP classifier
- **PIL/Pillow** - Image manipulation
- **NumPy** - Numerical operations
- **tkinter** - Desktop GUI for overlays
- **ctypes** - Windows API access
