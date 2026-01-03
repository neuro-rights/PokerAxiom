"""
Value recognition using character template matching.

Reads dollar amounts from poker table regions (stacks, bets, pot)
by isolating text pixels and matching against character templates.
"""

import cv2
import numpy as np

from src.engine.base import BaseDetector
from src.engine.preprocessing import HSV_RANGES
from src.engine.results import ValueDetectionResult
from src.ml.digit_classifier import get_model as get_digit_model
from src.ml.digit_classifier import predict_digit
from src.paths import MODELS_DIR

# Character templates directories
TEMPLATES_DIR_STACK = MODELS_DIR / "char_templates"  # Cyan stack text
TEMPLATES_DIR_WHITE = MODELS_DIR / "char_templates_white"  # White/yellow bet/pot text

# Valid characters in dollar amounts
VALID_CHARS = set("$0123456789.")

# Map text types to HSV range keys
TEXT_TYPE_TO_HSV_KEY = {
    "stack": "stack_text",
    "bet": "bet_text",
    "pot": "pot_text",
}

# Map text types to template directories
TEMPLATE_DIRS = {
    "stack": TEMPLATES_DIR_STACK,
    "bet": TEMPLATES_DIR_WHITE,
    "pot": TEMPLATES_DIR_WHITE,
}

# Cached templates per text type
_TEMPLATES_CACHE: dict[str, dict[str, list[np.ndarray]]] = {}


def load_templates(text_type: str = "stack") -> dict[str, list[np.ndarray]]:
    """Load character templates from disk (multiple per character)."""
    global _TEMPLATES_CACHE

    if text_type in _TEMPLATES_CACHE:
        return _TEMPLATES_CACHE[text_type]

    templates_dir = TEMPLATE_DIRS.get(text_type, TEMPLATES_DIR_STACK)

    if not templates_dir.exists():
        return {}

    templates = {}
    for f in templates_dir.glob("*.png"):
        # Handle names like "6.png", "6_alt.png", "dollar.png", "dollar_alt.png"
        name = f.stem.split("_")[0]  # Get base name without _alt suffix
        template = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if template is not None:
            if name not in templates:
                templates[name] = []
            templates[name].append(template)

    _TEMPLATES_CACHE[text_type] = templates
    return templates


def char_name_to_char(name: str) -> str:
    """Convert template filename to actual character."""
    if name == "dollar":
        return "$"
    elif name == "dot":
        return "."
    else:
        return name  # "0"-"9" stay as is


def isolate_text(img: np.ndarray, text_type: str = "stack") -> np.ndarray:
    """
    Isolate text pixels by color.

    Args:
        img: BGR image
        text_type: "stack" (cyan), "bet" (white), or "pot" (yellow)

    Returns:
        Binary mask of text pixels
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    hsv_key = TEXT_TYPE_TO_HSV_KEY.get(text_type, "stack_text")
    color_range = HSV_RANGES[hsv_key]
    mask = cv2.inRange(hsv, color_range["lower"], color_range["upper"])

    return mask


def find_characters(
    mask: np.ndarray, min_area: int = 1
) -> list[tuple[int, int, int, int, np.ndarray]]:
    """
    Find character bounding boxes in binary mask.

    Handles merged characters by splitting wide blobs.

    Args:
        mask: Binary mask from isolate_text()
        min_area: Minimum contour area (filters noise)

    Returns:
        List of (x, y, w, h, crop) sorted left-to-right
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    chars = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Use bounding box area (not cv2.contourArea) to preserve tiny dots
        area = w * h
        if area < min_area:
            continue
        crop = mask[y : y + h, x : x + w]

        # Check if this might be merged characters (width > 15 and area > 100)
        # Typical digit: w=9-11, h=15-17, area=40-80
        if w > 15 and area > 100:
            # Try to split into multiple characters
            # Estimate number of chars based on width
            n_chars = round(w / 10)  # ~10px per character
            if n_chars >= 2:
                char_w = w // n_chars
                for i in range(n_chars):
                    cx = i * char_w
                    char_crop = crop[:, cx : cx + char_w]
                    chars.append((x + cx, y, char_w, h, char_crop))
                continue

        chars.append((x, y, w, h, crop))

    # Sort by x position (left to right)
    chars.sort(key=lambda c: c[0])

    return chars


