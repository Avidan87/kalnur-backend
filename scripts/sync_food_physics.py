"""
sync_food_physics.py - Auto-sync checker and scaffolder for food physics files.

Whenever a new food is added to nigerian_foods_v2_improved.jsonl, run this script.
It will:
  1. Check which foods are missing from nigerian_food_heights.py
  2. Check which foods are missing from nigerian_food_densities.py
  3. Check which foods are missing from nigerian_food_priors.py
  4. Print a ready-to-paste scaffold for every missing entry

Usage:
    python scripts/sync_food_physics.py
    python scripts/sync_food_physics.py --auto-append   # appends scaffolds directly to files
"""

import json
import sys
import argparse
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.parent
JSONL_PATH = ROOT / "knowledge-base" / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"
HEIGHTS_PATH = ROOT / "modal" / "nigerian_food_heights.py"
DENSITIES_PATH = ROOT / "modal" / "nigerian_food_densities.py"
PRIORS_PATH = ROOT / "modal" / "nigerian_food_priors.py"

# Shape -> prior config defaults
SHAPE_TO_PRIOR = {
    "mound":      {"shape": "mound",          "height_ratio": 0.3},
    "bowl":       {"shape": "bowl_contained",  "height_ratio": 0.5},
    "flat_piece": {"shape": "flat_pieces",     "height_ratio": 0.15},
    "flat_stack": {"shape": "flat_pieces",     "height_ratio": 0.15},
    "flat":       {"shape": "flat_pieces",     "height_ratio": 0.1},
    "pieces":     {"shape": "flat_pieces",     "height_ratio": 0.2},
    "sphere":     {"shape": "dome",            "height_ratio": 0.55},
    "heap":       {"shape": "mound",           "height_ratio": 0.4},
    "layered":    {"shape": "mound",           "height_ratio": 0.3},
    "cylinder":   {"shape": "dome",            "height_ratio": 0.5},
    "liquid":     {"shape": "bowl_contained",  "height_ratio": 0.6},
    "mixed":      {"shape": "mound",           "height_ratio": 0.3},
}

# Category -> sensible density fallback (g/ml)
CATEGORY_DENSITY = {
    "starch":       0.90,
    "swallow":      1.00,
    "soup":         0.94,
    "protein":      1.00,
    "protein_dish": 0.92,
    "vegetable":    0.75,
    "fruit":        0.95,
    "snack":        0.65,
    "beverage":     1.01,
    "condiment":    0.90,
    "breakfast":    0.55,
}

# Category -> sensible height fallback (min, typical, max, shape)
CATEGORY_HEIGHT = {
    "starch":       (2.0, 4.0, 6.0, "mound"),
    "swallow":      (4.0, 7.0, 10.0, "mound"),
    "soup":         (2.0, 4.0, 6.0, "bowl"),
    "protein":      (1.5, 3.0, 5.0, "flat_piece"),
    "protein_dish": (2.0, 3.5, 5.0, "bowl"),
    "vegetable":    (1.5, 3.0, 5.0, "heap"),
    "fruit":        (3.0, 5.0, 7.0, "sphere"),
    "snack":        (2.0, 3.5, 5.0, "heap"),
    "beverage":     (6.0, 9.0, 12.0, "liquid"),
    "condiment":    (0.5, 1.5, 3.0, "liquid"),
    "breakfast":    (2.0, 4.0, 6.0, "flat_stack"),
}


