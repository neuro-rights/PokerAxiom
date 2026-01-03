"""
Standardized result types for the poker bot engine.

All detectors return DetectionResult for consistent handling across the codebase.
"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import numpy as np

T = TypeVar("T")


@dataclass
class DetectionResult(Generic[T]):
    """
    Standardized detection result.

    All detectors return this type for consistent handling.

    Attributes:
        value: The detected value (type varies by detector)
        confidence: Detection confidence (0.0 to 1.0)
        is_valid: Whether detection succeeded
        raw_output: Optional raw model output for debugging
        metadata: Optional additional information
    """

    value: T | None
    confidence: float
    is_valid: bool = True
    raw_output: Any = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def success(cls, value: T, confidence: float, **metadata) -> "DetectionResult[T]":
        """Create a successful detection result."""
        return cls(value=value, confidence=confidence, is_valid=True, metadata=metadata)

    @classmethod
    def failure(cls, reason: str = "", confidence: float = 0.0) -> "DetectionResult[T]":
        """Create a failed detection result."""
        return cls(
            value=None,
            confidence=confidence,
            is_valid=False,
            metadata={"failure_reason": reason} if reason else {},
        )

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.is_valid and self.value is not None

    def to_legacy_dict(self, value_key: str = "value") -> dict | None:
        """
        Convert to legacy dict format for backward compatibility.

        Args:
            value_key: Key name for the value in the dict (e.g., "card", "seat")

        Returns:
            Dict with value_key and confidence, or None if not valid
        """
        if not self.is_valid or self.value is None:
            return None
        result = {value_key: self.value, "confidence": self.confidence}
        result.update(self.metadata)
        return result


@dataclass
class ExtractionResult:
    """
    Result of image extraction.

    Attributes:
        image: Extracted image (numpy BGR format)
        source_region: Original region config used
        pixel_coords: (x, y, w, h) in source image pixels
        scale_factor: Scale factor applied
        metadata: Additional extraction info
    """

    image: np.ndarray
    source_region: dict
    pixel_coords: tuple[int, int, int, int]
    scale_factor: float = 1.0
    metadata: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if extraction produced valid image."""
        return self.image is not None and self.image.size > 0


# Type aliases for common detection types
CardDetectionResult = DetectionResult[str]  # e.g., "As", "Kh"
ValueDetectionResult = DetectionResult[float]  # e.g., 3.97
BoolDetectionResult = DetectionResult[bool]  # e.g., is_present
SeatDetectionResult = DetectionResult[int]  # e.g., seat number
