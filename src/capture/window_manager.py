"""
Window Management Utility

Provides functions to resize and cascade poker table windows to a standard size.
This ensures consistent capture sizes for calibration and recognition.

Usage:
    from src.capture.window_manager import arrange_tables, STANDARD_SIZE

    # Resize and cascade all poker tables from top-left
    arranged = arrange_tables()
    print(f"Arranged {len(arranged)} tables")

    # Or with custom pattern/size/offset
    arranged = arrange_tables(pattern="*NLHA*", size=(1062, 769), offset_x=40, offset_y=40)
"""

import ctypes
import fnmatch
from ctypes import wintypes

user32 = ctypes.windll.user32

# Standard window size for all captures and calibration
STANDARD_SIZE = (1062, 769)

# Default pattern to match poker tables
DEFAULT_PATTERN = "*NLHA*"

# Cascade offset (how much each window is offset from the previous)
CASCADE_OFFSET_X = 30
CASCADE_OFFSET_Y = 30


def find_windows(
    pattern: str = DEFAULT_PATTERN, visible_only: bool = True
) -> list[tuple[int, str]]:
    """
    Find all windows matching title pattern.

    Args:
        pattern: Window title pattern with wildcards (e.g., "*NLHA*")
        visible_only: Only return visible windows

    Returns:
        List of (hwnd, title) tuples
    """
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    results = []

    def callback(hwnd, lparam):
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            if fnmatch.fnmatch(buff.value, pattern):
                results.append((hwnd, buff.value))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return results


