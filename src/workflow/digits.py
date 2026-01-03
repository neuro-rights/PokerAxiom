"""Digits workflow for training the digit classifier.

Provides extract → label → train → verify pipeline for digit disambiguation.
"""

import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from src.calibration.calibration_manager import load_config
from src.ml.digit_classifier import (
    DIGIT_CLASSES,
    build_training_data,
    create_model,
    extract_digit_mask,
    get_model,
    mask_to_feature,
    predict_digit,
)
from src.paths import (
    CHAR_TEMPLATES_LIVE_DIR,
    DIGIT_CLASSIFIER_MODEL,
    DIGIT_CROPS_DIR,
    SAMPLES_DIR,
)
from src.recognition.value_reader import find_characters, isolate_text

from .base import BaseWorkflow


class DigitsWorkflow(BaseWorkflow):
    """Workflow for training digit classifier."""

    name = "digits"
    classes = "0123456789$."  # All digits plus $ and . symbols
    extract_dir = DIGIT_CROPS_DIR
    labeled_dir = CHAR_TEMPLATES_LIVE_DIR
    model_path = DIGIT_CLASSIFIER_MODEL

    def __init__(self):
        """Initialize digits workflow."""
        super().__init__()
        self._model = None
        self._labels_file = self.extract_dir / "labels.json"
        self._labels = {}
        self._load_labels()

    def _load_labels(self):
        """Load existing labels from disk."""
        if self._labels_file.exists():
            with open(self._labels_file) as f:
                self._labels = json.load(f)

    def _save_labels(self):
        """Save labels to disk."""
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        with open(self._labels_file, "w") as f:
            json.dump(self._labels, f, indent=2)

    def extract(self, sample_dir: Path = None, limit: int = None) -> int:
        """Extract digit crops from stack/bet regions in sample images.

        Args:
            sample_dir: Directory containing samples (default: SAMPLES_DIR)
            limit: Maximum samples to process

        Returns:
            Number of digit crops extracted
        """
        sample_dir = sample_dir or SAMPLES_DIR
        if not sample_dir.exists():
            print(f"Sample directory not found: {sample_dir}")
            return 0

        # Load calibration
        try:
            regions, _ = load_config()
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

        self.extract_dir.mkdir(parents=True, exist_ok=True)

        print(f"Extracting digits from {len(samples)} samples...")
        total_extracted = 0

        # Region types to extract from
        region_types = [
            ("stack", "stack"),  # (region_prefix, text_type)
            ("bet", "bet"),
        ]

        for i, sample_path in enumerate(samples):
            try:
                img = cv2.imread(str(sample_path))
                if img is None:
                    continue

                full_h, full_w = img.shape[:2]
                sample_name = sample_path.stem

                # Process each region type
                for region_prefix, text_type in region_types:
                    # Find all regions with this prefix (e.g., stack_1, stack_2, ...)
                    for region_name, region in regions.items():
                        if not region_name.startswith(region_prefix):
                            continue

                        # Crop region
                        x = int(region["x"] * full_w)
                        y = int(region["y"] * full_h)
                        w = int(region["w"] * full_w)
                        h = int(region["h"] * full_h)

                        region_crop = img[y : y + h, x : x + w]
                        if region_crop.size == 0:
                            continue

                        # Isolate text and find characters
                        mask = isolate_text(region_crop, text_type)
                        chars = find_characters(mask, min_area=10)

                        # Save each digit crop
                        for j, (cx, cy, cw, ch, char_crop) in enumerate(chars):
                            # Skip very small or very large crops (noise or merged)
                            if cw < 5 or ch < 8 or cw > 20 or ch > 25:
                                continue

                            # Create unique filename
                            filename = f"{sample_name}_{region_name}_char{j}.png"
                            out_path = self.extract_dir / filename

                            # Save the binary mask crop
                            cv2.imwrite(str(out_path), char_crop)
                            total_extracted += 1

                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{len(samples)} samples...")

            except Exception as e:
                print(f"  Error processing {sample_path.name}: {e}")

        print(f"Extracted {total_extracted} digit crops to {self.extract_dir}")
        return total_extracted

    def predict(self, img: np.ndarray) -> tuple[str | None, float]:
        """Predict digit from crop image.

        Args:
            img: Grayscale or BGR digit crop image

        Returns:
            (digit, confidence) tuple
        """
        if self._model is None:
            self._model = get_model()

        if self._model is None:
            return None, 0.0

        return predict_digit(img, self._model)

    def train(self, incremental: bool = True) -> float:
        """Train digit classifier on template data.

        Args:
            incremental: Unused (always trains on all data)

        Returns:
            Training accuracy
        """
        # Build training data from all templates
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

        print(f"Trained on {X.shape[0]} samples, accuracy: {accuracy:.1%}")
        return float(accuracy)

    def verify(self) -> tuple[int, int]:
        """Verify model accuracy on live templates.

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

        # Test on live templates (filename format: "3_samplename.png")
        for img_path in self.labeled_dir.glob("*.png"):
            name = img_path.stem
            if not name:
                continue

            # First character is the label
            true_digit = name[0]
            if true_digit not in DIGIT_CLASSES:
                continue

            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            pred_digit, _ = self.predict(img)
            total += 1
            if pred_digit == true_digit:
                correct += 1

        return correct, total

    def _image_hash(self, img_path: Path) -> str:
        """Compute hash of image content for deduplication."""
        import hashlib

        data = img_path.read_bytes()
        return hashlib.md5(data).hexdigest()

    def get_unlabeled_items(self) -> list[Path]:
        """Get digit crops not yet labeled, deduplicated by pixel content.

        Returns:
            List of paths to unlabeled digit crops (unique images only)
        """
        if not self.extract_dir.exists():
            return []

        # Get all extracted digit crops
        all_crops = list(self.extract_dir.glob("*.png"))

        # Track which have been labeled (by source filename)
        labeled_sources = set()
        if self.labeled_dir.exists():
            for f in self.labeled_dir.glob("*.png"):
                # Parse original source from filename (e.g., "3_sample_stack1_char0.png")
                parts = f.stem.split("_", 1)
                if len(parts) >= 2:
                    labeled_sources.add(parts[1])

        # Also check labels.json for labeled items
        for source in self._labels.keys():
            labeled_sources.add(Path(source).stem)

        # Collect hashes of already-labeled images to skip duplicates
        labeled_hashes = set()
        if self.labeled_dir.exists():
            for f in self.labeled_dir.glob("*.png"):
                labeled_hashes.add(self._image_hash(f))

        # Filter unlabeled and deduplicate by image content
        seen_hashes = set(labeled_hashes)
        unlabeled = []
        for crop_path in all_crops:
            if crop_path.stem not in labeled_sources:
                img_hash = self._image_hash(crop_path)
                if img_hash not in seen_hashes:
                    seen_hashes.add(img_hash)
                    unlabeled.append(crop_path)

        return unlabeled

    def save_label(self, item_path: Path, label: str) -> Path:
        """Save a labeled digit.

        Saves to both:
        1. labels.json in extract_dir (for tracking)
        2. char_templates_live for training

        Args:
            item_path: Path to the digit crop
            label: The digit label (0-9)

        Returns:
            Path to the saved labeled item
        """
        # Update labels.json
        self._labels[item_path.name] = label
        self._save_labels()

        # Save all digits to char_templates_live for training
        if label in DIGIT_CLASSES:
            self.labeled_dir.mkdir(parents=True, exist_ok=True)

            # Create filename: {label}_{original_stem}.png
            dest_filename = f"{label}_{item_path.stem}.png"
            dest_path = self.labeled_dir / dest_filename

            shutil.copy2(item_path, dest_path)
            return dest_path

        return item_path

    def undo_label(self, item_path: Path, saved_path: Path) -> None:
        """Undo a label (for going back).

        Args:
            item_path: Original path to the digit crop
            saved_path: Path where the labeled item was saved
        """
        # Remove from labels.json
        if item_path.name in self._labels:
            del self._labels[item_path.name]
            self._save_labels()

        # Delete from char_templates_live if it exists
        if saved_path and saved_path.exists() and saved_path != item_path:
            saved_path.unlink()

    def get_feature_and_label(self, labeled_path: Path) -> tuple[np.ndarray, str] | None:
        """Extract training data from a labeled digit.

        Args:
            labeled_path: Path to labeled digit image

        Returns:
            (feature_vector, digit_label) or None if invalid
        """
        name = labeled_path.stem
        if not name:
            return None

        # First character is the label
        digit = name[0]
        if digit not in DIGIT_CLASSES:
            return None

        img = cv2.imread(str(labeled_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None

        mask = extract_digit_mask(img)
        feature = mask_to_feature(mask)

        return feature.flatten(), digit
