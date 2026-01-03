"""
Standard Window Capture Module

Captures visible windows using Windows GDI PrintWindow API.
Works with windows that allow standard screen capture.

Note: Some applications use SetWindowDisplayAffinity to prevent
screen capture. This module does not bypass such protection.

Usage:
    from src.capture.window_capture import WindowCapture

    capture = WindowCapture()

    # Capture by window title pattern
    img = capture.grab("*NLHA*")

    # Or capture specific region
    img = capture.grab("*NLHA*", region=(100, 100, 500, 400))

    # Returns PIL.Image ready for processing
"""

import ctypes
from ctypes import wintypes

from PIL import Image

# Windows API
user32 = ctypes.windll.user32


class WindowCapture:
    """
    Standard window capture using Windows GDI.

    Captures window content using the PrintWindow API, which works
    even when windows are partially obscured by other windows.
    """

    def __init__(self):
        pass

    def find_window(self, pattern: str) -> tuple[int, str] | None:
        """
        Find window by title pattern (supports * wildcards).

        Args:
            pattern: Window title pattern (e.g., "*NLHA*")

        Returns:
            Tuple of (hwnd, title) or None if not found
        """
        results = self.find_all_windows(pattern)
        return results[0] if results else None

    def find_all_windows(self, pattern: str, visible_only: bool = True) -> list[tuple[int, str]]:
        """
        Find all windows matching title pattern (supports * wildcards).

        Args:
            pattern: Window title pattern (e.g., "*NLHA*")
            visible_only: If True, only return visible (non-hidden) windows

        Returns:
            List of (hwnd, title) tuples for all matching windows
        """
        import fnmatch

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        results = []

        def callback(hwnd, lparam):
            # Skip non-visible windows if requested
            if visible_only and not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if fnmatch.fnmatch(buff.value, pattern):
                    results.append((hwnd, buff.value))
            return True  # Continue enumeration

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return results

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        """Get window rectangle (left, top, right, bottom)"""
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def get_window_pid(self, hwnd: int) -> int:
        """Get process ID for window"""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _capture_printwindow(self, hwnd: int) -> Image.Image | None:
        """Capture window client area using PrintWindow API.

        Works even when window is behind others. Captures client area directly
        to avoid black bars from bitmap/capture size mismatches.
        """
        gdi32 = ctypes.windll.gdi32

        # Get client rect - this is what we want to capture
        client_rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client_rect))
        client_width = client_rect.right - client_rect.left
        client_height = client_rect.bottom - client_rect.top

        if client_width == 0 or client_height == 0:
            return None

        # Create DC and bitmap at CLIENT size (not full window size)
        # This ensures no uninitialized black regions
        hwnd_dc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, client_width, client_height)
        gdi32.SelectObject(mem_dc, bitmap)

        # PrintWindow with PW_CLIENTONLY (1) - captures just the client area
        # This renders client area content directly to our client-sized bitmap
        PW_CLIENTONLY = 1
        result = user32.PrintWindow(hwnd, mem_dc, PW_CLIENTONLY)

        if not result:
            # Fallback: try without any flags
            user32.PrintWindow(hwnd, mem_dc, 0)

        # BITMAPINFOHEADER structure
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = client_width
        bmi.biHeight = -client_height  # Negative for top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buffer = ctypes.create_string_buffer(client_width * client_height * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, client_height, buffer, ctypes.byref(bmi), 0)

        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        # Convert to PIL Image - already client area size, no crop needed
        img = Image.frombuffer("RGBA", (client_width, client_height), buffer, "raw", "BGRA", 0, 1)
        img = img.convert("RGB")

        return img

    def grab(
        self, window: str | int, region: tuple[int, int, int, int] | None = None
    ) -> Image.Image | None:
        """
        Capture a window using PrintWindow API.
        Works even when window is behind others.

        Args:
            window: Window title pattern (str) or HWND (int)
            region: Optional (left, top, right, bottom) relative to window.
                   If None, captures entire window.

        Returns:
            PIL.Image or None if capture failed
        """
        # Find window
        if isinstance(window, str):
            result = self.find_window(window)
            if not result:
                return None
            hwnd, title = result
        else:
            hwnd = window

        # Capture using PrintWindow
        img = self._capture_printwindow(hwnd)

        if img is None:
            return None

        # Apply region crop if specified
        if region:
            img = img.crop(region)

        return img

    def grab_region(
        self, window: str | int, x: int, y: int, width: int, height: int
    ) -> Image.Image | None:
        """
        Capture a specific region of a window.

        Args:
            window: Window title pattern or HWND
            x, y: Top-left corner relative to window
            width, height: Size of region to capture

        Returns:
            PIL.Image or None
        """
        return self.grab(window, region=(x, y, x + width, y + height))


# Backwards compatibility alias
StealthCapture = WindowCapture


# Convenience function
def capture(
    window: str | int, region: tuple[int, int, int, int] | None = None
) -> Image.Image | None:
    """
    Quick capture function.

    Args:
        window: Window title pattern (e.g., "*NLHA*") or HWND
        region: Optional (left, top, right, bottom) relative to window

    Returns:
        PIL.Image ready for processing

    Example:
        from src.capture.window_capture import capture

        img = capture("*NLHA*")
        if img:
            img.save("screenshot.png")
    """
    cap = WindowCapture()
    return cap.grab(window, region)


def main():
    # Demo usage
    print("Window Capture Demo")
    print("=" * 40)

    cap = WindowCapture()

    # Find window
    result = cap.find_window("*NLHA*")
    if not result:
        print("Window not found!")
        return

    hwnd, title = result
    print(f"Found: {title}")
    print(f"HWND: {hwnd}")

    # Capture
    img = cap.grab(hwnd)
    if img:
        print(f"Captured: {img.size[0]}x{img.size[1]}")
        img.save("capture_demo.png")
        print("Saved: capture_demo.png")
    else:
        print("Capture failed!")


if __name__ == "__main__":
    main()
