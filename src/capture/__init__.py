"""
Capture module - screen capture and overlay functionality.

Sets DPI awareness early to ensure consistent window sizing across all capture tools.
"""

import ctypes

# Set DPI awareness BEFORE any windowing code runs
# This must be called once per process, as early as possible
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
    except Exception:
        pass