def load_jsonl():
    foods = []
    with open(JSONL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                foods.append(json.loads(line))
    return foods


def load_heights_keys():
    """Parse all keys from NIGERIAN_FOOD_HEIGHTS dict."""
    keys = set()
    text = HEIGHTS_PATH.read_text(encoding="utf-8")
    import re
    for m in re.finditer(r'"([a-z0-9_]+)"\s*:', text):
        keys.add(m.group(1))
    return keys


def load_density_keys():
    """Parse all keys from NIGERIAN_FOOD_DENSITIES dict."""
    keys = set()
    text = DENSITIES_PATH.read_text(encoding="utf-8")
    import re
    for m in re.finditer(r'"([a-z0-9_-]+)"\s*:', text):
        keys.add(m.group(1))
    return keys


def load_prior_keys():
    """Parse all keys from FOOD_SHAPES dict."""
    keys = set()
    text = PRIORS_PATH.read_text(encoding="utf-8")
    import re
    for m in re.finditer(r"'([a-z0-9_]+)'\s*:", text):
        keys.add(m.group(1))
    return keys


def is_covered(food_id, keys):
    """Check if food_id or any partial match exists in keys."""
    if food_id in keys:
        return True
    return any(k in food_id or food_id in k for k in keys)


def check_missing(foods):
    height_keys = load_heights_keys()
    density_keys = load_density_keys()
    prior_keys = load_prior_keys()

    missing_h, missing_d, missing_p = [], [], []

    for food in foods:
        fid = food["id"]
        fid_dash = fid.replace("_", "-")

        if not is_covered(fid, height_keys):
            missing_h.append(food)
        if not is_covered(fid_dash, density_keys):
            missing_d.append(food)
        if not is_covered(fid, prior_keys):
            missing_p.append(food)

    return missing_h, missing_d, missing_p


def scaffold_height(food):
    fid = food["id"]
    cat = food.get("category", "starch")
    kb_height = food.get("typical_height_cm")
    kb_density = food.get("density_g_per_ml", 0.9)
    defaults = CATEGORY_HEIGHT.get(cat, (2.0, 4.0, 6.0, "mound"))

    if kb_height:
        # Use KB height as typical, estimate min/max
        min_h = round(kb_height * 0.6, 1)
        max_h = round(kb_height * 1.6, 1)
        shape = defaults[3]
        return f'    "{fid}": ({min_h}, {kb_height}, {max_h}, "{shape}"),  # auto-scaffolded'
    else:
        mn, typ, mx, shape = defaults
        return f'    "{fid}": ({mn}, {typ}, {mx}, "{shape}"),  # auto-scaffolded, check manually'


def scaffold_density(food):
    fid_dash = food["id"].replace("_", "-")
    kb_density = food.get("density_g_per_ml")
    cat = food.get("category", "starch")

    if kb_density:
        return f'    "{fid_dash}": {kb_density},  # from knowledge base'
    else:
        fallback = CATEGORY_DENSITY.get(cat, 0.90)
        return f'    "{fid_dash}": {fallback},  # auto-scaffolded, check manually'


def scaffold_prior(food, height_keys):
    fid = food["id"]
    cat = food.get("category", "starch")
    kb_height = food.get("typical_height_cm")

    # Try to get shape from heights file match
    shape_type = CATEGORY_HEIGHT.get(cat, (0, 0, 0, "mound"))[3]
    prior_cfg = SHAPE_TO_PRIOR.get(shape_type, {"shape": "mound", "height_ratio": 0.3})

    typical_h = kb_height if kb_height else CATEGORY_HEIGHT.get(cat, (0, 4.0, 0, "mound"))[1]

    return (
        f"        '{fid}': {{'shape': '{prior_cfg['shape']}', "
        f"'height_ratio': {prior_cfg['height_ratio']}, "
        f"'typical_height_cm': {typical_h}}},  # auto-scaffolded"
    )


def print_report(missing_h, missing_d, missing_p, foods):
    total = len(foods)
    print(f"\n{'='*60}")
    print(f"  FOOD PHYSICS SYNC REPORT  ({total} foods in KB)")
    print(f"{'='*60}")
    print(f"  Heights  : {total - len(missing_h)}/{total} covered  ({len(missing_h)} missing)")
    print(f"  Densities: {total - len(missing_d)}/{total} covered  ({len(missing_d)} missing)")
    print(f"  Priors   : {total - len(missing_p)}/{total} covered  ({len(missing_p)} missing)")

    if not missing_h and not missing_d and not missing_p:
        print("\n  All 3 files are fully in sync with the knowledge base!")
        return

    if missing_h:
        print(f"\n--- ADD TO nigerian_food_heights.py (NIGERIAN_FOOD_HEIGHTS dict) ---")
        for food in missing_h:
            print(scaffold_height(food))

    if missing_d:
        print(f"\n--- ADD TO nigerian_food_densities.py (NIGERIAN_FOOD_DENSITIES dict) ---")
        for food in missing_d:
            print(scaffold_density(food))

    if missing_p:
        print(f"\n--- ADD TO nigerian_food_priors.py (FOOD_SHAPES dict) ---")
        for food in missing_p:
            print(scaffold_prior(food, set()))

    print(f"\n{'='*60}")
    print("  Scaffolded values use KB data + category defaults.")
    print("  Review and adjust before committing — especially:")
    print("    - Leafy veg densities (often 0.06-0.15, not 0.75)")
    print("    - Bread densities (often 0.28-0.40, not 0.90)")
    print("    - Whole fruit heights (sphere shape, 6-9cm)")
    print(f"{'='*60}\n")


def auto_append(missing_h, missing_d, missing_p, foods):
    """Append scaffolded entries directly to the files."""
    height_keys = load_heights_keys()

    if missing_h:
        lines = ["\n    # AUTO-SCAFFOLDED — review and adjust values\n"]
        for food in missing_h:
            lines.append(scaffold_height(food) + "\n")
        # Insert before closing } of NIGERIAN_FOOD_HEIGHTS
        text = HEIGHTS_PATH.read_text(encoding="utf-8")
        insert_at = text.rfind("}\n\n\n# Shape-based")
        if insert_at == -1:
            insert_at = text.rfind("}\n\n\n# Convenience")
        new_text = text[:insert_at] + "".join(lines) + text[insert_at:]
        HEIGHTS_PATH.write_text(new_text, encoding="utf-8")
        print(f"Appended {len(missing_h)} entries to nigerian_food_heights.py")

    if missing_d:
        lines = ["\n    # AUTO-SCAFFOLDED — review and adjust values\n"]
        for food in missing_d:
            lines.append(scaffold_density(food) + "\n")
        text = DENSITIES_PATH.read_text(encoding="utf-8")
        insert_at = text.rfind("}\n\n\ndef get_density")
        new_text = text[:insert_at] + "".join(lines) + text[insert_at:]
        DENSITIES_PATH.write_text(new_text, encoding="utf-8")
        print(f"Appended {len(missing_d)} entries to nigerian_food_densities.py")

    if missing_p:
        lines = ["\n        # AUTO-SCAFFOLDED — review and adjust values\n"]
        for food in missing_p:
            lines.append(scaffold_prior(food, height_keys) + "\n")
        text = PRIORS_PATH.read_text(encoding="utf-8")
        insert_at = text.rfind("    }\n\n    def apply_shape_prior")
        new_text = text[:insert_at] + "".join(lines) + text[insert_at:]
        PRIORS_PATH.write_text(new_text, encoding="utf-8")
        print(f"Appended {len(missing_p)} entries to nigerian_food_priors.py")


def main():
    parser = argparse.ArgumentParser(description="Sync food physics files with knowledge base")
    parser.add_argument("--auto-append", action="store_true",
                        help="Automatically append scaffolded entries to files")
    args = parser.parse_args()

    foods = load_jsonl()
    missing_h, missing_d, missing_p = check_missing(foods)

    print_report(missing_h, missing_d, missing_p, foods)

    if args.auto_append and (missing_h or missing_d or missing_p):
        print("Auto-appending scaffolded entries...")
        auto_append(missing_h, missing_d, missing_p, foods)
        print("Done! Review the appended entries before deploying.")


if __name__ == "__main__":
    main()
