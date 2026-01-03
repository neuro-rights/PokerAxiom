#!/usr/bin/env python
"""
Extract character templates from sample stack regions.

Scans through samples, extracts unique character crops,
and allows interactive labeling to build the template library.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import hashlib
import json

import cv2
import numpy as np

from src.paths import CONFIG_DIR, MODELS_DIR, SAMPLES_DIR

# Output directory
TEMPLATES_DIR = MODELS_DIR / "char_templates"

# HSV range for cyan stack text
LOWER_HSV = np.array([90, 80, 80])
UPPER_HSV = np.array([115, 255, 255])


def isolate_text(img: np.ndarray) -> np.ndarray:
    """Isolate cyan text pixels."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, LOWER_HSV, UPPER_HSV)


def extract_chars(mask: np.ndarray) -> list:
    """Extract character crops from mask."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    chars = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 2:  # Filter noise
            continue

        x, y, w, h = cv2.boundingRect(c)
        crop = mask[y : y + h, x : x + w]
        chars.append((x, crop))

    # Sort left to right
    chars.sort(key=lambda c: c[0])
    return [c[1] for c in chars]


def crop_hash(crop: np.ndarray) -> str:
    """Get a hash of a character crop for deduplication."""
    # Normalize to fixed height for comparison
    h, w = crop.shape
    target_h = 20
    scale = target_h / h
    resized = cv2.resize(crop, (int(w * scale), target_h))
    return hashlib.md5(resized.tobytes()).hexdigest()[:8]


def main():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    # Load regions config
    regions_file = CONFIG_DIR / "calibrated_regions.json"
    with open(regions_file) as f:
        regions = json.load(f)

    # Collect unique characters
    unique_chars = {}  # hash -> (crop, source_info)

    samples = sorted(SAMPLES_DIR.glob("*.png"))
    print(f"Scanning {len(samples)} samples for characters...")

    for sample_path in samples:
        img = cv2.imread(str(sample_path))
        if img is None:
            continue

        h, w = img.shape[:2]

        # Extract from stack regions
        for i in range(1, 10):
            key = f"stack_{i}"
            if key not in regions:
                continue

            r = regions[key]
            x1, y1 = int(r["x"] * w), int(r["y"] * h)
            x2, y2 = int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)

            crop = img[y1:y2, x1:x2]
            mask = isolate_text(crop)
            chars = extract_chars(mask)

            for char_crop in chars:
                h_val = crop_hash(char_crop)
                if h_val not in unique_chars:
                    unique_chars[h_val] = (char_crop, f"{sample_path.name}:{key}")

    print(f"Found {len(unique_chars)} unique character shapes")
    print()

    # Interactive labeling
    print("Label each character (0-9, $ for dollar, . for dot, s to skip, q to quit):")
    print()

    labeled = 0
    for h_val, (crop, source) in unique_chars.items():
        # Check if already labeled
        existing = list(TEMPLATES_DIR.glob(f"*_{h_val}.png"))
        if existing:
            print(f"  [{h_val}] Already labeled as {existing[0].stem.split('_')[0]}")
            continue

        # Show the character
        # Scale up for visibility
        display = cv2.resize(
            crop, (crop.shape[1] * 8, crop.shape[0] * 8), interpolation=cv2.INTER_NEAREST
        )

        cv2.imshow("Character", display)
        print(f"  [{h_val}] from {source}")
        print(f"    Size: {crop.shape[1]}x{crop.shape[0]}")

        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            print("Quit.")
            break
        elif key == ord("s"):
            print("    Skipped")
            continue
        elif key == ord("$"):
            label = "dollar"
        elif key == ord("."):
            label = "dot"
        elif chr(key).isdigit():
            label = chr(key)
        else:
            print(f"    Invalid key: {chr(key) if key < 128 else key}")
            continue

        # Save template
        out_path = TEMPLATES_DIR / f"{label}_{h_val}.png"
        cv2.imwrite(str(out_path), crop)
        print(f"    Saved as {label}")
        labeled += 1

    cv2.destroyAllWindows()

    print()
    print(f"Labeled {labeled} new templates")
    print(f"Templates directory: {TEMPLATES_DIR}")

    # Show summary
    templates = list(TEMPLATES_DIR.glob("*.png"))
    if templates:
        labels = set(t.stem.split("_")[0] for t in templates)
        print(f"Total templates: {len(templates)}")
        print(f"Characters covered: {sorted(labels)}")


if __name__ == "__main__":
    main()
