"""
Card detection using a trained rank classifier + 4-color deck.

4-color deck mapping:
- Black = Spades (s)
- Red = Hearts (h)
- Blue = Diamonds (d)
- Green = Clubs (c)
"""

import cv2
import numpy as np
from PIL import Image

from src.engine.base import BaseDetector
from src.engine.preprocessing import HSV_RANGES, rotate_image
from src.engine.results import CardDetectionResult

# Reference card size the classifier was trained on
REFERENCE_CARD_SIZE = (30, 64)  # width, height


def detect_suit_by_color(img: np.ndarray) -> str:
    """
    Detect suit from 4-color deck using dominant color.

    Args:
        img: BGR image (cv2 format)

    Returns:
        's' (spades/black), 'h' (hearts/red), 'd' (diamonds/blue), 'c' (clubs/green)
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Red (hearts) - wraps around 0
    red_ranges = HSV_RANGES["suit_red"]
    red_mask = cv2.inRange(hsv, red_ranges["lower1"], red_ranges["upper1"]) | cv2.inRange(
        hsv, red_ranges["lower2"], red_ranges["upper2"]
    )

    # Blue (diamonds)
    blue_ranges = HSV_RANGES["suit_blue"]
    blue_mask = cv2.inRange(hsv, blue_ranges["lower"], blue_ranges["upper"])

    # Green (clubs)
    green_ranges = HSV_RANGES["suit_green"]
    green_mask = cv2.inRange(hsv, green_ranges["lower"], green_ranges["upper"])

    # Count pixels for each color
    red_count = cv2.countNonZero(red_mask)
    blue_count = cv2.countNonZero(blue_mask)
    green_count = cv2.countNonZero(green_mask)

    # Black detection - low saturation and low value, but not white
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    black_mask = gray < 80
    # Exclude white background
    white_mask = gray > 200
    black_count = np.sum(black_mask & ~white_mask)

    # Find dominant color
    counts = {
        "h": red_count,  # hearts = red
        "d": blue_count,  # diamonds = blue
        "c": green_count,  # clubs = green
        "s": black_count,  # spades = black
    }

    return max(counts, key=counts.get)


def isolate_suit_color(img: np.ndarray, suit: str) -> np.ndarray:
    """
    Isolate pixels matching the suit color for OCR.
    4-color deck: ranks are same color as suit.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    if suit == "h":  # Red hearts
        mask1 = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([160, 80, 80]), np.array([180, 255, 255]))
        mask = mask1 | mask2
    elif suit == "d":  # Blue diamonds
        mask = cv2.inRange(hsv, np.array([100, 80, 80]), np.array([130, 255, 255]))
    elif suit == "c":  # Green clubs
        mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
    else:  # Black spades
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = (gray < 100).astype(np.uint8) * 255

    return mask


def de_tilt(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate image to correct for tilt."""
    return rotate_image(img, angle_deg, border_value=(255, 255, 255))


def is_card_present(img: np.ndarray, min_white_ratio: float = 0.35) -> bool:
    """
    Heuristic to detect if a card is present in the crop based on white area.
    Returns False when the crop is mostly table/felt/background.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white_ratio = np.mean(gray > 200)
    return white_ratio >= min_white_ratio


class CardDetector(BaseDetector):
    """
    Card detector using trained MLP rank classifier and color-based suit detection.

    Implements the standardized BaseDetector interface.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        min_white_ratio: float = 0.35,
        reference_size: tuple[int, int] = REFERENCE_CARD_SIZE,
    ):
        """
        Initialize card detector.

        Args:
            confidence_threshold: Minimum confidence for valid detection
            min_white_ratio: Minimum white pixel ratio for card presence check
            reference_size: Reference card size (width, height) for normalization
        """
        super().__init__(confidence_threshold)
        self.min_white_ratio = min_white_ratio
        self.reference_size = reference_size

    def detect(
        self,
        img: np.ndarray | Image.Image | str,
        tilt: float = 0,
        allow_presence_check: bool = True,
        **kwargs,
    ) -> CardDetectionResult:
        """
        Detect a card from an image.

        Args:
            img: Card image (PIL, numpy BGR, or file path)
            tilt: Rotation angle in degrees to correct for
            allow_presence_check: Whether to check for card presence first

        Returns:
            CardDetectionResult with card string (e.g., "As") and confidence
        """
        # Convert to cv2 BGR format
        if isinstance(img, str):
            img_cv = cv2.imread(img)
        elif isinstance(img, Image.Image):
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        else:
            img_cv = img

        if img_cv is None or img_cv.size == 0:
            return CardDetectionResult.failure("Invalid image")

        # De-tilt if needed
        if tilt != 0:
            img_cv = de_tilt(img_cv, tilt)

        # Check if card is present
        if allow_presence_check and not is_card_present(img_cv, self.min_white_ratio):
            return CardDetectionResult.failure("No card present", confidence=0.0)

        # Normalize to reference size for consistent classifier input
        h, w = img_cv.shape[:2]
        ref_w, ref_h = self.reference_size
        if w != ref_w or h != ref_h:
            img_cv = cv2.resize(img_cv, (ref_w, ref_h), interpolation=cv2.INTER_AREA)

        # Lazy import to avoid circular dependency
        from src.ml.rank_classifier import predict_rank

        rank, score = predict_rank(img_cv)
        if rank:
            suit = detect_suit_by_color(img_cv)
            card = f"{rank}{suit}"
            return CardDetectionResult.success(card, float(score))

        return CardDetectionResult.failure("Rank detection failed")


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

# Module-level detector instance for backward compatibility
_detector = CardDetector()


def detect_card(
    img_or_path,
    tilt: float = 0,
    allow_presence_check: bool = True,
    min_white_ratio: float = 0.35,
) -> dict | None:
    """
    Detect a card using the trained rank classifier.

    BACKWARD COMPATIBLE: This function preserves the original API.

    Args:
        img_or_path: PIL Image, numpy array, or file path
        tilt: rotation angle in degrees to correct for
        allow_presence_check: whether to check for card presence
        min_white_ratio: minimum white ratio for presence check

    Returns:
        dict with 'card' (e.g., 'As', 'Kh') and 'confidence', or None
    """
    # Use the detector with possibly different min_white_ratio
    if min_white_ratio != _detector.min_white_ratio:
        detector = CardDetector(min_white_ratio=min_white_ratio)
    else:
        detector = _detector

    result = detector.detect(img_or_path, tilt=tilt, allow_presence_check=allow_presence_check)

    if result:
        return {"card": result.value, "confidence": result.confidence}
    return None


def detect_cards_in_region(img, slots_config):
    """
    Detect multiple cards in a region using slot configuration.

    Args:
        img: PIL Image of the region
        slots_config: dict of slot configs with 'corners' and 'output_size'

    Returns:
        list of detected cards
    """
    from test_yolo_cards import crop_perspective

    cards = []
    for slot_name, slot_data in slots_config.items():
        corners = slot_data["corners"]
        output_size = slot_data["output_size"]

        # Scale up for better OCR
        scaled_output = [output_size[0] * 3, output_size[1] * 3]
        card_img = crop_perspective(img, corners, scaled_output)

        detection = detect_card(card_img)
        if detection:
            cards.append(detection["card"])

    return cards


def main():
    import sys

    if len(sys.argv) > 1:
        result = detect_card(sys.argv[1])
        print(f"Detected: {result}")
    else:
        # Test on debug images
        for f in ["debug_hero_left.png", "debug_hero_right.png"]:
            result = detect_card(f)
            print(f"{f}: {result}")


if __name__ == "__main__":
    main()
