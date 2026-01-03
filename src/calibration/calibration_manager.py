"""
Unified Calibration Manager - Single source of truth for all calibration data.

This module provides backwards-compatible functions that replace the scattered
load functions across card_extractor, button_detector, and card_back_detector.

All data is loaded from a single calibration.json file.
"""

import json
from functools import lru_cache
from pathlib import Path

from src.paths import CALIBRATION_FILE


class CalibrationError(Exception):
    """Raised when calibration data is missing or invalid."""

    pass


@lru_cache(maxsize=1)
def _load_calibration_data() -> dict:
    """Load and cache calibration data from unified config file."""
    if not CALIBRATION_FILE.exists():
        raise CalibrationError(
            f"Calibration file not found: {CALIBRATION_FILE}\n"
            "Run 'python scripts/calibrate.py' to calibrate regions."
        )

    with open(CALIBRATION_FILE) as f:
        data = json.load(f)

    # Validate required sections
    required = ["reference_size", "regions", "card_slots", "stacks", "bets", "buttons"]
    missing = [k for k in required if k not in data]
    if missing:
        raise CalibrationError(f"Calibration file missing sections: {missing}")

    return data


def reload_calibration():
    """Clear the cache and reload calibration data."""
    _load_calibration_data.cache_clear()


def _get_offset() -> tuple[float, float]:
    """Get the global offset from calibration data."""
    data = _load_calibration_data()
    offset = data.get("offset", {"x": 0.0, "y": 0.0})
    return offset.get("x", 0.0), offset.get("y", 0.0)


def _apply_offset_to_region(reg: dict, ox: float, oy: float) -> dict:
    """Apply offset to a region dict (x, y, w, h)."""
    return {
        "x": reg["x"] + ox,
        "y": reg["y"] + oy,
        "w": reg.get("w", 0),
        "h": reg.get("h", 0),
    }


def _apply_offset_to_pos(pos: dict, ox: float, oy: float) -> dict:
    """Apply offset to a position dict (x, y only)."""
    return {
        "x": pos["x"] + ox,
        "y": pos["y"] + oy,
    }


def load_config() -> tuple[dict, dict]:
    """
    Load regions and card slots config.

    Returns:
        (regions, slots_cfg) tuple matching card_extractor.load_config() format:
        - regions: {"hero_cards": {"x", "y", "w", "h"}, "board": {...}, "stack_1": {...}, ...}
        - slots_cfg: {"card_size": [w, h], "reference_size": [w, h],
                      "slots": {"hero_left": {"x", "y", "tilt"}, ...}}
    """
    data = _load_calibration_data()
    ox, oy = _get_offset()

    # Build regions dict (matches calibrated_regions.json format) with offset applied
    regions = {}
    for key, reg in data["regions"].items():
        regions[key] = _apply_offset_to_region(reg, ox, oy)

    # Add stack regions with w/h from unified size
    stack_size = data["stacks"]["size"]
    ref_w, ref_h = data["reference_size"]
    stack_w_norm = stack_size[0] / ref_w
    stack_h_norm = stack_size[1] / ref_h

    for key, pos in data["stacks"].items():
        if key == "size":
            continue
        regions[key] = {
            "x": pos["x"] + ox,
            "y": pos["y"] + oy,
            "w": stack_w_norm,
            "h": stack_h_norm,
        }

    # Add bet regions
    bet_size = data["bets"]["size"]
    bet_w_norm = bet_size[0] / ref_w
    bet_h_norm = bet_size[1] / ref_h

    for key, pos in data["bets"].items():
        if key == "size":
            continue
        regions[key] = {"x": pos["x"] + ox, "y": pos["y"] + oy, "w": bet_w_norm, "h": bet_h_norm}

    # Add card_back regions
    if "card_backs" in data:
        cb_size = data["card_backs"]["size"]
        for key, pos in data["card_backs"].items():
            if key == "size":
                continue
            regions[key] = {
                "x": pos["x"] + ox,
                "y": pos["y"] + oy,
                "w": cb_size[0],
                "h": cb_size[1],
            }

    # Build slots_cfg dict (matches card_slots.json format)
    # Note: card slots are relative to parent region, so they don't need offset
    card_slots = data["card_slots"]
    slots_cfg = {
        "card_size": card_slots["size"],
        "reference_size": data["reference_size"],
        "slots": {k: v for k, v in card_slots.items() if k != "size"},
    }

    return regions, slots_cfg


def load_button_config() -> dict:
    """
    Load button detection config.

    Returns:
        Dict matching button_detector.load_button_config() format:
        {"buttons": {"btn_1": {"x", "y"}, ...},
         "button_size": [w, h],
         "reference_size": [w, h]}
    """
    data = _load_calibration_data()
    ox, oy = _get_offset()

    # Apply offset to button positions
    buttons = {}
    for k, v in data["buttons"].items():
        if k == "size":
            continue
        buttons[k] = _apply_offset_to_pos(v, ox, oy)

    return {
        "buttons": buttons,
        "button_size": data["buttons"]["size"],
        "reference_size": data["reference_size"],
    }


def load_card_back_regions() -> dict:
    """
    Load card back regions for opponent detection.

    Returns:
        Dict matching card_back_detector.load_card_back_regions() format:
        {"card_back_2": {"x", "y", "w", "h"}, ...}
    """
    data = _load_calibration_data()
    ox, oy = _get_offset()

    if "card_backs" not in data:
        return {}

    cb_size = data["card_backs"]["size"]
    regions = {}

    for key, pos in data["card_backs"].items():
        if key == "size":
            continue
        regions[key] = {"x": pos["x"] + ox, "y": pos["y"] + oy, "w": cb_size[0], "h": cb_size[1]}

    return regions


def get_scaled_card_size(current_w: int, current_h: int) -> tuple[int, int]:
    """
    Get card size scaled for current window dimensions.

    Centralizes the scaling logic that was duplicated in card_extractor.py
    and strategy_overlay.py.

    Args:
        current_w: Current window width in pixels
        current_h: Current window height in pixels

    Returns:
        (width, height) of card in pixels for current window size
    """
    data = _load_calibration_data()

    card_w, card_h = data["card_slots"]["size"]
    ref_w, ref_h = data["reference_size"]

    scale = current_w / ref_w
    return int(card_w * scale), int(card_h * scale)


def get_reference_size() -> tuple[int, int]:
    """Get the reference window size used during calibration."""
    data = _load_calibration_data()
    return tuple(data["reference_size"])


def save_calibration(data: dict, path: Path = None):
    """
    Save calibration data to file.

    Args:
        data: Calibration data dict
        path: Optional path (defaults to CALIBRATION_FILE)
    """
    if path is None:
        path = CALIBRATION_FILE

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    # Clear cache so next load gets fresh data
    reload_calibration()
