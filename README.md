# PokerAxiom

A poker decision support system demonstrating advanced software engineering, machine learning, and game theory concepts.

*Axiom: a statement accepted as true as the basis for argument or inference — like GTO strategy in poker.*

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Overview

PokerAxiom is a real-time poker analysis engine that combines:
- **Hybrid GTO-Exploitative Strategy** - Game theory optimal baselines with population-specific exploits
- **ML Card Detection** - Custom MLP classifiers achieving 99.4% accuracy
- **Real-Time Analysis** - Live decision recommendations through an overlay HUD

## Technical Highlights

### Strategy Engine

The strategy engine (`src/strategy/`) implements sophisticated poker decision-making with 1700+ lines of strategy logic:

| Component | Description |
|-----------|-------------|
| `strategy_engine.py` | Central decision coordinator with trace debugging |
| `gto_baseline.py` | GTO frequencies with exploit modifiers |
| `mdf.py` | Minimum Defense Frequency calculations |
| `spr_strategy.py` | Stack-to-Pot Ratio commitment decisions |
| `board_analysis.py` | Board texture classification (dry/medium/wet) |
| `hand_evaluator.py` | Complete hand strength evaluation |
| `dynamic_ranges.py` | Position-aware opening ranges |
| `opponent_db.py` | Opponent profiling and stat tracking |

### Machine Learning Pipeline

- **Card Rank Classifier**: OpenCV MLP trained on card images (99.4% accuracy)
- **Digit Recognition**: OCR for pot and stack values
- **4-Color Suit Detection**: HSV color analysis for suit identification
- **Active Learning**: Confidence-based sample prioritization

### Computer Vision

- Region-based calibration for different table layouts
- Template matching for dealer button detection
- Real-time frame processing for live overlay

## Architecture

```
PokerAxiom/
├── src/
│   ├── strategy/      # Game theory + exploitative strategy (1700+ lines)
│   ├── ml/            # Machine learning classifiers
│   ├── detection/     # Card, button, and value detection
│   ├── calibration/   # Interactive calibration tools
│   └── capture/       # Window capture system
├── docs/              # Architecture and concept documentation
├── examples/          # Usage examples
├── models/            # Trained ML models
└── config/            # Calibration data
```

## Documentation

- [Architecture Guide](docs/ARCHITECTURE.md) - System design and data flow
- [Strategy Concepts](docs/CONCEPTS.md) - Poker theory explained (GTO, MDF, SPR)
- [ML Pipeline](docs/ML_PIPELINE.md) - Training workflow details
- [API Reference](docs/API.md) - Library usage documentation

## Quick Start

### As a Library

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
)

# Get recommendation
engine = StrategyEngine()
action = engine.get_recommendation(state)
print(f"Recommended: {action.action_type.name} {action.amount}")
```

### Running Examples

```bash
# Strategy engine demo
python examples/strategy_demo.py

# Hand evaluation demo
python examples/hand_evaluation.py

# Board analysis demo
python examples/board_analysis.py

# MDF calculations demo
python examples/mdf_calculator.py
```

### Running the Overlay

```bash
# Install dependencies
pip install pillow numpy opencv-python

# Calibrate for your table layout
python scripts/calibrate.py

# Run the strategy overlay
python scripts/run_strategy.py
```

## Key Concepts Implemented

### GTO (Game Theory Optimal)
Mathematically balanced strategy that cannot be exploited. The engine starts with GTO baselines then applies population-specific exploits.

See: `src/strategy/gto_baseline.py`

### MDF (Minimum Defense Frequency)
Defense frequency required to prevent exploitation by bluffs. Formula: `MDF = 1 - (bet / (pot + bet))`

See: `src/strategy/mdf.py`

### SPR (Stack-to-Pot Ratio)
Determines commitment thresholds for different hand strengths:
- **Low SPR (1-3)**: One pair hands very valuable
- **Medium SPR (4-7)**: Need stronger hands to commit
- **High SPR (8+)**: Favor nutted hands, draws gain value

See: `src/strategy/spr_strategy.py`

### Board Texture Analysis
Classifies boards by draw potential:
- **Dry**: Few draws possible (K72 rainbow) → C-bet frequently
- **Wet**: Many draws possible (JT9 two-tone) → C-bet selectively

See: `src/strategy/board_analysis.py`

## Technical Details

### No External Poker Libraries
All hand evaluation, equity calculation, and range analysis built from scratch using Python with type hints.

### Design Patterns
- Dataclass-based architecture for clean data containers
- Enum-based state machines for decision logic
- Decision trace system for debugging

### Technology Stack
- **Python 3.11+** with comprehensive type hints
- **OpenCV** - Image processing and MLP classifiers
- **PIL/Pillow** - Image manipulation
- **NumPy** - Numerical operations
- **tkinter** - Desktop GUI for overlays
- **ctypes** - Windows API access

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run linting: `ruff check . && ruff format .`
5. Submit a Pull Request

### Code Style
- Python 3.11+ type hints
- Ruff for linting and formatting
- Dataclasses for data containers

## License

MIT License - See [LICENSE](LICENSE) for details.
