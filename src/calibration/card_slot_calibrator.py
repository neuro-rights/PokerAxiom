"""
Card Slot Calibrator - Unified size with tilt support

Controls:
- Click a slot button to select it
- Drag on canvas to move selected slot
- Arrow keys to nudge selected slot (Shift for 5px)
- Set card size via spinboxes
- Tilt sliders for hero cards (left/right separate)
"""

import json
import math
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from src.paths import CARD_SLOTS_FILE, REGIONS_FILE, SAMPLES_DIR


class CardSlotCalibrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Card Slot Calibrator")

        # Load samples
        self.samples = sorted(SAMPLES_DIR.glob("*.png"))
        if not self.samples:
            print(f"No samples found in {SAMPLES_DIR}/")
            return

        # Load parent regions
        if not REGIONS_FILE.exists():
            print(f"Error: {REGIONS_FILE} not found")
            return

        with open(REGIONS_FILE) as f:
            self.parent_regions = json.load(f)

        self.current_idx = 0
        self.mode = "hero"  # 'hero' or 'board'

        # Card size in pixels
        self.card_width = tk.IntVar(value=50)
        self.card_height = tk.IntVar(value=70)

        # Slots config - stores top-left corner positions (normalized 0-1)
        self.slots = {
            "hero_left": {"x": 0.05, "y": 0.1, "tilt": 0},
            "hero_right": {"x": 0.55, "y": 0.1, "tilt": 0},
            "board_1": {"x": 0.0, "y": 0.0},
            "board_2": {"x": 0.2, "y": 0.0},
            "board_3": {"x": 0.4, "y": 0.0},
            "board_4": {"x": 0.6, "y": 0.0},
            "board_5": {"x": 0.8, "y": 0.0},
        }

        # Currently selected slot
        self.selected_slot = None
        self.dragging = False
        self.drag_offset = (0, 0)

        # Reference window size (saved at calibration time for scaling)
        self.reference_size = None

        # Load saved config
        if CARD_SLOTS_FILE.exists():
            with open(CARD_SLOTS_FILE) as f:
                data = json.load(f)
                self.card_width.set(data.get("card_size", [50, 70])[0])
                self.card_height.set(data.get("card_size", [50, 70])[1])
                self.slots = data.get("slots", self.slots)
                self.reference_size = data.get("reference_size")
                print(f"[+] Loaded from {CARD_SLOTS_FILE}")

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas
        self.canvas = tk.Canvas(main_frame, bg="black", cursor="hand2")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Control panel
        ctrl = ttk.Frame(main_frame, width=240)
        ctrl.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        ctrl.pack_propagate(False)

        ttk.Label(ctrl, text="Card Slot Calibrator", font=("Arial", 12, "bold")).pack(pady=5)

        # Card size controls
        size_frame = ttk.LabelFrame(ctrl, text="Card Size (pixels)")
        size_frame.pack(fill=tk.X, pady=5, padx=5)

        row1 = ttk.Frame(size_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Width:").pack(side=tk.LEFT)
        ttk.Spinbox(
            row1, from_=20, to=200, width=6, textvariable=self.card_width, command=self.redraw
        ).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="Height:").pack(side=tk.LEFT)
        ttk.Spinbox(
            row1, from_=20, to=200, width=6, textvariable=self.card_height, command=self.redraw
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Mode selection
        mode_frame = ttk.LabelFrame(ctrl, text="Region")
        mode_frame.pack(fill=tk.X, pady=5, padx=5)
        self.mode_var = tk.StringVar(value="hero")
        ttk.Radiobutton(
            mode_frame,
            text="Hero Cards (H)",
            variable=self.mode_var,
            value="hero",
            command=self.on_mode_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            mode_frame,
            text="Board (B)",
            variable=self.mode_var,
            value="board",
            command=self.on_mode_change,
        ).pack(anchor=tk.W)

        # Sample navigation
        nav_frame = ttk.Frame(ctrl)
        nav_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Button(nav_frame, text="< Prev", command=self.prev_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(nav_frame, text="Next >", command=self.next_sample).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        self.sample_label = ttk.Label(ctrl, text="", wraplength=220)
        self.sample_label.pack(pady=2)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Slot buttons
        slots_frame = ttk.LabelFrame(ctrl, text="Select Slot (click to select, then drag)")
        slots_frame.pack(fill=tk.X, pady=5, padx=5)

        # Hero slots
        hero_row = ttk.Frame(slots_frame)
        hero_row.pack(fill=tk.X, pady=2)
        ttk.Label(hero_row, text="Hero:").pack(side=tk.LEFT)
        self.btn_hero_left = ttk.Button(
            hero_row, text="Left (L)", command=lambda: self.select_slot("hero_left")
        )
        self.btn_hero_left.pack(side=tk.LEFT, padx=2)
        self.btn_hero_right = ttk.Button(
            hero_row, text="Right (R)", command=lambda: self.select_slot("hero_right")
        )
        self.btn_hero_right.pack(side=tk.LEFT, padx=2)

        # Board slots
        board_row = ttk.Frame(slots_frame)
        board_row.pack(fill=tk.X, pady=2)
        ttk.Label(board_row, text="Board:").pack(side=tk.LEFT)
        for i in range(1, 6):
            btn = ttk.Button(
                board_row, text=str(i), width=3, command=lambda s=i: self.select_slot(f"board_{s}")
            )
            btn.pack(side=tk.LEFT, padx=1)

        # Tilt controls (hero only)
        self.tilt_frame = ttk.LabelFrame(ctrl, text="Hero Tilt (degrees)")
        self.tilt_frame.pack(fill=tk.X, pady=5, padx=5)

        # Left tilt
        left_row = ttk.Frame(self.tilt_frame)
        left_row.pack(fill=tk.X)
        ttk.Label(left_row, text="Left:", width=6).pack(side=tk.LEFT)
        self.tilt_left_var = tk.DoubleVar(value=0)
        self.tilt_left_scale = ttk.Scale(
            left_row,
            from_=-15,
            to=15,
            variable=self.tilt_left_var,
            orient=tk.HORIZONTAL,
            command=lambda v: self.on_tilt_change("left"),
        )
        self.tilt_left_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tilt_left_label = ttk.Label(left_row, text="0.0", width=5)
        self.tilt_left_label.pack(side=tk.LEFT)

        # Right tilt
        right_row = ttk.Frame(self.tilt_frame)
        right_row.pack(fill=tk.X)
        ttk.Label(right_row, text="Right:", width=6).pack(side=tk.LEFT)
        self.tilt_right_var = tk.DoubleVar(value=0)
        self.tilt_right_scale = ttk.Scale(
            right_row,
            from_=-15,
            to=15,
            variable=self.tilt_right_var,
            orient=tk.HORIZONTAL,
            command=lambda v: self.on_tilt_change("right"),
        )
        self.tilt_right_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tilt_right_label = ttk.Label(right_row, text="0.0", width=5)
        self.tilt_right_label.pack(side=tk.LEFT)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Status / selected slot info
        self.status_label = ttk.Label(
            ctrl,
            text="Click a slot button, then drag on image\nArrow keys to nudge (Shift=5px)",
            wraplength=220,
            justify=tk.CENTER,
        )
        self.status_label.pack(pady=5)

        # Selected slot position display
        pos_frame = ttk.Frame(ctrl)
        pos_frame.pack(fill=tk.X, padx=5)
        ttk.Label(pos_frame, text="Position:").pack(side=tk.LEFT)
        self.pos_label = ttk.Label(pos_frame, text="--", font=("Courier", 10))
        self.pos_label.pack(side=tk.LEFT, padx=5)

        ttk.Separator(ctrl, orient="horizontal").pack(fill=tk.X, pady=5)

        # Save button
        ttk.Button(ctrl, text="Save (S)", command=self.save_config).pack(pady=10, fill=tk.X, padx=5)

        # Bindings
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<KeyRelease>", self.on_key)

        self.load_sample()

    def select_slot(self, slot_name):
        self.selected_slot = slot_name
        slot = self.slots.get(slot_name, {})
        x_pct = slot.get("x", 0) * 100
        y_pct = slot.get("y", 0) * 100
        self.status_label.config(text=f"Selected: {slot_name}")
        self.pos_label.config(text=f"x={x_pct:.1f}% y={y_pct:.1f}%")
        self.redraw()

    def on_mode_change(self):
        self.mode = self.mode_var.get()
        self.selected_slot = None
        self.load_sample()

    def on_tilt_change(self, side):
        if side == "left":
            tilt = self.tilt_left_var.get()
            self.tilt_left_label.config(text=f"{tilt:.1f}")
            self.slots["hero_left"]["tilt"] = tilt
        else:
            tilt = self.tilt_right_var.get()
            self.tilt_right_label.config(text=f"{tilt:.1f}")
            self.slots["hero_right"]["tilt"] = tilt
        self.redraw()

    def get_parent_region(self):
        if self.mode == "hero":
            return self.parent_regions.get("hero_cards", {"x": 0, "y": 0, "w": 1, "h": 1})
        else:
            return self.parent_regions.get("board", {"x": 0, "y": 0, "w": 1, "h": 1})

    def load_sample(self):
        if not self.samples:
            return

        path = self.samples[self.current_idx]
        full_image = Image.open(path)
        full_w, full_h = full_image.size

        # Store reference size from first sample (or update if not set)
        if self.reference_size is None:
            self.reference_size = [full_w, full_h]
            print(f"[+] Reference size set to {full_w}x{full_h}")

        # Crop to parent region
        parent = self.get_parent_region()
        x1 = int(parent["x"] * full_w)
        y1 = int(parent["y"] * full_h)
        x2 = int((parent["x"] + parent["w"]) * full_w)
        y2 = int((parent["y"] + parent["h"]) * full_h)

        self.cropped_image = full_image.crop((x1, y1, x2, y2))
        self.crop_w, self.crop_h = self.cropped_image.size

        # Scale for visibility (at least 3x)
        self.scale = max(3, 500 // max(self.crop_w, self.crop_h))
        new_w = self.crop_w * self.scale
        new_h = self.crop_h * self.scale
        self.display_image = self.cropped_image.resize((new_w, new_h), Image.NEAREST)
        self.img_width, self.img_height = new_w, new_h

        self.canvas.config(width=self.img_width, height=self.img_height)
        region_name = "hero_cards" if self.mode == "hero" else "board"
        self.sample_label.config(
            text=f"{self.current_idx + 1}/{len(self.samples)} | {path.name}\n[{region_name}: {self.crop_w}x{self.crop_h}]"
        )

        # Update tilt sliders
        if self.mode == "hero":
            self.tilt_left_var.set(self.slots.get("hero_left", {}).get("tilt", 0))
            self.tilt_right_var.set(self.slots.get("hero_right", {}).get("tilt", 0))
            self.tilt_left_label.config(text=f"{self.tilt_left_var.get():.1f}")
            self.tilt_right_label.config(text=f"{self.tilt_right_var.get():.1f}")

        self.redraw()

    def redraw(self):
        img = self.display_image.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        card_w = self.card_width.get() * self.scale
        card_h = self.card_height.get() * self.scale

        # Draw slots for current mode
        if self.mode == "hero":
            slots_to_draw = ["hero_left", "hero_right"]
            colors = ["#FF4444", "#44FF44"]
        else:
            slots_to_draw = [f"board_{i}" for i in range(1, 6)]
            colors = ["#FF4444", "#44FF44", "#4444FF", "#FFFF44", "#FF44FF"]

        for i, slot_name in enumerate(slots_to_draw):
            slot = self.slots.get(slot_name, {})
            x = slot.get("x", 0) * self.img_width
            y = slot.get("y", 0) * self.img_height
            tilt = slot.get("tilt", 0)

            color = colors[i % len(colors)]
            outline_width = 3 if slot_name == self.selected_slot else 2
            if slot_name == self.selected_slot:
                color = "#FFFFFF"

            if tilt != 0 and self.mode == "hero":
                # Draw tilted rectangle
                corners = self.get_tilted_corners(x, y, card_w, card_h, tilt)
                draw.polygon(corners, outline=color, fill=color + "30")
            else:
                # Draw normal rectangle
                draw.rectangle(
                    [x, y, x + card_w, y + card_h],
                    outline=color,
                    fill=color + "30",
                    width=outline_width,
                )

            # Label
            label = slot_name.replace("hero_", "H").replace("board_", "B")
            draw.text((x + 4, y + 4), label, fill=color)

        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def get_tilted_corners(self, x, y, w, h, tilt_deg):
        """Get corners of tilted rectangle"""
        cx, cy = x + w / 2, y + h / 2
        angle = math.radians(tilt_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        corners_rel = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        corners = []
        for rx, ry in corners_rel:
            nx = cx + rx * cos_a - ry * sin_a
            ny = cy + rx * sin_a + ry * cos_a
            corners.append((nx, ny))
        return corners

    def on_mouse_down(self, event):
        if not self.selected_slot:
            return

        # Check if clicking on the selected slot
        slot = self.slots.get(self.selected_slot, {})
        x = slot.get("x", 0) * self.img_width
        y = slot.get("y", 0) * self.img_height
        w = self.card_width.get() * self.scale
        h = self.card_height.get() * self.scale

        if x <= event.x <= x + w and y <= event.y <= y + h:
            self.dragging = True
            self.drag_offset = (event.x - x, event.y - y)
        else:
            # Click elsewhere - move slot there
            self.move_slot_to(event.x, event.y)

    def on_mouse_drag(self, event):
        if self.dragging and self.selected_slot:
            new_x = event.x - self.drag_offset[0]
            new_y = event.y - self.drag_offset[1]
            self.move_slot_to(new_x, new_y, use_center=False)

    def on_mouse_up(self, event):
        self.dragging = False

    def move_slot_to(self, px, py, use_center=True):
        if not self.selected_slot:
            return

        if use_center:
            # Center the slot on click position
            w = self.card_width.get() * self.scale
            h = self.card_height.get() * self.scale
            px -= w / 2
            py -= h / 2

        # Clamp to bounds
        px = max(0, min(px, self.img_width - self.card_width.get() * self.scale))
        py = max(0, min(py, self.img_height - self.card_height.get() * self.scale))

        # Convert to normalized
        nx = px / self.img_width
        ny = py / self.img_height

        self.slots[self.selected_slot]["x"] = round(nx, 4)
        self.slots[self.selected_slot]["y"] = round(ny, 4)

        self.pos_label.config(text=f"x={nx * 100:.1f}% y={ny * 100:.1f}%")
        self.redraw()

    def nudge_slot(self, dx, dy):
        if not self.selected_slot:
            return

        slot = self.slots[self.selected_slot]
        # Convert pixel delta to normalized
        dx_norm = dx / self.crop_w
        dy_norm = dy / self.crop_h

        new_x = max(0, min(1, slot["x"] + dx_norm))
        new_y = max(0, min(1, slot["y"] + dy_norm))

        slot["x"] = round(new_x, 4)
        slot["y"] = round(new_y, 4)

        self.pos_label.config(text=f"x={new_x * 100:.1f}% y={new_y * 100:.1f}%")
        self.redraw()

    def on_key(self, event):
        key = event.keysym.lower()
        shift = event.state & 0x1

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
        elif key == "h":
            self.mode_var.set("hero")
            self.on_mode_change()
        elif key == "b":
            self.mode_var.set("board")
            self.on_mode_change()
        elif key == "l":
            self.select_slot("hero_left")
        elif key == "r":
            self.select_slot("hero_right")
        elif key in "12345":
            self.select_slot(f"board_{key}")

    def next_sample(self):
        self.current_idx = (self.current_idx + 1) % len(self.samples)
        self.load_sample()

    def prev_sample(self):
        self.current_idx = (self.current_idx - 1) % len(self.samples)
        self.load_sample()

    def save_config(self):
        # Ensure config directory exists
        CARD_SLOTS_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "card_size": [self.card_width.get(), self.card_height.get()],
            "reference_size": self.reference_size,
            "slots": self.slots,
        }
        with open(CARD_SLOTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Saved to {CARD_SLOTS_FILE}")
        print(
            f"    Card size: {self.card_width.get()}x{self.card_height.get()} @ {self.reference_size[0]}x{self.reference_size[1]}"
        )
        self.status_label.config(text="Saved!")

    def run(self):
        if self.samples:
            self.root.mainloop()


def main():
    print("Card Slot Calibrator")
    print("=" * 40)
    print("1. Set card Width/Height in pixels")
    print("2. Click slot button (L/R or 1-5) to select")
    print("3. Click on image to position, or drag")
    print("4. Arrow keys to nudge (Shift=5px)")
    print("5. Adjust tilt for hero cards")
    print("6. Press S to save")
    print()

    calibrator = CardSlotCalibrator()
    calibrator.run()


if __name__ == "__main__":
    main()
