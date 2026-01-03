"""
Dealer button detection using brightness analysis.

The dealer button is a white/cream chip with "D" on it.
Detection checks all 9 calibrated positions and returns which seat has the button.
"""

import cv2
import numpy as np
from PIL import Image

from src.calibration.calibration_manager import load_button_config
from src.engine.base import BaseDetector
from src.engine.results import SeatDetectionResult


class DealerButtonDetector(BaseDetector):
    """
    Dealer button detector using brightness analysis.

    Implements the standardized BaseDetector interface.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.4,
        min_white_ratio: float = 0.40,
        button_config: dict | None = None,
    ):
        """
        Initialize dealer button detector.

        Args:
            confidence_threshold: Minimum confidence for valid detection
            min_white_ratio: Minimum bright pixel ratio for button presence
            button_config: Pre-loaded button configuration (optional)
        """
        super().__init__(confidence_threshold)
        self.min_white_ratio = min_white_ratio
        self._button_config = button_config

    @property
    def button_config(self) -> dict:
        """Get button configuration, loading if needed."""
        if self._button_config is None:
            self._button_config = load_button_config()
        return self._button_config

    def is_button_present(self, img: np.ndarray) -> tuple[bool, float]:
        """
        Check if dealer button is present in a cropped region.

        Args:
            img: BGR image of button region (24x24 approx)

        Returns:
            (is_present, confidence_score)
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Count bright pixels (white button)
        bright_pixels = np.sum(gray > 180)
        white_ratio = bright_pixels / gray.size

        # Check for dark center (the "D" letter)
        h, w = gray.shape
        center = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
        has_dark_center = np.sum(center < 100) > (center.size * 0.05)

        is_present = white_ratio >= self.min_white_ratio and has_dark_center
        return is_present, white_ratio if is_present else 0.0

    def detect(
        self,
        img: Image.Image,
        button_config: dict | None = None,
        **kwargs,
    ) -> SeatDetectionResult:
        """
        Detect which seat has the dealer button.

        Args:
            img: PIL Image of full table
            button_config: Optional config override

        Returns:
            SeatDetectionResult with seat number (1-9) and confidence
        """
        config = button_config or self.button_config

        buttons = config["buttons"]
        btn_w, btn_h = config["button_size"]
        ref_w, ref_h = config["reference_size"]

        full_w, full_h = img.size
        scale = full_w / ref_w
        scaled_btn_w = int(btn_w * scale)
        scaled_btn_h = int(btn_h * scale)

        best_seat = None
        best_confidence = 0.0

        for btn_name, pos in buttons.items():
            # Skip btn_1 placeholder at (0, 0)
            if pos["x"] == 0 and pos["y"] == 0:
                continue

            seat_num = int(btn_name.split("_")[1])
            x = int(pos["x"] * full_w)
            y = int(pos["y"] * full_h)

            btn_crop = img.crop((x, y, x + scaled_btn_w, y + scaled_btn_h))
            btn_cv = cv2.cvtColor(np.array(btn_crop), cv2.COLOR_RGB2BGR)

            is_present, confidence = self.is_button_present(btn_cv)
            if is_present and confidence > best_confidence:
                best_seat = seat_num
                best_confidence = confidence

        if best_seat is not None and self.is_confident(best_confidence):
            return SeatDetectionResult.success(best_seat, best_confidence)

        return SeatDetectionResult.failure("No button detected")


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

# Module-level detector instance
_detector = DealerButtonDetector()


def is_button_present(img: np.ndarray, min_white_ratio: float = 0.40) -> tuple[bool, float]:
    """
    Check if dealer button is present in a cropped region.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: BGR image of button region (24x24 approx)
        min_white_ratio: Minimum ratio of bright pixels to consider button present

    Returns:
        (is_present, confidence_score)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Count bright pixels (white button)
    bright_pixels = np.sum(gray > 180)
    white_ratio = bright_pixels / gray.size

    # Check for dark center (the "D" letter)
    h, w = gray.shape
    center = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
    has_dark_center = np.sum(center < 100) > (center.size * 0.05)

    is_present = white_ratio >= min_white_ratio and has_dark_center
    return is_present, white_ratio if is_present else 0.0


def detect_dealer_button(img: Image.Image, button_config: dict | None = None) -> dict | None:
    """
    Detect which seat has the dealer button.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: PIL Image of full table
        button_config: Optional pre-loaded config (for performance)

    Returns:
        {'seat': int (1-9), 'confidence': float} or None if not found
    """
    result = _detector.detect(img, button_config=button_config)

    if result and result.confidence > 0.4:
        return {"seat": result.value, "confidence": result.confidence}
    return None
