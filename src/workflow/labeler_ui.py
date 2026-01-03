"""Tkinter-based labeling UI for training workflows.

Displays images with predictions and handles user input for labeling.
Matches the style of the unified calibrator.
"""

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk


class LabelerUI:
    """Interactive labeling UI using Tkinter.

    Displays:
    - The image to label (scaled for visibility)
    - Current prediction and confidence
    - Valid labels and controls
    - Progress counter
    - Current selection highlighting

    Controls:
    - Click buttons or press keys (A-K for cards, 0-9 for digits) to label
    - SPACE: Accept current prediction
    - ESC: Skip this item
    - Q: Quit session
    """

    def __init__(self, data_type: str, valid_classes: str):
        """Initialize labeler UI.

        Args:
            data_type: Name of data type (e.g., "cards", "digits")
            valid_classes: String of valid class labels (e.g., "A23456789TJQK")
        """
        self.data_type = data_type
        self.valid_classes = valid_classes
        self.result = None
        self.running = True

        # Build key mapping
        self.key_map = self._build_key_map()

        # Setup UI
        self._setup_ui()

    def _build_key_map(self) -> dict[str, str]:
        """Build mapping from key names to class labels."""
        key_map = {}
        for label in self.valid_classes:
            # Map both lowercase and uppercase
            key_map[label.lower()] = label
            key_map[label.upper()] = label

            # Special mappings for cards
            if label == "T":
                key_map["0"] = "T"  # 0 key also maps to T (ten)
            elif label == "A":
                key_map["1"] = "A"  # 1 key also maps to A (ace)

        # Direct mappings for special characters (digits workflow)
        # Note: Shift+4 sends "$" directly, so no need for "4" -> "$" mapping
        if "$" in self.valid_classes:
            key_map["$"] = "$"
        if "." in self.valid_classes:
            key_map["."] = "."
            key_map["period"] = "."
        return key_map

    def _setup_ui(self):
        """Set up the tkinter UI."""
        self.root = tk.Tk()
        self.root.title(f"Label {self.data_type.title()}")
        self.root.configure(bg="#2b2b2b")

        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Style
        style = ttk.Style()
        style.configure("TFrame", background="#2b2b2b")
        style.configure("TLabel", background="#2b2b2b", foreground="#ffffff")
        style.configure("TButton", padding=5)
        style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        style.configure("Status.TLabel", font=("Arial", 11))
        style.configure("Key.TLabel", font=("Courier", 10), foreground="#888888")

        # Left side: Image display
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas for image
        self.canvas = tk.Canvas(left_frame, bg="#1a1a1a", width=400, height=400)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Right side: Control panel (wider to fit all buttons)
        right_frame = ttk.Frame(main_frame, width=320)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(20, 0))
        right_frame.pack_propagate(False)

        # Title
        ttk.Label(right_frame, text=f"Label {self.data_type.title()}", style="Header.TLabel").pack(
            pady=(0, 15)
        )

        # Progress section
        progress_frame = ttk.LabelFrame(right_frame, text="Progress")
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_label = ttk.Label(progress_frame, text="0 labeled, 0 remaining")
        self.progress_label.pack(padx=10, pady=5)

        # Prediction section
        pred_frame = ttk.LabelFrame(right_frame, text="Model Prediction")
        pred_frame.pack(fill=tk.X, pady=(0, 15))

        self.pred_label = ttk.Label(pred_frame, text="--", font=("Arial", 24, "bold"))
        self.pred_label.pack(padx=10, pady=5)

        self.conf_label = ttk.Label(pred_frame, text="Confidence: --%")
        self.conf_label.pack(padx=10, pady=(0, 5))

        # Current selection section
        sel_frame = ttk.LabelFrame(right_frame, text="Your Selection")
        sel_frame.pack(fill=tk.X, pady=(0, 15))

        self.selection_label = ttk.Label(
            sel_frame, text="--", font=("Arial", 28, "bold"), foreground="#00ff00"
        )
        self.selection_label.pack(padx=10, pady=10)

        # Class buttons
        btn_frame = ttk.LabelFrame(right_frame, text="Classes")
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        self.class_buttons = {}

        if self.data_type == "cards":
            # Row 1: A, 2-5
            row1 = ttk.Frame(btn_frame)
            row1.pack(fill=tk.X, pady=2, padx=5)
            for label in "A2345":
                btn = ttk.Button(
                    row1, text=label, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn

            # Row 2: 6-9, T
            row2 = ttk.Frame(btn_frame)
            row2.pack(fill=tk.X, pady=2, padx=5)
            for label in "6789T":
                btn = ttk.Button(
                    row2, text=label, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn

            # Row 3: J, Q, K
            row3 = ttk.Frame(btn_frame)
            row3.pack(fill=tk.X, pady=2, padx=5)
            for label in "JQK":
                btn = ttk.Button(
                    row3, text=label, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn
        else:
            # Digits: 0-9 plus $ and . in three rows
            row1 = ttk.Frame(btn_frame)
            row1.pack(fill=tk.X, pady=2, padx=5)
            for label in "01234":
                btn = ttk.Button(
                    row1, text=label, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn

            row2 = ttk.Frame(btn_frame)
            row2.pack(fill=tk.X, pady=2, padx=5)
            for label in "56789":
                btn = ttk.Button(
                    row2, text=label, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn

            row3 = ttk.Frame(btn_frame)
            row3.pack(fill=tk.X, pady=2, padx=5)
            for label, display in [("$", "$"), (".", ".")]:
                btn = ttk.Button(
                    row3, text=display, width=3, command=lambda lbl=label: self._select_class(lbl)
                )
                btn.pack(side=tk.LEFT, padx=2)
                self.class_buttons[label] = btn

        # Action buttons
        action_frame = ttk.LabelFrame(right_frame, text="Actions")
        action_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Button(
            action_frame, text="Accept Prediction (Space)", command=self._accept_prediction
        ).pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(action_frame, text="Go Back (Backspace)", command=self._go_back).pack(
            fill=tk.X, padx=10, pady=5
        )
        ttk.Button(action_frame, text="Skip (Esc)", command=self._skip).pack(
            fill=tk.X, padx=10, pady=5
        )
        ttk.Button(action_frame, text="Quit Session (Ctrl+Q)", command=self._quit).pack(
            fill=tk.X, padx=10, pady=5
        )

        # Keyboard shortcuts help
        help_frame = ttk.LabelFrame(right_frame, text="Keyboard")
        help_frame.pack(fill=tk.X)

        if self.data_type == "cards":
            ttk.Label(help_frame, text="A, 2-9, T, J, Q, K: Select rank", style="Key.TLabel").pack(
                anchor=tk.W, padx=5
            )
        else:
            ttk.Label(help_frame, text="0-9, $, .: Select digit", style="Key.TLabel").pack(
                anchor=tk.W, padx=5
            )
        ttk.Label(help_frame, text="Space: Accept prediction", style="Key.TLabel").pack(
            anchor=tk.W, padx=5
        )
        ttk.Label(help_frame, text="Backspace: Go back", style="Key.TLabel").pack(
            anchor=tk.W, padx=5
        )
        ttk.Label(help_frame, text="Esc: Skip item", style="Key.TLabel").pack(anchor=tk.W, padx=5)
        ttk.Label(help_frame, text="Ctrl+Q: Quit", style="Key.TLabel").pack(anchor=tk.W, padx=5)

        # Bind keyboard events
        self.root.bind("<Key>", self._on_key)
        self.root.bind("<Escape>", lambda e: self._skip())
        self.root.bind("<space>", lambda e: self._accept_prediction())
        self.root.bind("<BackSpace>", lambda e: self._go_back())

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # Store current prediction for accept
        self.current_prediction = None

    def _select_class(self, label: str):
        """Handle class selection."""
        self.selection_label.config(text=label)
        self.result = label
        self.root.quit()

    def _accept_prediction(self):
        """Accept the current prediction."""
        if self.current_prediction and self.current_prediction in self.valid_classes:
            self._select_class(self.current_prediction)

    def _skip(self):
        """Skip current item."""
        self.result = "skip"
        self.root.quit()

    def _go_back(self):
        """Go back to previous item."""
        self.result = "back"
        self.root.quit()

    def _quit(self):
        """Quit labeling session."""
        self.result = "quit"
        self.running = False
        self.root.quit()

    def _on_key(self, event):
        """Handle keyboard input."""
        key = event.char
        keysym = event.keysym.lower()
        ctrl = event.state & 0x4  # Check if Ctrl is pressed

        # Ctrl+Q to quit (not just Q, since Q is a card rank)
        if ctrl and keysym == "q":
            self._quit()
            return

        # Check for class key
        if key in self.key_map:
            self._select_class(self.key_map[key])
        elif keysym in self.key_map:
            self._select_class(self.key_map[keysym])

    def show(
        self,
        img: np.ndarray,
        prediction: str | None,
        confidence: float,
        labeled_count: int,
        remaining_count: int,
    ) -> str | None:
        """Display image and get user input.

        Args:
            img: BGR image to display
            prediction: Model's predicted class (or None)
            confidence: Prediction confidence (0.0 to 1.0)
            labeled_count: Number of items labeled so far
            remaining_count: Number of items remaining

        Returns:
            - Label string if user provided a label
            - "skip" if user pressed ESC
            - "quit" if user pressed Q
            - None if window was closed
        """
        if not self.running:
            return "quit"

        self.result = None
        self.current_prediction = prediction

        # Update progress
        self.progress_label.config(text=f"{labeled_count} labeled, {remaining_count} remaining")

        # Update prediction
        if prediction:
            self.pred_label.config(text=prediction)
            conf_pct = int(confidence * 100)
            self.conf_label.config(text=f"Confidence: {conf_pct}%")

            # Color based on confidence
            if confidence > 0.8:
                self.pred_label.config(foreground="#00ff00")  # Green
            elif confidence > 0.5:
                self.pred_label.config(foreground="#ffff00")  # Yellow
            else:
                self.pred_label.config(foreground="#ff6600")  # Orange
        else:
            self.pred_label.config(text="--", foreground="#888888")
            self.conf_label.config(text="Confidence: --%")

        # Reset selection
        self.selection_label.config(text="--")

        # Convert and display image
        # Scale up small images
        h, w = img.shape[:2]
        scale = max(1, min(300 // w, 300 // h))
        if scale > 1:
            img = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)

        # Convert BGR to RGB for PIL
        if len(img.shape) == 2:
            # Grayscale
            img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        pil_img = Image.fromarray(img_rgb)
        self.photo = ImageTk.PhotoImage(pil_img)

        # Update canvas
        self.canvas.delete("all")
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        x = max(0, (canvas_w - pil_img.width) // 2)
        y = max(0, (canvas_h - pil_img.height) // 2)
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo)

        # Run event loop until user makes a choice
        self.root.mainloop()

        return self.result

    def close(self):
        """Close the labeling window."""
        try:
            self.root.destroy()
        except tk.TclError:
            pass  # Window already destroyed