def classify_confusable_digit(crop: np.ndarray) -> str:
    """
    Classify confusable digits (0, 3, 6, 9) using MLP classifier.

    Uses a trained neural network for robust classification that handles
    anti-aliasing, compression artifacts, and rendering variations.

    Args:
        crop: Binary character image

    Returns:
        Predicted digit ('0', '3', '6', or '9'), or '0' as fallback
    """
    # Get the MLP model
    model = get_digit_model()
    if model is None:
        return "0"  # Fallback if no trained model

    # Predict using MLP - always trust the prediction
    predicted, confidence = predict_digit(crop, model)

    if predicted is None:
        return "0"

    return predicted


def match_character(crop: np.ndarray, templates: dict[str, list[np.ndarray]]) -> tuple[str, float]:
    """
    Match a character crop against templates.

    Uses aspect ratio filtering, pixel density, and normalized pixel comparison.
    Supports multiple template variants per character.

    Args:
        crop: Binary character image
        templates: Dict of template_name -> list of template_images

    Returns:
        (character, confidence) tuple
    """
    if not templates:
        return ("?", 0.0)

    crop_h, crop_w = crop.shape
    crop_area = crop_h * crop_w

    # Small, roughly square shapes are likely decimal points
    # Dots are typically 2-6px in each dimension
    if crop_area < 50 and crop_h > 0 and 0.5 <= (crop_w / crop_h) <= 2.0:
        fill_ratio = np.sum(crop > 0) / crop_area
        if fill_ratio > 0.3:
            return (".", 0.9)

    crop_aspect = crop_w / crop_h if crop_h > 0 else 0
    crop_density = np.sum(crop > 0) / (crop_w * crop_h) if crop_w * crop_h > 0 else 0

    # Larger standard size for better discrimination
    STD_SIZE = (20, 30)  # width, height

    # Resize crop to standard size
    crop_std = cv2.resize(crop, STD_SIZE, interpolation=cv2.INTER_AREA)
    crop_norm = crop_std.astype(np.float32) / 255.0

    best_char = "?"
    best_score = -1.0

    for name, template_list in templates.items():
        for template in template_list:
            tmpl_h, tmpl_w = template.shape
            tmpl_aspect = tmpl_w / tmpl_h if tmpl_h > 0 else 0
            tmpl_density = np.sum(template > 0) / (tmpl_w * tmpl_h) if tmpl_w * tmpl_h > 0 else 0

            # Aspect ratio filter
            aspect_diff = abs(crop_aspect - tmpl_aspect)
            if aspect_diff > 0.5:
                continue

            # Pixel density penalty (helps distinguish 0 vs 9, etc.)
            density_diff = abs(crop_density - tmpl_density)
            density_penalty = density_diff * 0.3  # Slight penalty for density mismatch

            # Resize template to standard size
            tmpl_std = cv2.resize(template, STD_SIZE, interpolation=cv2.INTER_AREA)
            tmpl_norm = tmpl_std.astype(np.float32) / 255.0

            # Normalized correlation
            corr = np.sum(crop_norm * tmpl_norm) / (
                np.sqrt(np.sum(crop_norm**2)) * np.sqrt(np.sum(tmpl_norm**2)) + 1e-6
            )

            # Combined score
            score = corr - density_penalty

            if score > best_score:
                best_score = score
                best_char = char_name_to_char(name)

    # Use MLP classifier directly for confusable digits (0, 3, 6, 9)
    # MLP is more robust than template matching for these
    if best_char in ("0", "3", "6", "9"):
        best_char = classify_confusable_digit(crop)

    return (best_char, best_score)


