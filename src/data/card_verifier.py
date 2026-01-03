"""
Model verification tool - manually check predictions on card samples.

Usage:
    python scripts/verify_cards.py              # Verify on templates/cards/
    python scripts/verify_cards.py --labeled    # Verify on templates/labeled/
    python scripts/verify_cards.py --shuffle    # Random order

Keyboard controls:
    y / SPACE  - Correct prediction
    n          - Wrong prediction
    1-9,t,j,q,k,a - Enter actual rank (marks as wrong)
    ESC        - Skip
    q          - Quit and show results
"""

import argparse
import random

import cv2
import numpy as np

from src.detection.card_detector import detect_suit_by_color, is_card_present
from src.ml.rank_classifier import RANK_ORDER, get_model, predict_rank
from src.paths import CARDS_DIR, LABELED_DIR

MIN_DISPLAY_SIZE = 300

RANK_KEYS = {
    ord("a"): "A",
    ord("A"): "A",
    ord("2"): "2",
    ord("3"): "3",
    ord("4"): "4",
    ord("5"): "5",
    ord("6"): "6",
    ord("7"): "7",
    ord("8"): "8",
    ord("9"): "9",
    ord("t"): "T",
    ord("T"): "T",
    ord("0"): "T",
    ord("j"): "J",
    ord("J"): "J",
    ord("q"): "Q",
    ord("Q"): "Q",
    ord("k"): "K",
    ord("K"): "K",
}


def scale_image_for_display(img, min_size=MIN_DISPLAY_SIZE):
    h, w = img.shape[:2]
    if h >= min_size and w >= min_size:
        return img
    scale = max(min_size / h, min_size / w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)


def get_expected_label(img_path):
    """Extract expected label from filename if in labeled folder."""
    name = img_path.stem
    if len(name) >= 2 and name[0].upper() in RANK_ORDER:
        rank = name[0].upper()
        suit = name[1].lower() if name[1].lower() in "shdc" else None
        if suit:
            return f"{rank}{suit}"
    return None


def create_display(img, pred_card, confidence, expected, source_path, idx, total, stats):
    scaled = scale_image_for_display(img)
    h, w = scaled.shape[:2]

    canvas_h = h + 200
    canvas_w = max(w, 450)
    canvas = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 40

    x_offset = (canvas_w - w) // 2
    canvas[0:h, x_offset : x_offset + w] = scaled

    y = h + 30
    font = cv2.FONT_HERSHEY_SIMPLEX

    # Prediction
    if pred_card:
        color = (0, 255, 0) if confidence >= 0.85 else (0, 200, 255)
        cv2.putText(canvas, f"Prediction: {pred_card}", (10, y), font, 0.8, color, 2)
        cv2.putText(canvas, f"({confidence:.0%})", (200, y), font, 0.6, color, 1)
    else:
        cv2.putText(canvas, "Prediction: NONE", (10, y), font, 0.8, (0, 0, 255), 2)

    # Expected (if from labeled folder)
    y += 30
    if expected:
        match = expected.upper() == pred_card.upper() if pred_card else False
        color = (0, 255, 0) if match else (0, 0, 255)
        cv2.putText(canvas, f"Expected: {expected}", (10, y), font, 0.6, color, 1)

    # Progress and stats
    y += 30
    acc = stats["correct"] / max(stats["correct"] + stats["wrong"], 1) * 100
    cv2.putText(canvas, f"Image {idx}/{total}", (10, y), font, 0.5, (200, 200, 200), 1)
    y += 22
    cv2.putText(
        canvas,
        f"Correct: {stats['correct']} | Wrong: {stats['wrong']} | Acc: {acc:.0f}%",
        (10, y),
        font,
        0.5,
        (200, 200, 200),
        1,
    )

    # Source
    y += 25
    src = str(source_path.name)
    cv2.putText(canvas, f"File: {src}", (10, y), font, 0.4, (150, 150, 150), 1)

    # Instructions
    y += 30
    cv2.putText(
        canvas,
        "y/SPACE=correct | n=wrong | a,2-9,t,j,q,k=actual rank",
        (10, y),
        font,
        0.45,
        (180, 180, 180),
        1,
    )
    y += 20
    cv2.putText(canvas, "ESC=skip | q=quit", (10, y), font, 0.45, (180, 180, 180), 1)

    return canvas


def verify_cards(source_dir, shuffle=False):
    model = get_model()
    if model is None:
        print("No trained model found. Run: python scripts/train_classifier.py")
        return

    all_images = list(source_dir.glob("**/*.png"))
    if shuffle:
        random.shuffle(all_images)
    else:
        all_images.sort()

    total = len(all_images)
    print(f"Found {total} images in {source_dir}")

    stats = {"correct": 0, "wrong": 0, "skipped": 0}
    errors = []  # Track misclassifications

    cv2.namedWindow("Card Verifier", cv2.WINDOW_AUTOSIZE)

    idx = 0
    while idx < total:
        img_path = all_images[idx]
        idx += 1

        img = cv2.imread(str(img_path))
        if img is None:
            stats["skipped"] += 1
            continue

        if not is_card_present(img):
            stats["skipped"] += 1
            continue

        # Predict
        pred_rank, confidence = predict_rank(img, model)
        pred_suit = detect_suit_by_color(img)
        pred_card = f"{pred_rank}{pred_suit}" if pred_rank else None

        # Expected label (if from labeled folder)
        expected = get_expected_label(img_path)

        # Auto-verify if we have expected label
        if expected and pred_card:
            if expected[0].upper() == pred_card[0].upper():
                stats["correct"] += 1
                continue
            else:
                stats["wrong"] += 1
                errors.append((img_path.name, pred_card, expected))
                print(f"WRONG: {img_path.name} -> predicted {pred_card}, expected {expected}")
                continue

        # Manual verification
        display = create_display(img, pred_card, confidence, expected, img_path, idx, total, stats)
        cv2.imshow("Card Verifier", display)

        key = cv2.waitKey(0) & 0xFF

        if key == ord("q") or key == ord("Q"):
            break

        if key == 27:  # ESC
            stats["skipped"] += 1
            continue

        if key == ord("y") or key == ord("Y") or key == ord(" "):
            stats["correct"] += 1
            continue

        if key == ord("n") or key == ord("N"):
            stats["wrong"] += 1
            errors.append((img_path.name, pred_card, "?"))
            continue

        # User entered actual rank = wrong prediction
        if key in RANK_KEYS:
            actual_rank = RANK_KEYS[key]
            stats["wrong"] += 1
            errors.append((img_path.name, pred_card, f"{actual_rank}?"))

    cv2.destroyAllWindows()

    # Final report
    total_verified = stats["correct"] + stats["wrong"]
    if total_verified > 0:
        acc = stats["correct"] / total_verified * 100
        print("\n=== Verification Results ===")
        print(f"Correct: {stats['correct']}")
        print(f"Wrong:   {stats['wrong']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Accuracy: {acc:.1f}%")

        if errors:
            print(f"\n=== Misclassifications ({len(errors)}) ===")
            for name, pred, actual in errors[:20]:  # Show first 20
                print(f"  {name}: predicted {pred}, actual {actual}")
            if len(errors) > 20:
                print(f"  ... and {len(errors) - 20} more")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labeled", action="store_true", help="Verify on templates/labeled/ (auto-check)"
    )
    parser.add_argument("--shuffle", action="store_true", help="Random order")
    args = parser.parse_args()

    source_dir = LABELED_DIR if args.labeled else CARDS_DIR
    verify_cards(source_dir, shuffle=args.shuffle)


if __name__ == "__main__":
    main()
