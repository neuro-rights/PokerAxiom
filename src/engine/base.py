"""
Base protocols and classes for the poker bot engine.

Defines standard interfaces for Detectors and Learners.
"""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from .results import DetectionResult


class BaseDetector(ABC):
    """
    Abstract base class for detectors.

    Provides common preprocessing and result formatting.
    All detectors should inherit from this class.
    """

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize detector.

        Args:
            confidence_threshold: Minimum confidence for valid detection (0.0 to 1.0)
        """
        self._confidence_threshold = confidence_threshold

    @property
    def confidence_threshold(self) -> float:
        """Get the confidence threshold."""
        return self._confidence_threshold

    @confidence_threshold.setter
    def confidence_threshold(self, value: float):
        """Set the confidence threshold (clamped to 0.0-1.0)."""
        self._confidence_threshold = max(0.0, min(1.0, value))

    def is_confident(self, confidence: float) -> bool:
        """Check if confidence meets threshold."""
        return confidence >= self._confidence_threshold

    @abstractmethod
    def detect(self, img: np.ndarray, **kwargs) -> DetectionResult:
        """
        Detect/recognize content in an image.

        Args:
            img: Preprocessed image (numpy BGR or grayscale)
            **kwargs: Detector-specific options

        Returns:
            DetectionResult with value and confidence
        """
        ...


class BaseLearner(ABC):
    """
    Abstract base class for ML models.

    Provides common model lifecycle management.
    All trainable models should inherit from this class.
    """

    def __init__(self, model_path: str | None = None):
        """
        Initialize learner.

        Args:
            model_path: Path to saved model file (optional)
        """
        self._model = None
        self._model_path = model_path
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._is_loaded and self._model is not None

    @property
    def model_path(self) -> str | None:
        """Get the model path."""
        return self._model_path

    def ensure_loaded(self) -> bool:
        """
        Ensure model is loaded, loading from disk if needed.

        Returns:
            True if model is loaded successfully
        """
        if not self._is_loaded and self._model_path:
            return self.load(self._model_path)
        return self._is_loaded

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """
        Train the model on labeled data.

        Args:
            X: Feature matrix (samples x features)
            y: Label vector
        """
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> tuple[Any, float]:
        """
        Predict from input.

        Args:
            X: Feature vector or matrix

        Returns:
            (prediction, confidence) tuple
        """
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """
        Save model to disk.

        Args:
            path: File path to save model
        """
        ...

    @abstractmethod
    def load(self, path: str) -> bool:
        """
        Load model from disk.

        Args:
            path: File path to load model from

        Returns:
            True if load successful
        """
        ...
