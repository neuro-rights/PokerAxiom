"""
Strategy Overlay - Live decision support overlay for poker tables.

Extends the debug overlay with strategy recommendations based on
the 2NL 9-max TAG strategy engine.

Usage:
    python scripts/run_strategy.py

Edit Mode:
    Press Shift+E to toggle edit mode.
    In edit mode, drag panels to reposition them.
    Use mouse wheel to scale the overlay.
    Changes are saved automatically when exiting edit mode.
"""

import ctypes
import ctypes.wintypes
import json
import threading
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np

# Import capture module early to set DPI awareness before tkinter
import src.capture  # noqa: F401 - sets DPI awareness
from src.capture.window_capture import WindowCapture
from src.capture.window_manager import arrange_tables
from src.data.card_extractor import load_config
from src.detection.button_detector import detect_dealer_button, load_button_config
from src.detection.card_back_detector import get_active_seats, load_card_back_regions
from src.detection.card_detector import detect_card
from src.engine.scaling import get_scaled_card_size
from src.recognition.name_hasher import get_all_name_hashes
from src.recognition.value_reader import read_value
from src.strategy.game_state import GameState, Street
from src.strategy.hand_evaluator import count_outs, equity_estimate, get_category_color
from src.strategy.positions import get_position_color
from src.strategy.session_tracker import SessionTracker
from src.strategy.strategy_engine import StrategyEngine

user32 = ctypes.windll.user32

# Windows constants
GWL_EXSTYLE = -20
GWL_HWNDPARENT = -8
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20

# Hotkey constants
MOD_SHIFT = 0x0004
VK_S = 0x53
VK_E = 0x45
WM_HOTKEY = 0x0312
HOTKEY_ID_DEBUG = 1
HOTKEY_ID_EDIT = 2

# Overlay settings file
OVERLAY_SETTINGS_FILE = Path(__file__).parent.parent.parent / "config" / "overlay_settings.json"

# Default overlay settings
# Per-seat elements (stacks_2, bets_3, opp_stats_4, etc.) default to offset (0, 0)
DEFAULT_OVERLAY_SETTINGS = {
    "scale": 1.0,
    "panels": {
        "strategy": {"x": 0.02, "y": 0.06},
        "position_badge": {"x": 0.02, "y": 0.02},
        "street_badge": {"offset_x": 60},
        "hand_info": {"offset_x": 140},
        "pot": {"offset_x": 0, "offset_y": 0},
        "hero_cards": {"offset_x": 0, "offset_y": 0},
        "board_cards": {"offset_x": 0, "offset_y": 0},
        "dealer": {"offset_x": 0, "offset_y": 0},
    },
}


def load_overlay_settings():
    """Load overlay settings from config file."""
    try:
        with open(OVERLAY_SETTINGS_FILE) as f:
            settings = json.load(f)
        # Merge with defaults for any missing keys
        merged = DEFAULT_OVERLAY_SETTINGS.copy()
        merged["scale"] = settings.get("scale", DEFAULT_OVERLAY_SETTINGS["scale"])
        merged["panels"] = DEFAULT_OVERLAY_SETTINGS["panels"].copy()
        for panel_name, panel_cfg in settings.get("panels", {}).items():
            if panel_name in merged["panels"]:
                merged["panels"][panel_name].update(panel_cfg)
            else:
                merged["panels"][panel_name] = panel_cfg
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_OVERLAY_SETTINGS.copy()


def save_overlay_settings(settings):
    """Save overlay settings to config file."""
    OVERLAY_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERLAY_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_foreground_window():
    """Get the handle of the foreground window."""
    return user32.GetForegroundWindow()


# Transparent color key
TRANSPARENT_COLOR = "#010101"

# Suit colors for card display
SUIT_COLORS = {
    "s": "#cccccc",  # Spades - silver
    "h": "#ff6666",  # Hearts - red
    "d": "#6699ff",  # Diamonds - blue
    "c": "#66cc66",  # Clubs - green
}

# Street colors
STREET_COLORS = {
    Street.PREFLOP: "#cccc55",  # Yellow
    Street.FLOP: "#cc8855",  # Orange
    Street.TURN: "#cc6688",  # Pink
    Street.RIVER: "#cc5555",  # Red
}

# Player type colors for HUD
PLAYER_TYPE_COLORS = {
    "fish": "#ff6666",  # Red - loose passive
    "nit": "#6699ff",  # Blue - tight passive
    "TAG": "#66cc66",  # Green - tight aggressive
    "LAG": "#ff9933",  # Orange - loose aggressive
    "maniac": "#ff33ff",  # Magenta - very aggressive
    "unknown": "#888888",  # Gray - not enough data
}


def get_window_rect(hwnd):
    """Get window position and size."""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def get_client_rect_screen(hwnd):
    """Get client area position and size in screen coordinates.

    Returns (x, y, width, height) of the client area in screen coords.
    This is what the capture returns - use for overlay positioning.
    """
    # Get window position
    win_rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(win_rect))

    # Get client area offset (where client area starts in screen coords)
    point = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(point))

    # Get client size
    client_rect = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))

    return (
        point.x,
        point.y,
        client_rect.right - client_rect.left,
        client_rect.bottom - client_rect.top,
    )


def get_client_offset(hwnd):
    """Get offset from window top-left to client area top-left (border sizes)."""
    win_rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(win_rect))
    point = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(point))
    return point.x - win_rect.left, point.y - win_rect.top


