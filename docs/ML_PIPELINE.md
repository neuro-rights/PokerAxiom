# Machine Learning Pipeline

This document describes the ML training workflow for card and digit recognition.

## Overview

Poka uses lightweight MLP (Multi-Layer Perceptron) classifiers for:
1. **Card Rank Recognition** - Identifying A, K, Q, J, T, 9, 8, 7, 6, 5, 4, 3, 2
2. **Digit Recognition** - Reading pot, stack, and bet amounts

## Architecture

### Card Rank Classifier

```
Input: 20x30 grayscale image
    │
    ▼
Preprocessing: Normalize, threshold
    │
    ▼
Flatten: 600 features
    │
    ▼
MLP: 600 → 128 → 64 → 13 (ranks)
    │
    ▼
Output: Rank prediction + confidence
```

**Model Details:**
- Type: OpenCV MLP Classifier
- Input size: 20×30 pixels
- Hidden layers: 128, 64 neurons
- Output: 13 classes (A, K, Q, J, T, 9-2)
- Accuracy: 99.4%

### Digit Classifier

```
Input: Variable width grayscale segment
    │
    ▼
Preprocessing: Resize to standard height
    │
    ▼
Template matching OR MLP classification
    │
    ▼
Output: Digit (0-9) or symbol (., $, k, M)
```

## Training Workflow

### 1. Extract Samples

Capture game screenshots and extract card/digit regions.

```bash
# Capture table screenshots when it's hero's turn
python scripts/capture_turns.py

# Extract card images from screenshots
python scripts/workflow.py cards extract
```

**Extraction Process:**
1. Load calibration data for card slot positions
2. Capture screenshots during gameplay
3. Crop card regions using calibrated coordinates
4. Save individual card images with timestamps

### 2. Label Samples

Interactive UI for labeling extracted samples.

```bash
# Label card samples
python scripts/workflow.py cards label
```

**Labeling UI Features:**
- Shows extracted card image
- Keyboard shortcuts for quick labeling (A, K, Q, J, T, 9-2)
- Skip option for unclear images
- Saves labels to JSON file

### 3. Train Classifier

Train MLP on labeled samples.

```bash
# Train card classifier
python scripts/workflow.py cards train
```

**Training Process:**
```python
# Load labeled samples
samples, labels = load_labeled_data()

# Preprocess images
X = [preprocess(img) for img in samples]
y = encode_labels(labels)

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Configure MLP
mlp = cv2.ml.ANN_MLP_create()
mlp.setLayerSizes(np.array([600, 128, 64, 13]))
mlp.setActivationFunction(cv2.ml.ANN_MLP_SIGMOID_SYM)
mlp.setTrainMethod(cv2.ml.ANN_MLP_BACKPROP)

# Train
mlp.train(X_train, cv2.ml.ROW_SAMPLE, y_train)

# Save model
mlp.save("models/rank_classifier.xml")
```

### 4. Verify Accuracy

Test classifier on held-out samples.

```bash
# Verify card classifier
python scripts/workflow.py cards verify
```

**Verification Output:**
```
=== Card Classifier Verification ===
Total samples: 500
Correct: 497
Accuracy: 99.4%

Confusion Matrix:
      A    K    Q    J    T  ...
A   [38,   0,   0,   0,   0, ...]
K   [ 0,  35,   0,   0,   0, ...]
...
```

### Complete Pipeline

Run all steps in sequence:

```bash
python scripts/workflow.py cards all
python scripts/workflow.py digits all
```

## Image Preprocessing

### Card Preprocessing

```python
def preprocess_card(img):
    """Prepare card image for classification."""
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Resize to standard dimensions
    resized = cv2.resize(gray, (20, 30))

    # Normalize pixel values
    normalized = resized.astype(np.float32) / 255.0

    # Flatten for MLP input
    return normalized.flatten()
```

### Suit Detection

Suits are detected using HSV color analysis (4-color deck):

```python
# HSV ranges for 4-color deck
SUIT_COLORS = {
    "spades": {"h": (0, 180), "s": (0, 30), "v": (0, 100)},    # Black
    "hearts": {"h": (0, 15), "s": (100, 255), "v": (100, 255)}, # Red
    "diamonds": {"h": (100, 130), "s": (100, 255), "v": (100, 255)}, # Blue
    "clubs": {"h": (40, 80), "s": (100, 255), "v": (100, 255)},  # Green
}

def detect_suit(img):
    """Detect suit from color."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    for suit, ranges in SUIT_COLORS.items():
        mask = cv2.inRange(hsv, lower, upper)
        if cv2.countNonZero(mask) > threshold:
            return suit
    return None
```

## Active Learning

The system uses confidence-based sample prioritization:

1. **High Confidence (>0.95):** Correct classification, no action needed
2. **Medium Confidence (0.7-0.95):** Likely correct, verify periodically
3. **Low Confidence (<0.7):** Needs human labeling

```python
def prioritize_samples(predictions):
    """Sort samples by classification confidence."""
    low_confidence = [p for p in predictions if p.confidence < 0.7]
    return sorted(low_confidence, key=lambda x: x.confidence)
```

## Model Files

| File | Purpose |
|------|---------|
| `models/rank_classifier.xml` | Trained card rank MLP |
| `models/digit_classifier.xml` | Trained digit MLP |
| `models/rank_labels.json` | Label encoding mapping |
| `models/char_templates_white/` | OCR templates for digit matching |

## Performance Considerations

### Real-time Inference

- Inference time: <5ms per card
- Memory footprint: ~10MB for models
- CPU-only (no GPU required)

### Accuracy Optimization

1. **Data Augmentation:**
   - Slight rotations (±5°)
   - Brightness variations
   - Minor translations

2. **Calibration:**
   - Precise card slot positioning
   - Consistent capture size
   - Resolution-independent scaling

3. **Edge Cases:**
   - Partial card visibility
   - Glare/reflections
   - Animation transitions

## Troubleshooting

### Low Accuracy

1. **Check calibration:** Ensure card slots are precisely positioned
2. **Verify samples:** Review labeled data for mislabels
3. **Increase training data:** Capture more diverse samples
4. **Check preprocessing:** Ensure consistent image quality

### Recognition Failures

1. **Verify 4-color deck:** Suit detection requires distinct colors
2. **Check lighting:** Avoid screen glare
3. **Retrain with failures:** Add failed cases to training set
