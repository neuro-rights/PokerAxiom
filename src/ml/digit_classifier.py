"""
Digit classifier using a lightweight OpenCV MLP.

Classifies all digits 0-9 for poker stack/bet value recognition.

Train once from character templates, then use predict_digit() at runtime.
"""

import cv2
import numpy as np

from src.engine.base import BaseLearner
from src.paths import MODELS_DIR

# Model path
DIGIT_CLASSIFIER_MODEL = MODELS_DIR / "digit_classifier.xml"

# Character templates directories
TEMPLATES_DIR = MODELS_DIR / "char_templates"
TEMPLATES_DIR_WHITE = MODELS_DIR / "char_templates_white"
TEMPLATES_DIR_LIVE = MODELS_DIR / "char_templates_live"  # Labeled from real samples

# All characters we classify (digits plus currency symbols)
DIGIT_CLASSES = "0123456789$."

# Feature size for normalization (height, width)
FEATURE_SIZE = (30, 15)


def extract_digit_mask(crop: np.ndarray) -> np.ndarray:
    """
    Prepare a binary digit crop for classification.

    Args:
        crop: Binary mask of the digit (any size)

    Returns:
        Resized mask of shape FEATURE_SIZE
    """
    if crop is None or crop.size == 0:
        return np.zeros(FEATURE_SIZE, dtype=np.uint8)

    # Ensure it's 2D grayscale
    if len(crop.shape) == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Resize to standard size
    resized = cv2.resize(crop, (FEATURE_SIZE[1], FEATURE_SIZE[0]), interpolation=cv2.INTER_AREA)
    return resized