def get_window_size(hwnd: int) -> tuple[int, int]:
    """Get window client area size (width, height)."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return (rect.right - rect.left, rect.bottom - rect.top)


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Get window rectangle (left, top, right, bottom)."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def resize_window(hwnd: int, width: int, height: int) -> bool:
    """
    Resize window to specified client area size.

    Args:
        hwnd: Window handle
        width: Desired client width
        height: Desired client height

    Returns:
        True if successful
    """
    # Get current window and client rects to calculate border size
    window_rect = wintypes.RECT()
    client_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))

    # Calculate border/frame sizes
    border_width = (window_rect.right - window_rect.left) - (client_rect.right - client_rect.left)
    border_height = (window_rect.bottom - window_rect.top) - (client_rect.bottom - client_rect.top)

    # Calculate full window size needed for desired client size
    full_width = width + border_width
    full_height = height + border_height

    # Resize window (keep current position)
    # SWP_NOMOVE = 0x0002, SWP_NOZORDER = 0x0004
    return bool(
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,  # Position ignored due to SWP_NOMOVE
            full_width,
            full_height,
            0x0002 | 0x0004,  # SWP_NOMOVE | SWP_NOZORDER
        )
    )


def move_window(hwnd: int, x: int, y: int) -> bool:
    """
    Move window to specified position.

    Args:
        hwnd: Window handle
        x: Screen X position
        y: Screen Y position

    Returns:
        True if successful
    """
    # SWP_NOSIZE = 0x0001, SWP_NOZORDER = 0x0004
    return bool(
        user32.SetWindowPos(
            hwnd,
            0,
            x,
            y,
            0,
            0,  # Size ignored due to SWP_NOSIZE
            0x0001 | 0x0004,  # SWP_NOSIZE | SWP_NOZORDER
        )
    )


def resize_and_move_window(
    hwnd: int, x: int, y: int, width: int, height: int, verify: bool = True
) -> bool:
    """
    Resize and move window in one operation.

    Args:
        hwnd: Window handle
        x, y: Screen position
        width, height: Desired client area size
        verify: If True, verify resize succeeded and warn if not

    Returns:
        True if successful (and verified if verify=True)
    """
    import time

    # Get border sizes
    window_rect = wintypes.RECT()
    client_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))

    border_width = (window_rect.right - window_rect.left) - (client_rect.right - client_rect.left)
    border_height = (window_rect.bottom - window_rect.top) - (client_rect.bottom - client_rect.top)

    full_width = width + border_width
    full_height = height + border_height

    # SWP_NOZORDER = 0x0004
    success = bool(
        user32.SetWindowPos(
            hwnd,
            0,
            x,
            y,
            full_width,
            full_height,
            0x0004,  # SWP_NOZORDER
        )
    )

    if not verify:
        return success

    # Verify the resize took effect
    time.sleep(0.1)  # Brief wait for window to settle
    actual = get_window_size(hwnd)
    if actual != (width, height):
        print(f"[!] Window resize mismatch: got {actual}, wanted ({width}, {height})")
        return False

    return True


def get_screen_size() -> tuple[int, int]:
    """Get primary screen resolution."""
    return (
        user32.GetSystemMetrics(0),  # SM_CXSCREEN
        user32.GetSystemMetrics(1),  # SM_CYSCREEN
    )


def arrange_tables(
    pattern: str = DEFAULT_PATTERN,
    size: tuple[int, int] = STANDARD_SIZE,
    start_x: int = 0,
    start_y: int = 0,
    offset_x: int = CASCADE_OFFSET_X,
    offset_y: int = CASCADE_OFFSET_Y,
) -> list[tuple[int, str, tuple[int, int]]]:
    """
    Find, resize, and cascade all matching poker table windows.

    Windows are cascaded from top-left, each offset slightly from the previous.

    Args:
        pattern: Window title pattern (default: "*NLHA*")
        size: Target client size as (width, height) (default: 1062x769)
        start_x: Starting X position (default: 0)
        start_y: Starting Y position (default: 0)
        offset_x: Horizontal cascade offset (default: 30)
        offset_y: Vertical cascade offset (default: 30)

    Returns:
        List of (hwnd, title, (x, y)) for each arranged window
    """
    windows = find_windows(pattern)
    if not windows:
        return []

    arranged = []
    x, y = start_x, start_y

    for hwnd, title in windows:
        # Resize and move
        resize_and_move_window(hwnd, x, y, size[0], size[1])
        arranged.append((hwnd, title, (x, y)))

        # Cascade: offset next window
        x += offset_x
        y += offset_y

    return arranged


def validate_window_size(hwnd: int, expected_size: tuple[int, int] = STANDARD_SIZE) -> bool:
    """
    Check if window matches expected size.

    Args:
        hwnd: Window handle
        expected_size: Expected (width, height)

    Returns:
        True if window matches expected size
    """
    actual = get_window_size(hwnd)
    return actual == expected_size


def get_mismatched_windows(
    pattern: str = DEFAULT_PATTERN, expected_size: tuple[int, int] = STANDARD_SIZE
) -> list[tuple[int, str, tuple[int, int]]]:
    """
    Find windows that don't match the expected size.

    Returns:
        List of (hwnd, title, actual_size) for mismatched windows
    """
    windows = find_windows(pattern)
    mismatched = []

    for hwnd, title in windows:
        actual = get_window_size(hwnd)
        if actual != expected_size:
            mismatched.append((hwnd, title, actual))

    return mismatched


def main():
    """Demo: arrange all poker tables."""
    print("Window Manager")
    print("=" * 50)
    print(f"Standard size: {STANDARD_SIZE[0]}x{STANDARD_SIZE[1]}")
    print(f"Cascade offset: {CASCADE_OFFSET_X}, {CASCADE_OFFSET_Y}")
    print(f"Looking for windows matching: {DEFAULT_PATTERN}")
    print()

    windows = find_windows()
    if not windows:
        print("No poker tables found!")
        return

    print(f"Found {len(windows)} table(s):")
    for hwnd, title in windows:
        size = get_window_size(hwnd)
        status = "OK" if size == STANDARD_SIZE else f"WRONG SIZE: {size[0]}x{size[1]}"
        print(f"  - {title[:40]}... [{status}]")

    print()
    response = input("Resize and cascade all tables? [y/N]: ").strip().lower()
    if response == "y":
        arranged = arrange_tables()
        print(f"\nArranged {len(arranged)} table(s):")
        for hwnd, title, (x, y) in arranged:
            size = get_window_size(hwnd)
            print(f"  - {title[:30]}... at ({x}, {y}) size {size[0]}x{size[1]}")
    else:
        print("Cancelled.")


if __name__ == "__main__":
    main()
