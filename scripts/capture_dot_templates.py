#!/usr/bin/env python
"""
Extract dot templates from bet regions.

Usage:
    python scripts/capture_dot_templates.py image.png
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json

import cv2

from src.paths import CONFIG_DIR, MODELS_DIR


def extract_dots(image_path: str):
    """Extract dot templates from all bet regions in an image."""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load {image_path}")
        return

    h, w = img.shape[:2]
    print(f"Image: {w}x{h}")

    # Load regions
    regions = json.loads((CONFIG_DIR / "calibrated_regions.json").read_text())
    templates_dir = MODELS_DIR / "char_templates_white"

    # Find next available index
    existing = list(templates_dir.glob("dot_alt*.png"))
    next_idx = len(existing) + 1

    saved = 0
    for key in [f"bet_{i}" for i in range(1, 10)]:
        if key not in regions:
            continue

        r = regions[key]
        x1, y1 = int(r["x"] * w), int(r["y"] * h)
        x2, y2 = int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)
        crop = img[y1:y2, x1:x2]

        # Isolate white text
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 120), (180, 60, 255))

        # Find dots
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            area = cw * ch
            if area < 50 and ch > 0 and 0.3 <= cw / ch <= 3.0:
                dot = mask[y : y + ch, x : x + cw]
                name = f"dot_alt{next_idx}.png"
                cv2.imwrite(str(templates_dir / name), dot)
                print(f"Saved {name} from {key}: {cw}x{ch}")
                next_idx += 1
                saved += 1

    print(f"Done! Saved {saved} dot template(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/capture_dot_templates.py image.png")
        sys.exit(1)
    extract_dots(sys.argv[1])
