#!/usr/bin/env python
"""
Train and test the digit classifier for 0/9 and 3/6 disambiguation.

Usage:
    python scripts/train_digit_classifier.py --train    # Train the model
    python scripts/train_digit_classifier.py --test     # Test on templates
    python scripts/train_digit_classifier.py            # Both train and test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.digit_classifier import test_classifier, train_classifier


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Train/test digit classifier for 0/9 and 3/6 disambiguation"
    )
    parser.add_argument("--train", action="store_true", help="Train and save the classifier")
    parser.add_argument("--test", action="store_true", help="Test classifier on template images")
    args = parser.parse_args()

    if args.train:
        print("Training digit classifier...")
        train_classifier()
        print()

    if args.test:
        print("Testing digit classifier...")
        test_classifier()

    if not args.train and not args.test:
        # Default: train and test
        print("Training digit classifier...")
        train_classifier()
        print()
        print("Testing digit classifier...")
        test_classifier()


if __name__ == "__main__":
    main()