def augment_mask(mask: np.ndarray) -> list:
    """
    Generate augmentations to improve robustness.

    Includes:
    - Original
    - Multi-distance shifts (simulates slight misalignment)
    - Erosion/dilation with multiple kernel sizes
    - Gaussian blur (simulates anti-aliasing)
    - Scale variations
    - Slight rotations

    Args:
        mask: Input binary mask

    Returns:
        List of augmented masks
    """
    masks = [mask]
    h, w = mask.shape
    center = (w // 2, h // 2)

    # Multi-distance shifts in 8 directions
    for dist in [1, 2]:
        shifts = [
            (-dist, 0),
            (dist, 0),
            (0, -dist),
            (0, dist),
            (-dist, -dist),
            (-dist, dist),
            (dist, -dist),
            (dist, dist),
        ]
        for dx, dy in shifts:
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            shifted = cv2.warpAffine(mask, M, (w, h), borderValue=0)
            masks.append(shifted)

    # Morphological operations with multiple kernel sizes
    for ksize in [2, 3]:
        kernel = np.ones((ksize, ksize), np.uint8)
        masks.append(cv2.erode(mask, kernel, iterations=1))
        masks.append(cv2.dilate(mask, kernel, iterations=1))

    # Multiple blur intensities
    for ksize in [(3, 3), (5, 5)]:
        blurred = cv2.GaussianBlur(mask, ksize, 0)
        masks.append(blurred)

    # Scale variations
    for scale in [0.85, 0.9, 0.95, 1.05, 1.1, 1.15]:
        new_h, new_w = int(h * scale), int(w * scale)
        if new_h > 0 and new_w > 0:
            scaled = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_AREA)
            # Pad or crop to original size
            if scale < 1.0:
                pad_h = (h - new_h) // 2
                pad_w = (w - new_w) // 2
                padded = np.zeros((h, w), dtype=np.uint8)
                padded[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = scaled
                masks.append(padded)
            else:
                crop_h = (new_h - h) // 2
                crop_w = (new_w - w) // 2
                cropped = scaled[crop_h : crop_h + h, crop_w : crop_w + w]
                if cropped.shape == (h, w):
                    masks.append(cropped)

    # Slight rotations (helps with rendering variations)
    for angle in [-3, -2, 2, 3]:
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(mask, M, (w, h), borderValue=0)
        masks.append(rotated)

    return masks


def mask_to_feature(mask: np.ndarray) -> np.ndarray:
    """Convert a mask to a normalized feature vector."""
    feat = mask.astype(np.float32) / 255.0
    return feat.reshape(1, -1)


def build_training_data():
    """
    Build (X, y) training data from character templates.

    Loads templates for all digits 0-9 from both cyan and white
    template directories, and applies augmentation.

    Returns:
        (X, y) where X is feature matrix, y is one-hot labels
        or (None, None) if no data found
    """
    label_to_idx = {digit: i for i, digit in enumerate(DIGIT_CLASSES)}

    X_rows = []
    y_rows = []

    # Template files to load for each character
    # Note: 9_alt3.png excluded as it visually looks like a 0 (closed loop)
    # $ and . have no base templates - trained from live samples only
    template_files = {
        "0": ["0.png"],
        "1": ["1.png"],
        "2": ["2.png", "2_alt.png"],
        "3": ["3.png"],
        "4": ["4.png", "4_alt.png"],
        "5": ["5.png", "5_alt.png"],
        "6": ["6.png", "6_alt.png"],
        "7": ["7.png", "7_alt.png"],
        "8": ["8.png"],
        "9": ["9.png", "9_alt.png", "9_alt2.png"],  # 9_alt3 excluded
        "$": [],  # Trained from live samples only
        ".": [],  # Trained from live samples only
    }

    # Load from template directories
    template_dirs = [TEMPLATES_DIR, TEMPLATES_DIR_WHITE]

    for templates_dir in template_dirs:
        if not templates_dir.exists():
            continue

        for digit, filenames in template_files.items():
            if digit not in label_to_idx:
                continue

            for filename in filenames:
                template_path = templates_dir / filename
                if not template_path.exists():
                    continue

                # Load template as grayscale
                template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
                if template is None:
                    continue

                # Prepare mask
                mask = extract_digit_mask(template)

                # Generate augmentations
                for aug_mask in augment_mask(mask):
                    X_rows.append(mask_to_feature(aug_mask))
                    y_rows.append(label_to_idx[digit])

    # Load from live-labeled templates (real sample corrections)
    # Filenames are like "3_samplename_stack1_char2.png" where first char is the label
    if TEMPLATES_DIR_LIVE.exists():
        live_count = 0
        for template_path in TEMPLATES_DIR_LIVE.glob("*.png"):
            # First character of filename is the digit label
            digit = template_path.stem[0]
            if digit not in label_to_idx:
                continue

            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                continue

            mask = extract_digit_mask(template)
            for aug_mask in augment_mask(mask):
                X_rows.append(mask_to_feature(aug_mask))
                y_rows.append(label_to_idx[digit])
            live_count += 1

        if live_count > 0:
            print(f"Loaded {live_count} live-labeled templates")

    if not X_rows:
        print("No training data found")
        return None, None

    # Stack features
    X = np.vstack(X_rows).astype(np.float32)
    y_idx = np.array(y_rows, dtype=np.int32)

    # One-hot encode labels
    y = np.zeros((len(y_idx), len(DIGIT_CLASSES)), dtype=np.float32)
    y[np.arange(len(y_idx)), y_idx] = 1.0

    print(f"Built training data: {X.shape[0]} samples, {X.shape[1]} features")
    return X, y


def create_model(input_dim: int):
    """
    Create a small MLP model.

    Architecture: input -> 64 hidden -> 32 hidden -> 4 outputs
    """
    model = cv2.ml.ANN_MLP_create()
    model.setLayerSizes(np.array([input_dim, 64, 32, len(DIGIT_CLASSES)], dtype=np.int32))
    model.setActivationFunction(cv2.ml.ANN_MLP_SIGMOID_SYM, 1.0, 1.0)
    model.setTrainMethod(cv2.ml.ANN_MLP_BACKPROP, 0.1, 0.1)
    model.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER | cv2.TERM_CRITERIA_EPS, 1000, 1e-5))
    return model


