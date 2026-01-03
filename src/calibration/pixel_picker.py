"""
Simple Pixel Picker Tool

Click on an image to get normalized coordinates and color.
Used to calibrate fold button detection pixel.

Usage:
    python scripts/pick_pixel.py
"""

import json
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from src.paths import FOLD_PIXEL_FILE, SAMPLES_DIR


class PixelPicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pixel Picker - Click to select fold button pixel")

        # Load samples
        self.samples = sorted(SAMPLES_DIR.glob("*.png"))
        if not self.samples:
            print(f"No samples found in {SAMPLES_DIR}/")
            return

        self.current_idx = 0
        self.selected_pixel = None
        self.selected_color = None

        # Load saved config if exists
        if FOLD_PIXEL_FILE.exists():
            with open(FOLD_PIXEL_FILE) as f:
                config = json.load(f)
                self.selected_pixel = (config.get("x", 0.67), config.get("y", 0.865))
                print(f"[+] Loaded pixel from {FOLD_PIXEL_FILE}: {self.selected_pixel}")

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas for image
        self.canvas = tk.Canvas(main_frame, bg="black", cursor="crosshair")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Control panel
        control_frame = ttk.Frame(main_frame, width=250)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(control_frame, text="Pixel Picker", font=("Arial", 14, "bold")).pack(pady=10)
        ttk.Label(
            control_frame,
            text="Click on the FOLD button\nto select detection pixel",
            wraplength=200,
        ).pack(pady=5)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Sample navigation
        ttk.Label(control_frame, text="Sample:").pack()
        nav_frame = ttk.Frame(control_frame)
        nav_frame.pack(pady=5)
        ttk.Button(nav_frame, text="< Prev", command=self.prev_sample).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Next >", command=self.next_sample).pack(side=tk.LEFT, padx=2)

        self.sample_label = ttk.Label(control_frame, text="", wraplength=200)
        self.sample_label.pack(pady=5)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Selected pixel info
        ttk.Label(control_frame, text="Selected Pixel:", font=("Arial", 10, "bold")).pack()

        self.coord_label = ttk.Label(control_frame, text="Click to select...", font=("Courier", 10))
        self.coord_label.pack(pady=5)

        self.color_label = ttk.Label(control_frame, text="", font=("Courier", 10))
        self.color_label.pack(pady=5)

        # Color preview
        self.color_canvas = tk.Canvas(control_frame, width=100, height=50, bg="gray")
        self.color_canvas.pack(pady=10)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Live pixel under cursor
        ttk.Label(control_frame, text="Cursor:", font=("Arial", 10, "bold")).pack()
        self.cursor_label = ttk.Label(control_frame, text="Move mouse...", font=("Courier", 9))
        self.cursor_label.pack(pady=5)

        ttk.Separator(control_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Save button
        ttk.Button(control_frame, text="Save Pixel Config (S)", command=self.save_config).pack(
            pady=10
        )

        # Bindings
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.root.bind("<Key>", self.on_key)

        self.load_sample()

    def load_sample(self):
        if not self.samples:
            return

        path = self.samples[self.current_idx]
        self.current_image = Image.open(path)
        self.img_width, self.img_height = self.current_image.size

        self.canvas.config(width=self.img_width, height=self.img_height)
        self.sample_label.config(text=f"{self.current_idx + 1}/{len(self.samples)}\n{path.name}")

        self.redraw()

    def redraw(self):
        img = self.current_image.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # Draw selected pixel marker
        if self.selected_pixel:
            nx, ny = self.selected_pixel
            x = int(nx * self.img_width)
            y = int(ny * self.img_height)

            # Draw crosshair
            draw.line([(x - 20, y), (x + 20, y)], fill="yellow", width=2)
            draw.line([(x, y - 20), (x, y + 20)], fill="yellow", width=2)
            draw.ellipse([x - 8, y - 8, x + 8, y + 8], outline="yellow", width=3)

            # Get color at this point
            pixel = self.current_image.getpixel((x, y))
            r, g, b = pixel[0], pixel[1], pixel[2]
            self.selected_color = (r, g, b)

            # Update color preview
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.color_canvas.config(bg=hex_color)
            self.color_label.config(text=f"RGB({r:3d}, {g:3d}, {b:3d})")

        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def on_click(self, event):
        x, y = event.x, event.y

        # Convert to normalized coordinates
        nx = round(x / self.img_width, 4)
        ny = round(y / self.img_height, 4)

        self.selected_pixel = (nx, ny)
        self.coord_label.config(text=f"x={nx:.4f}, y={ny:.4f}")

        self.redraw()

    def on_motion(self, event):
        x, y = event.x, event.y

        if 0 <= x < self.img_width and 0 <= y < self.img_height:
            nx = x / self.img_width
            ny = y / self.img_height
            pixel = self.current_image.getpixel((x, y))
            r, g, b = pixel[0], pixel[1], pixel[2]
            self.cursor_label.config(text=f"({nx:.3f}, {ny:.3f})\nRGB({r}, {g}, {b})")

    def on_key(self, event):
        key = event.keysym.lower()

        if key == "n" or key == "right":
            self.next_sample()
        elif key == "p" or key == "left":
            self.prev_sample()
        elif key == "s":
            self.save_config()
        elif key == "q":
            self.root.quit()

    def next_sample(self):
        if self.samples:
            self.current_idx = (self.current_idx + 1) % len(self.samples)
            self.load_sample()

    def prev_sample(self):
        if self.samples:
            self.current_idx = (self.current_idx - 1) % len(self.samples)
            self.load_sample()

    def save_config(self):
        if not self.selected_pixel:
            print("No pixel selected!")
            return

        # Ensure config directory exists
        FOLD_PIXEL_FILE.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "x": self.selected_pixel[0],
            "y": self.selected_pixel[1],
            "description": "Fold button detection pixel (normalized coordinates)",
        }

        if self.selected_color:
            config["sample_color"] = {
                "r": self.selected_color[0],
                "g": self.selected_color[1],
                "b": self.selected_color[2],
            }

        with open(FOLD_PIXEL_FILE, "w") as f:
            json.dump(config, f, indent=2)

        print(f"[+] Saved to {FOLD_PIXEL_FILE}:")
        print(f"    Pixel: ({self.selected_pixel[0]}, {self.selected_pixel[1]})")
        if self.selected_color:
            print(f"    Color: RGB{self.selected_color}")

        self.coord_label.config(
            text=f"SAVED!\nx={self.selected_pixel[0]:.4f}, y={self.selected_pixel[1]:.4f}"
        )

    def run(self):
        if self.samples:
            self.root.mainloop()


def main():
    print("Pixel Picker")
    print("=" * 40)
    print("Click on the FOLD button to select detection pixel")
    print()
    print("Controls:")
    print("  Click    - Select pixel")
    print("  N/Right  - Next sample")
    print("  P/Left   - Previous sample")
    print("  S        - Save config")
    print("  Q        - Quit")
    print()

    picker = PixelPicker()
    picker.run()


if __name__ == "__main__":
    main()
