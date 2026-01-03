"""
Manual card labeling tool with OpenCV UI.

Usage:
    python scripts/label_cards.py

Keyboard controls:
    A, 2-9, T, J, Q, K  - Set rank
    s, h, d, c          - Set/override suit
    SPACE               - Accept auto-prediction
    ENTER               - Confirm and save
    ESC                 - Skip image
    x                   - Mark as no-card/invalid
    q                   - Quit
"""

import shutil

import cv2
import numpy as np

from src.detection.card_detector import detect_suit_by_color, is_card_present
from src.ml.rank_classifier import get_model, predict_rank
from src.paths import CARDS_DIR, LABELED_DIR

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

SUIT_KEYS = {
    ord("s"): "s",
    ord("S"): "s",
    ord("h"): "h",
    ord("H"): "h",
    ord("d"): "d",
    ord("D"): "d",
    ord("c"): "c",
    ord("C"): "c",
}

CONFIDENCE_THRESHOLD = 0.85
MIN_DISPLAY_SIZE = 300


def get_existing_labels():
    """Scan labeled folder and return dict of card_code -> count."""
    existing = {}
    if not LABELED_DIR.exists():
        return existing

    for f in LABELED_DIR.glob("*.png"):
        # Parse filename like "Ac_001.png" or "2h_002.png"
        name = f.stem
        if "_" in name:
            card_code = name.split("_")[0]
        else:
            card_code = name

        if len(card_code) == 2:
            existing[card_code] = existing.get(card_code, 0) + 1

    return existing


def get_next_filename(card_code, existing):
    """Generate next available filename like Ac_003.png."""
    count = existing.get(card_code, 0) + 1
    return f"{card_code}_{count:03d}.png"


def scale_image_for_display(img, min_size=MIN_DISPLAY_SIZE):
    """Scale small card crops to be visible in OpenCV window."""
    h, w = img.shape[:2]
    if h >= min_size and w >= min_size:
        return img

    scale = max(min_size / h, min_size / w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)


def create_display_image(card_img, rank, suit, confidence, source_path, idx, total, stats):
    """Create a display image with card and info overlay."""
    # Scale card image
    scaled = scale_image_for_display(card_img)
    h, w = scaled.shape[:2]

    # Create larger canvas for text
    canvas_h = h + 180
    canvas_w = max(w, 400)
    canvas = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 40  # Dark gray background

    # Place card image centered
    x_offset = (canvas_w - w) // 2
    canvas[0:h, x_offset : x_offset + w] = scaled

    # Add text info below image
    y = h + 30
    font = cv2.FONT_HERSHEY_SIMPLEX

    # Prediction
    if rank:
        pred_text = f"Predicted: {rank}{suit} (conf: {confidence:.2f})"
        color = (0, 255, 0) if confidence >= CONFIDENCE_THRESHOLD else (0, 200, 255)
    else:
        pred_text = "Predicted: ? (no model)"
        color = (0, 0, 255)
    cv2.putText(canvas, pred_text, (10, y), font, 0.6, color, 1)

    # Progress
    y += 25
    progress_text = (
        f"Image {idx}/{total} | Labeled: {stats['labeled']} | Skipped: {stats['skipped']}"
    )
    cv2.putText(canvas, progress_text, (10, y), font, 0.5, (200, 200, 200), 1)

    # Source path (truncated)
    y += 25
    src_text = str(source_path.relative_to(CARDS_DIR))
    if len(src_text) > 50:
        src_text = "..." + src_text[-47:]
    cv2.putText(canvas, f"Source: {src_text}", (10, y), font, 0.4, (150, 150, 150), 1)

    # Instructions
    y += 30
    cv2.putText(
        canvas, "Keys: A,2-9,T,J,Q,K=rank | s,h,d,c=suit", (10, y), font, 0.45, (180, 180, 180), 1
    )
    y += 20
    cv2.putText(
        canvas,
        "SPACE=accept | ENTER=save | ESC=skip | x=no-card | q=quit",
        (10, y),
        font,
        0.45,
        (180, 180, 180),
        1,
    )

    # Current selection
    y += 30
    if rank and suit:
        sel_text = f"Current: {rank}{suit}"
        cv2.putText(canvas, sel_text, (10, y), font, 0.7, (255, 255, 0), 2)

    return canvas


def label_cards():
    """Main labeling loop."""
    # Ensure labeled directory exists
    LABELED_DIR.mkdir(parents=True, exist_ok=True)

    # Get existing labels
    existing = get_existing_labels()
    print(f"Found {sum(existing.values())} existing labeled images")

    # Load model
    model = get_model()
    if model is None:
        print("Warning: No trained model found. Predictions unavailable.")

    # Collect all card images
    all_images = sorted(CARDS_DIR.glob("**/*.png"))
    total = len(all_images)
    print(f"Found {total} images to process")

    # Stats
    stats = {"labeled": 0, "skipped": 0, "no_card": 0}

    cv2.namedWindow("Card Labeler", cv2.WINDOW_AUTOSIZE)

    idx = 0
    while idx < total:
        img_path = all_images[idx]
        idx += 1

        # Load image
        img = cv2.imread(str(img_path))
        if img is None:
            stats["skipped"] += 1
            continue

        # Check if card is present
        if not is_card_present(img):
            stats["no_card"] += 1
            stats["skipped"] += 1
            continue

        # Predict rank and detect suit
        pred_rank, confidence = predict_rank(img, model) if model else (None, 0)
        pred_suit = detect_suit_by_color(img)

        # Auto-skip if high confidence and already have this card
        if pred_rank and confidence >= CONFIDENCE_THRESHOLD:
            card_code = f"{pred_rank}{pred_suit}"
            if card_code in existing:
                stats["skipped"] += 1
                continue

        # Current selection
        current_rank = pred_rank
        current_suit = pred_suit

        # Display loop for this image
        while True:
            display = create_display_image(
                img, current_rank, current_suit, confidence, img_path, idx, total, stats
            )
            cv2.imshow("Card Labeler", display)

            key = cv2.waitKey(0) & 0xFF

            # Quit
            if key == ord("q") or key == ord("Q"):
                print(f"\nQuitting. Stats: {stats}")
                cv2.destroyAllWindows()
                return

            # Skip
            if key == 27:  # ESC
                stats["skipped"] += 1
                break

            # Mark as no-card
            if key == ord("x") or key == ord("X"):
                stats["no_card"] += 1
                stats["skipped"] += 1
                break

            # Accept prediction with SPACE
            if key == ord(" "):
                if pred_rank and pred_suit:
                    current_rank = pred_rank
                    current_suit = pred_suit

            # Set rank
            if key in RANK_KEYS:
                current_rank = RANK_KEYS[key]

            # Set suit
            if key in SUIT_KEYS:
                current_suit = SUIT_KEYS[key]

            # Confirm and save with ENTER
            if key == 13:  # ENTER
                if current_rank and current_suit:
                    card_code = f"{current_rank}{current_suit}"
                    filename = get_next_filename(card_code, existing)
                    dest_path = LABELED_DIR / filename

                    shutil.copy2(img_path, dest_path)

                    existing[card_code] = existing.get(card_code, 0) + 1
                    stats["labeled"] += 1
                    print(f"Saved: {filename}")
                    break

    cv2.destroyAllWindows()
    print(f"\nDone! Stats: {stats}")
    print(f"Labeled images saved to: {LABELED_DIR}")


def main():
    label_cards()


if __name__ == "__main__":
    main()
