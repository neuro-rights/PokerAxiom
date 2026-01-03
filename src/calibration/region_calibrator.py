"""
Region Calibrator Tool

Visual tool to calibrate OCR regions using sample screenshots.
- Overlays current regions on samples
- Click to define new region corners
- Exports updated region coordinates
- Also calibrates card template regions (rank/suit)

Usage:
    python scripts/calibrate_regions.py
    python scripts/calibrate_regions.py --cards   (card template mode)

Controls:
    Left click  - Set region corner (2 clicks = one region)
    R           - Reset current region selection
    S           - Save current regions to file
    N           - Next sample image
    P           - Previous sample image
    Q           - Quit
    1-9         - Quick select seat stack region
    Shift+1-9   - Quick select seat bet region
    Ctrl+2-9    - Quick select seat card back region
    B           - Select board region
    H           - Select hero cards region
    T           - Select pot region
    A           - Select actions region

Card Back Regions:
    - First card_back: 2 clicks to define size and position
    - Subsequent card_backs: 1 click to position (size is locked)

Card Template Mode:
    K           - Select rank region
    U           - Select suit region
"""

import json
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from src.paths import REGIONS_FILE, SAMPLES_DIR

# Current regions from ocr_extractor.py
CURRENT_REGIONS = {
    "hero_cards": {"x": 0.38, "y": 0.73, "w": 0.24, "h": 0.14},
    "board": {"x": 0.26, "y": 0.28, "w": 0.48, "h": 0.14},
    "pot": {"x": 0.34, "y": 0.19, "w": 0.32, "h": 0.06},
    "actions": {"x": 0.62, "y": 0.68, "w": 0.36, "h": 0.12},
    "stack_1": {"x": 0.40, "y": 0.88, "w": 0.20, "h": 0.05},
    "stack_2": {"x": 0.12, "y": 0.72, "w": 0.12, "h": 0.05},
    "stack_3": {"x": 0.00, "y": 0.48, "w": 0.12, "h": 0.05},
    "stack_4": {"x": 0.06, "y": 0.24, "w": 0.12, "h": 0.05},
    "stack_5": {"x": 0.24, "y": 0.14, "w": 0.12, "h": 0.05},
    "stack_6": {"x": 0.44, "y": 0.14, "w": 0.12, "h": 0.05},
    "stack_7": {"x": 0.64, "y": 0.14, "w": 0.12, "h": 0.05},
    "stack_8": {"x": 0.82, "y": 0.24, "w": 0.12, "h": 0.05},
    "stack_9": {"x": 0.88, "y": 0.48, "w": 0.12, "h": 0.05},
    "bet_1": {"x": 0.44, "y": 0.58, "w": 0.12, "h": 0.05},
    "bet_2": {"x": 0.22, "y": 0.58, "w": 0.10, "h": 0.05},
    "bet_3": {"x": 0.12, "y": 0.44, "w": 0.10, "h": 0.05},
    "bet_4": {"x": 0.16, "y": 0.32, "w": 0.10, "h": 0.05},
    "bet_5": {"x": 0.28, "y": 0.24, "w": 0.10, "h": 0.05},
    "bet_6": {"x": 0.46, "y": 0.24, "w": 0.10, "h": 0.05},
    "bet_7": {"x": 0.58, "y": 0.24, "w": 0.10, "h": 0.05},
    "bet_8": {"x": 0.72, "y": 0.32, "w": 0.10, "h": 0.05},
    "bet_9": {"x": 0.76, "y": 0.44, "w": 0.10, "h": 0.05},
    # Card back regions for opponent detection (seats 2-9)
    "card_back_2": {"x": 0.14, "y": 0.68, "w": 0.06, "h": 0.06},
    "card_back_3": {"x": 0.02, "y": 0.44, "w": 0.06, "h": 0.06},
    "card_back_4": {"x": 0.08, "y": 0.20, "w": 0.06, "h": 0.06},
    "card_back_5": {"x": 0.26, "y": 0.10, "w": 0.06, "h": 0.06},
    "card_back_6": {"x": 0.46, "y": 0.10, "w": 0.06, "h": 0.06},
    "card_back_7": {"x": 0.66, "y": 0.10, "w": 0.06, "h": 0.06},
    "card_back_8": {"x": 0.84, "y": 0.20, "w": 0.06, "h": 0.06},
    "card_back_9": {"x": 0.90, "y": 0.44, "w": 0.06, "h": 0.06},
}

