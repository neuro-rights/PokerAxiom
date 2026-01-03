"""
Unified Calibrator - Single tool for all calibration needs.

All regions are visible on a single canvas with color-coded overlays.
Supports: parent regions, card slots, stacks, bets, buttons, card backs.

Usage:
1. Click a button in the control panel to select a region
2. Click on the canvas to position it
3. Press Tab to move to the next seat (Shift+Tab for previous)
4. Arrow keys to nudge position (Shift for 5px)
5. Press S to save

Keyboard shortcuts:
- Tab / Shift+Tab: Next/previous seat in current category
- Arrow keys: Nudge position (Shift = 5px)
- N/P: Next/previous sample image
- S: Save calibration
- Escape: Deselect
"""

# Import capture module early to set DPI awareness before tkinter
import json
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

import src.capture  # noqa: F401 - sets DPI awareness
from src.calibration.calibration_manager import save_calibration
from src.paths import CALIBRATION_FILE, SAMPLES_DIR

# Color scheme for different region types
COLORS = {
    "parent_region": "#FF4444",  # Red
    "card_slot": "#4488FF",  # Blue
    "stack": "#00FFFF",  # Cyan
    "bet": "#FFA500",  # Orange
    "button": "#44FF44",  # Green
    "card_back": "#FF69B4",  # Pink
    "selected": "#FFFFFF",  # White
}


class UnifiedCalibrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Unified Calibrator")

        # Load samples
        self.samples = sorted(SAMPLES_DIR.glob("*.png"))
        if not self.samples:
            print(f"No samples found in {SAMPLES_DIR}/")
            return

        self.current_idx = 0

        # Selection state
        self.selected = None  # (category, key) e.g. ("stack", "stack_1")
        self.mode = "select"  # "select", "draw_rect", "position"
        self.click_start = None

        # Reference size (will be set from first sample)
        self.reference_size = None

        # Initialize calibration data structure
        self.init_data()

        # Load existing calibration if available
        self.load_config()

        self.setup_ui()
        self.load_sample()
        self.root.mainloop()

    def init_data(self):
        """Initialize default calibration data structure."""
        self.data = {
            "version": 1,
            "offset": {"x": 0.0, "y": 0.0},
            "reference_size": [1062, 769],
            "regions": {
                "hero_cards": {"x": 0.43, "y": 0.73, "w": 0.14, "h": 0.10},
                "board": {"x": 0.29, "y": 0.40, "w": 0.45, "h": 0.16},
                "pot": {"x": 0.51, "y": 0.37, "w": 0.07, "h": 0.03},
                "actions": {"x": 0.60, "y": 0.82, "w": 0.39, "h": 0.17},
            },
            "card_slots": {
                "size": [30, 64],
                "hero_left": {"x": 0.05, "y": 0.18, "tilt": -5.0},
                "hero_right": {"x": 0.43, "y": 0.12, "tilt": 5.0},
                "board_1": {"x": 0.01, "y": 0.06},
                "board_2": {"x": 0.20, "y": 0.07},
                "board_3": {"x": 0.38, "y": 0.07},
                "board_4": {"x": 0.57, "y": 0.07},
                "board_5": {"x": 0.76, "y": 0.06},
            },
            "stacks": {"size": [90, 28]},
            "bets": {"size": [60, 28]},
            "buttons": {"size": [24, 24]},
            "card_backs": {"size": [0.118, 0.034]},
        }

        # Initialize 9 stacks, bets, buttons
        for i in range(1, 10):
            self.data["stacks"][f"stack_{i}"] = {"x": 0.0, "y": 0.0}
            self.data["bets"][f"bet_{i}"] = {"x": 0.0, "y": 0.0}
            self.data["buttons"][f"btn_{i}"] = {"x": 0.0, "y": 0.0}

        # Initialize card backs (seats 2-9)
        for i in range(2, 10):
            self.data["card_backs"][f"card_back_{i}"] = {"x": 0.0, "y": 0.0}

    def load_config(self):
        """Load existing calibration if available."""
        if not CALIBRATION_FILE.exists():
            return

        try:
            with open(CALIBRATION_FILE) as f:
                saved = json.load(f)

            # Merge saved data into our structure
            if "offset" in saved:
                self.data["offset"] = saved["offset"]

            if "reference_size" in saved:
                self.data["reference_size"] = saved["reference_size"]

            if "regions" in saved:
                self.data["regions"].update(saved["regions"])

            if "card_slots" in saved:
                self.data["card_slots"].update(saved["card_slots"])

            if "stacks" in saved:
                self.data["stacks"].update(saved["stacks"])

            if "bets" in saved:
                self.data["bets"].update(saved["bets"])

            if "buttons" in saved:
                self.data["buttons"].update(saved["buttons"])

            if "card_backs" in saved:
                self.data["card_backs"].update(saved["card_backs"])

            print(f"[+] Loaded calibration from {CALIBRATION_FILE}")
        except Exception as e:
            print(f"[!] Failed to load calibration: {e}")

    def setup_ui(self):
        """Set up the UI."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas
        self.canvas = tk.Canvas(main_frame, bg="black", cursor="crosshair")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Control panel
        ctrl_container = ttk.Frame(main_frame, width=380)
        ctrl_container.pack(side=tk.RIGHT, fill=tk.Y)
        ctrl_container.pack_propagate(False)

        # Scrollable frame
        canvas_ctrl = tk.Canvas(ctrl_container, width=360, highlightthickness=0)
        scrollbar = ttk.Scrollbar(ctrl_container, orient="vertical", command=canvas_ctrl.yview)
        ctrl = ttk.Frame(canvas_ctrl)

        ctrl.bind(
            "<Configure>", lambda e: canvas_ctrl.configure(scrollregion=canvas_ctrl.bbox("all"))
        )
        canvas_ctrl.create_window((0, 0), window=ctrl, anchor="nw")
        canvas_ctrl.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas_ctrl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(ctrl, text="Unified Calibrator", font=("Arial", 12, "bold")).pack(pady=5)

        # Sample navigation
        nav_frame = ttk.Frame(ctrl)
        nav_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Button(nav_frame, text="< Prev (P)", command=self.prev_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(nav_frame, text="Next (N) >", command=self.next_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )

        self.sample_label = ttk.Label(ctrl, text="", wraplength=340)
        self.sample_label.pack(pady=2)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Global offset controls
        self._setup_offset_controls(ctrl)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Size controls
        self._setup_size_controls(ctrl)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Tilt controls for hero cards
        self._setup_tilt_controls(ctrl)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Quick selection buttons
        self._setup_selection_buttons(ctrl)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Keyboard shortcuts help
        self._setup_help(ctrl)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Status and save
        self.status_label = ttk.Label(
            ctrl, text="Select region, then click to position", wraplength=340
        )
        self.status_label.pack(pady=5)

        self.pos_label = ttk.Label(ctrl, text="x=---, y=---", font=("Courier", 10))
        self.pos_label.pack(pady=2)

        ttk.Button(ctrl, text="Save (S)", command=self.save_config).pack(
            pady=10, padx=20, fill=tk.X
        )

        # Bind events
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.root.bind("<Key>", self.on_key)

    def _setup_offset_controls(self, parent):
        """Set up global offset controls."""
        offset_frame = ttk.LabelFrame(parent, text="Global Offset (Ctrl+Arrows)")
        offset_frame.pack(fill=tk.X, pady=5, padx=5)

        # Initialize offset variables
        self.offset_x = tk.DoubleVar(value=self.data["offset"]["x"])
        self.offset_y = tk.DoubleVar(value=self.data["offset"]["y"])

        # X offset
        row = ttk.Frame(offset_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="X:", width=4).pack(side=tk.LEFT)
        self.offset_x_spin = ttk.Spinbox(
            row,
            from_=-0.1,
            to=0.1,
            increment=0.001,
            width=10,
            textvariable=self.offset_x,
            command=self.redraw,
        )
        self.offset_x_spin.pack(side=tk.LEFT)
        ttk.Button(row, text="Reset", width=5, command=lambda: self._reset_offset("x")).pack(
            side=tk.LEFT, padx=5
        )

        # Y offset
        row = ttk.Frame(offset_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Y:", width=4).pack(side=tk.LEFT)
        self.offset_y_spin = ttk.Spinbox(
            row,
            from_=-0.1,
            to=0.1,
            increment=0.001,
            width=10,
            textvariable=self.offset_y,
            command=self.redraw,
        )
        self.offset_y_spin.pack(side=tk.LEFT)
        ttk.Button(row, text="Reset", width=5, command=lambda: self._reset_offset("y")).pack(
            side=tk.LEFT, padx=5
        )

        # Reset both button
        ttk.Button(offset_frame, text="Reset Both to 0", command=self._reset_offset_both).pack(
            pady=2
        )

    def _reset_offset(self, axis):
        """Reset offset for one axis."""
        if axis == "x":
            self.offset_x.set(0.0)
        else:
            self.offset_y.set(0.0)
        self.redraw()

    def _reset_offset_both(self):
        """Reset both offsets to 0."""
        self.offset_x.set(0.0)
        self.offset_y.set(0.0)
        self.redraw()

    def _setup_size_controls(self, parent):
        """Set up size spinboxes."""
        size_frame = ttk.LabelFrame(parent, text="Sizes (pixels)")
        size_frame.pack(fill=tk.X, pady=5, padx=5)

        # Card size
        self.card_w = tk.IntVar(value=self.data["card_slots"]["size"][0])
        self.card_h = tk.IntVar(value=self.data["card_slots"]["size"][1])
        row = ttk.Frame(size_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Card:", width=8).pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=20, to=100, width=4, textvariable=self.card_w, command=self.redraw
        ).pack(side=tk.LEFT)
        ttk.Label(row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=40, to=150, width=4, textvariable=self.card_h, command=self.redraw
        ).pack(side=tk.LEFT)

        # Stack size
        self.stack_w = tk.IntVar(value=self.data["stacks"]["size"][0])
        self.stack_h = tk.IntVar(value=self.data["stacks"]["size"][1])
        row = ttk.Frame(size_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Stack:", width=8).pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=20, to=200, width=4, textvariable=self.stack_w, command=self.redraw
        ).pack(side=tk.LEFT)
        ttk.Label(row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=10, to=100, width=4, textvariable=self.stack_h, command=self.redraw
        ).pack(side=tk.LEFT)

        # Bet size
        self.bet_w = tk.IntVar(value=self.data["bets"]["size"][0])
        self.bet_h = tk.IntVar(value=self.data["bets"]["size"][1])
        row = ttk.Frame(size_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Bet:", width=8).pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=20, to=200, width=4, textvariable=self.bet_w, command=self.redraw
        ).pack(side=tk.LEFT)
        ttk.Label(row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=10, to=100, width=4, textvariable=self.bet_h, command=self.redraw
        ).pack(side=tk.LEFT)

        # Button size
        self.btn_w = tk.IntVar(value=self.data["buttons"]["size"][0])
        self.btn_h = tk.IntVar(value=self.data["buttons"]["size"][1])
        row = ttk.Frame(size_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Button:", width=8).pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=10, to=100, width=4, textvariable=self.btn_w, command=self.redraw
        ).pack(side=tk.LEFT)
        ttk.Label(row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=10, to=100, width=4, textvariable=self.btn_h, command=self.redraw
        ).pack(side=tk.LEFT)

    def _setup_tilt_controls(self, parent):
        """Set up tilt sliders for hero cards."""
        tilt_frame = ttk.LabelFrame(parent, text="Hero Card Tilt")
        tilt_frame.pack(fill=tk.X, pady=5, padx=5)

        # Left tilt
        self.tilt_left = tk.DoubleVar(value=self.data["card_slots"]["hero_left"].get("tilt", -5))
        row = ttk.Frame(tilt_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Left:", width=6).pack(side=tk.LEFT)
        ttk.Scale(
            row,
            from_=-15,
            to=15,
            variable=self.tilt_left,
            orient=tk.HORIZONTAL,
            command=lambda v: self.redraw(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tilt_left_label = ttk.Label(row, text=f"{self.tilt_left.get():+.1f}")
        self.tilt_left_label.pack(side=tk.LEFT)

        # Right tilt
        self.tilt_right = tk.DoubleVar(value=self.data["card_slots"]["hero_right"].get("tilt", 5))
        row = ttk.Frame(tilt_frame)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text="Right:", width=6).pack(side=tk.LEFT)
        ttk.Scale(
            row,
            from_=-15,
            to=15,
            variable=self.tilt_right,
            orient=tk.HORIZONTAL,
            command=lambda v: self.redraw(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tilt_right_label = ttk.Label(row, text=f"{self.tilt_right.get():+.1f}")
        self.tilt_right_label.pack(side=tk.LEFT)

    def _setup_selection_buttons(self, parent):
        """Set up selection buttons for all regions."""
        # Store button references for highlighting
        self.region_buttons = {}

        # Parent regions
        reg_frame = ttk.LabelFrame(parent, text="Parent Regions (click corners)")
        reg_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(reg_frame)
        row.pack(fill=tk.X, pady=2)
        for key, label in [
            ("hero_cards", "Hero"),
            ("board", "Board"),
            ("pot", "Pot"),
            ("actions", "Actions"),
        ]:
            btn = ttk.Button(
                row, text=label, width=7, command=lambda k=key: self.select("regions", k)
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.region_buttons[("regions", key)] = btn

        # Card slots
        card_frame = ttk.LabelFrame(parent, text="Card Slots")
        card_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(card_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Hero:", width=6).pack(side=tk.LEFT)
        for key, label in [("hero_left", "Left"), ("hero_right", "Right")]:
            btn = ttk.Button(
                row, text=label, width=5, command=lambda k=key: self.select("card_slots", k)
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.region_buttons[("card_slots", key)] = btn
        row = ttk.Frame(card_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Board:", width=6).pack(side=tk.LEFT)
        for i in range(1, 6):
            key = f"board_{i}"
            btn = ttk.Button(
                row, text=str(i), width=3, command=lambda k=key: self.select("card_slots", k)
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.region_buttons[("card_slots", key)] = btn

        # Stacks (seats 1-9)
        stack_frame = ttk.LabelFrame(parent, text="Stacks (Tab = next seat)")
        stack_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(stack_frame)
        row.pack(fill=tk.X, pady=2)
        for i in range(1, 10):
            key = f"stack_{i}"
            btn = ttk.Button(
                row, text=str(i), width=3, command=lambda k=key: self.select("stacks", k)
            )
            btn.pack(side=tk.LEFT, padx=1)
            self.region_buttons[("stacks", key)] = btn

        # Bets (seats 1-9)
        bet_frame = ttk.LabelFrame(parent, text="Bets (Tab = next seat)")
        bet_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(bet_frame)
        row.pack(fill=tk.X, pady=2)
        for i in range(1, 10):
            key = f"bet_{i}"
            btn = ttk.Button(
                row, text=str(i), width=3, command=lambda k=key: self.select("bets", k)
            )
            btn.pack(side=tk.LEFT, padx=1)
            self.region_buttons[("bets", key)] = btn

        # Dealer Buttons (seats 1-9)
        dbtn_frame = ttk.LabelFrame(parent, text="Dealer Buttons (Tab = next seat)")
        dbtn_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(dbtn_frame)
        row.pack(fill=tk.X, pady=2)
        for i in range(1, 10):
            key = f"btn_{i}"
            btn = ttk.Button(
                row, text=str(i), width=3, command=lambda k=key: self.select("buttons", k)
            )
            btn.pack(side=tk.LEFT, padx=1)
            self.region_buttons[("buttons", key)] = btn

        # Card Backs (seats 2-9)
        cb_frame = ttk.LabelFrame(parent, text="Card Backs (Tab = next seat)")
        cb_frame.pack(fill=tk.X, pady=5, padx=5)
        row = ttk.Frame(cb_frame)
        row.pack(fill=tk.X, pady=2)
        for i in range(2, 10):
            key = f"card_back_{i}"
            btn = ttk.Button(
                row, text=str(i), width=3, command=lambda k=key: self.select("card_backs", k)
            )
            btn.pack(side=tk.LEFT, padx=1)
            self.region_buttons[("card_backs", key)] = btn

    def _setup_help(self, parent):
        """Set up keyboard shortcuts help."""
        help_frame = ttk.LabelFrame(parent, text="Keyboard")
        help_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Label(help_frame, text="Tab: Next seat", font=("Courier", 9)).pack(anchor=tk.W)
        ttk.Label(help_frame, text="Shift+Tab: Previous seat", font=("Courier", 9)).pack(
            anchor=tk.W
        )
        ttk.Label(help_frame, text="Arrows: Nudge (Shift=5px)", font=("Courier", 9)).pack(
            anchor=tk.W
        )
        ttk.Label(help_frame, text="N/P: Next/Prev sample", font=("Courier", 9)).pack(anchor=tk.W)
        ttk.Label(help_frame, text="S: Save | Esc: Deselect", font=("Courier", 9)).pack(anchor=tk.W)

    def load_sample(self):
        """Load and display current sample."""
        if not self.samples:
            return

        path = self.samples[self.current_idx]
        self.current_image = Image.open(path)
        self.img_w, self.img_h = self.current_image.size

        # Set reference size from first load
        if self.reference_size is None:
            self.reference_size = (self.img_w, self.img_h)
            self.data["reference_size"] = list(self.reference_size)

        self.sample_label.config(text=f"{path.name} ({self.current_idx + 1}/{len(self.samples)})")
        self.redraw()

    def redraw(self, event=None):
        """Redraw canvas with regions."""
        if not hasattr(self, "current_image"):
            return

        # Update size data
        self.data["card_slots"]["size"] = [self.card_w.get(), self.card_h.get()]
        self.data["stacks"]["size"] = [self.stack_w.get(), self.stack_h.get()]
        self.data["bets"]["size"] = [self.bet_w.get(), self.bet_h.get()]
        self.data["buttons"]["size"] = [self.btn_w.get(), self.btn_h.get()]

        # Update tilt data
        self.data["card_slots"]["hero_left"]["tilt"] = self.tilt_left.get()
        self.data["card_slots"]["hero_right"]["tilt"] = self.tilt_right.get()
        self.tilt_left_label.config(text=f"{self.tilt_left.get():+.1f}")
        self.tilt_right_label.config(text=f"{self.tilt_right.get():+.1f}")

        # Update offset data
        if hasattr(self, "offset_x"):
            self.data["offset"]["x"] = self.offset_x.get()
            self.data["offset"]["y"] = self.offset_y.get()

        # Get current offset for visual preview
        ox = self.data["offset"]["x"]
        oy = self.data["offset"]["y"]

        # Create overlay image
        overlay = self.current_image.copy()
        draw = ImageDraw.Draw(overlay, "RGBA")

        w, h = self.img_w, self.img_h

        # Draw parent regions (with offset applied)
        for key, reg in self.data["regions"].items():
            x1 = int((reg["x"] + ox) * w)
            y1 = int((reg["y"] + oy) * h)
            x2 = int((reg["x"] + ox + reg["w"]) * w)
            y2 = int((reg["y"] + oy + reg["h"]) * h)

            is_selected = self.selected == ("regions", key)
            color = COLORS["selected"] if is_selected else COLORS["parent_region"]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            draw.text((x1 + 3, y1 + 3), key[:3].upper(), fill=color)

        # Draw card slots (offset applied through parent)
        card_w, card_h = self.data["card_slots"]["size"]
        for key, slot in self.data["card_slots"].items():
            if key == "size":
                continue

            # Card slots are relative to parent region (parent has offset applied)
            if key.startswith("hero"):
                parent = self.data["regions"]["hero_cards"]
            else:
                parent = self.data["regions"]["board"]

            px = int((parent["x"] + ox) * w)
            py = int((parent["y"] + oy) * h)
            pw = int(parent["w"] * w)
            ph = int(parent["h"] * h)

            x = px + int(slot["x"] * pw)
            y = py + int(slot["y"] * ph)

            is_selected = self.selected == ("card_slots", key)
            color = COLORS["selected"] if is_selected else COLORS["card_slot"]
            draw.rectangle([x, y, x + card_w, y + card_h], outline=color, width=2)
            label = "L" if key == "hero_left" else "R" if key == "hero_right" else key[-1]
            draw.text((x + 3, y + 3), label, fill=color)

        # Draw stacks (with offset)
        stack_w, stack_h = self.data["stacks"]["size"]
        for key, pos in self.data["stacks"].items():
            if key == "size" or (pos["x"] == 0 and pos["y"] == 0):
                continue
            x = int((pos["x"] + ox) * w)
            y = int((pos["y"] + oy) * h)
            is_selected = self.selected == ("stacks", key)
            color = COLORS["selected"] if is_selected else COLORS["stack"]
            draw.rectangle([x, y, x + stack_w, y + stack_h], outline=color, width=2)
            draw.text((x + 2, y + 2), f"S{key[-1]}", fill=color)

        # Draw bets (with offset)
        bet_w, bet_h = self.data["bets"]["size"]
        for key, pos in self.data["bets"].items():
            if key == "size" or (pos["x"] == 0 and pos["y"] == 0):
                continue
            x = int((pos["x"] + ox) * w)
            y = int((pos["y"] + oy) * h)
            is_selected = self.selected == ("bets", key)
            color = COLORS["selected"] if is_selected else COLORS["bet"]
            draw.rectangle([x, y, x + bet_w, y + bet_h], outline=color, width=2)
            draw.text((x + 2, y + 2), f"B{key[-1]}", fill=color)

        # Draw buttons (with offset)
        btn_w, btn_h = self.data["buttons"]["size"]
        for key, pos in self.data["buttons"].items():
            if key == "size" or (pos["x"] == 0 and pos["y"] == 0):
                continue
            x = int((pos["x"] + ox) * w)
            y = int((pos["y"] + oy) * h)
            is_selected = self.selected == ("buttons", key)
            color = COLORS["selected"] if is_selected else COLORS["button"]
            draw.rectangle([x, y, x + btn_w, y + btn_h], outline=color, width=2)
            draw.text((x + 2, y + 2), f"D{key[-1]}", fill=color)

        # Draw card backs (with offset)
        cb_size = self.data["card_backs"]["size"]
        cb_w = int(cb_size[0] * w)
        cb_h = int(cb_size[1] * h)
        for key, pos in self.data["card_backs"].items():
            if key == "size" or (pos["x"] == 0 and pos["y"] == 0):
                continue
            x = int((pos["x"] + ox) * w)
            y = int((pos["y"] + oy) * h)
            is_selected = self.selected == ("card_backs", key)
            color = COLORS["selected"] if is_selected else COLORS["card_back"]
            draw.rectangle([x, y, x + cb_w, y + cb_h], outline=color, width=2)
            draw.text((x + 2, y + 2), f"C{key[-1]}", fill=color)

        # Display on canvas
        self.photo = ImageTk.PhotoImage(overlay)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.config(scrollregion=(0, 0, w, h))

    def select(self, category, key):
        """Select a region for editing."""
        self.selected = (category, key)

        if category == "regions":
            self.mode = "draw_rect"
            self.click_start = None
            self.status_label.config(text=f"Click two corners: {key}")
        elif category == "stacks":
            seat = key.split("_")[1]
            self.mode = "position"
            self.status_label.config(text=f"Stack {seat} - click to position (Tab=next)")
        elif category == "bets":
            seat = key.split("_")[1]
            self.mode = "position"
            self.status_label.config(text=f"Bet {seat} - click to position (Tab=next)")
        elif category == "buttons":
            seat = key.split("_")[1]
            self.mode = "position"
            self.status_label.config(text=f"Button {seat} - click to position (Tab=next)")
        elif category == "card_backs":
            seat = key.split("_")[2]
            self.mode = "position"
            self.status_label.config(text=f"Card Back {seat} - click to position (Tab=next)")
        elif category == "card_slots":
            self.mode = "position"
            self.status_label.config(text=f"{key} - click to position (Tab=next)")
        else:
            self.mode = "position"
            self.status_label.config(text=f"Click to position {key}")

        self.redraw()

    def on_click(self, event):
        """Handle mouse click."""
        x, y = event.x, event.y
        w, h = self.img_w, self.img_h

        if not self.selected:
            self.status_label.config(text="Select a region first")
            return

        category, key = self.selected

        if self.mode == "draw_rect":
            if self.click_start is None:
                # First click - record start
                self.click_start = (x, y)
                self.status_label.config(text=f"Click opposite corner for {key}")
            else:
                # Second click - complete rectangle
                x1, y1 = self.click_start
                x2, y2 = x, y

                # Normalize to 0-1
                self.data["regions"][key] = {
                    "x": min(x1, x2) / w,
                    "y": min(y1, y2) / h,
                    "w": abs(x2 - x1) / w,
                    "h": abs(y2 - y1) / h,
                }

                self.click_start = None
                self.mode = "select"
                self.status_label.config(text=f"Defined {key}")
                self.redraw()

        elif self.mode == "position":
            if category == "card_slots":
                # Card slots are relative to parent
                if key.startswith("hero"):
                    parent = self.data["regions"]["hero_cards"]
                else:
                    parent = self.data["regions"]["board"]

                px = int(parent["x"] * w)
                py = int(parent["y"] * h)
                pw = int(parent["w"] * w)
                ph = int(parent["h"] * h)

                # Convert to relative coords
                rel_x = (x - px) / pw
                rel_y = (y - py) / ph
                self.data["card_slots"][key]["x"] = max(0, min(1, rel_x))
                self.data["card_slots"][key]["y"] = max(0, min(1, rel_y))
            else:
                # Absolute positioning
                self.data[category][key]["x"] = x / w
                self.data[category][key]["y"] = y / h

            self.redraw()

    def on_drag(self, event):
        """Handle mouse drag."""
        if self.mode == "position" and self.selected:
            self.on_click(event)

    def on_release(self, event):
        """Handle mouse release."""
        pass

    def on_motion(self, event):
        """Handle mouse motion for coordinate display."""
        x, y = event.x, event.y
        w, h = self.img_w, self.img_h
        if 0 <= x < w and 0 <= y < h:
            self.pos_label.config(text=f"x={x / w:.4f}, y={y / h:.4f}")

    def on_key(self, event):
        """Handle keyboard input."""
        key = event.keysym
        state = event.state

        # Modifiers
        shift = state & 0x1
        ctrl = state & 0x4

        # Ctrl+Arrow to adjust global offset
        if ctrl and key in ("Left", "Right", "Up", "Down"):
            self.nudge_offset(key, shift)
            return

        # Save
        if key.lower() == "s":
            self.save_config()
            return

        # Navigation
        if key.lower() == "n":
            self.next_sample()
            return
        if key.lower() == "p":
            self.prev_sample()
            return

        # Escape to deselect
        if key == "Escape":
            self.selected = None
            self.mode = "select"
            self.click_start = None
            self.status_label.config(text="Deselected")
            self.redraw()
            return

        # Tab to cycle through seats
        if key == "Tab":
            if shift:
                self.prev_seat()
            else:
                self.next_seat()
            return

        # Arrow keys for nudging
        if key in ("Left", "Right", "Up", "Down"):
            self.nudge(key, shift)

    def next_seat(self):
        """Move to next seat in current category."""
        if not self.selected:
            return

        category, key = self.selected

        # Define seat sequences for each category
        if category == "stacks":
            seats = [f"stack_{i}" for i in range(1, 10)]
        elif category == "bets":
            seats = [f"bet_{i}" for i in range(1, 10)]
        elif category == "buttons":
            seats = [f"btn_{i}" for i in range(1, 10)]
        elif category == "card_backs":
            seats = [f"card_back_{i}" for i in range(2, 10)]
        elif category == "card_slots":
            seats = [
                "hero_left",
                "hero_right",
                "board_1",
                "board_2",
                "board_3",
                "board_4",
                "board_5",
            ]
        else:
            return  # No cycling for parent regions

        if key in seats:
            idx = seats.index(key)
            next_idx = (idx + 1) % len(seats)
            self.select(category, seats[next_idx])

    def prev_seat(self):
        """Move to previous seat in current category."""
        if not self.selected:
            return

        category, key = self.selected

        # Define seat sequences for each category
        if category == "stacks":
            seats = [f"stack_{i}" for i in range(1, 10)]
        elif category == "bets":
            seats = [f"bet_{i}" for i in range(1, 10)]
        elif category == "buttons":
            seats = [f"btn_{i}" for i in range(1, 10)]
        elif category == "card_backs":
            seats = [f"card_back_{i}" for i in range(2, 10)]
        elif category == "card_slots":
            seats = [
                "hero_left",
                "hero_right",
                "board_1",
                "board_2",
                "board_3",
                "board_4",
                "board_5",
            ]
        else:
            return  # No cycling for parent regions

        if key in seats:
            idx = seats.index(key)
            prev_idx = (idx - 1) % len(seats)
            self.select(category, seats[prev_idx])

    def nudge(self, direction, large=False):
        """Nudge selected region by pixels."""
        if not self.selected:
            return

        category, key = self.selected
        amount = 5 if large else 1
        w, h = self.img_w, self.img_h

        # Get current position
        if category == "regions":
            pos = self.data["regions"][key]
        elif category == "card_slots":
            pos = self.data["card_slots"][key]
        else:
            pos = self.data[category][key]

        # Convert to pixels, nudge, convert back
        if direction == "Left":
            pos["x"] -= amount / w
        elif direction == "Right":
            pos["x"] += amount / w
        elif direction == "Up":
            pos["y"] -= amount / h
        elif direction == "Down":
            pos["y"] += amount / h

        self.redraw()

    def nudge_offset(self, direction, large=False):
        """Nudge global offset by pixels."""
        amount = 0.005 if large else 0.001

        if direction == "Left":
            self.offset_x.set(self.offset_x.get() - amount)
        elif direction == "Right":
            self.offset_x.set(self.offset_x.get() + amount)
        elif direction == "Up":
            self.offset_y.set(self.offset_y.get() - amount)
        elif direction == "Down":
            self.offset_y.set(self.offset_y.get() + amount)

        self.status_label.config(
            text=f"Offset: x={self.offset_x.get():.3f}, y={self.offset_y.get():.3f}"
        )
        self.redraw()

    def prev_sample(self):
        """Go to previous sample."""
        self.current_idx = (self.current_idx - 1) % len(self.samples)
        self.load_sample()

    def next_sample(self):
        """Go to next sample."""
        self.current_idx = (self.current_idx + 1) % len(self.samples)
        self.load_sample()

    def save_config(self):
        """Save calibration to file."""
        save_calibration(self.data)
        self.status_label.config(text=f"Saved to {CALIBRATION_FILE.name}")
        print(f"[+] Saved calibration to {CALIBRATION_FILE}")


def main():
    UnifiedCalibrator()


if __name__ == "__main__":
    main()
