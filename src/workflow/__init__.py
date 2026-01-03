"""Unified training workflow package.

Provides consistent extract → label → train → verify pipeline for all data types.
"""

from .base import BaseWorkflow
from .cards import CardsWorkflow
from .digits import DigitsWorkflow

__all__ = ["BaseWorkflow", "CardsWorkflow", "DigitsWorkflow"]
