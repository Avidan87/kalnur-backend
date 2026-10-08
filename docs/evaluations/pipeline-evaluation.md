# Vision and segmentation evaluation 🔬

This report records a small engineering evaluation carried out for Kalnur's
food-logging pipeline. It is included to make the design decisions visible,
not to claim clinical or nutritional accuracy.

> The test photos remain private. They are not included in this repository.
> The evaluations were run in a private development environment with the
> developer's own provider accounts and knowledge-base deployment.

## Pipelines evaluated

| Pipeline | Stages |
| --- | --- |
| **Claude + SAM 3** | Claude Sonnet 4.6 on AWS Bedrock → SAM 3 → Depth Anything V2 → Nigerian-food knowledge matching |
| **GPT-4o + SAM 2** | GPT-4o → SAM 2 → Depth Anything V2 → Nigerian-food knowledge matching |

Both paths use the same downstream nutrient-scaling logic. The purpose was to
observe end-to-end behaviour: food identification, mask coverage, portion
estimation, cost, and latency.

## Test protocol

Two private Nigerian meal photographs were used:

1. Beans and fried plantain
2. Rice, tomato stew, and fried plantain

Each run recorded the detected foods, whether segmentation supplied usable
masks, estimated portions, nutrient totals, estimated provider cost, and total
pipeline latency. A reviewer also inspected the generated masks against the
source photo.

## Observed development runs

These figures are included for reproducibility of the engineering discussion.
They are model estimates, **not** nutritional ground truth and not a claim that
one total is correct.

| Meal | Pipeline | Top-level foods | Estimated total | Estimated run cost | End-to-end latency |
| --- | --- | ---: | ---: | ---: | ---: |
| Beans + plantain, initial | Claude + SAM 3 | 3 | 1,738 kcal | $0.0223 | 28.5 s |
| Beans + plantain, initial | GPT-4o + SAM 2 | 2 | 549 kcal | $0.0100 | 14.5 s |
| Rice + stew + plantain | Claude + SAM 3 | 3 | 346 kcal | $0.0213 | 19.4 s |
| Rice + stew + plantain | GPT-4o + SAM 2 | 3 | 665 kcal | $0.0111 | 12.3 s |
| Beans + plantain, corrected retest | Claude + SAM 3 | 2 | 1,144 kcal | $0.0203 | 33.0 s |

The first beans run exposed the error discussed below. The corrected retest is
shown separately because the improved prompt changed the detected components;
it is not a like-for-like accuracy comparison against the earlier GPT-4o run.

## What the evaluation found

### 1. An important double-counting failure

On the beans-and-plantain image, the Claude + SAM 3 path initially returned a
third top-level item: pepper sauce. In the photograph, that sauce was part of
the beans rather than a separately served, measurable portion. Treating it as
its own food inflated the meal estimate.

The issue had two causes:

- the vision instruction did not sufficiently distinguish an integrated sauce
  or ingredient from a separately served component; and
- the older fallback behaviour could assign the full plate to every food when
  segmentation failed, creating overlapping portion estimates.

### 2. Corrections applied

The evaluation led to these safeguards:

- the vision contract now keeps integrated sauces, oil, and seasoning in
  `visible_ingredients` unless they have their own measurable serving;
- empty or failed segmentation no longer produces a full-plate depth estimate
  for every detected food;
- segmentation masks support the service's PNG/base64 response format; and
- food/mask names are normalised before matching so harmless casing differences
  do not discard valid masks.

### 3. Retest result

After the correction, the Claude + SAM 3 path returned the beans-and-plantain
meal as **two** top-level components—stewed beans and fried plantain—with masks
covering the two visible regions. It did not create a separate sauce serving.

## Interpretation

This is useful evidence that the orchestration catches and corrects an
important class of failure: duplicate or overlapping meal components. It is
also evidence that the two paths can be compared by cost, latency, and visible
segmentation behaviour.

It is **not** evidence that one pipeline is more accurate in grams or calories.
Neither test meal had a weighed ground-truth reference. A future labelled meal
set would be required to calculate food-detection precision/recall, mask IoU,
portion error, and calorie error.

## Reproducing a comparison

The repository includes the benchmark entry point:

```bash
python scripts/benchmark_vision.py --image path/to/meal.jpg --meal-type lunch
```

Run it only against infrastructure and provider accounts you control. It can
invoke paid model and GPU services. Keep source images and generated reports
private unless you have consent to publish them.

## Status

The production-oriented default remains **GPT-4o + SAM 2 + Depth Anything V2**.
**Claude + SAM 3** remains an evaluated alternative until a broader,
ground-truth evaluation supports a change.
