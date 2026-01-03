"""
Player name identification using perceptual hashing.

Instead of OCR, we hash the visual pattern of name regions to get
a consistent unique identifier for each player. This is more reliable
than character recognition and requires no training.

Uses edge detection (Canny) which is invariant to brightness changes,
handling both active (white) and inactive (grey) player name colors.
"""

import hashlib

import cv2
import numpy as np


def get_name_hash(img: np.ndarray, hash_size: tuple[int, int] = (32, 8)) -> str:
    """
    Get a perceptual hash of a name region.

    The hash is consistent across frames for the same player name,
    allowing us to track players without OCR. Uses edge detection
    which is invariant to brightness changes (active vs inactive).

    Args:
        img: BGR image of the name region
        hash_size: Size to normalize to before hashing (width, height)

    Returns:
        12-character hex hash string (unique per name)
    """
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur to reduce noise
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Edge detection - invariant to brightness, captures shape only
    edges = cv2.Canny(gray, 30, 100)

    # Dilate edges to make them thicker and more connected
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    # Check if region has any edges (text)
    if np.sum(edges > 0) < 30:
        return ""

    # Resize to standard size
    std = cv2.resize(edges, hash_size, interpolation=cv2.INTER_AREA)

    # Clean threshold
    _, std = cv2.threshold(std, 50, 255, cv2.THRESH_BINARY)

    # Hash the binary pattern
    return hashlib.md5(std.tobytes()).hexdigest()[:12]


def get_all_name_hashes(
    img: np.ndarray, regions: dict, img_size: tuple[int, int]
) -> dict[int, str]:
    """
    Get name hashes for all player seats.

    Args:
        img: Full table BGR image
        regions: Calibrated regions config (must have 'names' section)
        img_size: (width, height) of image

    Returns:
        {seat_num: hash_string} for seats 2-9 (empty string if no name)
    """
    w, h = img_size
    result = {}

    if "names" not in regions:
        return result

    names_config = regions["names"]
    size = names_config.get("size", [100, 20])

    # Reference size for scaling
    ref_w, ref_h = 1062, 769

    for i in range(2, 10):  # Seats 2-9 (hero is seat 1)
        key = f"name_{i}"
        if key in names_config:
            r = names_config[key]
            x1 = int(r["x"] * w)
            y1 = int(r["y"] * h)
            x2 = x1 + int(size[0] * w / ref_w)
            y2 = y1 + int(size[1] * h / ref_h)
            crop = img[y1:y2, x1:x2]
            result[i] = get_name_hash(crop)

    return result
