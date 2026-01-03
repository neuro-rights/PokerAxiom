"""
On-Table HUD Overlay - Transparent canvas overlay for poker table regions.

Shows detected cards, stacks, bets, pot, and dealer position
with labels positioned near their actual regions on the table.

Usage:
    python scripts/run_overlay.py
"""

import ctypes
import ctypes.wintypes
import tkinter as tk

import cv2
import numpy as np

from src.capture.window_capture import WindowCapture
from src.capture.window_manager import arrange_tables
from src.data.card_extractor import load_config
from src.detection.button_detector import detect_dealer_button, load_button_config
from src.detection.card_detector import detect_card
from src.engine.scaling import get_scaled_card_size
from src.recognition.value_reader import read_value

user32 = ctypes.windll.user32

# Windows constants
GWL_EXSTYLE = -20
GWL_HWNDPARENT = -8
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20

# Transparent color key
TRANSPARENT_COLOR = "#010101"

# Suit colors
SUIT_COLORS = {
    "s": "#cccccc",  # Spades - silver
    "h": "#ff6666",  # Hearts - red
    "d": "#6699ff",  # Diamonds - blue
    "c": "#66cc66",  # Clubs - green
}


def get_window_rect(hwnd):
    """Get window position and size."""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def get_client_rect_screen(hwnd):
    """Get client area position and size in screen coordinates."""
    win_rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(win_rect))
    point = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(point))
    client_rect = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    return (
        point.x,
        point.y,
        client_rect.right - client_rect.left,
        client_rect.bottom - client_rect.top,
    )