class CanvasOverlay:
    """Transparent canvas overlay positioned over a window."""

    def __init__(self, master, table_hwnd, settings=None):
        self.table_hwnd = table_hwnd
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.configure_bg = TRANSPARENT_COLOR
        self.win.configure(bg=TRANSPARENT_COLOR)

        self.canvas = tk.Canvas(self.win, bg=TRANSPARENT_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Label storage: name -> (rect_id, text_id)
        self.labels = {}

        # Edit mode state
        self.edit_mode = False
        self.settings = settings or load_overlay_settings()
        self._on_settings_changed = None  # Callback for settings changes

        # Drag state
        self._drag_item = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_panel_name = None

        # Draggable panel tracking: name -> (panel items tuple, normalized x, normalized y)
        self.draggable_panels = {}

        # Scale indicator (shown in edit mode)
        self._scale_text_id = None

        # Setup window after it's created
        self.win.update_idletasks()
        self._setup_window()

        # Bind mouse events for dragging (only active in edit mode)
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        # Bind mouse wheel to window level (more reliable on Windows)
        self.win.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

    def _setup_window(self):
        """Setup window: make click-through and set owner relationship."""
        try:
            frame_id = self.win.wm_frame()
            self.overlay_hwnd = int(frame_id, 16)

            user32.SetWindowLongPtrW(self.overlay_hwnd, GWL_HWNDPARENT, self.table_hwnd)

            style = user32.GetWindowLongPtrW(self.overlay_hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(
                self.overlay_hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception as e:
            print(f"Window setup failed: {e}")
            self.overlay_hwnd = None

    def set_edit_mode(self, enabled):
        """Toggle edit mode - when enabled, panels can be dragged and scaled."""
        if self.edit_mode == enabled:
            return

        self.edit_mode = enabled

        if not self.overlay_hwnd:
            return

        style = user32.GetWindowLongPtrW(self.overlay_hwnd, GWL_EXSTYLE)

        if enabled:
            # Remove click-through so we can interact with the overlay
            style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(self.overlay_hwnd, GWL_EXSTYLE, style)

            # Bring overlay to top and give it focus
            self.win.attributes("-topmost", True)
            self.win.lift()
            self.win.focus_force()

            # Create edit mode placeholder panels if none exist
            self._create_edit_placeholders()

            print(f"[Edit] Draggable panels: {list(self.draggable_panels.keys())}")
            self._show_edit_indicator()
        else:
            # Restore click-through
            style |= WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(self.overlay_hwnd, GWL_EXSTYLE, style)

            # Reset topmost (parent window will manage z-order)
            self.win.attributes("-topmost", False)

            # Remove edit placeholders
            self._remove_edit_placeholders()

            self._hide_edit_indicator()
            # Save settings when exiting edit mode
            if self._on_settings_changed:
                self._on_settings_changed(self.settings)

    def _create_edit_placeholders(self):
        """Create visible placeholder panels for editing when no game state exists."""
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w <= 0 or canvas_h <= 0:
            return

        if not hasattr(self, "_edit_placeholders"):
            self._edit_placeholders = {}

        # Create strategy panel placeholder if not already registered
        if "strategy" not in self.draggable_panels:
            norm_x, norm_y = self.get_panel_position("strategy")
            x, y = int(norm_x * canvas_w), int(norm_y * canvas_h)

            bg = self.canvas.create_rectangle(
                x, y, x + 250, y + 100, fill="#1a1a1a", outline="#444444", width=2
            )
            text1 = self.canvas.create_text(
                x + 10,
                y + 10,
                text="STRATEGY PANEL",
                fill="#ffcc00",
                font=("Consolas", 14, "bold"),
                anchor="nw",
            )
            text2 = self.canvas.create_text(
                x + 10,
                y + 40,
                text="(Drag to move)",
                fill="#888888",
                font=("Consolas", 10),
                anchor="nw",
            )
            self._edit_placeholders["strategy"] = (bg, text1, text2)
            self.register_draggable("strategy", (bg, text1, text2), norm_x, norm_y)

        # Create position badges placeholder if not already registered
        if "position_badge" not in self.draggable_panels:
            norm_x, norm_y = self.get_panel_position("position_badge")
            x, y = int(norm_x * canvas_w), int(norm_y * canvas_h)

            bg = self.canvas.create_rectangle(
                x, y, x + 200, y + 25, fill="#1a1a1a", outline="#444444", width=1
            )
            text = self.canvas.create_text(
                x + 5,
                y + 5,
                text="BTN  FLOP  AKs (Premium)",
                fill="#aaaaaa",
                font=("Consolas", 11, "bold"),
                anchor="nw",
            )
            self._edit_placeholders["position_badge"] = (bg, text)
            self.register_draggable("position_badge", (bg, text), norm_x, norm_y)

        # Note: Offset-based elements (stacks, bets, etc.) are registered as draggable
        # in their respective update methods when they become visible during gameplay

    def _remove_edit_placeholders(self):
        """Remove edit mode placeholder panels."""
        if not hasattr(self, "_edit_placeholders"):
            return

        for name, items in self._edit_placeholders.items():
            for item in items:
                self.canvas.delete(item)
            # Remove from draggable panels
            if name in self.draggable_panels:
                del self.draggable_panels[name]

        self._edit_placeholders = {}

    def _show_edit_indicator(self):
        """Show edit mode indicator and scale info."""
        # Create edit mode background bar if needed
        if not hasattr(self, "_edit_bar_id") or self._edit_bar_id is None:
            self._edit_bar_id = self.canvas.create_rectangle(
                0,
                0,
                800,
                30,
                fill="#004400",
                outline="#00ff00",
                width=2,
            )
        if self._scale_text_id is None:
            self._scale_text_id = self.canvas.create_text(
                10,
                8,
                text="",
                fill="#00ff00",
                font=("Consolas", 11, "bold"),
                anchor="nw",
            )
        scale = self.settings.get("scale", 1.0)
        self.canvas.itemconfig(
            self._scale_text_id,
            text=f"EDIT MODE (Scale: {scale:.0%}) - Drag panels | Scroll to scale | Shift+E to exit",
            state="normal",
        )
        self.canvas.itemconfig(self._edit_bar_id, state="normal")
        self.canvas.tag_raise(self._edit_bar_id)
        self.canvas.tag_raise(self._scale_text_id)

        # Highlight draggable panels with visible borders
        self._show_drag_handles()

    def _show_drag_handles(self):
        """Show visible drag handles around draggable panels."""
        if not hasattr(self, "_drag_handles"):
            self._drag_handles = []

        # Clear old handles
        for handle in self._drag_handles:
            self.canvas.delete(handle)
        self._drag_handles = []

        # Create handles for each draggable panel
        for panel_name, panel_info in self.draggable_panels.items():
            panel_items = panel_info[0]
            if not panel_items:
                continue

            # Get bounding box of all panel items
            min_x, min_y, max_x, max_y = None, None, None, None
            for item in panel_items:
                bbox = self.canvas.bbox(item)
                if bbox:
                    if min_x is None:
                        min_x, min_y, max_x, max_y = bbox
                    else:
                        min_x = min(min_x, bbox[0])
                        min_y = min(min_y, bbox[1])
                        max_x = max(max_x, bbox[2])
                        max_y = max(max_y, bbox[3])

            if min_x is not None:
                # Draw highlight border
                handle = self.canvas.create_rectangle(
                    min_x - 3,
                    min_y - 3,
                    max_x + 3,
                    max_y + 3,
                    outline="#ffff00",
                    width=2,
                    dash=(4, 2),
                )
                self._drag_handles.append(handle)

    def _hide_edit_indicator(self):
        """Hide edit mode indicator."""
        if self._scale_text_id:
            self.canvas.itemconfig(self._scale_text_id, state="hidden")
        if hasattr(self, "_edit_bar_id") and self._edit_bar_id:
            self.canvas.itemconfig(self._edit_bar_id, state="hidden")

        # Remove drag handles
        if hasattr(self, "_drag_handles"):
            for handle in self._drag_handles:
                self.canvas.delete(handle)
            self._drag_handles = []

    def _find_panel_at(self, x, y):
        """Find which draggable panel is at the given coordinates."""
        # Check each draggable panel's bounding box
        for panel_name, panel_info in self.draggable_panels.items():
            panel_items = panel_info[0]
            if not panel_items:
                continue

            # Get bounding box of all panel items
            min_x, min_y, max_x, max_y = None, None, None, None
            for item in panel_items:
                bbox = self.canvas.bbox(item)
                if bbox:
                    if min_x is None:
                        min_x, min_y, max_x, max_y = bbox
                    else:
                        min_x = min(min_x, bbox[0])
                        min_y = min(min_y, bbox[1])
                        max_x = max(max_x, bbox[2])
                        max_y = max(max_y, bbox[3])

            # Check if click is within bounding box (with padding)
            if min_x is not None:
                padding = 10
                if (
                    min_x - padding <= x <= max_x + padding
                    and min_y - padding <= y <= max_y + padding
                ):
                    return panel_name

        return None

    def _on_mouse_down(self, event):
        """Handle mouse button down - start dragging if in edit mode."""
        if not self.edit_mode:
            return

        panel_name = self._find_panel_at(event.x, event.y)
        if panel_name:
            self._drag_panel_name = panel_name
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self.canvas.config(cursor="fleur")  # Move cursor
            print(f"[Edit] Started dragging: {panel_name}")

    def _on_mouse_drag(self, event):
        """Handle mouse drag - move panel if dragging."""
        if not self.edit_mode or not self._drag_panel_name:
            return

        # Calculate movement
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y

        # Move all items in the panel
        panel_info = self.draggable_panels.get(self._drag_panel_name)
        if panel_info:
            panel_items = panel_info[0]
            for item in panel_items:
                self.canvas.move(item, dx, dy)

        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_mouse_up(self, event):
        """Handle mouse button up - finish dragging and save position."""
        if not self.edit_mode or not self._drag_panel_name:
            self.canvas.config(cursor="")
            return

        dropped_name = self._drag_panel_name

        # Get the new position from the panel's first item
        panel_info = self.draggable_panels.get(self._drag_panel_name)
        if panel_info:
            panel_items = panel_info[0]
            if panel_items:
                # Get first item's position (usually the background rect)
                coords = self.canvas.coords(panel_items[0])
                if coords:
                    # Convert to normalized coordinates
                    canvas_w = self.canvas.winfo_width()
                    canvas_h = self.canvas.winfo_height()
                    if canvas_w > 0 and canvas_h > 0:
                        norm_x = coords[0] / canvas_w
                        norm_y = coords[1] / canvas_h

                        # Check if this is an offset-based element
                        is_offset_element = (
                            hasattr(self, "_offset_elements")
                            and self._drag_panel_name in self._offset_elements
                        )

                        if "panels" not in self.settings:
                            self.settings["panels"] = {}

                        if is_offset_element:
                            # Save as offset from base position (per-seat)
                            base_x, base_y = self._offset_elements[self._drag_panel_name]
                            offset_x = norm_x - base_x
                            offset_y = norm_y - base_y
                            # Save with full element name (e.g., "stacks_2") for per-seat positioning
                            self.set_element_offset(self._drag_panel_name, offset_x, offset_y)
                            print(
                                f"[Edit] Dropped {self._drag_panel_name} offset ({offset_x:.2%}, {offset_y:.2%})"
                            )
                        else:
                            # Save as absolute position
                            if self._drag_panel_name not in self.settings["panels"]:
                                self.settings["panels"][self._drag_panel_name] = {}
                            self.settings["panels"][self._drag_panel_name]["x"] = norm_x
                            self.settings["panels"][self._drag_panel_name]["y"] = norm_y
                            print(f"[Edit] Dropped {dropped_name} at ({norm_x:.2%}, {norm_y:.2%})")

                        # Update draggable panel info
                        self.draggable_panels[self._drag_panel_name] = (panel_items, norm_x, norm_y)

        self._drag_panel_name = None
        self.canvas.config(cursor="")

        # Refresh drag handles to show new position
        if self.edit_mode:
            self._show_drag_handles()

    def _on_mouse_wheel(self, event):
        """Handle mouse wheel - adjust scale in edit mode."""
        if not self.edit_mode:
            return

        # Adjust scale
        current_scale = self.settings.get("scale", 1.0)
        if event.delta > 0:
            new_scale = min(2.0, current_scale + 0.05)
        else:
            new_scale = max(0.5, current_scale - 0.05)

        self.settings["scale"] = new_scale
        print(f"[Edit] Scale: {new_scale:.0%}")
        self._show_edit_indicator()  # Update the displayed scale

    def get_scale(self):
        """Get current scale factor."""
        return self.settings.get("scale", 1.0)

    def get_panel_position(self, panel_name):
        """Get normalized position for a panel from settings."""
        panels = self.settings.get("panels", {})
        panel_cfg = panels.get(panel_name, {})
        default_panels = DEFAULT_OVERLAY_SETTINGS.get("panels", {})
        default_cfg = default_panels.get(panel_name, {})
        return (
            panel_cfg.get("x", default_cfg.get("x", 0.02)),
            panel_cfg.get("y", default_cfg.get("y", 0.02)),
        )

    def get_panel_offset(self, panel_name):
        """Get pixel offset for secondary panels (relative to position badge)."""
        panels = self.settings.get("panels", {})
        panel_cfg = panels.get(panel_name, {})
        default_panels = DEFAULT_OVERLAY_SETTINGS.get("panels", {})
        default_cfg = default_panels.get(panel_name, {})
        return panel_cfg.get("offset_x", default_cfg.get("offset_x", 0))

    def get_element_offset(self, element_name):
        """Get normalized x,y offset for an element type (stacks, bets, etc)."""
        panels = self.settings.get("panels", {})
        panel_cfg = panels.get(element_name, {})
        default_panels = DEFAULT_OVERLAY_SETTINGS.get("panels", {})
        default_cfg = default_panels.get(element_name, {})
        return (
            panel_cfg.get("offset_x", default_cfg.get("offset_x", 0)),
            panel_cfg.get("offset_y", default_cfg.get("offset_y", 0)),
        )

    def set_element_offset(self, element_name, offset_x, offset_y):
        """Set normalized offset for an element type."""
        if "panels" not in self.settings:
            self.settings["panels"] = {}
        if element_name not in self.settings["panels"]:
            self.settings["panels"][element_name] = {}
        self.settings["panels"][element_name]["offset_x"] = offset_x
        self.settings["panels"][element_name]["offset_y"] = offset_y

    def register_draggable(self, name, items, norm_x, norm_y):
        """Register a panel as draggable."""
        self.draggable_panels[name] = (items, norm_x, norm_y)

    def reposition(self):
        """Reposition overlay to match table window client area."""
        if not user32.IsWindow(self.table_hwnd):
            return False

        # Use client area dimensions to match captured image coordinates
        x, y, w, h = get_client_rect_screen(self.table_hwnd)
        self.canvas.config(width=w, height=h)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        return True

    def _get_scaled_font(self, base_size, bold=False):
        """Get font tuple with scaling applied."""
        scale = self.get_scale()
        scaled_size = max(8, int(base_size * scale))
        weight = "bold" if bold else "normal"
        return ("Consolas", scaled_size, weight)

    def create_label(self, name):
        """Create a label (background rect + text) on the canvas."""
        rect = self.canvas.create_rectangle(
            0, 0, 1, 1, fill="#1a1a1a", outline="#333333", state="hidden"
        )
        text = self.canvas.create_text(
            0,
            0,
            text="--",
            fill="#ffffff",
            font=self._get_scaled_font(11, bold=True),
            anchor="nw",
            state="hidden",
        )
        self.labels[name] = (rect, text)

    def update_label(self, name, x, y, text, color="#ffffff", visible=True):
        """Update a label's position, text, and visibility."""
        if name not in self.labels:
            return

        rect_id, text_id = self.labels[name]

        if not visible or not text:
            self.canvas.itemconfig(rect_id, state="hidden")
            self.canvas.itemconfig(text_id, state="hidden")
            return

        # Apply scaling to font
        self.canvas.itemconfig(
            text_id,
            text=text,
            fill=color,
            font=self._get_scaled_font(11, bold=True),
            state="normal",
        )
        self.canvas.coords(text_id, x + 5, y + 3)

        bbox = self.canvas.bbox(text_id)
        if bbox:
            self.canvas.coords(rect_id, bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2)
            self.canvas.itemconfig(rect_id, state="normal")

    def hide_label(self, name):
        """Hide a specific label."""
        if name in self.labels:
            items = self.labels[name]
            for item_id in items:
                self.canvas.itemconfig(item_id, state="hidden")

    def create_indicator(self, name, size=8):
        """Create a small circular indicator dot."""
        dot = self.canvas.create_oval(
            0, 0, size, size, fill="#888888", outline="#444444", width=1, state="hidden"
        )
        self.labels[name] = (dot,)

    def update_indicator(self, name, x, y, color, visible=True, size=8):
        """Update indicator position and color."""
        if name not in self.labels:
            return

        dot_id = self.labels[name][0]

        if not visible:
            self.canvas.itemconfig(dot_id, state="hidden")
            return

        self.canvas.coords(dot_id, x, y, x + size, y + size)
        self.canvas.itemconfig(dot_id, fill=color, state="normal")

    def create_strategy_panel(self, name):
        """Create a larger strategy panel with multiple text elements."""
        # Background panel
        panel_bg = self.canvas.create_rectangle(
            0, 0, 1, 1, fill="#1a1a1a", outline="#444444", width=2, state="hidden"
        )
        # Action text (large)
        action_text = self.canvas.create_text(
            0,
            0,
            text="--",
            fill="#ffffff",
            font=self._get_scaled_font(14, bold=True),
            anchor="nw",
            state="hidden",
        )
        # Info text (smaller)
        info_text = self.canvas.create_text(
            0,
            0,
            text="",
            fill="#aaaaaa",
            font=self._get_scaled_font(9),
            anchor="nw",
            state="hidden",
        )
        self.labels[name] = (panel_bg, action_text, info_text)

    def update_strategy_panel(self, name, x, y, action_str, action_color, info_lines, visible=True):
        """Update the strategy panel with action and info."""
        if name not in self.labels:
            return

        panel_bg, action_text, info_text = self.labels[name]

        if not visible:
            self.canvas.itemconfig(panel_bg, state="hidden")
            self.canvas.itemconfig(action_text, state="hidden")
            self.canvas.itemconfig(info_text, state="hidden")
            return

        scale = self.get_scale()
        padding = int(10 * scale)
        spacing = int(22 * scale)

        # Update action text with scaled font
        self.canvas.itemconfig(
            action_text,
            text=action_str,
            fill=action_color,
            font=self._get_scaled_font(14, bold=True),
            state="normal",
        )
        self.canvas.coords(action_text, x + padding, y + int(8 * scale))

        # Update info text with scaled font
        info_str = "\n".join(info_lines)
        self.canvas.itemconfig(
            info_text, text=info_str, font=self._get_scaled_font(9), state="normal"
        )
        self.canvas.coords(info_text, x + padding, y + spacing + int(8 * scale))

        # Calculate panel size
        action_bbox = self.canvas.bbox(action_text)
        info_bbox = self.canvas.bbox(info_text)

        if action_bbox and info_bbox:
            left = min(action_bbox[0], info_bbox[0]) - int(8 * scale)
            top = action_bbox[1] - int(6 * scale)
            right = max(action_bbox[2], info_bbox[2]) + int(8 * scale)
            bottom = info_bbox[3] + int(6 * scale)
            self.canvas.coords(panel_bg, left, top, right, bottom)
            self.canvas.itemconfig(panel_bg, state="normal")

            # Register as draggable (use panel background position for normalized coords)
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if canvas_w > 0 and canvas_h > 0:
                norm_x = left / canvas_w
                norm_y = top / canvas_h
                self.register_draggable(name, (panel_bg, action_text, info_text), norm_x, norm_y)

    def destroy(self):
        """Destroy the overlay window."""
        try:
            self.win.destroy()
        except Exception:
            pass


class StrategyHUD:
    """Strategy HUD overlay for a single poker table."""

    def __init__(
        self,
        master,
        hwnd,
        title,
        regions,
        slots_cfg,
        capture,
        button_cfg=None,
        card_back_regions=None,
        name_regions=None,
        overlay_settings=None,
        on_settings_changed=None,
    ):
        self.master = master
        self.hwnd = hwnd
        self.title = title
        self.regions = regions
        self.slots_cfg = slots_cfg
        self.slots = slots_cfg["slots"]
        self.capture = capture
        self.button_cfg = button_cfg
        self.card_back_regions = card_back_regions
        self.name_regions = name_regions
        self.running = True

        # Strategy engine
        self.strategy = StrategyEngine()

        # Session tracker for opponent modeling
        self.session_tracker = SessionTracker()

        # Detection state cache
        self.hero_cards = []
        self.board_cards = []
        self.pot = None
        self.stacks = {}
        self.bets = {}
        self.dealer_seat = 0
        self.active_seats = {}  # Seats with visible card backs (still in hand)
        self.player_names = {}  # Detected player names by seat

        # Debug capture state cache
        self._last_game_state = None
        self._last_action = None
        self._last_screenshot = None
        self._last_trace = None

        # Create canvas overlay with settings
        self.overlay = CanvasOverlay(master, hwnd, overlay_settings)
        self.overlay._on_settings_changed = on_settings_changed
        self._create_labels()

    def set_edit_mode(self, enabled):
        """Toggle edit mode for the overlay."""
        self.overlay.set_edit_mode(enabled)

    def _create_labels(self):
        """Create all label items on the canvas."""
        # Hero cards
        for slot in ["hero_left", "hero_right"]:
            self.overlay.create_label(slot)

        # Board cards
        for i in range(1, 6):
            self.overlay.create_label(f"board_{i}")

        # Stacks
        for i in range(1, 10):
            self.overlay.create_label(f"stack_{i}")

        # Bets
        for i in range(1, 10):
            self.overlay.create_label(f"bet_{i}")

        # Pot
        self.overlay.create_label("pot")

        # Dealer
        self.overlay.create_label("dealer")

        # Strategy panel (new)
        self.overlay.create_strategy_panel("strategy")

        # Position badge
        self.overlay.create_label("position")

        # Street badge
        self.overlay.create_label("street")

        # Hand info
        self.overlay.create_label("hand_info")

        # Card back indicators (seats 2-9)
        for i in range(2, 10):
            self.overlay.create_indicator(f"active_{i}")

        # Opponent stats HUD (seats 2-9)
        for i in range(2, 10):
            self.overlay.create_label(f"opp_stats_{i}")

    def _hide_all(self):
        """Hide all overlay elements."""
        for name in self.overlay.labels:
            self.overlay.hide_label(name)
        # Also hide strategy panel
        self.overlay.update_strategy_panel("strategy", 0, 0, "", "#888888", [], visible=False)

    def _get_suit_color(self, suit):
        return SUIT_COLORS.get(suit, "#ffffff")

    def update(self):
        """Main update loop."""
        if not self.running:
            return

        if not user32.IsWindow(self.hwnd):
            self.stop()
            return

        if not self.overlay.reposition():
            self.stop()
            return

        # Only show overlay for the foreground table
        fg_hwnd = get_foreground_window()
        is_foreground = fg_hwnd == self.hwnd

        if not is_foreground and not self.overlay.edit_mode:
            # Hide all overlay elements when not in foreground (unless in edit mode)
            self._hide_all()
            return

        try:
            img = self.capture.grab(self.hwnd)
            if img is None:
                return
        except Exception:
            return

        # Store screenshot for debug capture
        self._last_screenshot = img

        # Get image dimensions - captured image is client area,
        # so use these for both cropping and overlay coordinate conversion
        full_w, full_h = img.size
        table_w, table_h = full_w, full_h  # Overlay coords match capture coords

        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        card_w, card_h = get_scaled_card_size(self.slots_cfg, full_w, full_h)

        # Update detections
        self._update_hero_cards(img, full_w, full_h, card_w, card_h, table_w, table_h)
        self._update_board_cards(img, full_w, full_h, card_w, card_h, table_w, table_h)
        self._update_pot(img_cv, full_w, full_h, table_w, table_h)
        self._update_stacks(img_cv, full_w, full_h, table_w, table_h)
        self._update_bets(img_cv, full_w, full_h, table_w, table_h)
        self._update_dealer_button(img, table_w, table_h)
        self._update_card_backs(img, table_w, table_h)
        self._update_player_names(img_cv, full_w, full_h)
        self._update_opponent_stats(table_w, table_h)

        # Update strategy recommendation
        self._update_strategy(table_w, table_h)

    def _norm_to_canvas(self, norm_x, norm_y, table_w, table_h):
        """Convert normalized coords to canvas coords."""
        return int(norm_x * table_w), int(norm_y * table_h)

    def _update_hero_cards(self, img, full_w, full_h, card_w, card_h, table_w, table_h):
        """Update hero card labels."""
        # Skip position updates while dragging this element
        if self.overlay._drag_panel_name == "hero_cards":
            return

        hero_reg = self.regions.get("hero_cards")
        if not hero_reg:
            self.hero_cards = []
            return

        # Get offset from settings
        off_x, off_y = self.overlay.get_element_offset("hero_cards")

        hx = int(hero_reg["x"] * full_w)
        hy = int(hero_reg["y"] * full_h)
        hw = int(hero_reg["w"] * full_w)
        hh = int(hero_reg["h"] * full_h)
        hero_img = img.crop((hx, hy, hx + hw, hy + hh))

        cards = []
        for slot_name in ["hero_left", "hero_right"]:
            slot = self.slots.get(slot_name)
            if not slot:
                continue

            sx = int(slot["x"] * hw)
            sy = int(slot["y"] * hh)
            tilt = slot.get("tilt", 0)

            card_crop = hero_img.crop((sx, sy, sx + card_w, sy + card_h))
            card_cv = cv2.cvtColor(np.array(card_crop), cv2.COLOR_RGB2BGR)
            result = detect_card(card_cv, tilt=tilt)

            base_x = hero_reg["x"] + slot["x"] * hero_reg["w"] + 0.02
            base_y = hero_reg["y"] + hero_reg["h"] + 0.005
            label_norm_x = base_x + off_x
            label_norm_y = base_y + off_y
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if result:
                card = result["card"]
                cards.append(card)
                self.overlay.update_label(
                    slot_name, canvas_x, canvas_y, card, self._get_suit_color(card[1])
                )
                # Register first hero card for dragging (moves all hero cards)
                if slot_name == "hero_left" and slot_name in self.overlay.labels:
                    items = self.overlay.labels[slot_name]
                    self.overlay.register_draggable("hero_cards", items, label_norm_x, label_norm_y)
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements["hero_cards"] = (base_x, base_y)
            else:
                self.overlay.update_label(slot_name, canvas_x, canvas_y, "--", "#555555")

        self.hero_cards = cards

    def _update_board_cards(self, img, full_w, full_h, card_w, card_h, table_w, table_h):
        """Update board card labels."""
        # Skip position updates while dragging this element
        if self.overlay._drag_panel_name == "board_cards":
            return

        board_reg = self.regions.get("board")
        if not board_reg:
            self.board_cards = []
            return

        # Get offset from settings
        off_x, off_y = self.overlay.get_element_offset("board_cards")

        bx = int(board_reg["x"] * full_w)
        by = int(board_reg["y"] * full_h)
        bw = int(board_reg["w"] * full_w)
        bh = int(board_reg["h"] * full_h)
        board_img = img.crop((bx, by, bx + bw, by + bh))

        cards = []
        for i in range(1, 6):
            slot_name = f"board_{i}"
            slot = self.slots.get(slot_name)
            if not slot:
                continue

            sx = int(slot["x"] * bw)
            sy = int(slot["y"] * bh)

            card_crop = board_img.crop((sx, sy, sx + card_w, sy + card_h))
            card_cv = cv2.cvtColor(np.array(card_crop), cv2.COLOR_RGB2BGR)
            result = detect_card(card_cv, tilt=0)

            base_x = board_reg["x"] + slot["x"] * board_reg["w"] + 0.01
            base_y = board_reg["y"] + board_reg["h"] + 0.005
            label_norm_x = base_x + off_x
            label_norm_y = base_y + off_y
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if result and result["confidence"] > 0.6:
                card = result["card"]
                cards.append(card)
                self.overlay.update_label(
                    slot_name, canvas_x, canvas_y, card, self._get_suit_color(card[1])
                )
                # Register first board card for dragging (moves all board cards)
                if slot_name == "board_1" and slot_name in self.overlay.labels:
                    items = self.overlay.labels[slot_name]
                    self.overlay.register_draggable(
                        "board_cards", items, label_norm_x, label_norm_y
                    )
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements["board_cards"] = (base_x, base_y)
            else:
                cards.append("--")
                self.overlay.update_label(slot_name, canvas_x, canvas_y, "--", "#555555")

        self.board_cards = cards

    def _update_pot(self, img_cv, full_w, full_h, table_w, table_h):
        """Update pot value label."""
        # Skip position updates while dragging this element
        if self.overlay._drag_panel_name == "pot":
            return

        pot_reg = self.regions.get("pot")
        if not pot_reg:
            self.pot = None
            self.overlay.hide_label("pot")
            return

        # Get offset from settings
        off_x, off_y = self.overlay.get_element_offset("pot")

        px = int(pot_reg["x"] * full_w)
        py = int(pot_reg["y"] * full_h)
        pw = int(pot_reg["w"] * full_w)
        ph = int(pot_reg["h"] * full_h)

        pot_crop = img_cv[py : py + ph, px : px + pw]
        pot_val = read_value(pot_crop, "pot")

        base_x = pot_reg["x"] + pot_reg["w"] / 2
        base_y = pot_reg["y"] - 0.06
        label_norm_x = base_x + off_x
        label_norm_y = base_y + off_y
        canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

        if pot_val is not None:
            self.pot = pot_val
            self.overlay.update_label("pot", canvas_x, canvas_y, f"${pot_val:.2f}", "#ffcc00")
            # Register pot for dragging
            if "pot" in self.overlay.labels:
                items = self.overlay.labels["pot"]
                self.overlay.register_draggable("pot", items, label_norm_x, label_norm_y)
                if not hasattr(self.overlay, "_offset_elements"):
                    self.overlay._offset_elements = {}
                self.overlay._offset_elements["pot"] = (base_x, base_y)
        else:
            self.pot = None
            self.overlay.hide_label("pot")

    def _update_stacks(self, img_cv, full_w, full_h, table_w, table_h):
        """Update stack labels for all seats."""
        for seat in range(1, 10):
            key = f"stack_{seat}"
            element_name = f"stacks_{seat}"

            # Skip position updates while dragging this specific seat
            if self.overlay._drag_panel_name == element_name:
                continue

            stack_reg = self.regions.get(key)

            if not stack_reg:
                self.stacks[seat] = None
                self.overlay.hide_label(key)
                continue

            sx = int(stack_reg["x"] * full_w)
            sy = int(stack_reg["y"] * full_h)
            sw = int(stack_reg["w"] * full_w)
            sh = int(stack_reg["h"] * full_h)

            stack_crop = img_cv[sy : sy + sh, sx : sx + sw]
            stack_val = read_value(stack_crop, "stack")

            # Get per-seat offset from settings
            off_x, off_y = self.overlay.get_element_offset(element_name)

            base_x = stack_reg["x"] + stack_reg["w"] / 2
            base_y = stack_reg["y"] + stack_reg["h"] + 0.01
            label_norm_x = base_x + off_x
            label_norm_y = base_y + off_y
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if stack_val is not None:
                self.stacks[seat] = stack_val
                self.overlay.update_label(key, canvas_x, canvas_y, f"${stack_val:.2f}", "#55ff55")
                # Register each visible stack for individual dragging
                if self.overlay.edit_mode and key in self.overlay.labels:
                    items = self.overlay.labels[key]
                    self.overlay.register_draggable(element_name, items, label_norm_x, label_norm_y)
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements[element_name] = (base_x, base_y)
            else:
                self.stacks[seat] = None
                self.overlay.hide_label(key)

    def _update_bets(self, img_cv, full_w, full_h, table_w, table_h):
        """Update bet labels for all seats."""
        for seat in range(1, 10):
            key = f"bet_{seat}"
            element_name = f"bets_{seat}"

            # Skip position updates while dragging this specific seat
            if self.overlay._drag_panel_name == element_name:
                continue

            bet_reg = self.regions.get(key)

            if not bet_reg:
                self.bets[seat] = None
                self.overlay.hide_label(key)
                continue

            bx = int(bet_reg["x"] * full_w)
            by = int(bet_reg["y"] * full_h)
            bw = int(bet_reg["w"] * full_w)
            bh = int(bet_reg["h"] * full_h)

            bet_crop = img_cv[by : by + bh, bx : bx + bw]
            bet_val = read_value(bet_crop, "bet")

            # Get per-seat offset from settings
            off_x, off_y = self.overlay.get_element_offset(element_name)

            base_x = bet_reg["x"] + bet_reg["w"] / 2
            base_y = bet_reg["y"] + bet_reg["h"] + 0.005
            label_norm_x = base_x + off_x
            label_norm_y = base_y + off_y
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if bet_val is not None and bet_val > 0:
                self.bets[seat] = bet_val
                self.overlay.update_label(key, canvas_x, canvas_y, f"${bet_val:.2f}", "#ffffff")
                # Register each visible bet for individual dragging
                if self.overlay.edit_mode and key in self.overlay.labels:
                    items = self.overlay.labels[key]
                    self.overlay.register_draggable(element_name, items, label_norm_x, label_norm_y)
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements[element_name] = (base_x, base_y)
            else:
                self.bets[seat] = None
                self.overlay.hide_label(key)

    def _update_dealer_button(self, img, table_w, table_h):
        """Update dealer button indicator."""
        # Skip position updates while dragging this element
        if self.overlay._drag_panel_name == "dealer":
            return

        if not self.button_cfg:
            self.dealer_seat = 0
            self.overlay.hide_label("dealer")
            return

        # Get offset from settings
        off_x, off_y = self.overlay.get_element_offset("dealer")

        result = detect_dealer_button(img, self.button_cfg)

        if result and result["confidence"] > 0.4:
            seat = result["seat"]
            self.dealer_seat = seat
            buttons = self.button_cfg.get("buttons", {})
            btn_pos = buttons.get(f"btn_{seat}")

            if btn_pos and not (btn_pos["x"] == 0 and btn_pos["y"] == 0):
                base_x = btn_pos["x"] - 0.02
                base_y = btn_pos["y"] - 0.03
                dealer_x = base_x + off_x
                dealer_y = base_y + off_y
                canvas_x, canvas_y = self._norm_to_canvas(dealer_x, dealer_y, table_w, table_h)
                self.overlay.update_label("dealer", canvas_x, canvas_y, f"D{seat}", "#ffcc00")
                # Register dealer for dragging
                if "dealer" in self.overlay.labels:
                    items = self.overlay.labels["dealer"]
                    self.overlay.register_draggable("dealer", items, dealer_x, dealer_y)
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements["dealer"] = (base_x, base_y)
            else:
                self.overlay.hide_label("dealer")
        else:
            self.dealer_seat = 0
            self.overlay.hide_label("dealer")

    def _update_card_backs(self, img, table_w, table_h):
        """Update active seats based on visible card backs and show indicators."""
        if not self.card_back_regions:
            # No card back regions calibrated - hide all indicators
            self.active_seats = {}
            for i in range(2, 10):
                self.overlay.update_indicator(f"active_{i}", 0, 0, "#888888", visible=False)
            return

        self.active_seats = get_active_seats(img, self.card_back_regions)

        # Update visual indicators for each seat
        for seat in range(2, 10):
            region_name = f"card_back_{seat}"
            reg = self.card_back_regions.get(region_name)

            if not reg:
                self.overlay.update_indicator(f"active_{seat}", 0, 0, "#888888", visible=False)
                continue

            # Position indicator at top-right of the card_back region
            ind_x = int((reg["x"] + reg["w"]) * table_w) + 2
            ind_y = int(reg["y"] * table_h) - 2

            is_active = self.active_seats.get(seat, False)
            color = "#00ff00" if is_active else "#ff4444"  # Green if active, red if folded

            self.overlay.update_indicator(f"active_{seat}", ind_x, ind_y, color, visible=True)

    def _update_player_names(self, img_cv, full_w, full_h):
        """Update player identifiers for all seats using visual hashing."""
        if not self.name_regions:
            # No name regions calibrated
            self.player_names = {}
            return

        # Get unique hash identifiers from name regions (no OCR needed)
        hashes = get_all_name_hashes(img_cv, {"names": self.name_regions}, (full_w, full_h))
        self.player_names = {seat: h for seat, h in hashes.items() if h}

    def _update_opponent_stats(self, table_w, table_h):
        """Update session tracker and display opponent stats HUD."""
        # Build game state for session tracker
        game_state = GameState.from_detection(
            hero_cards=self.hero_cards,
            board_cards=self.board_cards,
            pot=self.pot or 0,
            stacks=self.stacks,
            bets=self.bets,
            dealer_seat=self.dealer_seat,
            active_seats=self.active_seats,
        )

        # Update session tracker with current state and names
        self.session_tracker.update(game_state, self.player_names)

        # Get current stats for display
        seat_stats = self.session_tracker.get_seat_stats()

        # Display stats for each seat
        for seat in range(2, 10):
            label_name = f"opp_stats_{seat}"
            element_name = f"opp_stats_{seat}"

            # Skip position updates while dragging this specific seat
            if self.overlay._drag_panel_name == element_name:
                continue

            # Position near the stack label (below it)
            stack_reg = self.regions.get(f"stack_{seat}")
            if not stack_reg:
                self.overlay.hide_label(label_name)
                continue

            # Get per-seat offset from settings
            off_x, off_y = self.overlay.get_element_offset(element_name)

            # Position below stack, offset for visibility
            base_x = stack_reg["x"] + stack_reg["w"] / 2
            base_y = stack_reg["y"] + stack_reg["h"] + 0.035
            label_norm_x = base_x + off_x
            label_norm_y = base_y + off_y
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if seat in seat_stats:
                stats = seat_stats[seat]
                # Format: VPIP/PFR/AF (hands)
                hud_text = stats.to_hud_string()
                player_type = stats.player_type
                color = PLAYER_TYPE_COLORS.get(player_type, "#888888")
                self.overlay.update_label(label_name, canvas_x, canvas_y, hud_text, color)
                # Register each visible opp_stats for individual dragging
                if self.overlay.edit_mode and label_name in self.overlay.labels:
                    items = self.overlay.labels[label_name]
                    self.overlay.register_draggable(element_name, items, label_norm_x, label_norm_y)
                    if not hasattr(self.overlay, "_offset_elements"):
                        self.overlay._offset_elements = {}
                    self.overlay._offset_elements[element_name] = (base_x, base_y)
            else:
                # No stats for this seat
                self.overlay.hide_label(label_name)

    def _update_strategy(self, table_w, table_h):
        """Update strategy recommendation panel."""
        # Skip position updates while dragging these panels
        if self.overlay._drag_panel_name in ("strategy", "position_badge"):
            return

        # Build game state from detections
        game_state = GameState.from_detection(
            hero_cards=self.hero_cards,
            board_cards=self.board_cards,
            pot=self.pot or 0,
            stacks=self.stacks,
            bets=self.bets,
            dealer_seat=self.dealer_seat,
            active_seats=self.active_seats,
        )

        # Get positions from settings (allow dragging to move these)
        badge_norm_x, badge_norm_y = self.overlay.get_panel_position("position_badge")
        pos_x, pos_y = self._norm_to_canvas(badge_norm_x, badge_norm_y, table_w, table_h)

        # Get scale for offset adjustments
        scale = self.overlay.get_scale()

        if not game_state.is_valid():
            # Hide all strategy elements when no valid state
            self.overlay.hide_label("position")
            self.overlay.hide_label("street")
            self.overlay.hide_label("hand_info")
            self.overlay.update_strategy_panel("strategy", 0, 0, "", "#888888", [], visible=False)
            return

        # Update position badge
        position = game_state.position
        pos_color = get_position_color(position)
        self.overlay.update_label("position", pos_x, pos_y, position.value, pos_color)

        # Register position badge as draggable (includes the 3 badge labels)
        if "position" in self.overlay.labels:
            position_items = self.overlay.labels["position"]
            street_items = self.overlay.labels.get("street", ())
            hand_items = self.overlay.labels.get("hand_info", ())
            all_badge_items = position_items + street_items + hand_items
            self.overlay.register_draggable(
                "position_badge", all_badge_items, badge_norm_x, badge_norm_y
            )

        # Update street badge (offset from position)
        street = game_state.street
        street_color = STREET_COLORS.get(street, "#888888")
        street_offset = int(self.overlay.get_panel_offset("street_badge") * scale)
        self.overlay.update_label(
            "street", pos_x + street_offset, pos_y, street.value.upper(), street_color
        )

        # Update hand info (offset from position)
        notation = game_state.hand_notation
        category = game_state.preflop_category
        cat_color = get_category_color(category)
        hand_offset = int(self.overlay.get_panel_offset("hand_info") * scale)
        self.overlay.update_label(
            "hand_info", pos_x + hand_offset, pos_y, f"{notation} ({category.value})", cat_color
        )

        # Get strategy recommendation (with villain adjustments if stats available)
        villain_stats = self.session_tracker.get_seat_stats()
        action = self.strategy.recommend(game_state, villain_stats)

        # Cache for debug capture
        self._last_game_state = game_state
        self._last_action = action
        self._last_trace = self.strategy.last_trace

        # Build info lines for panel
        info_lines = []

        # Context info
        info_lines.append(f"Context: {game_state.get_context_description()}")

        # Pot odds (if applicable)
        to_call = game_state.to_call()
        if to_call > 0:
            pot_odds = game_state.pot_odds()
            info_lines.append(f"Pot Odds: {pot_odds * 100:.0f}%  To Call: ${to_call:.2f}")

        # Equity estimate (postflop)
        if not game_state.is_preflop():
            draws = game_state.draws
            outs = count_outs(draws)
            equity = equity_estimate(game_state.hand_strength, draws, game_state.street.value)
            equity_str = f"Equity: ~{equity * 100:.0f}%"
            if outs > 0:
                equity_str += f" ({outs} outs)"
            info_lines.append(equity_str)

            # Hand strength
            info_lines.append(f"Hand: {game_state.hand_description}")

        # Reasoning
        if action.reasoning:
            info_lines.append(f"Why: {action.reasoning}")

        # Button to click (emphasized for easy reference)
        # Many clients use percentage buttons (33%, 66%, 80%, 100%) for all streets
        # For preflop BB-based recommendations, show the dollar amount since
        # there may not be BB buttons - user should use the raise slider
        if action.button:
            btn = action.button
            is_bb_button = "bb" in btn.lower()
            is_pct_button = "%" in btn

            if is_bb_button:
                # BB-based button - show dollar amount for manual entry
                if action.amount:
                    info_lines.append(f"Set: ${action.amount:.2f}")
            elif is_pct_button:
                # Percentage button
                info_lines.append(f"Click: [{btn}]")
            elif btn.lower() == "pot":
                info_lines.append("Click: [100%]")

        # Position strategy panel (from settings)
        panel_norm_x, panel_norm_y = self.overlay.get_panel_position("strategy")
        panel_x, panel_y = self._norm_to_canvas(panel_norm_x, panel_norm_y, table_w, table_h)

        # Combine action and button for visual display (kept separate for automation)
        action_display = action.get_display_text(street=street.value)
        button_display = action.get_button_display()
        full_display = f"{action_display} {button_display}".strip()

        self.overlay.update_strategy_panel(
            "strategy",
            panel_x,
            panel_y,
            full_display,
            action.get_color(),
            info_lines,
            visible=True,
        )

    def capture_debug_snapshot(self, debug_capture) -> bool:
        """
        Capture current state for debugging.

        Args:
            debug_capture: DebugCapture instance

        Returns:
            True if capture succeeded
        """
        if not all([self._last_game_state, self._last_action, self._last_screenshot]):
            print("[Debug] No valid state to capture")
            return False

        if not self._last_game_state.is_valid():
            print("[Debug] Game state not valid for capture")
            return False

        debug_capture.save_capture(
            screenshot=self._last_screenshot,
            game_state=self._last_game_state,
            action=self._last_action,
            table_title=self.title,
            trace=self._last_trace,
        )
        return True

    def stop(self):
        self.running = False
        # Save accumulated opponent stats before closing
        self.session_tracker.save_all_stats()
        self.overlay.destroy()


class StrategyOverlay:
    """Manager for multiple strategy HUDs."""

    def __init__(self):
        self.root = tk.Tk()

        # Force Tk to use 1:1 scaling (disable DPI scaling in Tkinter)
        # This ensures overlay coordinates match the captured image coordinates
        self.root.tk.call("tk", "scaling", 1.0)

        self.root.withdraw()

        self.regions, self.slots_cfg = load_config()
        self.button_cfg = load_button_config()
        self.card_back_regions = self._load_card_back_regions()
        self.name_regions = self._load_name_regions()
        self.capture = WindowCapture()
        self.overlays = []

        # Load overlay settings (positions, scale)
        self.overlay_settings = load_overlay_settings()

        # Initialize debug session
        from src.capture.debug_capture import DebugCapture, DebugSession

        self.debug_session = DebugSession()
        self.debug_capture = DebugCapture(self.debug_session)

        # Flags for pending actions (set by hotkey thread, processed by main thread)
        self._pending_capture = False
        self._pending_edit_toggle = False
        self._edit_mode = False

        # Register global hotkeys (Shift+S for debug, Shift+E for edit)
        self._register_global_hotkey()

        self._attach_tables()
        self._update_loop()

    def _register_global_hotkey(self):
        """Register global hotkeys using Windows API."""

        def hotkey_listener():
            # Register hotkeys in this thread
            if not user32.RegisterHotKey(None, HOTKEY_ID_DEBUG, MOD_SHIFT, VK_S):
                print("[Debug] Failed to register Shift+S hotkey")
            else:
                print("[Debug] Global hotkey Shift+S registered")

            if not user32.RegisterHotKey(None, HOTKEY_ID_EDIT, MOD_SHIFT, VK_E):
                print("[Edit] Failed to register Shift+E hotkey")
            else:
                print("[Edit] Global hotkey Shift+E registered")

            # Message loop to listen for hotkeys
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    if msg.wParam == HOTKEY_ID_DEBUG:
                        self._pending_capture = True
                    elif msg.wParam == HOTKEY_ID_EDIT:
                        self._pending_edit_toggle = True

            # Unregister on exit
            user32.UnregisterHotKey(None, HOTKEY_ID_DEBUG)
            user32.UnregisterHotKey(None, HOTKEY_ID_EDIT)

        # Start hotkey listener in daemon thread
        self._hotkey_thread = threading.Thread(target=hotkey_listener, daemon=True)
        self._hotkey_thread.start()

    def _on_settings_changed(self, settings):
        """Callback when overlay settings are changed (e.g., after dragging)."""
        self.overlay_settings = settings
        save_overlay_settings(settings)
        print(f"[Edit] Overlay settings saved (scale: {settings.get('scale', 1.0):.0%})")

    def _process_pending_edit_toggle(self):
        """Process any pending edit mode toggle request (called from main thread)."""
        if not self._pending_edit_toggle:
            return

        self._pending_edit_toggle = False
        self._edit_mode = not self._edit_mode

        # Toggle edit mode on all overlays
        for overlay in self.overlays:
            if overlay.running:
                overlay.set_edit_mode(self._edit_mode)

        if self._edit_mode:
            print("[Edit] Edit mode ENABLED - Drag panels to reposition, scroll to scale")
        else:
            print("[Edit] Edit mode DISABLED - Settings saved")

    def _process_pending_capture(self):
        """Process any pending debug capture request (called from main thread)."""
        if not self._pending_capture:
            return

        self._pending_capture = False

        # Only capture the active (foreground) table
        fg_hwnd = get_foreground_window()
        active_overlay = None
        for overlay in self.overlays:
            if overlay.running and overlay.hwnd == fg_hwnd:
                active_overlay = overlay
                break

        if active_overlay is None:
            print("[Debug] No active poker table in foreground")
            return

        if active_overlay.capture_debug_snapshot(self.debug_capture):
            print(f"[Debug] Captured active table: {active_overlay.title}")
        else:
            print("[Debug] Failed to capture active table (no valid state)")

    def _attach_tables(self):
        windows = self.capture.find_all_windows("*NLHA*")
        if not windows:
            print("No poker tables found. Exiting.")
            self.root.quit()
            return

        for hwnd, title in windows:
            ov = StrategyHUD(
                self.root,
                hwnd,
                title,
                self.regions,
                self.slots_cfg,
                self.capture,
                self.button_cfg,
                self.card_back_regions,
                self.name_regions,
                overlay_settings=self.overlay_settings,
                on_settings_changed=self._on_settings_changed,
            )
            self.overlays.append(ov)

        print(f"Attached Strategy HUD to {len(self.overlays)} table(s).")
        print("Press Shift+S to capture debug snapshot.")
        print("Press Shift+E to toggle edit mode (drag panels, scroll to scale).")
        print("Ctrl+C to stop.")

    def _load_card_back_regions(self):
        """Load card back regions, returning None if not calibrated."""
        try:
            regions = load_card_back_regions()
            if regions:
                print(f"[+] Loaded {len(regions)} card back regions")
                return regions
        except FileNotFoundError:
            pass
        print("[!] Card back regions not calibrated - opponent count may be inaccurate")
        return None

    def _load_name_regions(self):
        """Load name regions from calibration, returning None if not present."""
        try:
            import json

            from src.paths import CALIBRATION_FILE

            with open(CALIBRATION_FILE) as f:
                config = json.load(f)
            names_cfg = config.get("names")
            if names_cfg:
                count = len([k for k in names_cfg.keys() if k.startswith("name_")])
                print(f"[+] Loaded {count} name regions for opponent tracking")
                return names_cfg
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        print("[!] Name regions not calibrated - opponent tracking disabled")
        return None

    def _update_loop(self):
        # Process any pending hotkey actions
        self._process_pending_capture()
        self._process_pending_edit_toggle()

        dead = []
        for ov in self.overlays:
            if ov.running:
                ov.update()
            else:
                dead.append(ov)

        for ov in dead:
            self.overlays.remove(ov)

        if not self.overlays:
            print("All tables closed. Exiting.")
            self.root.quit()
            return

        self.root.after(100, self._update_loop)

    def run(self):
        self.root.mainloop()


def main():
    # Ensure windows are properly sized before attaching overlays
    arranged = arrange_tables()
    if arranged:
        print(f"Arranged {len(arranged)} table(s) to standard size")
    StrategyOverlay().run()


if __name__ == "__main__":
    main()