# Colors for different region types
COLORS = {
    "hero_cards": "#FF0000",  # Red
    "board": "#00FF00",  # Green
    "pot": "#FFFF00",  # Yellow
    "actions": "#FF00FF",  # Magenta
    "stack": "#00FFFF",  # Cyan
    "bet": "#FFA500",  # Orange
    "card_back": "#FF69B4",  # Hot pink
}


class RegionCalibrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Region Calibrator")

        # Load samples
        self.samples = sorted(SAMPLES_DIR.glob("*.png"))
        if not self.samples:
            print(f"No samples found in {SAMPLES_DIR}/")
            return

        self.current_idx = 0
        self.regions = CURRENT_REGIONS.copy()

        # Selection state
        self.selecting_region = None
        self.click_start = None

        # Fixed card back size (set from first calibrated card_back region)
        self.card_back_size = None  # (w, h) in normalized coords

        # Load saved regions if exists
        if REGIONS_FILE.exists():
            with open(REGIONS_FILE) as f:
                self.regions = json.load(f)
                print(f"[+] Loaded regions from {REGIONS_FILE}")

        # Extract card_back size from any existing card_back region
        self._init_card_back_size()

        self.setup_ui()

    def _init_card_back_size(self):
        """Initialize card_back_size from any existing card_back region."""
        for name, reg in self.regions.items():
            if name.startswith("card_back_") and "w" in reg and "h" in reg:
                self.card_back_size = (reg["w"], reg["h"])
                print(
                    f"[+] Card back size: {self.card_back_size[0]:.3f} x {self.card_back_size[1]:.3f}"
                )
                break

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas for image
        self.canvas = tk.Canvas(main_frame, bg="black")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Control panel
        control_frame = ttk.Frame(main_frame, width=200)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        # Sample navigation
        ttk.Label(control_frame, text="Sample:").pack()
        nav_frame = ttk.Frame(control_frame)
        nav_frame.pack()
        ttk.Button(nav_frame, text="< Prev", command=self.prev_sample).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="Next >", command=self.next_sample).pack(side=tk.LEFT)

        self.sample_label = ttk.Label(control_frame, text="")
        self.sample_label.pack()

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Region selection
        ttk.Label(control_frame, text="Select Region:").pack()

        region_frame = ttk.Frame(control_frame)
        region_frame.pack()

        ttk.Button(
            region_frame, text="Hero Cards (H)", command=lambda: self.start_select("hero_cards")
        ).pack(fill=tk.X)
        ttk.Button(region_frame, text="Board (B)", command=lambda: self.start_select("board")).pack(
            fill=tk.X
        )
        ttk.Button(region_frame, text="Pot (T)", command=lambda: self.start_select("pot")).pack(
            fill=tk.X
        )
        ttk.Button(
            region_frame, text="Actions (A)", command=lambda: self.start_select("actions")
        ).pack(fill=tk.X)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Label(control_frame, text="Stacks (1-9):").pack()

        stack_frame = ttk.Frame(control_frame)
        stack_frame.pack()
        for i in range(1, 10):
            btn = ttk.Button(
                stack_frame,
                text=str(i),
                width=3,
                command=lambda s=i: self.start_select(f"stack_{s}"),
            )
            btn.grid(row=(i - 1) // 3, column=(i - 1) % 3)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Label(control_frame, text="Bets (Shift+1-9):").pack()

        bet_frame = ttk.Frame(control_frame)
        bet_frame.pack()
        for i in range(1, 10):
            btn = ttk.Button(
                bet_frame, text=str(i), width=3, command=lambda s=i: self.start_select(f"bet_{s}")
            )
            btn.grid(row=(i - 1) // 3, column=(i - 1) % 3)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Label(control_frame, text="Card Backs (Ctrl+2-9):").pack()

        cardback_frame = ttk.Frame(control_frame)
        cardback_frame.pack()
        for i in range(2, 10):
            btn = ttk.Button(
                cardback_frame,
                text=str(i),
                width=3,
                command=lambda s=i: self.start_select(f"card_back_{s}"),
            )
            btn.grid(row=(i - 2) // 4, column=(i - 2) % 4)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Status
        self.status_label = ttk.Label(control_frame, text="Click region to select", wraplength=180)
        self.status_label.pack()

        # Save button
        ttk.Button(control_frame, text="Save Regions (S)", command=self.save_regions).pack(pady=10)
        ttk.Button(control_frame, text="Export to Code", command=self.export_code).pack()

        # Bindings
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.root.bind("<Key>", self.on_key)

        # Load first image
        self.load_sample()

    def load_sample(self):
        if not self.samples:
            return

        path = self.samples[self.current_idx]
        self.current_image = Image.open(path)
        self.img_width, self.img_height = self.current_image.size

        # Resize canvas
        self.canvas.config(width=self.img_width, height=self.img_height)

        self.sample_label.config(text=f"{self.current_idx + 1}/{len(self.samples)}\n{path.name}")
        self.redraw()

    def redraw(self):
        # Create annotated image
        img = self.current_image.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # Draw all regions
        for name, reg in self.regions.items():
            x1 = int(reg["x"] * self.img_width)
            y1 = int(reg["y"] * self.img_height)
            x2 = int((reg["x"] + reg["w"]) * self.img_width)
            y2 = int((reg["y"] + reg["h"]) * self.img_height)

            # Determine color
            if name.startswith("stack"):
                color = COLORS["stack"]
            elif name.startswith("bet"):
                color = COLORS["bet"]
            elif name.startswith("card_back"):
                color = COLORS["card_back"]
            else:
                color = COLORS.get(name, "#FFFFFF")

            # Highlight selected region
            if name == self.selecting_region:
                color = "#FFFFFF"

            # Draw rectangle with semi-transparent fill
            fill_color = color + "40"  # 25% opacity
            draw.rectangle([x1, y1, x2, y2], outline=color, fill=fill_color, width=2)

            # Draw label
            label = name.replace("_", " ").title()
            if (
                name.startswith("stack_")
                or name.startswith("bet_")
                or name.startswith("card_back_")
            ):
                label = name[-1]  # Just show number
            draw.text((x1 + 2, y1 + 2), label, fill=color)

        # Draw selection in progress
        if self.selecting_region and self.click_start:
            x1, y1 = self.click_start
            # Draw crosshair at start point
            draw.line([(x1 - 10, y1), (x1 + 10, y1)], fill="white", width=2)
            draw.line([(x1, y1 - 10), (x1, y1 + 10)], fill="white", width=2)

        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def start_select(self, region_name):
        self.selecting_region = region_name
        self.click_start = None

        # Card backs use single-click positioning after first one is calibrated
        if region_name.startswith("card_back_") and self.card_back_size:
            self.status_label.config(text=f"Click to position {region_name}\n(size locked)")
        else:
            self.status_label.config(text=f"Click top-left corner of {region_name}")
        self.redraw()

    def on_click(self, event):
        if not self.selecting_region:
            return

        x, y = event.x, event.y
        is_card_back = self.selecting_region.startswith("card_back_")

        # Card backs with locked size: single click to position
        if is_card_back and self.card_back_size:
            w, h = self.card_back_size
            self.regions[self.selecting_region] = {
                "x": round(x / self.img_width, 3),
                "y": round(y / self.img_height, 3),
                "w": w,
                "h": h,
            }
            reg = self.regions[self.selecting_region]
            self.status_label.config(
                text=f"Set {self.selecting_region}:\nx={reg['x']}, y={reg['y']}\n(size: {w:.3f} x {h:.3f})"
            )
            self.selecting_region = None
            self.click_start = None
            self.redraw()
            return

        if self.click_start is None:
            # First click - top-left corner
            self.click_start = (x, y)
            self.status_label.config(text=f"Click bottom-right corner of {self.selecting_region}")
        else:
            # Second click - bottom-right corner
            x1, y1 = self.click_start
            x2, y2 = x, y

            # Ensure proper ordering
            if x1 > x2:
                x1, x2 = x2, x1
            if y1 > y2:
                y1, y2 = y2, y1

            # Convert to percentages
            new_w = round((x2 - x1) / self.img_width, 3)
            new_h = round((y2 - y1) / self.img_height, 3)

            self.regions[self.selecting_region] = {
                "x": round(x1 / self.img_width, 3),
                "y": round(y1 / self.img_height, 3),
                "w": new_w,
                "h": new_h,
            }

            # If this is the first card_back region, lock in the size
            if is_card_back and self.card_back_size is None:
                self.card_back_size = (new_w, new_h)
                print(f"[+] Card back size locked: {new_w:.3f} x {new_h:.3f}")

            reg = self.regions[self.selecting_region]
            self.status_label.config(
                text=f"Set {self.selecting_region}:\nx={reg['x']}, y={reg['y']}\nw={reg['w']}, h={reg['h']}"
            )

            self.selecting_region = None
            self.click_start = None
            self.redraw()

    def on_motion(self, event):
        if not self.selecting_region:
            return

        is_card_back = self.selecting_region.startswith("card_back_")

        # Card back with locked size: show preview rectangle at cursor
        if is_card_back and self.card_back_size:
            self.redraw()
            w, h = self.card_back_size
            x1, y1 = event.x, event.y
            x2 = x1 + int(w * self.img_width)
            y2 = y1 + int(h * self.img_height)
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#FF69B4", width=2, dash=(4, 4))
        elif self.click_start:
            # Show preview rectangle for two-click mode
            self.redraw()
            x1, y1 = self.click_start
            x2, y2 = event.x, event.y
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="white", width=2, dash=(4, 4))

    def on_key(self, event):
        key = event.keysym.lower()

        if key == "n" or key == "right":
            self.next_sample()
        elif key == "p" or key == "left":
            self.prev_sample()
        elif key == "s":
            self.save_regions()
        elif key == "q":
            self.root.quit()
        elif key == "r":
            self.selecting_region = None
            self.click_start = None
            self.status_label.config(text="Selection reset")
            self.redraw()
        elif key == "h":
            self.start_select("hero_cards")
        elif key == "b":
            self.start_select("board")
        elif key == "t":
            self.start_select("pot")
        elif key == "a":
            self.start_select("actions")
        elif key in "123456789":
            seat = int(key)
            if event.state & 4:  # Ctrl held
                if seat >= 2:  # Card backs only for seats 2-9
                    self.start_select(f"card_back_{seat}")
            elif event.state & 1:  # Shift held
                self.start_select(f"bet_{seat}")
            else:
                self.start_select(f"stack_{seat}")

    def next_sample(self):
        if self.samples:
            self.current_idx = (self.current_idx + 1) % len(self.samples)
            self.load_sample()

    def prev_sample(self):
        if self.samples:
            self.current_idx = (self.current_idx - 1) % len(self.samples)
            self.load_sample()

    def save_regions(self):
        # Ensure config directory exists
        REGIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(REGIONS_FILE, "w") as f:
            json.dump(self.regions, f, indent=2)
        self.status_label.config(text=f"Saved to {REGIONS_FILE.name}")
        print(f"[+] Saved regions to {REGIONS_FILE}")

    def export_code(self):
        """Export regions as Python code for ocr_extractor.py"""
        lines = ["# Updated regions - paste into ocr_extractor.py", "REGIONS_9MAX = {"]

        for name, reg in self.regions.items():
            lines.append(
                f'    "{name}": Region("{name}", {reg["x"]}, {reg["y"]}, {reg["w"]}, {reg["h"]}),'
            )

        lines.append("}")

        code = "\n".join(lines)

        # Save to file
        from src.paths import PROJECT_ROOT

        export_file = PROJECT_ROOT / "regions_export.py"
        with open(export_file, "w") as f:
            f.write(code)

        print("\n" + code + "\n")
        print(f"[+] Exported to {export_file}")
        self.status_label.config(text="Exported to regions_export.py")

    def run(self):
        if self.samples:
            self.root.mainloop()


def main():
    print("Region Calibrator")
    print("=" * 40)
    print("Controls:")
    print("  Click      - Define region corners")
    print("  N/Right    - Next sample")
    print("  P/Left     - Previous sample")
    print("  1-9        - Select stack region")
    print("  Shift+1-9  - Select bet region")
    print("  Ctrl+2-9   - Select card back region")
    print("  H/B/T/A    - Hero/Board/Pot/Actions")
    print("  S          - Save regions")
    print("  R          - Reset selection")
    print("  Q          - Quit")
    print()
    print("Card Backs: First one uses 2 clicks (sets size),")
    print("            then 1 click to position others.")
    print()

    calibrator = RegionCalibrator()
    calibrator.run()


if __name__ == "__main__":
    main()
