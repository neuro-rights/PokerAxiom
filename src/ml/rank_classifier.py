"""
Rank classifier using a lightweight OpenCV MLP.

Train once from labeled card crops, then use predict_rank() at runtime.
"""

import json

import cv2
import numpy as np

from src.detection.card_detector import detect_suit_by_color, isolate_suit_color
from src.engine.base import BaseLearner
from src.paths import CARDS_DIR, LABELED_DIR, RANK_CLASSIFIER_MODEL, RANK_LABELS_FILE

RANK_ORDER = "A23456789TJQK"

# Manual labels for training images (relative to templates/cards/)
LABELED_CARDS = {
    # Hero left cards
    "hero_left/NLHAWhite08_185020.png": "6",  # 6h
    "hero_left/NLHAWhite08_20251231_182821_001.png": "A",  # Ad
    "hero_left/NLHAWhite08_20251231_182925_002.png": "K",  # Kc
    "hero_left/NLHAWhite08_20251231_183012_004.png": "Q",  # Qc
    "hero_left/NLHAWhite08_20251231_183242_007.png": "T",  # Tc
    "hero_left/NLHAWhite08_20251231_183329_008.png": "9",  # 9c
    "hero_left/NLHAWhite08_20251231_183424_009.png": "J",  # Jd
    "hero_left/NLHAWhite08_20251231_183507_010.png": "7",  # 7d
    "hero_left/NLHAWhite08_20251231_183648_012.png": "4",  # 4c
    "hero_left/NLHAWhite08_20251231_183822_013.png": "8",  # 8s
    "hero_left/NLHAWhite08_20251231_183911_014.png": "K",  # Ks (black)
    "hero_left/NLHAWhite08_20251231_184747_017.png": "Q",  # Qh (red)
    "hero_left/NLHAWhite08_20251231_184822_018.png": "A",  # As (black)
    "hero_left/NLHAWhite08_20251231_185046_024.png": "6",  # 6c (green)
    # Hero right cards
    "hero_right/NLHAWhite08_185020.png": "3",  # 3c
    "hero_right/NLHAWhite08_20251231_182821_001.png": "2",  # 2c
    "hero_right/NLHAWhite08_20251231_182925_002.png": "7",  # 7c
    "hero_right/NLHAWhite08_20251231_183012_004.png": "9",  # 9c
    "hero_right/NLHAWhite08_20251231_183119_006.png": "8",  # 8s
    "hero_right/NLHAWhite08_20251231_183242_007.png": "8",  # 8d
    "hero_right/NLHAWhite08_20251231_183329_008.png": "5",  # 5c
    "hero_right/NLHAWhite08_20251231_183424_009.png": "3",  # 3s
    "hero_right/NLHAWhite08_20251231_183507_010.png": "5",  # 5s
    "hero_right/NLHAWhite08_20251231_183624_011.png": "6",  # 6d
    "hero_right/NLHAWhite08_20251231_183648_012.png": "2",  # 2h
    "hero_right/NLHAWhite08_20251231_183822_013.png": "4",  # 4c
    "hero_right/NLHAWhite08_20251231_183911_014.png": "K",  # Kh
}

FEATURE_SIZE = (30, 15)  # (h, w)


def extract_rank_mask(card_img):
    """Extract rank mask from a card image."""
    h, w = card_img.shape[:2]
    rank_area = card_img[0 : int(h * 0.45), :]
    suit = detect_suit_by_color(card_img)
    mask = isolate_suit_color(rank_area, suit)
    mask = cv2.resize(mask, (FEATURE_SIZE[1], FEATURE_SIZE[0]))
    return mask


def augment_mask(mask):
    """Generate simple augmentations to improve robustness."""
    masks = [mask]

    shifts = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dx, dy in shifts:
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(mask, M, (mask.shape[1], mask.shape[0]), borderValue=0)
        masks.append(shifted)

    kernel = np.ones((2, 2), np.uint8)
    masks.append(cv2.erode(mask, kernel, iterations=1))
    masks.append(cv2.dilate(mask, kernel, iterations=1))
    return masks


def mask_to_feature(mask):
    """Convert a mask to a normalized feature vector."""
    feat = mask.astype(np.float32) / 255.0
    return feat.reshape(1, -1)


def build_training_data():
    """Build (X, y) from labeled cards with augmentation."""
    label_to_idx = {rank: i for i, rank in enumerate(RANK_ORDER)}
    X_rows = []
    y_rows = []

    # Legacy labels from LABELED_CARDS dict and rank_labels.json
    labels = dict(LABELED_CARDS)
    if RANK_LABELS_FILE.exists():
        with open(RANK_LABELS_FILE) as f:
            labels.update(json.load(f))

    for rel_path, rank in labels.items():
        path = CARDS_DIR / rel_path
        if not path.exists():
            continue

        img = cv2.imread(str(path))
        if img is None:
            continue

        mask = extract_rank_mask(img)
        for aug in augment_mask(mask):
            X_rows.append(mask_to_feature(aug))
            y_rows.append(label_to_idx[rank])

    # New labeled images from templates/labeled/ folder (e.g., Ac_001.png, Ts_002.png)
    if LABELED_DIR.exists():
        for img_path in LABELED_DIR.glob("*.png"):
            # Parse rank from filename (first character: A,2-9,T,J,Q,K)
            name = img_path.stem
            if len(name) >= 2:
                rank = name[0].upper()
                if rank in RANK_ORDER:
                    img = cv2.imread(str(img_path))
                    if img is None:
                        continue

                    mask = extract_rank_mask(img)
                    for aug in augment_mask(mask):
                        X_rows.append(mask_to_feature(aug))
                        y_rows.append(label_to_idx[rank])

    if not X_rows:
        return None, None

    X = np.vstack(X_rows).astype(np.float32)
    y_idx = np.array(y_rows, dtype=np.int32)

    # One-hot labels for MLP
    y = np.zeros((len(y_idx), len(RANK_ORDER)), dtype=np.float32)
    y[np.arange(len(y_idx)), y_idx] = 1.0

    return X, y


