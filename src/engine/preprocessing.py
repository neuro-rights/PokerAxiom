"""
Shared preprocessing utilities.

Consolidates image preprocessing logic and color definitions used across detectors.
"""

import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV BGR format."""
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def cv2_to_pil(img: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR to PIL Image."""
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def to_bgr(img: Image.Image | np.ndarray) -> np.ndarray:
    """
    Ensure image is in OpenCV BGR format.

    Args:
        img: PIL Image or numpy array

    Returns:
        BGR numpy array
    """
    if isinstance(img, Image.Image):
        return pil_to_cv2(img)
    if len(img.shape) == 2:  # Grayscale
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """
    Convert image to grayscale.

    Args:
        img: BGR or grayscale image

    Returns:
        Grayscale image
    """
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def normalize_size(
    img: np.ndarray,
    target_size: tuple[int, int],
    interpolation: int = cv2.INTER_AREA,
) -> np.ndarray:
    """
    Resize image to target size.

    Args:
        img: Input image
        target_size: (width, height) target
        interpolation: OpenCV interpolation method

    Returns:
        Resized image
    """
    return cv2.resize(img, target_size, interpolation=interpolation)


def rotate_image(
    img: np.ndarray,
    angle_deg: float,
    border_value: tuple = (255, 255, 255),
) -> np.ndarray:
    """
    Rotate image around center.

    Args:
        img: Input image
        angle_deg: Rotation angle in degrees
        border_value: Fill color for border

    Returns:
        Rotated image
    """
    if abs(angle_deg) < 0.5:
        return img

    h, w = img.shape[:2]
    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=border_value)


def extract_by_hsv_color(
    img: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    """
    Extract pixels within HSV color range.

    Args:
        img: BGR image
        lower: Lower HSV bound [H, S, V]
        upper: Upper HSV bound [H, S, V]

    Returns:
        Binary mask of matching pixels
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, lower, upper)


def mask_to_feature_vector(
    mask: np.ndarray,
    target_size: tuple[int, int] = (30, 15),
) -> np.ndarray:
    """
    Convert mask to normalized feature vector for ML.

    Args:
        mask: Binary mask
        target_size: (height, width) for feature

    Returns:
        Flattened normalized feature vector (1, N)
    """
    resized = cv2.resize(mask, (target_size[1], target_size[0]), interpolation=cv2.INTER_AREA)
    feat = resized.astype(np.float32) / 255.0
    return feat.reshape(1, -1)


# =============================================================================
# Centralized HSV color ranges
# =============================================================================

# HSV ranges for text colors (value reading)
HSV_RANGES = {
    # Stack text (cyan/green)
    "stack_text": {
        "lower": np.array([90, 80, 80]),
        "upper": np.array([115, 255, 255]),
    },
    # Bet text (white)
    "bet_text": {
        "lower": np.array([0, 0, 180]),
        "upper": np.array([180, 40, 255]),
    },
    # Pot text (yellow/gold)
    "pot_text": {
        "lower": np.array([15, 150, 150]),
        "upper": np.array([30, 255, 255]),
    },
    # Card suits (4-color deck)
    "suit_red": {
        "lower1": np.array([0, 100, 100]),
        "upper1": np.array([10, 255, 255]),
        "lower2": np.array([160, 100, 100]),
        "upper2": np.array([180, 255, 255]),
    },
    "suit_blue": {
        "lower": np.array([100, 100, 100]),
        "upper": np.array([130, 255, 255]),
    },
    "suit_green": {
        "lower": np.array([35, 100, 100]),
        "upper": np.array([85, 255, 255]),
    },
    # Card backs (opponent detection)
    "card_back_red": {
        "lower1": np.array([0, 30, 30]),
        "upper1": np.array([12, 200, 150]),
        "lower2": np.array([168, 30, 30]),
        "upper2": np.array([180, 200, 150]),
    },
    "card_back_blue": {
        "lower": np.array([100, 30, 30]),
        "upper": np.array([130, 200, 150]),
    },
}


def get_hsv_mask(img: np.ndarray, color_key: str) -> np.ndarray:
    """
    Get HSV mask for a predefined color range.

    Args:
        img: BGR image
        color_key: Key from HSV_RANGES (e.g., "stack_text", "suit_red")

    Returns:
        Binary mask
    """
    if color_key not in HSV_RANGES:
        raise ValueError(f"Unknown color key: {color_key}")

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    ranges = HSV_RANGES[color_key]

    # Handle dual-range colors (like red which wraps around 0)
    if "lower1" in ranges:
        mask1 = cv2.inRange(hsv, ranges["lower1"], ranges["upper1"])
        mask2 = cv2.inRange(hsv, ranges["lower2"], ranges["upper2"])
        return mask1 | mask2
    else:
        return cv2.inRange(hsv, ranges["lower"], ranges["upper"])
