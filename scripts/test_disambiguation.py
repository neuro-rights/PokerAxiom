#!/usr/bin/env python
"""
Test disambiguation functions against known templates.

Validates that disambiguate_0_9 and disambiguate_3_6 correctly
identify all template files in models/char_templates.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2

from src.paths import MODELS_DIR
from src.recognition.value_reader import disambiguate_0_9, disambiguate_3_6

TEMPLATES_DIR = MODELS_DIR / "char_templates"
TEMPLATES_DIR_WHITE = MODELS_DIR / "char_templates_white"


def test_templates(templates_dir: Path, name: str) -> dict:
    """Test all 0, 9, 3, 6 templates in the given directory.

    The disambiguation functions now take a template_match parameter
    and return the template match when uncertain. This test verifies
    that the functions don't incorrectly OVERRIDE a correct template match.
    """
    results = {"pass": 0, "fail": 0, "errors": []}

    # Test 0 templates: when template says "0", should not override to "9"
    for f in templates_dir.glob("0*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            results["errors"].append(f"{f.name}: Could not load")
            results["fail"] += 1
            continue
        # Template matching would say "0", disambiguation should preserve it
        result = disambiguate_0_9(img, template_match="0")
        if result == "0":
            results["pass"] += 1
        else:
            results["fail"] += 1
            results["errors"].append(f"{name}/{f.name}: template=0, wrongly overridden to {result}")

    # Test 9 templates: when template says "9", should not override to "0"
    for f in templates_dir.glob("9*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            results["errors"].append(f"{f.name}: Could not load")
            results["fail"] += 1
            continue
        # Template matching would say "9", disambiguation should preserve it
        result = disambiguate_0_9(img, template_match="9")
        if result == "9":
            results["pass"] += 1
        else:
            results["fail"] += 1
            results["errors"].append(f"{name}/{f.name}: template=9, wrongly overridden to {result}")

    # Test 3 templates: when template says "3", should not override to "6"
    for f in templates_dir.glob("3*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            results["errors"].append(f"{f.name}: Could not load")
            results["fail"] += 1
            continue
        result = disambiguate_3_6(img, template_match="3")
        if result == "3":
            results["pass"] += 1
        else:
            results["fail"] += 1
            results["errors"].append(f"{name}/{f.name}: template=3, wrongly overridden to {result}")

    # Test 6 templates: when template says "6", should not override to "3"
    for f in templates_dir.glob("6*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            results["errors"].append(f"{f.name}: Could not load")
            results["fail"] += 1
            continue
        result = disambiguate_3_6(img, template_match="6")
        if result == "6":
            results["pass"] += 1
        else:
            results["fail"] += 1
            results["errors"].append(f"{name}/{f.name}: template=6, wrongly overridden to {result}")

    return results


def test_correction_capability(templates_dir: Path, name: str) -> dict:
    """Test if disambiguation can correct a WRONG template match.

    This tests the scenario where template matching picks the wrong digit
    and disambiguation should correct it (when confident enough).
    """
    results = {"corrected": 0, "preserved": 0, "details": []}

    # Test if 0 templates can be distinguished when wrongly matched as 9
    for f in templates_dir.glob("0*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        result = disambiguate_0_9(img, template_match="9")  # Wrong match
        if result == "0":
            results["corrected"] += 1
            results["details"].append(f"{name}/{f.name}: corrected 9->0")
        else:
            results["preserved"] += 1
            results["details"].append(f"{name}/{f.name}: kept wrong 9")

    # Test if 9 templates can be distinguished when wrongly matched as 0
    for f in templates_dir.glob("9*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        result = disambiguate_0_9(img, template_match="0")  # Wrong match
        if result == "9":
            results["corrected"] += 1
            results["details"].append(f"{name}/{f.name}: corrected 0->9")
        else:
            results["preserved"] += 1
            results["details"].append(f"{name}/{f.name}: kept wrong 0")

    # Similar for 3/6
    for f in templates_dir.glob("3*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        result = disambiguate_3_6(img, template_match="6")  # Wrong match
        if result == "3":
            results["corrected"] += 1
            results["details"].append(f"{name}/{f.name}: corrected 6->3")
        else:
            results["preserved"] += 1
            results["details"].append(f"{name}/{f.name}: kept wrong 6")

    for f in templates_dir.glob("6*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        result = disambiguate_3_6(img, template_match="3")  # Wrong match
        if result == "6":
            results["corrected"] += 1
            results["details"].append(f"{name}/{f.name}: corrected 3->6")
        else:
            results["preserved"] += 1
            results["details"].append(f"{name}/{f.name}: kept wrong 3")

    return results


def main():
    print("Testing disambiguation functions against templates...\n")

    total_pass = 0
    total_fail = 0
    all_errors = []

    # Test cyan templates (stack text)
    if TEMPLATES_DIR.exists():
        print(f"Testing {TEMPLATES_DIR}...")
        results = test_templates(TEMPLATES_DIR, "char_templates")
        total_pass += results["pass"]
        total_fail += results["fail"]
        all_errors.extend(results["errors"])
        print(f"  Passed: {results['pass']}, Failed: {results['fail']}")
    else:
        print(f"Warning: {TEMPLATES_DIR} not found")

    # Test white templates (bet/pot text)
    if TEMPLATES_DIR_WHITE.exists():
        print(f"Testing {TEMPLATES_DIR_WHITE}...")
        results = test_templates(TEMPLATES_DIR_WHITE, "char_templates_white")
        total_pass += results["pass"]
        total_fail += results["fail"]
        all_errors.extend(results["errors"])
        print(f"  Passed: {results['pass']}, Failed: {results['fail']}")
    else:
        print(f"Warning: {TEMPLATES_DIR_WHITE} not found")

    # Summary
    print(f"\n{'=' * 50}")
    print(f"TOTAL: {total_pass} passed, {total_fail} failed")

    if all_errors:
        print("\nFailures:")
        for err in all_errors:
            print(f"  FAIL: {err}")
        return 1
    else:
        print("\nAll templates correctly identified!")

    # Additional: Test correction capability
    print(f"\n{'=' * 50}")
    print("Testing correction capability (when template match is WRONG)...\n")

    for templates_dir, name in [
        (TEMPLATES_DIR, "char_templates"),
        (TEMPLATES_DIR_WHITE, "char_templates_white"),
    ]:
        if templates_dir.exists():
            results = test_correction_capability(templates_dir, name)
            print(
                f"{name}: {results['corrected']} corrected, {results['preserved']} preserved wrong match"
            )
            for detail in results["details"]:
                print(f"  {detail}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
