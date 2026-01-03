"""
Region Slot Calibrator - Consistent sizing for stack, bet, button, and pot regions

Controls:
- Click a slot button (1-9) to select it
- Click on canvas to move selected slot (centers on click)
- Drag to move selected slot
- Arrow keys to nudge selected slot (Shift for 5px)
- Set size via spinboxes or draw rectangle with "Set Size" mode
- S to save, N/P for sample navigation

Keyboard shortcuts:
- 1-9: Select stack slot
- Shift+1-9: Select bet slot
- Ctrl+1-9: Select button slot
- T: Select pot
"""

import json
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from src.paths import REGION_SLOTS_FILE, REGIONS_FILE, SAMPLES_DIR


class RegionCalibrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Region Slot Calibrator")

        # Load samples
        self.samples = sorted(SAMPLES_DIR.glob("*.png"))
        if not self.samples:
            print(f"No samples found in {SAMPLES_DIR}/")
            return

        self.current_idx = 0
        self.mode = "stack"  # 'stack', 'bet', 'button', 'pot'

        # Sizes in pixels (shared for all slots of each type)
        self.stack_width = tk.IntVar(value=90)
        self.stack_height = tk.IntVar(value=28)
        self.bet_width = tk.IntVar(value=60)
        self.bet_height = tk.IntVar(value=28)
        self.button_width = tk.IntVar(value=24)
        self.button_height = tk.IntVar(value=24)
        self.pot_width = tk.IntVar(value=75)
        self.pot_height = tk.IntVar(value=24)

        # Reference window size (saved at calibration time for scaling)
        self.reference_size = None

        # Slot positions (normalized 0-1, top-left corner)
        self.stacks = {f"stack_{i}": {"x": 0.0, "y": 0.0} for i in range(1, 10)}
        self.bets = {f"bet_{i}": {"x": 0.0, "y": 0.0} for i in range(1, 10)}
        self.buttons = {f"btn_{i}": {"x": 0.0, "y": 0.0} for i in range(1, 10)}
        self.pot = {"x": 0.5, "y": 0.35}  # Single pot region

        # Currently selected slot
        self.selected_slot = None
        self.dragging = False
        self.drag_offset = (0, 0)

        # Size definition mode
        self.defining_size = False
        self.size_click_start = None

        # Load existing regions as initial positions
        self.load_initial_positions()

        # Load saved config if exists
        self.load_config()

        self.setup_ui()

    def load_initial_positions(self):
        """Load initial positions from calibrated_regions.json"""
        if not REGIONS_FILE.exists():
            print(f"Warning: {REGIONS_FILE} not found, using defaults")
            return

        with open(REGIONS_FILE) as f:
            regions = json.load(f)

        # Extract stack positions
        for i in range(1, 10):
            key = f"stack_{i}"
            if key in regions:
                self.stacks[key] = {"x": regions[key]["x"], "y": regions[key]["y"]}

        # Extract bet positions
        for i in range(1, 10):
            key = f"bet_{i}"
            if key in regions:
                self.bets[key] = {"x": regions[key]["x"], "y": regions[key]["y"]}

        # Extract button positions (btn_1 to btn_9)
        for i in range(1, 10):
            key = f"btn_{i}"
            if key in regions:
                self.buttons[key] = {"x": regions[key]["x"], "y": regions[key]["y"]}

        # Extract pot position
        if "pot" in regions:
            self.pot = {"x": regions["pot"]["x"], "y": regions["pot"]["y"]}
            # Use pot size as default
            if self.reference_size:
                self.pot_width.set(int(regions["pot"]["w"] * self.reference_size[0]))
                self.pot_height.set(int(regions["pot"]["h"] * self.reference_size[1]))

        print(f"[+] Loaded initial positions from {REGIONS_FILE}")

    def load_config(self):
        """Load saved configuration"""
        if not REGION_SLOTS_FILE.exists():
            return

        with open(REGION_SLOTS_FILE) as f:
            data = json.load(f)

        # Load sizes
        if "stack_size" in data:
            self.stack_width.set(data["stack_size"][0])
            self.stack_height.set(data["stack_size"][1])
        if "bet_size" in data:
            self.bet_width.set(data["bet_size"][0])
            self.bet_height.set(data["bet_size"][1])
        if "button_size" in data:
            self.button_width.set(data["button_size"][0])
            self.button_height.set(data["button_size"][1])
        if "pot_size" in data:
            self.pot_width.set(data["pot_size"][0])
            self.pot_height.set(data["pot_size"][1])

        # Load reference size
        self.reference_size = data.get("reference_size")

        # Load positions
        if "stacks" in data:
            self.stacks = data["stacks"]
        if "bets" in data:
            self.bets = data["bets"]
        if "buttons" in data:
            self.buttons = data["buttons"]
        if "pot" in data:
            self.pot = data["pot"]

        print(f"[+] Loaded config from {REGION_SLOTS_FILE}")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas
        self.canvas = tk.Canvas(main_frame, bg="black", cursor="hand2")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Control panel with scrollbar for smaller screens
        ctrl_container = ttk.Frame(main_frame, width=280)
        ctrl_container.pack(side=tk.RIGHT, fill=tk.Y)
        ctrl_container.pack_propagate(False)

        # Scrollable frame
        canvas_ctrl = tk.Canvas(ctrl_container, width=260, highlightthickness=0)
        scrollbar = ttk.Scrollbar(ctrl_container, orient="vertical", command=canvas_ctrl.yview)
        ctrl = ttk.Frame(canvas_ctrl)

        ctrl.bind(
            "<Configure>", lambda e: canvas_ctrl.configure(scrollregion=canvas_ctrl.bbox("all"))
        )
        canvas_ctrl.create_window((0, 0), window=ctrl, anchor="nw")
        canvas_ctrl.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas_ctrl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(ctrl, text="Region Slot Calibrator", font=("Arial", 12, "bold")).pack(pady=5)

        # Mode selection
        mode_frame = ttk.LabelFrame(ctrl, text="Mode")
        mode_frame.pack(fill=tk.X, pady=5, padx=5)
        self.mode_var = tk.StringVar(value="stack")

        mode_row1 = ttk.Frame(mode_frame)
        mode_row1.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(
            mode_row1,
            text="Stacks",
            variable=self.mode_var,
            value="stack",
            command=self.on_mode_change,
        ).pack(side=tk.LEFT, expand=True)
        ttk.Radiobutton(
            mode_row1, text="Bets", variable=self.mode_var, value="bet", command=self.on_mode_change
        ).pack(side=tk.LEFT, expand=True)

        mode_row2 = ttk.Frame(mode_frame)
        mode_row2.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(
            mode_row2,
            text="Buttons",
            variable=self.mode_var,
            value="button",
            command=self.on_mode_change,
        ).pack(side=tk.LEFT, expand=True)
        ttk.Radiobutton(
            mode_row2, text="Pot", variable=self.mode_var, value="pot", command=self.on_mode_change
        ).pack(side=tk.LEFT, expand=True)

        # Sample navigation
        nav_frame = ttk.Frame(ctrl)
        nav_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Button(nav_frame, text="< Prev (P)", command=self.prev_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(nav_frame, text="Next (N) >", command=self.next_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        self.sample_label = ttk.Label(ctrl, text="", wraplength=250)
        self.sample_label.pack(pady=2)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Size controls
        size_frame = ttk.LabelFrame(ctrl, text="Region Sizes (pixels)")
        size_frame.pack(fill=tk.X, pady=5, padx=5)

        # Stack size
        stack_row = ttk.Frame(size_frame)
        stack_row.pack(fill=tk.X, pady=1)
        ttk.Label(stack_row, text="Stack:", width=7).pack(side=tk.LEFT)
        ttk.Spinbox(
            stack_row, from_=20, to=200, width=4, textvariable=self.stack_width, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)
        ttk.Label(stack_row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            stack_row,
            from_=10,
            to=100,
            width=4,
            textvariable=self.stack_height,
            command=self.redraw,
        ).pack(side=tk.LEFT, padx=1)

        # Bet size
        bet_row = ttk.Frame(size_frame)
        bet_row.pack(fill=tk.X, pady=1)
        ttk.Label(bet_row, text="Bet:", width=7).pack(side=tk.LEFT)
        ttk.Spinbox(
            bet_row, from_=20, to=200, width=4, textvariable=self.bet_width, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)
        ttk.Label(bet_row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            bet_row, from_=10, to=100, width=4, textvariable=self.bet_height, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)

        # Button size
        btn_row = ttk.Frame(size_frame)
        btn_row.pack(fill=tk.X, pady=1)
        ttk.Label(btn_row, text="Button:", width=7).pack(side=tk.LEFT)
        ttk.Spinbox(
            btn_row, from_=10, to=100, width=4, textvariable=self.button_width, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)
        ttk.Label(btn_row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            btn_row, from_=10, to=100, width=4, textvariable=self.button_height, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)

        # Pot size
        pot_row = ttk.Frame(size_frame)
        pot_row.pack(fill=tk.X, pady=1)
        ttk.Label(pot_row, text="Pot:", width=7).pack(side=tk.LEFT)
        ttk.Spinbox(
            pot_row, from_=20, to=200, width=4, textvariable=self.pot_width, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)
        ttk.Label(pot_row, text="x").pack(side=tk.LEFT)
        ttk.Spinbox(
            pot_row, from_=10, to=100, width=4, textvariable=self.pot_height, command=self.redraw
        ).pack(side=tk.LEFT, padx=1)

        # Set size button
        size_btn_row = ttk.Frame(size_frame)
        size_btn_row.pack(fill=tk.X, pady=2)
        self.set_size_btn = ttk.Button(
            size_btn_row, text="Draw to Set Size", command=self.start_size_definition
        )
        self.set_size_btn.pack(fill=tk.X)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Slot selection buttons
        slots_frame = ttk.LabelFrame(ctrl, text="Select Slot")
        slots_frame.pack(fill=tk.X, pady=5, padx=5)

        # Stack buttons - split into two rows
        stack_btn_row1 = ttk.Frame(slots_frame)
        stack_btn_row1.pack(fill=tk.X, pady=1)
        ttk.Label(stack_btn_row1, text="Stack:", width=7).pack(side=tk.LEFT)
        for i in range(1, 6):
            btn = ttk.Button(
                stack_btn_row1,
                text=str(i),
                width=2,
                command=lambda s=i: self.select_slot(f"stack_{s}"),
            )
            btn.pack(side=tk.LEFT, padx=1)

        stack_btn_row2 = ttk.Frame(slots_frame)
        stack_btn_row2.pack(fill=tk.X, pady=1)
        ttk.Label(stack_btn_row2, text="", width=7).pack(side=tk.LEFT)
        for i in range(6, 10):
            btn = ttk.Button(
                stack_btn_row2,
                text=str(i),
                width=2,
                command=lambda s=i: self.select_slot(f"stack_{s}"),
            )
            btn.pack(side=tk.LEFT, padx=1)

        # Bet buttons - split into two rows
        bet_btn_row1 = ttk.Frame(slots_frame)
        bet_btn_row1.pack(fill=tk.X, pady=1)
        ttk.Label(bet_btn_row1, text="Bet:", width=7).pack(side=tk.LEFT)
        for i in range(1, 6):
            btn = ttk.Button(
                bet_btn_row1, text=str(i), width=2, command=lambda s=i: self.select_slot(f"bet_{s}")
            )
            btn.pack(side=tk.LEFT, padx=1)

        bet_btn_row2 = ttk.Frame(slots_frame)
        bet_btn_row2.pack(fill=tk.X, pady=1)
        ttk.Label(bet_btn_row2, text="", width=7).pack(side=tk.LEFT)
        for i in range(6, 10):
            btn = ttk.Button(
                bet_btn_row2, text=str(i), width=2, command=lambda s=i: self.select_slot(f"bet_{s}")
            )
            btn.pack(side=tk.LEFT, padx=1)

        # Button (dealer) buttons - split into two rows
        btn_btn_row1 = ttk.Frame(slots_frame)
        btn_btn_row1.pack(fill=tk.X, pady=1)
        ttk.Label(btn_btn_row1, text="Button:", width=7).pack(side=tk.LEFT)
        for i in range(1, 6):
            btn = ttk.Button(
                btn_btn_row1, text=str(i), width=2, command=lambda s=i: self.select_slot(f"btn_{s}")
            )
            btn.pack(side=tk.LEFT, padx=1)

        btn_btn_row2 = ttk.Frame(slots_frame)
        btn_btn_row2.pack(fill=tk.X, pady=1)
        ttk.Label(btn_btn_row2, text="", width=7).pack(side=tk.LEFT)
        for i in range(6, 10):
            btn = ttk.Button(
                btn_btn_row2, text=str(i), width=2, command=lambda s=i: self.select_slot(f"btn_{s}")
            )
            btn.pack(side=tk.LEFT, padx=1)

        # Pot button
        pot_btn_row = ttk.Frame(slots_frame)
        pot_btn_row.pack(fill=tk.X, pady=2)
        ttk.Label(pot_btn_row, text="Pot:", width=7).pack(side=tk.LEFT)
        ttk.Button(
            pot_btn_row, text="Pot (T)", width=8, command=lambda: self.select_slot("pot")
        ).pack(side=tk.LEFT, padx=1)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Keyboard shortcuts help
        help_frame = ttk.LabelFrame(ctrl, text="Keyboard Shortcuts")
        help_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Label(help_frame, text="1-9: Stacks | Shift+1-9: Bets", font=("Courier", 8)).pack(
            anchor=tk.W
        )
        ttk.Label(help_frame, text="Ctrl+1-9: Buttons | T: Pot", font=("Courier", 8)).pack(
            anchor=tk.W
        )
        ttk.Label(help_frame, text="Arrows: Nudge | Shift+Arrows: 5px", font=("Courier", 8)).pack(
            anchor=tk.W
        )

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Status
        self.status_label = ttk.Label(
            ctrl, text="Click slot button, then click/drag", wraplength=250, justify=tk.CENTER
        )
        self.status_label.pack(pady=5)

        # Position display
        pos_frame = ttk.Frame(ctrl)
        pos_frame.pack(fill=tk.X, padx=5)
        ttk.Label(pos_frame, text="Position:").pack(side=tk.LEFT)
        self.pos_label = ttk.Label(pos_frame, text="--", font=("Courier", 10))
        self.pos_label.pack(side=tk.LEFT, padx=5)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Save button
        ttk.Button(ctrl, text="Save (S)", command=self.save_config).pack(pady=5, fill=tk.X, padx=5)

        # Export to old format
        ttk.Button(
            ctrl, text="Export to calibrated_regions.json", command=self.export_to_regions
        ).pack(pady=5, fill=tk.X, padx=5)

        # Bindings
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.root.bind("<Key>", self.on_key)

        # Mouse wheel for scrolling control panel
        def _on_mousewheel(event):
            canvas_ctrl.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas_ctrl.bind_all("<MouseWheel>", _on_mousewheel)

        self.load_sample()

    def on_mode_change(self):
        self.mode = self.mode_var.get()
        self.selected_slot = None
        self.redraw()

    def get_slots_for_type(self, slot_type):
        """Get the slots dictionary for a given type"""
        if slot_type == "stack":
            return self.stacks
        elif slot_type == "bet":
            return self.bets
        elif slot_type == "button" or slot_type == "btn":
            return self.buttons
        elif slot_type == "pot":
            return {"pot": self.pot}
        return {}

    def get_slot_type(self, slot_name):
        """Get the type of a slot from its name"""
        if slot_name.startswith("stack"):
            return "stack"
        elif slot_name.startswith("bet"):
            return "bet"
        elif slot_name.startswith("btn"):
            return "button"
        elif slot_name == "pot":
            return "pot"
        return "stack"

    def select_slot(self, slot_name):
        self.selected_slot = slot_name

        # Switch mode to match slot type
        slot_type = self.get_slot_type(slot_name)
        self.mode = slot_type
        self.mode_var.set(slot_type)

        # Get position
        if slot_name == "pot":
            slot = self.pot
        elif slot_name.startswith("stack"):
            slot = self.stacks.get(slot_name, {"x": 0, "y": 0})
        elif slot_name.startswith("bet"):
            slot = self.bets.get(slot_name, {"x": 0, "y": 0})
        elif slot_name.startswith("btn"):
            slot = self.buttons.get(slot_name, {"x": 0, "y": 0})
        else:
            slot = {"x": 0, "y": 0}

        x_pct = slot.get("x", 0) * 100
        y_pct = slot.get("y", 0) * 100

        self.status_label.config(text=f"Selected: {slot_name}")
        self.pos_label.config(text=f"x={x_pct:.1f}% y={y_pct:.1f}%")
        self.redraw()

    def start_size_definition(self):
        """Enter size definition mode"""
        self.defining_size = True
        self.size_click_start = None
        self.set_size_btn.config(text="Click & drag rectangle...")
        self.status_label.config(text=f"Draw rectangle to set {self.mode} size")
        self.canvas.config(cursor="crosshair")

    def load_sample(self):
        if not self.samples:
            return

        path = self.samples[self.current_idx]
        self.full_image = Image.open(path)
        self.img_width, self.img_height = self.full_image.size

        # Store reference size from first sample
        if self.reference_size is None:
            self.reference_size = [self.img_width, self.img_height]
            print(f"[+] Reference size set to {self.img_width}x{self.img_height}")

        # Display image (no scaling for full table view)
        self.display_image = self.full_image.copy()

        self.canvas.config(width=self.img_width, height=self.img_height)
        self.sample_label.config(
            text=f"{self.current_idx + 1}/{len(self.samples)} | {path.name}\n[{self.img_width}x{self.img_height}]"
        )

        self.redraw()

    def redraw(self):
        img = self.display_image.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # Get current sizes
        stack_w = self.stack_width.get()
        stack_h = self.stack_height.get()
        bet_w = self.bet_width.get()
        bet_h = self.bet_height.get()
        btn_w = self.button_width.get()
        btn_h = self.button_height.get()
        pot_w = self.pot_width.get()
        pot_h = self.pot_height.get()

        # Draw all stacks (cyan)
        for i in range(1, 10):
            slot_name = f"stack_{i}"
            slot = self.stacks.get(slot_name, {"x": 0, "y": 0})
            x = int(slot.get("x", 0) * self.img_width)
            y = int(slot.get("y", 0) * self.img_height)

            color = "#FFFFFF" if slot_name == self.selected_slot else "#00FFFF"
            outline_width = 3 if slot_name == self.selected_slot else 1
            fill = color + "40" if slot_name == self.selected_slot else color + "15"

            draw.rectangle(
                [x, y, x + stack_w, y + stack_h], outline=color, fill=fill, width=outline_width
            )
            draw.text((x + 2, y + 2), f"S{i}", fill=color)

        # Draw all bets (orange)
        for i in range(1, 10):
            slot_name = f"bet_{i}"
            slot = self.bets.get(slot_name, {"x": 0, "y": 0})
            x = int(slot.get("x", 0) * self.img_width)
            y = int(slot.get("y", 0) * self.img_height)

            color = "#FFFFFF" if slot_name == self.selected_slot else "#FFA500"
            outline_width = 3 if slot_name == self.selected_slot else 1
            fill = color + "40" if slot_name == self.selected_slot else color + "15"

            draw.rectangle(
                [x, y, x + bet_w, y + bet_h], outline=color, fill=fill, width=outline_width
            )
            draw.text((x + 2, y + 2), f"B{i}", fill=color)

        # Draw all buttons (green)
        for i in range(1, 10):
            slot_name = f"btn_{i}"
            slot = self.buttons.get(slot_name, {"x": 0, "y": 0})
            x = int(slot.get("x", 0) * self.img_width)
            y = int(slot.get("y", 0) * self.img_height)

            color = "#FFFFFF" if slot_name == self.selected_slot else "#00FF00"
            outline_width = 3 if slot_name == self.selected_slot else 1
            fill = color + "40" if slot_name == self.selected_slot else color + "15"

            draw.rectangle(
                [x, y, x + btn_w, y + btn_h], outline=color, fill=fill, width=outline_width
            )
            draw.text((x + 2, y + 2), f"D{i}", fill=color)

        # Draw pot (yellow)
        x = int(self.pot.get("x", 0) * self.img_width)
        y = int(self.pot.get("y", 0) * self.img_height)
        color = "#FFFFFF" if self.selected_slot == "pot" else "#FFFF00"
        outline_width = 3 if self.selected_slot == "pot" else 2
        fill = color + "40" if self.selected_slot == "pot" else color + "20"

        draw.rectangle([x, y, x + pot_w, y + pot_h], outline=color, fill=fill, width=outline_width)
        draw.text((x + 2, y + 2), "POT", fill=color)

        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def get_slot_size(self, slot_name):
        """Get size for a specific slot"""
        if slot_name.startswith("stack"):
            return self.stack_width.get(), self.stack_height.get()
        elif slot_name.startswith("bet"):
            return self.bet_width.get(), self.bet_height.get()
        elif slot_name.startswith("btn"):
            return self.button_width.get(), self.button_height.get()
        elif slot_name == "pot":
            return self.pot_width.get(), self.pot_height.get()
        return 50, 30

    def get_current_size(self):
        """Get size for current mode"""
        if self.mode == "stack":
            return self.stack_width.get(), self.stack_height.get()
        elif self.mode == "bet":
            return self.bet_width.get(), self.bet_height.get()
        elif self.mode == "button":
            return self.button_width.get(), self.button_height.get()
        elif self.mode == "pot":
            return self.pot_width.get(), self.pot_height.get()
        return 50, 30

    def on_mouse_down(self, event):
        if self.defining_size:
            # Start size definition rectangle
            self.size_click_start = (event.x, event.y)
            return

        if not self.selected_slot:
            return

        # Check if clicking on the selected slot
        if self.selected_slot == "pot":
            slot = self.pot
        elif self.selected_slot.startswith("stack"):
            slot = self.stacks.get(self.selected_slot, {"x": 0, "y": 0})
        elif self.selected_slot.startswith("bet"):
            slot = self.bets.get(self.selected_slot, {"x": 0, "y": 0})
        elif self.selected_slot.startswith("btn"):
            slot = self.buttons.get(self.selected_slot, {"x": 0, "y": 0})
        else:
            slot = {"x": 0, "y": 0}

        x = int(slot.get("x", 0) * self.img_width)
        y = int(slot.get("y", 0) * self.img_height)
        w, h = self.get_slot_size(self.selected_slot)

        if x <= event.x <= x + w and y <= event.y <= y + h:
            self.dragging = True
            self.drag_offset = (event.x - x, event.y - y)
        else:
            # Click elsewhere - move slot there (centered)
            self.move_slot_to(event.x, event.y)

    def on_mouse_drag(self, event):
        if self.defining_size and self.size_click_start:
            # Preview rectangle
            self.redraw()
            x1, y1 = self.size_click_start
            x2, y2 = event.x, event.y
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#FF00FF", width=2)
            # Show dimensions
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            self.status_label.config(text=f"Size: {w} x {h} pixels")
            return

        if self.dragging and self.selected_slot:
            new_x = event.x - self.drag_offset[0]
            new_y = event.y - self.drag_offset[1]
            self.move_slot_to(new_x, new_y, use_center=False)

    def on_mouse_up(self, event):
        if self.defining_size and self.size_click_start:
            # Apply size
            x1, y1 = self.size_click_start
            x2, y2 = event.x, event.y
            w = abs(x2 - x1)
            h = abs(y2 - y1)

            if w > 5 and h > 5:  # Minimum size
                if self.mode == "stack":
                    self.stack_width.set(w)
                    self.stack_height.set(h)
                elif self.mode == "bet":
                    self.bet_width.set(w)
                    self.bet_height.set(h)
                elif self.mode == "button":
                    self.button_width.set(w)
                    self.button_height.set(h)
                elif self.mode == "pot":
                    self.pot_width.set(w)
                    self.pot_height.set(h)
                self.status_label.config(text=f"Set {self.mode} size to {w}x{h}")

            self.defining_size = False
            self.size_click_start = None
            self.set_size_btn.config(text="Draw to Set Size")
            self.canvas.config(cursor="hand2")
            self.redraw()
            return

        self.dragging = False

    def move_slot_to(self, px, py, use_center=True):
        if not self.selected_slot:
            return

        w, h = self.get_slot_size(self.selected_slot)

        if use_center:
            # Center the slot on click position
            px -= w / 2
            py -= h / 2

        # Clamp to bounds
        px = max(0, min(px, self.img_width - w))
        py = max(0, min(py, self.img_height - h))

        # Convert to normalized
        nx = px / self.img_width
        ny = py / self.img_height

        # Update slot
        if self.selected_slot == "pot":
            self.pot["x"] = round(nx, 4)
            self.pot["y"] = round(ny, 4)
        elif self.selected_slot.startswith("stack"):
            self.stacks[self.selected_slot]["x"] = round(nx, 4)
            self.stacks[self.selected_slot]["y"] = round(ny, 4)
        elif self.selected_slot.startswith("bet"):
            self.bets[self.selected_slot]["x"] = round(nx, 4)
            self.bets[self.selected_slot]["y"] = round(ny, 4)
        elif self.selected_slot.startswith("btn"):
            self.buttons[self.selected_slot]["x"] = round(nx, 4)
            self.buttons[self.selected_slot]["y"] = round(ny, 4)

        self.pos_label.config(text=f"x={nx * 100:.1f}% y={ny * 100:.1f}%")
        self.redraw()

    def nudge_slot(self, dx, dy):
        if not self.selected_slot:
            return

        # Get slot
        if self.selected_slot == "pot":
            slot = self.pot
        elif self.selected_slot.startswith("stack"):
            slot = self.stacks[self.selected_slot]
        elif self.selected_slot.startswith("bet"):
            slot = self.bets[self.selected_slot]
        elif self.selected_slot.startswith("btn"):
            slot = self.buttons[self.selected_slot]
        else:
            return

        # Convert pixel delta to normalized
        dx_norm = dx / self.img_width
        dy_norm = dy / self.img_height

        new_x = max(0, min(1, slot["x"] + dx_norm))
        new_y = max(0, min(1, slot["y"] + dy_norm))

        slot["x"] = round(new_x, 4)
        slot["y"] = round(new_y, 4)

        self.pos_label.config(text=f"x={new_x * 100:.1f}% y={new_y * 100:.1f}%")
        self.redraw()

    def on_key(self, event):
        key = event.keysym.lower()
        shift = event.state & 0x1
        ctrl = event.state & 0x4

        step = 5 if shift else 1

        if key == "left":
            self.nudge_slot(-step, 0)
        elif key == "right":
            self.nudge_slot(step, 0)
        elif key == "up":
            self.nudge_slot(0, -step)
        elif key == "down":
            self.nudge_slot(0, step)
        elif key == "n":
            self.next_sample()
        elif key == "p":
            self.prev_sample()
        elif key == "s":
            self.save_config()
        elif key == "q":
            self.root.quit()
        elif key == "t":
            self.select_slot("pot")
        elif key in "123456789":
            idx = int(key)
            if ctrl:
                self.select_slot(f"btn_{idx}")
            elif shift:
                self.select_slot(f"bet_{idx}")
            else:
                self.select_slot(f"stack_{idx}")

    def next_sample(self):
        self.current_idx = (self.current_idx + 1) % len(self.samples)
        self.load_sample()

    def prev_sample(self):
        self.current_idx = (self.current_idx - 1) % len(self.samples)
        self.load_sample()

    def save_config(self):
        # Ensure config directory exists
        REGION_SLOTS_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "reference_size": self.reference_size,
            "stack_size": [self.stack_width.get(), self.stack_height.get()],
            "bet_size": [self.bet_width.get(), self.bet_height.get()],
            "button_size": [self.button_width.get(), self.button_height.get()],
            "pot_size": [self.pot_width.get(), self.pot_height.get()],
            "stacks": self.stacks,
            "bets": self.bets,
            "buttons": self.buttons,
            "pot": self.pot,
        }
        with open(REGION_SLOTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Saved to {REGION_SLOTS_FILE}")
        print(f"    Stack size: {self.stack_width.get()}x{self.stack_height.get()}")
        print(f"    Bet size: {self.bet_width.get()}x{self.bet_height.get()}")
        print(f"    Button size: {self.button_width.get()}x{self.button_height.get()}")
        print(f"    Pot size: {self.pot_width.get()}x{self.pot_height.get()}")
        print(f"    Reference: {self.reference_size[0]}x{self.reference_size[1]}")
        self.status_label.config(text="Saved!")

    def export_to_regions(self):
        """Export to calibrated_regions.json format for compatibility"""
        if not REGIONS_FILE.exists():
            regions = {}
        else:
            with open(REGIONS_FILE) as f:
                regions = json.load(f)

        ref_w, ref_h = self.reference_size

        # Calculate normalized sizes
        stack_w_norm = self.stack_width.get() / ref_w
        stack_h_norm = self.stack_height.get() / ref_h
        bet_w_norm = self.bet_width.get() / ref_w
        bet_h_norm = self.bet_height.get() / ref_h
        btn_w_norm = self.button_width.get() / ref_w
        btn_h_norm = self.button_height.get() / ref_h
        pot_w_norm = self.pot_width.get() / ref_w
        pot_h_norm = self.pot_height.get() / ref_h

        # Update stack regions
        for i in range(1, 10):
            key = f"stack_{i}"
            slot = self.stacks.get(key, {"x": 0, "y": 0})
            regions[key] = {
                "x": round(slot["x"], 4),
                "y": round(slot["y"], 4),
                "w": round(stack_w_norm, 4),
                "h": round(stack_h_norm, 4),
            }

        # Update bet regions
        for i in range(1, 10):
            key = f"bet_{i}"
            slot = self.bets.get(key, {"x": 0, "y": 0})
            regions[key] = {
                "x": round(slot["x"], 4),
                "y": round(slot["y"], 4),
                "w": round(bet_w_norm, 4),
                "h": round(bet_h_norm, 4),
            }

        # Update button regions
        for i in range(1, 10):
            key = f"btn_{i}"
            slot = self.buttons.get(key, {"x": 0, "y": 0})
            regions[key] = {
                "x": round(slot["x"], 4),
                "y": round(slot["y"], 4),
                "w": round(btn_w_norm, 4),
                "h": round(btn_h_norm, 4),
            }

        # Update pot region
        regions["pot"] = {
            "x": round(self.pot["x"], 4),
            "y": round(self.pot["y"], 4),
            "w": round(pot_w_norm, 4),
            "h": round(pot_h_norm, 4),
        }

        with open(REGIONS_FILE, "w") as f:
            json.dump(regions, f, indent=2)

        print(f"[+] Exported to {REGIONS_FILE}")
        self.status_label.config(text=f"Exported to {REGIONS_FILE.name}!")

    def run(self):
        if self.samples:
            self.root.mainloop()


def main():
    print("Region Slot Calibrator")
    print("=" * 40)
    print("Modes: Stacks, Bets, Buttons, Pot")
    print()
    print("Keyboard shortcuts:")
    print("  1-9: Select stack slot")
    print("  Shift+1-9: Select bet slot")
    print("  Ctrl+1-9: Select button (dealer) slot")
    print("  T: Select pot")
    print("  Arrows: Nudge 1px (Shift=5px)")
    print("  N/P: Navigate samples")
    print("  S: Save")
    print()

    calibrator = RegionCalibrator()
    calibrator.run()


if __name__ == "__main__":
    main()
