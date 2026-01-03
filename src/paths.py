# Centralized path definitions for the project

from pathlib import Path

# Project root is parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Config files
CONFIG_DIR = PROJECT_ROOT / "config"
CALIBRATION_FILE = CONFIG_DIR / "calibration.json"

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
TEMPLATES_DIR = DATA_DIR / "templates"
CARDS_DIR = TEMPLATES_DIR / "cards"
LABELED_DIR = TEMPLATES_DIR / "labeled"
DIGIT_CROPS_DIR = DATA_DIR / "digit_crops"

# Debug
DEBUG_SESSIONS_DIR = DATA_DIR / "debug_sessions"

# Models
MODELS_DIR = PROJECT_ROOT / "models"
RANK_CLASSIFIER_MODEL = MODELS_DIR / "rank_classifier.xml"
RANK_LABELS_FILE = MODELS_DIR / "rank_labels.json"
DIGIT_CLASSIFIER_MODEL = MODELS_DIR / "digit_classifier.xml"
CHAR_TEMPLATES_DIR = MODELS_DIR / "char_templates"
CHAR_TEMPLATES_WHITE_DIR = MODELS_DIR / "char_templates_white"
CHAR_TEMPLATES_LIVE_DIR = MODELS_DIR / "char_templates_live"

# Hand history
GAME_HISTORY_DIR = DATA_DIR / "game_history"
HISTORY_DB_FILE = DATA_DIR / "history.db"