class CanvasOverlay:
    """Transparent canvas overlay positioned over a window."""

    def __init__(self, master, table_hwnd):
        self.table_hwnd = table_hwnd
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.win.configure(bg=TRANSPARENT_COLOR)

        self.canvas = tk.Canvas(self.win, bg=TRANSPARENT_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Label storage: name -> (rect_id, text_id)
        self.labels = {}

        # Setup window after it's created
        self.win.update_idletasks()
        self._setup_window()

    def _setup_window(self):
        """Setup window: make click-through and set owner relationship."""
        try:
            # Get actual HWND from wm_frame()
            frame_id = self.win.wm_frame()
            self.overlay_hwnd = int(frame_id, 16)

            # Set owner to poker table - overlay will follow table's z-order
            user32.SetWindowLongPtrW(self.overlay_hwnd, GWL_HWNDPARENT, self.table_hwnd)

            # Add WS_EX_LAYERED and WS_EX_TRANSPARENT for click-through
            style = user32.GetWindowLongPtrW(self.overlay_hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(
                self.overlay_hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception as e:
            print(f"Window setup failed: {e}")
            self.overlay_hwnd = None

    def reposition(self):
        """Reposition overlay to match table window client area."""
        if not user32.IsWindow(self.table_hwnd):
            return False

        # Use client area dimensions to match captured image coordinates
        x, y, w, h = get_client_rect_screen(self.table_hwnd)
        self.canvas.config(width=w, height=h)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        return True

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
            font=("Consolas", 11, "bold"),
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

        # Update text
        self.canvas.itemconfig(text_id, text=text, fill=color, state="normal")
        self.canvas.coords(text_id, x + 5, y + 3)

        # Update background to fit text
        bbox = self.canvas.bbox(text_id)
        if bbox:
            self.canvas.coords(rect_id, bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2)
            self.canvas.itemconfig(rect_id, state="normal")

    def hide_label(self, name):
        """Hide a specific label."""
        if name in self.labels:
            rect_id, text_id = self.labels[name]
            self.canvas.itemconfig(rect_id, state="hidden")
            self.canvas.itemconfig(text_id, state="hidden")

    def destroy(self):
        """Destroy the overlay window."""
        try:
            self.win.destroy()
        except Exception:
            pass


class TableHUD:
    """On-table HUD overlay for a single poker table."""

    def __init__(self, master, hwnd, title, regions, slots_cfg, capture, button_cfg=None):
        self.master = master
        self.hwnd = hwnd
        self.title = title
        self.regions = regions
        self.slots_cfg = slots_cfg
        self.slots = slots_cfg["slots"]
        self.capture = capture
        self.button_cfg = button_cfg
        self.running = True

        # Create canvas overlay
        self.overlay = CanvasOverlay(master, hwnd)
        self._create_labels()

    def _create_labels(self):
        """Create all label items on the canvas."""
        # Hero cards
        for slot in ["hero_left", "hero_right"]:
            self.overlay.create_label(slot)

        # Board cards
        for i in range(1, 6):
            self.overlay.create_label(f"board_{i}")

        # All stacks
        for i in range(1, 10):
            self.overlay.create_label(f"stack_{i}")

        # All bets
        for i in range(1, 10):
            self.overlay.create_label(f"bet_{i}")

        # Pot
        self.overlay.create_label("pot")

        # Dealer
        self.overlay.create_label("dealer")

    def _get_suit_color(self, suit):
        return SUIT_COLORS.get(suit, "#ffffff")

    def update(self):
        """Main update loop."""
        if not self.running:
            return

        if not user32.IsWindow(self.hwnd):
            self.stop()
            return

        # Reposition overlay to match table
        if not self.overlay.reposition():
            self.stop()
            return

        try:
            img = self.capture.grab(self.hwnd)
            if img is None:
                return
        except Exception:
            return

        # Get image dimensions - captured image is client area,
        # so use these for both cropping and overlay coordinate conversion
        full_w, full_h = img.size
        table_w, table_h = full_w, full_h  # Overlay coords match capture coords
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        card_w, card_h = get_scaled_card_size(self.slots_cfg, full_w, full_h)

        # Update all components
        self._update_hero_cards(img, full_w, full_h, card_w, card_h, table_w, table_h)
        self._update_board_cards(img, full_w, full_h, card_w, card_h, table_w, table_h)
        self._update_pot(img_cv, full_w, full_h, table_w, table_h)
        self._update_stacks(img_cv, full_w, full_h, table_w, table_h)
        self._update_bets(img_cv, full_w, full_h, table_w, table_h)
        self._update_dealer_button(img, table_w, table_h)

    def _norm_to_canvas(self, norm_x, norm_y, table_w, table_h):
        """Convert normalized coords to canvas coords."""
        return int(norm_x * table_w), int(norm_y * table_h)

    def _update_hero_cards(self, img, full_w, full_h, card_w, card_h, table_w, table_h):
        """Update hero card labels."""
        hero_reg = self.regions.get("hero_cards")
        if not hero_reg:
            return

        hx = int(hero_reg["x"] * full_w)
        hy = int(hero_reg["y"] * full_h)
        hw = int(hero_reg["w"] * full_w)
        hh = int(hero_reg["h"] * full_h)
        hero_img = img.crop((hx, hy, hx + hw, hy + hh))

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

            # Position below the card slot
            label_norm_x = hero_reg["x"] + slot["x"] * hero_reg["w"] + 0.02
            label_norm_y = hero_reg["y"] + hero_reg["h"] + 0.005
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if result:
                card = result["card"]
                self.overlay.update_label(
                    slot_name, canvas_x, canvas_y, card, self._get_suit_color(card[1])
                )
            else:
                self.overlay.update_label(slot_name, canvas_x, canvas_y, "--", "#555555")

    def _update_board_cards(self, img, full_w, full_h, card_w, card_h, table_w, table_h):
        """Update board card labels."""
        board_reg = self.regions.get("board")
        if not board_reg:
            return

        bx = int(board_reg["x"] * full_w)
        by = int(board_reg["y"] * full_h)
        bw = int(board_reg["w"] * full_w)
        bh = int(board_reg["h"] * full_h)
        board_img = img.crop((bx, by, bx + bw, by + bh))

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

            # Position below each board card
            label_norm_x = board_reg["x"] + slot["x"] * board_reg["w"] + 0.01
            label_norm_y = board_reg["y"] + board_reg["h"] + 0.005
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if result and result["confidence"] > 0.6:
                card = result["card"]
                self.overlay.update_label(
                    slot_name, canvas_x, canvas_y, card, self._get_suit_color(card[1])
                )
            else:
                self.overlay.update_label(slot_name, canvas_x, canvas_y, "--", "#555555")

    def _update_pot(self, img_cv, full_w, full_h, table_w, table_h):
        """Update pot value label."""
        pot_reg = self.regions.get("pot")
        if not pot_reg:
            self.overlay.hide_label("pot")
            return

        px = int(pot_reg["x"] * full_w)
        py = int(pot_reg["y"] * full_h)
        pw = int(pot_reg["w"] * full_w)
        ph = int(pot_reg["h"] * full_h)

        pot_crop = img_cv[py : py + ph, px : px + pw]
        pot_val = read_value(pot_crop, "pot")

        label_norm_x = pot_reg["x"] + pot_reg["w"] / 2
        label_norm_y = (
            pot_reg["y"] - 0.06
        )  # Position above pot (increased to avoid bet_5/bet_6 overlap)
        canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

        if pot_val is not None:
            self.overlay.update_label("pot", canvas_x, canvas_y, f"${pot_val:.2f}", "#ffcc00")
        else:
            self.overlay.hide_label("pot")

    def _update_stacks(self, img_cv, full_w, full_h, table_w, table_h):
        """Update stack labels for all seats."""
        for seat in range(1, 10):
            key = f"stack_{seat}"
            stack_reg = self.regions.get(key)

            if not stack_reg:
                self.overlay.hide_label(key)
                continue

            sx = int(stack_reg["x"] * full_w)
            sy = int(stack_reg["y"] * full_h)
            sw = int(stack_reg["w"] * full_w)
            sh = int(stack_reg["h"] * full_h)

            stack_crop = img_cv[sy : sy + sh, sx : sx + sw]
            stack_val = read_value(stack_crop, "stack")

            label_norm_x = stack_reg["x"] + stack_reg["w"] / 2
            label_norm_y = stack_reg["y"] + stack_reg["h"] + 0.01
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if stack_val is not None:
                self.overlay.update_label(key, canvas_x, canvas_y, f"${stack_val:.2f}", "#55ff55")
            else:
                self.overlay.hide_label(key)

    def _update_bets(self, img_cv, full_w, full_h, table_w, table_h):
        """Update bet labels for all seats."""
        for seat in range(1, 10):
            key = f"bet_{seat}"
            bet_reg = self.regions.get(key)

            if not bet_reg:
                self.overlay.hide_label(key)
                continue

            bx = int(bet_reg["x"] * full_w)
            by = int(bet_reg["y"] * full_h)
            bw = int(bet_reg["w"] * full_w)
            bh = int(bet_reg["h"] * full_h)

            bet_crop = img_cv[by : by + bh, bx : bx + bw]
            bet_val = read_value(bet_crop, "bet")

            label_norm_x = bet_reg["x"] + bet_reg["w"] / 2
            label_norm_y = bet_reg["y"] + bet_reg["h"] + 0.005
            canvas_x, canvas_y = self._norm_to_canvas(label_norm_x, label_norm_y, table_w, table_h)

            if bet_val is not None and bet_val > 0:
                self.overlay.update_label(key, canvas_x, canvas_y, f"${bet_val:.2f}", "#ffffff")
            else:
                self.overlay.hide_label(key)

    def _update_dealer_button(self, img, table_w, table_h):
        """Update dealer button indicator."""
        if not self.button_cfg:
            self.overlay.hide_label("dealer")
            return

        result = detect_dealer_button(img, self.button_cfg)

        if result and result["confidence"] > 0.4:
            seat = result["seat"]
            buttons = self.button_cfg.get("buttons", {})
            btn_pos = buttons.get(f"btn_{seat}")

            if btn_pos and not (btn_pos["x"] == 0 and btn_pos["y"] == 0):
                # Offset dealer label slightly up and left to avoid bet label overlap
                dealer_x = btn_pos["x"] - 0.02
                dealer_y = btn_pos["y"] - 0.03
                canvas_x, canvas_y = self._norm_to_canvas(dealer_x, dealer_y, table_w, table_h)
                self.overlay.update_label("dealer", canvas_x, canvas_y, f"D{seat}", "#ffcc00")
            else:
                self.overlay.hide_label("dealer")
        else:
            self.overlay.hide_label("dealer")

    def stop(self):
        self.running = False
        self.overlay.destroy()


class DebugOverlay:
    """Manager for multiple table HUDs."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.regions, self.slots_cfg = load_config()
        self.button_cfg = load_button_config()
        self.capture = WindowCapture()
        self.overlays = []

        self._attach_tables()
        self._update_loop()

    def _attach_tables(self):
        windows = self.capture.find_all_windows("*NLHA*")
        if not windows:
            print("No poker tables found. Exiting.")
            self.root.quit()
            return

        for hwnd, title in windows:
            ov = TableHUD(
                self.root, hwnd, title, self.regions, self.slots_cfg, self.capture, self.button_cfg
            )
            self.overlays.append(ov)

        print(f"Attached HUD to {len(self.overlays)} table(s). Press Ctrl+C to stop.")

    def _update_loop(self):
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
    DebugOverlay().run()


if __name__ == "__main__":
    main()
