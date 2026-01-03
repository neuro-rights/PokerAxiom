"""
Unified Engine - Standardized detection and learning infrastructure.

This module provides common base classes, result types, and utilities
for all detectors and ML models in the poker bot.
"""

from .base import BaseDetector, BaseLearner
from .preprocessing import (
    HSV_RANGES,
    cv2_to_pil,
    extract_by_hsv_color,
    get_hsv_mask,
    mask_to_feature_vector,
    normalize_size,
    pil_to_cv2,
    rotate_image,
    to_bgr,
    to_grayscale,
)
from .results import (
    BoolDetectionResult,
    CardDetectionResult,
    DetectionResult,
    ExtractionResult,
    SeatDetectionResult,
    ValueDetectionResult,
)
from .scaling import (
    calculate_scale_factor,
    clear_cache,
    get_reference_size,
    get_scaled_card_size,
    scale_coords,
    scale_size,
)

__all__ = [
    # Base classes
    "BaseDetector",
    "BaseLearner",
    # Result types
    "DetectionResult",
    "ExtractionResult",
    "CardDetectionResult",
    "ValueDetectionResult",
    "BoolDetectionResult",
    "SeatDetectionResult",
    # Scaling
    "get_reference_size",
    "calculate_scale_factor",
    "scale_size",
    "scale_coords",
    "get_scaled_card_size",
    "clear_cache",
    # Preprocessing
    "pil_to_cv2",
    "cv2_to_pil",
    "to_bgr",
    "to_grayscale",
    "normalize_size",
    "rotate_image",
    "extract_by_hsv_color",
    "get_hsv_mask",
    "mask_to_feature_vector",
    "HSV_RANGES",
]
