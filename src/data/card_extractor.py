"""
Card Extractor - Extract card images from samples using calibrated slots.

Outputs to data/templates/cards/ with organized naming:
  data/templates/cards/hero_left/sample_001.png
  data/templates/cards/hero_right/sample_001.png
  data/templates/cards/board_1/sample_001.png
  ...

Usage:
    python scripts/extract_cards.py                  # Extract from all samples
    python scripts/extract_cards.py --sample 3       # Extract from sample #3 only
    python scripts/extract_cards.py --show           # Display extracted cards
"""

import argparse

import cv2
import numpy as np
from PIL import Image

from src.calibration.calibration_manager import load_config
from src.engine.scaling import get_scaled_card_size
from src.paths import CARDS_DIR, SAMPLES_DIR


def extract_with_tilt(img, x, y, w, h, tilt_deg):
    """Extract card region with rotation correction."""
    # No tilt - simple crop
    card = img.crop((x, y, x + w, y + h))
    if abs(tilt_deg) < 0.5:
        return card

    # Rotate the cropped card around its center to de-tilt
    card_cv = cv2.cvtColor(np.array(card), cv2.COLOR_RGB2BGR)
    h_card, w_card = card_cv.shape[:2]
    center = (w_card / 2, h_card / 2)
    M = cv2.getRotationMatrix2D(center, tilt_deg, 1.0)
    rotated = cv2.warpAffine(card_cv, M, (w_card, h_card), borderValue=(255, 255, 255))
    return Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))


def extract_cards(sample_path, regions, slots_cfg, output_dir=None):
    """Extract all card slots from a sample image."""
    img = Image.open(sample_path)
    full_w, full_h = img.size

    card_w, card_h = get_scaled_card_size(slots_cfg, full_w, full_h)
    slots = slots_cfg["slots"]

    # Get parent regions
    hero_reg = regions["hero_cards"]
    board_reg = regions["board"]

    # Crop parent regions
    hx, hy = int(hero_reg["x"] * full_w), int(hero_reg["y"] * full_h)
    hw, hh = int(hero_reg["w"] * full_w), int(hero_reg["h"] * full_h)
    hero_img = img.crop((hx, hy, hx + hw, hy + hh))

    bx, by = int(board_reg["x"] * full_w), int(board_reg["y"] * full_h)
    bw, bh = int(board_reg["w"] * full_w), int(board_reg["h"] * full_h)
    board_img = img.crop((bx, by, bx + bw, by + bh))

    results = {}

    for slot_name, slot in slots.items():
        if slot_name.startswith("hero"):
            parent = hero_img
        else:
            parent = board_img

        parent_w, parent_h = parent.size
        x = int(slot["x"] * parent_w)
        y = int(slot["y"] * parent_h)
        tilt = slot.get("tilt", 0)

        # Extract with tilt correction
        card = extract_with_tilt(parent, x, y, card_w, card_h, tilt)
        results[slot_name] = card

        # Save if output_dir specified
        if output_dir:
            slot_dir = output_dir / slot_name
            slot_dir.mkdir(parents=True, exist_ok=True)

            sample_name = sample_path.stem
            out_path = slot_dir / f"{sample_name}.png"
            card.save(out_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract card images from samples")
    parser.add_argument("--sample", type=int, help="Extract from specific sample number (1-based)")
    parser.add_argument("--show", action="store_true", help="Display extracted cards")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    output_dir = CARDS_DIR if args.output is None else __import__("pathlib").Path(args.output)

    # Load config
    regions, slots_cfg = load_config()
    card_w, card_h = slots_cfg["card_size"]

    print(f"Card size: {card_w}x{card_h}")
    print(f"Output: {output_dir}/")
    print()

    # Get samples
    samples = sorted(SAMPLES_DIR.glob("*.png"))
    if not samples:
        print(f"No samples found in {SAMPLES_DIR}/")
        return

    if args.sample:
        idx = args.sample - 1
        if 0 <= idx < len(samples):
            samples = [samples[idx]]
        else:
            print(f"Sample {args.sample} not found (have {len(samples)} samples)")
            return

    print(f"Processing {len(samples)} sample(s)...")

    for i, sample_path in enumerate(samples):
        print(f"[{i + 1}/{len(samples)}] {sample_path.name}")

        cards = extract_cards(sample_path, regions, slots_cfg, output_dir)

        if args.show:
            # Create composite image for display
            slot_names = list(cards.keys())
            n = len(slot_names)
            cols = min(n, 7)
            rows = (n + cols - 1) // cols

            composite = Image.new(
                "RGB",
                (cols * card_w + (cols - 1) * 2, rows * card_h + (rows - 1) * 2),
                (40, 40, 40),
            )

            for j, name in enumerate(slot_names):
                col = j % cols
                row = j // cols
                x = col * (card_w + 2)
                y = row * (card_h + 2)
                composite.paste(cards[name], (x, y))

            composite.save("debug_cards_composite.png")
            print("  -> debug_cards_composite.png")

    print()
    print(f"Done! Cards saved to {output_dir}/")
    print("Subfolders: hero_left, hero_right, board_1..5")


if __name__ == "__main__":
    main()
