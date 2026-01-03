"""
Card back detection for opponent hand presence.

Detects if card backs are visible at each seat position to determine
which players are still in the hand (vs folded).

Card backs are typically red or blue with patterns, contrasting against
the green felt background.
"""

import cv2
import numpy as np
from PIL import Image

from src.calibration.calibration_manager import load_card_back_regions
from src.engine.base import BaseDetector
from src.engine.preprocessing import HSV_RANGES
from src.engine.results import BoolDetectionResult


class CardBackDetector(BaseDetector):
    """
    Card back detector for opponent hand presence.

    Implements the standardized BaseDetector interface.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.4,
        min_card_ratio: float = 0.40,
    ):
        """
        Initialize card back detector.

        Args:
            confidence_threshold: Minimum confidence for valid detection
            min_card_ratio: Minimum ratio of card-back colored pixels
        """
        super().__init__(confidence_threshold)
        self.min_card_ratio = min_card_ratio

    def detect(
        self,
        img: np.ndarray,
        min_card_ratio: float | None = None,
        **kwargs,
    ) -> BoolDetectionResult:
        """
        Check if card back is present in a cropped region.

        Args:
            img: BGR image of card back region
            min_card_ratio: Override for minimum card ratio

        Returns:
            BoolDetectionResult with is_present and confidence
        """
        ratio = min_card_ratio if min_card_ratio is not None else self.min_card_ratio

        # Convert to HSV for better color detection
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        total_pixels = img.shape[0] * img.shape[1]

        # Card backs are dark red/maroon
        red_ranges = HSV_RANGES["card_back_red"]
        red_mask = cv2.inRange(hsv, red_ranges["lower1"], red_ranges["upper1"]) | cv2.inRange(
            hsv, red_ranges["lower2"], red_ranges["upper2"]
        )
        red_ratio = np.sum(red_mask > 0) / total_pixels

        # Also check for blue card backs (some tables use blue)
        blue_ranges = HSV_RANGES["card_back_blue"]
        blue_mask = cv2.inRange(hsv, blue_ranges["lower"], blue_ranges["upper"])
        blue_ratio = np.sum(blue_mask > 0) / total_pixels

        card_ratio = red_ratio + blue_ratio

        # Card back is present if significant portion is card-back colored
        is_present = card_ratio >= ratio
        confidence = card_ratio if is_present else 0.0

        return BoolDetectionResult.success(is_present, confidence)


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

# Module-level detector instance
_detector = CardBackDetector()


def is_card_back_present(img: np.ndarray, min_card_ratio: float = 0.40) -> tuple[bool, float]:
    """
    Check if card back is present in a cropped region.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: BGR image of card back region
        min_card_ratio: Minimum ratio of card-back colored pixels

    Returns:
        (is_present, confidence_score)
    """
    result = _detector.detect(img, min_card_ratio=min_card_ratio)
    return (result.value or False, result.confidence)


def detect_card_backs(
    img: Image.Image, regions: dict | None = None
) -> dict[int, tuple[bool, float]]:
    """
    Detect card backs at all opponent seat positions.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: PIL Image of full table
        regions: Optional pre-loaded card back regions

    Returns:
        Dict mapping seat number (2-9) to (is_present, confidence)
    """
    if regions is None:
        regions = load_card_back_regions()

    if not regions:
        # No card back regions calibrated yet
        return {}

    full_w, full_h = img.size
    results = {}

    for region_name, reg in regions.items():
        # Extract seat number from region name (card_back_2 -> 2)
        seat_num = int(region_name.split("_")[-1])

        # Calculate pixel coordinates
        x = int(reg["x"] * full_w)
        y = int(reg["y"] * full_h)
        w = int(reg["w"] * full_w)
        h = int(reg["h"] * full_h)

        # Crop and convert
        crop = img.crop((x, y, x + w, y + h))
        crop_cv = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR)

        # Detect
        is_present, confidence = is_card_back_present(crop_cv)
        results[seat_num] = (is_present, confidence)

    return results


def get_active_seats(img: Image.Image, regions: dict | None = None) -> dict[int, bool]:
    """
    Get which seats have active players (card backs visible).

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: PIL Image of full table
        regions: Optional pre-loaded card back regions

    Returns:
        Dict mapping seat number (2-9) to is_active boolean
    """
    detections = detect_card_backs(img, regions)
    return {seat: is_present for seat, (is_present, _) in detections.items()}