class ValueDetector(BaseDetector):
    """
    Value detector for dollar amounts using template matching.

    Implements the standardized BaseDetector interface.
    """

    def __init__(
        self,
        text_type: str = "stack",
        confidence_threshold: float = 0.5,
    ):
        """
        Initialize value detector.

        Args:
            text_type: "stack", "bet", or "pot"
            confidence_threshold: Minimum match confidence
        """
        super().__init__(confidence_threshold)
        self.text_type = text_type
        self._templates = None

    @property
    def templates(self) -> dict[str, list[np.ndarray]]:
        """Get templates, loading if needed."""
        if self._templates is None:
            self._templates = load_templates(self.text_type)
        return self._templates

    def detect(
        self,
        img: np.ndarray,
        text_type: str | None = None,
        **kwargs,
    ) -> ValueDetectionResult:
        """
        Read a dollar value from an image region.

        Args:
            img: BGR image of the value region
            text_type: Override for text type

        Returns:
            ValueDetectionResult with float value and confidence
        """
        effective_type = text_type or self.text_type
        templates = load_templates(effective_type) if text_type else self.templates

        if not templates:
            return ValueDetectionResult.failure("No templates loaded")

        # Isolate text pixels
        mask = isolate_text(img, effective_type)

        # Find characters
        chars = find_characters(mask)
        if not chars:
            return ValueDetectionResult.failure("No characters found")

        # Match each character
        result_chars = []
        found_dollar = False
        min_confidence = float("inf")

        for x, y, w, h, crop in chars:
            char, confidence = match_character(crop, templates)
            if confidence >= self.confidence_threshold and char in VALID_CHARS:
                # Skip chars before $ (handles ": $0.17" pot format)
                if char == "$":
                    found_dollar = True
                if found_dollar:
                    result_chars.append(char)
                    min_confidence = min(min_confidence, confidence)

        # Assemble string
        text = "".join(result_chars)

        # Parse to float
        try:
            # Remove $ if present
            text = text.replace("$", "")
            if text:
                value = float(text)
                # Use minimum character confidence as overall confidence
                conf = min_confidence if min_confidence != float("inf") else 0.9
                return ValueDetectionResult.success(value, conf)
        except ValueError:
            pass

        return ValueDetectionResult.failure("Could not parse value")


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================


def read_value(
    img: np.ndarray, text_type: str = "stack", min_confidence: float = 0.5
) -> float | None:
    """
    Read a dollar value from an image region.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: BGR image of the value region
        text_type: "stack", "bet", or "pot"
        min_confidence: Minimum match confidence (0-1)

    Returns:
        Float value (e.g., 3.97) or None if not readable
    """
    detector = ValueDetector(text_type, min_confidence)
    result = detector.detect(img)
    return result.value if result else None


def read_all_values(img: np.ndarray, regions: dict, img_size: tuple[int, int]) -> dict:
    """
    Read all stacks, bets, and pot from a full table image.

    BACKWARD COMPATIBLE: Preserves original API.

    Args:
        img: Full table BGR image
        regions: Calibrated regions config
        img_size: (width, height) of image

    Returns:
        {
            'stacks': {1: 3.97, 2: 1.50, ...},
            'bets': {1: None, 2: 0.02, ...},
            'pot': 0.15
        }
    """
    w, h = img_size
    result = {"stacks": {}, "bets": {}, "pot": None}

    # Read stacks
    for i in range(1, 10):
        key = f"stack_{i}"
        if key in regions:
            r = regions[key]
            x1, y1 = int(r["x"] * w), int(r["y"] * h)
            x2, y2 = int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)
            crop = img[y1:y2, x1:x2]
            result["stacks"][i] = read_value(crop, "stack")

    # Read bets
    for i in range(1, 10):
        key = f"bet_{i}"
        if key in regions:
            r = regions[key]
            x1, y1 = int(r["x"] * w), int(r["y"] * h)
            x2, y2 = int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)
            crop = img[y1:y2, x1:x2]
            result["bets"][i] = read_value(crop, "bet")

    # Read pot
    if "pot" in regions:
        r = regions["pot"]
        x1, y1 = int(r["x"] * w), int(r["y"] * h)
        x2, y2 = int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)
        crop = img[y1:y2, x1:x2]
        result["pot"] = read_value(crop, "pot")

    return result
