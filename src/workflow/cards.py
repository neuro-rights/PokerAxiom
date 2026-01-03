"""Cards workflow for training the rank classifier.

Provides extract → label → train → verify pipeline for card rank recognition.
"""

import shutil
from pathlib import Path

import cv2
import numpy as np

from src.calibration.calibration_manager import load_config
from src.data.card_extractor import extract_cards
from src.detection.card_detector import detect_suit_by_color, is_card_present
from src.ml.rank_classifier import (
    RANK_ORDER,
    build_training_data,
    create_model,
    extract_rank_mask,
    get_model,
    mask_to_feature,
    predict_rank,
)
from src.paths import CARDS_DIR, LABELED_DIR, RANK_CLASSIFIER_MODEL, SAMPLES_DIR

from .base import BaseWorkflow


class CardsWorkflow(BaseWorkflow):
    """Workflow for training card rank classifier."""

    name = "cards"
    classes = "A23456789TJQK"
    extract_dir = CARDS_DIR
    labeled_dir = LABELED_DIR
    model_path = RANK_CLASSIFIER_MODEL

    def __init__(self):
        """Initialize cards workflow."""
        super().__init__()
        self._model = None
        self._training_X = []
        self._training_y = []
        self._label_to_idx = {rank: i for i, rank in enumerate(RANK_ORDER)}

    def extract(self, sample_dir: Path = None, limit: int = None) -> int:
        """Extract card crops from sample images.

        Args:
            sample_dir: Directory containing samples (default: SAMPLES_DIR)
            limit: Maximum samples to process

        Returns:
            Number of cards extracted
        """
        sample_dir = sample_dir or SAMPLES_DIR
        if not sample_dir.exists():
            print(f"Sample directory not found: {sample_dir}")
            return 0

        # Load calibration
        try:
            regions, slots_cfg = load_config()
        except Exception as e:
            print(f"Failed to load calibration: {e}")
            return 0

        # Get samples
        samples = sorted(sample_dir.glob("*.png"))
        if limit:
            samples = samples[:limit]

        if not samples:
            print(f"No samples found in {sample_dir}")
            return 0

        print(f"Extracting cards from {len(samples)} samples...")
        total_extracted = 0

        for i, sample_path in enumerate(samples):
            try:
                cards = extract_cards(sample_path, regions, slots_cfg, self.extract_dir)
                total_extracted += len(cards)
                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{len(samples)} samples...")
            except Exception as e:
                print(f"  Error processing {sample_path.name}: {e}")

        print(f"Extracted {total_extracted} card crops to {self.extract_dir}")
        return total_extracted

    def predict(self, img: np.ndarray) -> tuple[str | None, float]:
        """Predict card rank from image.

        Args:
            img: BGR card image

        Returns:
            (rank, confidence) tuple
        """
        if self._model is None:
            self._model = get_model()

        if self._model is None:
            return None, 0.0

        return predict_rank(img, self._model)

    def train(self, incremental: bool = True) -> float:
        """Train rank classifier on labeled data.

        Args:
            incremental: If True, use cached training data (faster for active learning)

        Returns:
            Training accuracy
        """
        # Build training data from all labeled cards
        X, y = build_training_data()
        if X is None:
            print("No training data found")
            return 0.0

        # Create and train model
        model = create_model(X.shape[1])
        model.train(X, cv2.ml.ROW_SAMPLE, y)

        # Update cached model
        self._model = model

        # Save model
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(self.model_path))

        # Calculate accuracy
        _, predictions = model.predict(X)
        pred_idx = np.argmax(predictions, axis=1)
        true_idx = np.argmax(y, axis=1)
        accuracy = np.mean(pred_idx == true_idx)

        return float(accuracy)

    def verify(self) -> tuple[int, int]:
        """Verify model accuracy on labeled data.

        Returns:
            (correct, total) tuple
        """
        if self._model is None:
            self._model = get_model()

        if self._model is None:
            print("No model found")
            return 0, 0

        if not self.labeled_dir.exists():
            print("No labeled directory found")
            return 0, 0

        correct = 0
        total = 0

        for img_path in self.labeled_dir.glob("*.png"):
            # Parse label from filename (e.g., "Ac_001.png" -> "A")
            name = img_path.stem
            if len(name) < 2 or "_" not in name:
                continue

            true_rank = name[0].upper()
            if true_rank not in self.classes:
                continue

            img = cv2.imread(str(img_path))
            if img is None:
                continue

            pred_rank, _ = self.predict(img)
            total += 1
            if pred_rank == true_rank:
                correct += 1

        return correct, total

    def get_unlabeled_items(self) -> list[Path]:
        """Get card images not yet labeled.

        Returns:
            List of paths to unlabeled card images
        """
        if not self.extract_dir.exists():
            return []

        # Get all extracted card images
        all_cards = list(self.extract_dir.glob("**/*.png"))

        # Get already labeled images (by checking if image exists in labeled dir)
        labeled_stems = set()
        if self.labeled_dir.exists():
            for f in self.labeled_dir.glob("*.png"):
                # Track the original source to avoid re-labeling
                labeled_stems.add(f.stem.split("_")[0] if "_" in f.stem else f.stem)

        # Filter to cards that:
        # 1. Haven't been labeled yet
        # 2. Actually contain a card (not empty slots)
        unlabeled = []
        for card_path in all_cards:
            img = cv2.imread(str(card_path))
            if img is None:
                continue

            # Skip if no card present
            if not is_card_present(img):
                continue

            unlabeled.append(card_path)

        return unlabeled

    def save_label(self, item_path: Path, label: str) -> Path:
        """Save a labeled card.

        The label is the rank (A, 2-9, T, J, Q, K).
        Suit is auto-detected from the image.

        Args:
            item_path: Path to the card image
            label: The rank label

        Returns:
            Path to the saved labeled image
        """
        self.labeled_dir.mkdir(parents=True, exist_ok=True)

        # Load image to detect suit
        img = cv2.imread(str(item_path))
        if img is None:
            raise ValueError(f"Could not load image: {item_path}")

        suit = detect_suit_by_color(img)
        card_code = f"{label}{suit}"

        # Find next available filename
        existing = list(self.labeled_dir.glob(f"{card_code}_*.png"))
        next_num = len(existing) + 1
        filename = f"{card_code}_{next_num:03d}.png"

        dest_path = self.labeled_dir / filename
        shutil.copy2(item_path, dest_path)

        return dest_path

    def undo_label(self, item_path: Path, saved_path: Path) -> None:
        """Undo a label (for going back).

        Args:
            item_path: Original path to the card image
            saved_path: Path where the labeled card was saved
        """
        # Delete from labeled_dir if it exists
        if saved_path and saved_path.exists() and saved_path != item_path:
            saved_path.unlink()

    def get_feature_and_label(self, labeled_path: Path) -> tuple[np.ndarray, str] | None:
        """Extract training data from a labeled card.

        Args:
            labeled_path: Path to labeled card image

        Returns:
            (feature_vector, rank_label) or None if invalid
        """
        # Parse label from filename
        name = labeled_path.stem
        if len(name) < 2:
            return None

        rank = name[0].upper()
        if rank not in self.classes:
            return None

        img = cv2.imread(str(labeled_path))
        if img is None:
            return None

        mask = extract_rank_mask(img)
        feature = mask_to_feature(mask)

        return feature.flatten(), rank
