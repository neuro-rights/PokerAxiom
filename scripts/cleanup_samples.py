#!/usr/bin/env python
"""
Clean up sample images that don't match the standard size.

Deletes all samples NOT at the calibration reference size (1062x769).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

from src.capture.window_manager import STANDARD_SIZE
from src.paths import SAMPLES_DIR


def analyze_samples():
    """Analyze sample sizes and report statistics."""
    samples = list(SAMPLES_DIR.glob("*.png"))
    if not samples:
        print(f"No samples found in {SAMPLES_DIR}")
        return {}

    sizes = {}
    for f in samples:
        try:
            size = Image.open(f).size
            sizes.setdefault(size, []).append(f)
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

    return sizes


def main():
    print("Sample Cleanup Tool")
    print("=" * 50)
    print(f"Standard size: {STANDARD_SIZE[0]}x{STANDARD_SIZE[1]}")
    print(f"Samples directory: {SAMPLES_DIR}")
    print()

    sizes = analyze_samples()
    if not sizes:
        return

    # Report
    total = sum(len(files) for files in sizes.values())
    print(f"Found {total} sample images in {len(sizes)} different sizes:\n")

    correct_count = 0
    wrong_files = []

    for size, files in sorted(sizes.items()):
        is_correct = size == STANDARD_SIZE
        marker = "OK" if is_correct else "WRONG"
        print(f"  {size[0]:4}x{size[1]:4}: {len(files):3} files [{marker}]")

        if is_correct:
            correct_count = len(files)
        else:
            wrong_files.extend(files)

    print()
    print(f"Correct size: {correct_count} files")
    print(f"Wrong size:   {len(wrong_files)} files")

    if not wrong_files:
        print("\nAll samples are correct size. Nothing to clean up.")
        return

    # Confirm deletion
    print()
    response = input(f"Delete {len(wrong_files)} wrong-sized files? [y/N]: ").strip().lower()

    if response != "y":
        print("Cancelled.")
        return

    # Delete files
    deleted = 0
    errors = 0
    for f in wrong_files:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"Error deleting {f.name}: {e}")
            errors += 1

    print()
    print(f"Deleted: {deleted} files")
    if errors:
        print(f"Errors:  {errors} files")

    # Final count
    remaining = list(SAMPLES_DIR.glob("*.png"))
    print(f"\nRemaining samples: {len(remaining)}")


if __name__ == "__main__":
    main()
