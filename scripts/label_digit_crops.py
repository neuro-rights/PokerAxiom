#!/usr/bin/env python
"""
Label digit crops for training the MLP classifier.

Shows each crop with the current MLP prediction, prioritizing:
1. Low-confidence predictions (more likely to be wrong)
2. Unique crops (skips near-duplicates)

Press the correct digit key (0-9) to label, or Enter to accept the prediction.
Press 's' to skip, 'q' to quit and save.

Usage:
    python scripts/label_digit_crops.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json

import cv2

from src.ml.digit_classifier import DIGIT_CLASSES, extract_digit_mask, get_model, predict_digit

CROPS_DIR = Path("data/digit_crops")
LABELS_FILE = Path("data/digit_crops/labels.json")
LABELED_DIR = Path("models/char_templates_live")


def visualize_crop(crop, scale=10):
    """Scale up a small crop for display."""
    h, w = crop.shape[:2]
    return cv2.resize(crop, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)


def compute_hash(img):
    """Compute a simple hash for deduplication."""
    mask = extract_digit_mask(img)
    # Downsample to 8x8 and threshold
    small = cv2.resize(mask, (8, 8), interpolation=cv2.INTER_AREA)
    return tuple((small > 127).flatten().tolist())


def is_similar(hash1, hash2, threshold=0.85):
    """Check if two hashes are similar (>threshold bits match)."""
    matches = sum(a == b for a, b in zip(hash1, hash2))
    return matches / len(hash1) > threshold


def main():
    # Load existing labels
    if LABELS_FILE.exists():
        with open(LABELS_FILE) as f:
            labels = json.load(f)
    else:
        labels = {}

    # Get all crops
    crops = sorted(CROPS_DIR.glob("*.png"))
    print(f"Found {len(crops)} crops, {len(labels)} already labeled")

    # Filter to unlabeled only
    unlabeled = [c for c in crops if c.name not in labels]
    print(f"Unlabeled: {len(unlabeled)}")

    if not unlabeled:
        print("All crops are labeled!")
        return

    # Load model
    model = get_model()
    if model is None:
        print("No model found - run train_digit_classifier.py first")
        return

    # Focus on confusable digits with confidence scores
    confusable_crops = []
    for crop_path in unlabeled:
        img = cv2.imread(str(crop_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        pred, conf = predict_digit(img, model)
        if pred in DIGIT_CLASSES:  # 0, 3, 6, 9
            img_hash = compute_hash(img)
            confusable_crops.append((crop_path, img, pred, conf, img_hash))

    print(f"Found {len(confusable_crops)} crops predicted as confusable digits (0,3,6,9)")

    # Sort by confidence (lowest first - most likely to be wrong)
    confusable_crops.sort(key=lambda x: x[3])

    # Deduplicate - keep only unique crops
    unique_crops = []
    seen_hashes = []
    for crop_path, img, pred, conf, img_hash in confusable_crops:
        is_dup = False
        for seen_hash in seen_hashes:
            if is_similar(img_hash, seen_hash):
                is_dup = True
                break
        if not is_dup:
            unique_crops.append((crop_path, img, pred, conf))
            seen_hashes.append(img_hash)

    print(f"After deduplication: {len(unique_crops)} unique crops")
    print("Showing lowest confidence first (most likely errors)")
    print("\nControls:")
    print("  0-9: Label as that digit")
    print("  Enter: Accept prediction")
    print("  s: Skip")
    print("  q: Quit and save")
    print()

    labeled_count = 0
    for crop_path, img, pred, conf in unique_crops:
        # Display
        display = visualize_crop(img, scale=15)
        cv2.imshow(f"Digit (pred={pred}, conf={conf:.2f})", display)

        print(f"{crop_path.name}: predicted {pred} (conf={conf:.2f}) - ", end="", flush=True)

        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            print("quit")
            break
        elif key == ord("s"):
            print("skipped")
            continue
        elif key == 13:  # Enter
            labels[crop_path.name] = pred
            print(f"accepted as {pred}")
            labeled_count += 1
        elif chr(key) in "0123456789":
            label = chr(key)
            labels[crop_path.name] = label
            print(f"labeled as {label}")
            labeled_count += 1

            # If it's a correction for a confusable digit, save to live templates
            if label in DIGIT_CLASSES and label != pred:
                LABELED_DIR.mkdir(exist_ok=True)
                save_path = LABELED_DIR / f"{label}_{crop_path.stem}.png"
                cv2.imwrite(str(save_path), img)
                print(f"  -> Saved correction to {save_path}")
        else:
            print("skipped (unknown key)")

        cv2.destroyAllWindows()

    # Save labels
    with open(LABELS_FILE, "w") as f:
        json.dump(labels, f, indent=2)

    print(f"\nLabeled {labeled_count} crops")
    print(f"Total labels saved: {len(labels)}")

    # Show stats
    if labels:
        counts = {}
        for label in labels.values():
            counts[label] = counts.get(label, 0) + 1
        print(f"Label distribution: {counts}")


if __name__ == "__main__":
    main()
