#!/usr/bin/env python3
"""Unified training workflow CLI.

Provides a consistent interface for training ML models with active learning.

Usage:
    python workflow.py <data_type> <action> [options]

Data Types:
    cards   - Card rank recognition (A, 2-9, T, J, Q, K)
    digits  - Digit disambiguation (0, 3, 6, 9)

Actions:
    extract - Extract crops from sample images
    label   - Interactive labeling with active learning
    train   - Train model on labeled data
    verify  - Verify model accuracy
    all     - Run full pipeline (extract → label → train → verify)

Examples:
    python workflow.py cards extract
    python workflow.py cards label
    python workflow.py cards train
    python workflow.py cards verify
    python workflow.py cards all

    python workflow.py digits extract --limit 100
    python workflow.py digits label
    python workflow.py digits train
    python workflow.py digits verify

Active Learning:
    During labeling, the model improves in real-time:
    - Items are sorted by confidence (lowest first)
    - Each label triggers model retraining
    - Predictions become more accurate as you label

Controls (during labeling):
    Cards:  A, 2-9, T, J, Q, K to label
    Digits: 0-9 to label
    SPACE:  Accept current prediction
    ESC:    Skip this item
    Q:      Quit session
"""

import argparse
import sys

# Add project root to path
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workflow import CardsWorkflow, DigitsWorkflow

WORKFLOWS = {
    "cards": CardsWorkflow,
    "digits": DigitsWorkflow,
}

ACTIONS = ["extract", "label", "train", "verify", "all"]


def main():
    parser = argparse.ArgumentParser(
        description="Unified training workflow CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python workflow.py cards extract        Extract card crops from samples
  python workflow.py cards label          Interactive labeling with active learning
  python workflow.py cards train          Train rank classifier
  python workflow.py cards verify         Test model accuracy
  python workflow.py cards all            Run full pipeline

  python workflow.py digits extract       Extract digit crops from stack regions
  python workflow.py digits label         Interactive labeling
  python workflow.py digits train         Train digit classifier
  python workflow.py digits verify        Test model accuracy
        """,
    )
    parser.add_argument(
        "data_type",
        choices=list(WORKFLOWS.keys()),
        help="Type of data to process",
    )
    parser.add_argument(
        "action",
        choices=ACTIONS,
        help="Action to perform",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of items to process",
    )
    parser.add_argument(
        "--sample-dir",
        type=str,
        default=None,
        help="Override sample directory for extraction",
    )

    args = parser.parse_args()

    # Create workflow
    workflow_class = WORKFLOWS[args.data_type]
    workflow = workflow_class()

    print(f"\n{'=' * 50}")
    print(f"  {args.data_type.upper()} WORKFLOW - {args.action.upper()}")
    print(f"{'=' * 50}\n")

    # Execute action
    if args.action == "extract":
        sample_dir = Path(args.sample_dir) if args.sample_dir else None
        count = workflow.extract(sample_dir=sample_dir, limit=args.limit)
        print(f"\nExtracted: {count} items")

    elif args.action == "label":
        count = workflow.label(limit=args.limit)
        print(f"\nLabeled: {count} items")

    elif args.action == "train":
        accuracy = workflow.train(incremental=False)
        print(f"\nTraining accuracy: {accuracy:.1%}")

    elif args.action == "verify":
        correct, total = workflow.verify()
        if total > 0:
            print(f"\nVerification: {correct}/{total} ({100 * correct / total:.0f}%)")
        else:
            print("\nNo items to verify")

    elif args.action == "all":
        workflow.run_all(limit=args.limit)

    print()


if __name__ == "__main__":
    main()