def create_model(input_dim):
    """Create a small MLP model."""
    model = cv2.ml.ANN_MLP_create()
    model.setLayerSizes(np.array([input_dim, 64, len(RANK_ORDER)], dtype=np.int32))
    model.setActivationFunction(cv2.ml.ANN_MLP_SIGMOID_SYM, 1.0, 1.0)
    model.setTrainMethod(cv2.ml.ANN_MLP_BACKPROP, 0.1, 0.1)
    model.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER | cv2.TERM_CRITERIA_EPS, 400, 1e-3))
    return model


class RankClassifier(BaseLearner):
    """
    Rank classifier using OpenCV MLP.

    Implements the standardized BaseLearner interface.
    """

    RANK_ORDER = "A23456789TJQK"
    FEATURE_SIZE = (30, 15)  # (h, w)

    def __init__(self, model_path: str | None = None):
        """
        Initialize rank classifier.

        Args:
            model_path: Path to saved model file
        """
        super().__init__(model_path or str(RANK_CLASSIFIER_MODEL))

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """
        Train the MLP classifier.

        Args:
            X: Feature matrix (samples x features)
            y: One-hot encoded labels
        """
        self._model = create_model(X.shape[1])
        self._model.train(X, cv2.ml.ROW_SAMPLE, y)
        self._is_loaded = True

    def predict(self, card_img: np.ndarray) -> tuple[str | None, float]:
        """
        Predict rank from card image.

        Args:
            card_img: BGR card image

        Returns:
            (rank, confidence) tuple, e.g., ('A', 0.95)
        """
        if not self.ensure_loaded():
            return None, 0.0

        mask = extract_rank_mask(card_img)
        feat = mask_to_feature(mask)

        _, outputs = self._model.predict(feat)
        scores = outputs.flatten()
        best_idx = int(np.argmax(scores))
        confidence = float((scores[best_idx] + 1.0) / 2.0)

        return self.RANK_ORDER[best_idx], confidence

    def save(self, path: str) -> None:
        """Save model to disk."""
        if self._model is not None:
            self._model.save(path)

    def load(self, path: str) -> bool:
        """Load model from disk."""
        try:
            self._model = cv2.ml.ANN_MLP_load(path)
            self._is_loaded = True
            return True
        except Exception:
            self._is_loaded = False
            return False


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

# Module-level cached model
_MODEL = None


def train_classifier():
    """Train the MLP and save to disk."""
    X, y = build_training_data()
    if X is None:
        raise RuntimeError("No training data found. Check LABELED_CARDS paths.")

    # Ensure models directory exists
    RANK_CLASSIFIER_MODEL.parent.mkdir(parents=True, exist_ok=True)

    model = create_model(X.shape[1])
    model.train(X, cv2.ml.ROW_SAMPLE, y)
    model.save(str(RANK_CLASSIFIER_MODEL))
    global _MODEL
    _MODEL = model
    return model


def load_model():
    """Load the trained classifier, if it exists."""
    if not RANK_CLASSIFIER_MODEL.exists():
        return None
    return cv2.ml.ANN_MLP_load(str(RANK_CLASSIFIER_MODEL))


def get_model():
    """Load and cache the model for repeated inference."""
    global _MODEL
    if _MODEL is None:
        _MODEL = load_model()
    return _MODEL


def predict_rank(card_img, model=None):
    """
    Predict rank from card image.

    BACKWARD COMPATIBLE: Preserves original API.

    Returns (rank, confidence) or (None, 0).
    """
    if model is None:
        model = get_model()
    if model is None:
        return None, 0

    mask = extract_rank_mask(card_img)
    feat = mask_to_feature(mask)

    _, outputs = model.predict(feat)
    scores = outputs.flatten()
    best_idx = int(np.argmax(scores))
    confidence = float((scores[best_idx] + 1.0) / 2.0)
    return RANK_ORDER[best_idx], confidence


def test_classifier():
    """Evaluate accuracy on the labeled set."""
    model = load_model()
    if model is None:
        print("No model found. Run --train first.")
        return

    labels = dict(LABELED_CARDS)
    if RANK_LABELS_FILE.exists():
        with open(RANK_LABELS_FILE) as f:
            labels.update(json.load(f))

    total = 0
    correct = 0

    for rel_path, rank in labels.items():
        path = CARDS_DIR / rel_path
        if not path.exists():
            continue

        img = cv2.imread(str(path))
        if img is None:
            continue

        pred, _ = predict_rank(img, model)
        total += 1
        if pred == rank:
            correct += 1

    if total == 0:
        print("No labeled images found for testing.")
        return

    print(f"Accuracy: {correct}/{total} ({100 * correct / total:.0f}%)")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="Train and save classifier")
    parser.add_argument("--test", action="store_true", help="Test classifier on labeled data")
    args = parser.parse_args()

    if args.train:
        train_classifier()
        print(f"Saved model to {RANK_CLASSIFIER_MODEL}")
    if args.test:
        test_classifier()
    if not args.train and not args.test:
        train_classifier()
        print(f"Saved model to {RANK_CLASSIFIER_MODEL}")
        test_classifier()


if __name__ == "__main__":
    main()
