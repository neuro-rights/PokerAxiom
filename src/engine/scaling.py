"""
Centralized scaling utilities.

Consolidates the duplicated scaling logic from:
- calibration_manager.get_scaled_card_size()
- card_extractor.get_scaled_card_size()
- strategy_overlay.get_scaled_card_size()
"""

from functools import lru_cache


@lru_cache(maxsize=1)
def get_reference_size() -> tuple[int, int]:
    """
    Get reference window size from calibration.

    Returns:
        (width, height) tuple of reference window size
    """
    from src.calibration.calibration_manager import get_reference_size as _get_ref

    return _get_ref()


def calculate_scale_factor(
    current_size: tuple[int, int],
    reference_size: tuple[int, int] | None = None,
) -> float:
    """
    Calculate scale factor between current and reference size.

    Args:
        current_size: (width, height) of current window
        reference_size: (width, height) reference. Uses calibration if None.

    Returns:
        Scale factor (current_width / reference_width)
    """
    if reference_size is None:
        reference_size = get_reference_size()
    ref_w, _ = reference_size
    current_w, _ = current_size
    if ref_w == 0:
        return 1.0
    return current_w / ref_w


def scale_size(
    base_size: tuple[int, int],
    current_window_size: tuple[int, int],
    reference_size: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """
    Scale a size for current window dimensions.

    Args:
        base_size: (width, height) at reference resolution
        current_window_size: Current (width, height)
        reference_size: Reference (width, height). Uses calibration if None.

    Returns:
        Scaled (width, height)
    """
    scale = calculate_scale_factor(current_window_size, reference_size)
    return (int(base_size[0] * scale), int(base_size[1] * scale))


def scale_coords(
    coords: dict,
    img_size: tuple[int, int],
    normalized: bool = True,
) -> tuple[int, int, int, int]:
    """
    Convert region coordinates to pixel values.

    Args:
        coords: Dict with 'x', 'y', 'w', 'h' keys
        img_size: (width, height) of image
        normalized: Whether coords are 0-1 normalized

    Returns:
        (x, y, width, height) in pixels
    """
    w, h = img_size
    if normalized:
        return (
            int(coords["x"] * w),
            int(coords["y"] * h),
            int(coords["w"] * w),
            int(coords["h"] * h),
        )
    return (
        int(coords["x"]),
        int(coords["y"]),
        int(coords["w"]),
        int(coords["h"]),
    )


def get_scaled_card_size(
    slots_cfg: dict,
    current_w: int,
    current_h: int,
) -> tuple[int, int]:
    """
    Get card size scaled for current window.

    BACKWARD COMPATIBLE: Matches signature of:
    - card_extractor.get_scaled_card_size()
    - strategy_overlay.get_scaled_card_size()

    Args:
        slots_cfg: Slots configuration dict with 'card_size' and 'reference_size'
        current_w: Current window width
        current_h: Current window height

    Returns:
        (width, height) of card in pixels for current window size
    """
    card_size = tuple(slots_cfg.get("card_size", (30, 64)))
    ref_size = slots_cfg.get("reference_size")
    return scale_size(card_size, (current_w, current_h), ref_size)


def clear_cache():
    """Clear the cached reference size."""
    get_reference_size.cache_clear()