class DigitClassifier(BaseLearner):
    """
    Digit classifier using OpenCV MLP.

    Classifies all digits 0-9 plus $ and . symbols.
    Implements the standardized BaseLearner interface.
    """

    DIGIT_CLASSES = "0123456789$."
    FEATURE_SIZE = (30, 15)  # (h, w)

    def __init__(self, model_path: str | None = None):
        """
        Initialize digit classifier.

        Args:
            model_path: Path to saved model file
        """
        super().__init__(model_path or str(DIGIT_CLASSIFIER_MODEL))

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

    def predict(self, crop: np.ndarray) -> tuple[str | None, float]:
        """
        Predict digit class from a binary crop.

        Args:
            crop: Binary mask of the digit

        Returns:
            (digit, confidence) tuple, e.g., ('9', 0.85)
        """
        if not self.ensure_loaded():
            return None, 0.0

        mask = extract_digit_mask(crop)
        feat = mask_to_feature(mask)

        _, outputs = self._model.predict(feat)
        scores = outputs.flatten()
        best_idx = int(np.argmax(scores))
        confidence = float((scores[best_idx] + 1.0) / 2.0)

        return self.DIGIT_CLASSES[best_idx], confidence

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

# Cached model
_MODEL = None


def train_classifier():
    """Train the MLP and save to disk."""
    X, y = build_training_data()
    if X is None:
        raise RuntimeError("No training data found. Check templates directory.")

    # Ensure models directory exists
    DIGIT_CLASSIFIER_MODEL.parent.mkdir(parents=True, exist_ok=True)

    model = create_model(X.shape[1])
    model.train(X, cv2.ml.ROW_SAMPLE, y)
    model.save(str(DIGIT_CLASSIFIER_MODEL))

    global _MODEL
    _MODEL = model

    print(f"Saved model to {DIGIT_CLASSIFIER_MODEL}")
    return model


def load_model():
    """Load the trained classifier, if it exists."""
    if not DIGIT_CLASSIFIER_MODEL.exists():
        return None
    return cv2.ml.ANN_MLP_load(str(DIGIT_CLASSIFIER_MODEL))


def get_model():
    """Load and cache the model for repeated inference."""
    global _MODEL
    if _MODEL is None:
        _MODEL = load_model()
    return _MODEL


def predict_digit(crop: np.ndarray, model=None) -> tuple:
    """
    Predict digit class from a binary crop.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        crop: Binary mask of the digit
        model: Optional pre-loaded model

    Returns:
        (digit, confidence) tuple, e.g., ('9', 0.85)
        Returns (None, 0) if model not available
    """
    if model is None:
        model = get_model()
    if model is None:
        return None, 0.0

    # Prepare features
    mask = extract_digit_mask(crop)
    feat = mask_to_feature(mask)

    # Predict
    _, outputs = model.predict(feat)
    scores = outputs.flatten()

    # Get best prediction
    best_idx = int(np.argmax(scores))
    # Convert from tanh output [-1, 1] to confidence [0, 1]
    confidence = float((scores[best_idx] + 1.0) / 2.0)

    return DIGIT_CLASSES[best_idx], confidence


def test_classifier():
    """Evaluate accuracy on the template set."""
    model = load_model()
    if model is None:
        print("No model found. Run train_classifier() first.")
        return

    # Note: 9_alt3.png excluded as it visually looks like a 0 (closed loop)
    template_files = {
        "0": ["0.png"],
        "3": ["3.png"],
        "6": ["6.png", "6_alt.png"],
        "9": ["9.png", "9_alt.png", "9_alt2.png"],
    }

    total = 0
    correct = 0
    errors = []

    for digit, filenames in template_files.items():
        for filename in filenames:
            template_path = TEMPLATES_DIR / filename
            if not template_path.exists():
                continue

            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                continue

            pred, conf = predict_digit(template, model)
            total += 1

            if pred == digit:
                correct += 1
                print(f"  {filename}: {pred} (conf={conf:.2f}) OK")
            else:
                errors.append((filename, digit, pred, conf))
                print(f"  {filename}: {pred} (conf={conf:.2f}) WRONG (expected {digit})")

    print(f"\nAccuracy: {correct}/{total} ({100 * correct / total:.0f}%)")

    if errors:
        print("\nErrors:")
        for filename, expected, got, conf in errors:
            print(f"  {filename}: expected {expected}, got {got} (conf={conf:.2f})")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train/test digit classifier")
    parser.add_argument("--train", action="store_true", help="Train and save classifier")
    parser.add_argument("--test", action="store_true", help="Test classifier on templates")
    args = parser.parse_args()

    if args.train:
        train_classifier()
    if args.test:
        test_classifier()
    if not args.train and not args.test:
        # Default: train and test
        train_classifier()
        test_classifier()


if __name__ == "__main__":
    main()
