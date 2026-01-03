"""Base workflow class with active learning support.

Provides the abstract interface and common logic for all training workflows.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np


class BaseWorkflow(ABC):
    """Base class for data type workflows with active learning.

    Subclasses must implement:
    - extract(): Extract crops from samples
    - predict(): Predict class and confidence for an image
    - train(): Train the model on labeled data
    - verify(): Verify model accuracy
    - get_unlabeled_items(): Get list of items to label
    - save_label(): Save a label for an item
    - get_feature_and_label(): Extract training data from a labeled item
    """

    # Subclasses must define these
    name: str = ""
    classes: str = ""  # Valid class labels (e.g., "A23456789TJQK" or "0123456789")
    extract_dir: Path = None
    labeled_dir: Path = None
    model_path: Path = None

    def __init__(self):
        """Initialize workflow."""
        self._model = None
        self._training_data = []  # List of (features, label) tuples

    @abstractmethod
    def extract(self, sample_dir: Path = None, limit: int = None) -> int:
        """Extract crops from samples.

        Args:
            sample_dir: Directory containing samples (default: SAMPLES_DIR)
            limit: Maximum samples to process (default: all)

        Returns:
            Number of items extracted
        """
        pass

    @abstractmethod
    def predict(self, img: np.ndarray) -> tuple[str | None, float]:
        """Predict class and confidence for an image.

        Args:
            img: BGR image to classify

        Returns:
            (predicted_class, confidence) tuple
        """
        pass

    @abstractmethod
    def train(self, incremental: bool = True) -> float:
        """Train model on labeled data.

        Args:
            incremental: If True, add new labels to existing training data

        Returns:
            Training accuracy (0.0 to 1.0)
        """
        pass

    @abstractmethod
    def verify(self) -> tuple[int, int]:
        """Verify model accuracy on labeled data.

        Returns:
            (correct, total) tuple
        """
        pass

    @abstractmethod
    def get_unlabeled_items(self) -> list[Path]:
        """Get list of extracted items not yet labeled.

        Returns:
            List of paths to unlabeled items
        """
        pass

    @abstractmethod
    def save_label(self, item_path: Path, label: str) -> Path:
        """Save a label for an item.

        Args:
            item_path: Path to the item being labeled
            label: The assigned label

        Returns:
            Path to the saved labeled item
        """
        pass

    @abstractmethod
    def undo_label(self, item_path: Path, saved_path: Path) -> None:
        """Undo a label (for going back).

        Args:
            item_path: Original path to the item
            saved_path: Path where the labeled item was saved
        """
        pass

    @abstractmethod
    def get_feature_and_label(self, labeled_path: Path) -> tuple[np.ndarray, str] | None:
        """Extract training data from a labeled item.

        Args:
            labeled_path: Path to the labeled item

        Returns:
            (feature_vector, label) tuple, or None if invalid
        """
        pass

    def prioritize_by_confidence(self, items: list[Path]) -> list[tuple[Path, str | None, float]]:
        """Sort items by prediction confidence (ascending).

        Low-confidence items are shown first (most uncertain = most valuable to label).

        Args:
            items: List of paths to items

        Returns:
            [(path, predicted_class, confidence), ...] sorted by confidence ascending
        """
        results = []
        for path in items:
            img = cv2.imread(str(path))
            if img is None:
                continue
            pred, conf = self.predict(img)
            results.append((path, pred, conf))
        return sorted(results, key=lambda x: x[2])  # Sort by confidence ASC

    def label(self, limit: int = None) -> int:
        """Interactive labeling with active learning.

        Flow:
        1. Load all unlabeled items
        2. Predict confidence for each
        3. Sort by confidence (lowest first - most uncertain)
        4. For each item:
           a. Show image + prediction + confidence
           b. User labels (or accepts prediction)
           c. Save label to disk
           d. Retrain model immediately
           e. Re-sort remaining items by new confidence
        5. Return count labeled

        Args:
            limit: Maximum items to label (default: all)

        Returns:
            Number of items labeled
        """
        from .labeler_ui import LabelerUI

        # Get unlabeled items
        items = self.get_unlabeled_items()
        if not items:
            print(f"No unlabeled {self.name} items found.")
            return 0

        print(f"Found {len(items)} unlabeled {self.name} items.")
        print("Calculating initial predictions...")

        # Sort by confidence (lowest first)
        prioritized = self.prioritize_by_confidence(items)
        if not prioritized:
            print("No valid items to label.")
            return 0

        # Initialize UI
        ui = LabelerUI(self.name, self.classes)

        labeled_count = 0
        skipped = set()  # Track skipped items
        history = []  # Track (path, pred, conf, saved_path) for going back

        idx = 0
        while idx < len(prioritized):
            if limit and labeled_count >= limit:
                break

            # Get current item
            path, pred, conf = prioritized[idx]

            # Skip if previously skipped
            if path in skipped:
                idx += 1
                continue

            # Load image
            img = cv2.imread(str(path))
            if img is None:
                idx += 1
                continue

            # Show labeling UI
            result = ui.show(img, pred, conf, labeled_count, len(prioritized) - idx)

            if result == "quit":
                print("\nQuitting labeling session...")
                break
            elif result == "back":
                # Go back to previous item
                if history:
                    prev_path, prev_pred, prev_conf, saved_path = history.pop()
                    # Undo the label
                    self.undo_label(prev_path, saved_path)
                    labeled_count -= 1
                    # Find the previous item in prioritized list and go back
                    for i, (p, _, _) in enumerate(prioritized):
                        if p == prev_path:
                            idx = i
                            break
                    print(f"\r  Labeled: {labeled_count} (undid last)", end="", flush=True)
                continue
            elif result == "skip":
                skipped.add(path)
                idx += 1
                continue
            elif result is not None:
                # User provided a label
                label = result

                # Save the label
                saved_path = self.save_label(path, label)
                history.append((path, pred, conf, saved_path))
                labeled_count += 1
                idx += 1
                print(f"\r  Labeled: {labeled_count}", end="", flush=True)

        ui.close()
        print(f"\nLabeled {labeled_count} items.")

        # Retrain once at end of session if we labeled anything
        if labeled_count > 0:
            print("Retraining model with new labels...")
            try:
                accuracy = self.train(incremental=False)
                print(f"Final accuracy: {accuracy:.1%}")
            except Exception as e:
                print(f"Train error: {e}")
        return labeled_count

    def run_all(self, limit: int = None) -> dict:
        """Run full pipeline: extract → label → train → verify.

        Args:
            limit: Maximum samples to process (default: all)

        Returns:
            Dict with results from each step
        """
        print(f"\n{'=' * 50}")
        print(f"  {self.name.upper()} WORKFLOW")
        print(f"{'=' * 50}\n")

        # Extract
        print("Step 1: EXTRACT")
        print("-" * 30)
        extracted = self.extract(limit=limit)
        print(f"Extracted: {extracted} items\n")

        # Label
        print("Step 2: LABEL")
        print("-" * 30)
        labeled = self.label(limit=limit)
        print(f"Labeled: {labeled} items\n")

        # Train
        print("Step 3: TRAIN")
        print("-" * 30)
        accuracy = self.train(incremental=False)
        print(f"Training accuracy: {accuracy:.1%}\n")

        # Verify
        print("Step 4: VERIFY")
        print("-" * 30)
        correct, total = self.verify()
        print(f"Verification: {correct}/{total} ({100 * correct / total:.0f}%)\n")

        return {
            "extracted": extracted,
            "labeled": labeled,
            "accuracy": accuracy,
            "verified": (correct, total),
        }
