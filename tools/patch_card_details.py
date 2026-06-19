"""
Patch known card attributes into card_detail_raw.csv.
Run this when the API fetch returns incomplete data (e.g. empty HP or subtypes).
Usage:  python tools/patch_card_details.py
"""
import csv
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_PATH = os.path.join(_ROOT, "data", "card_detail_raw.csv")

# card_id → fields to override / fill-in
PATCHES: dict[str, dict] = {
    # Evolution line
    "119": {"supertype": "Pokémon", "subtypes": "Basic", "hp": "40",
            "evolvesFrom": "", "evolvesTo": "Drakloak"},
    "120": {"supertype": "Pokémon", "subtypes": "Stage 1", "hp": "90",
            "evolvesFrom": "Dreepy", "evolvesTo": "Dragapult ex"},
    "121": {"supertype": "Pokémon", "subtypes": "Stage 2", "hp": "320",
            "evolvesFrom": "Drakloak", "evolvesTo": ""},
    "122": {"supertype": "Pokémon", "subtypes": "Basic", "hp": "70",
            "evolvesFrom": "", "evolvesTo": ""},
    "164": {"supertype": "Pokémon", "subtypes": "Basic", "hp": "60",
            "evolvesFrom": "", "evolvesTo": ""},
    # Trainers — subtype matters for correct scoring
    "1079": {"supertype": "Trainer", "subtypes": "Item"},
    "1080": {"supertype": "Trainer", "subtypes": "Item"},
    "1086": {"supertype": "Trainer", "subtypes": "Item"},
    "1088": {"supertype": "Trainer", "subtypes": "Item"},
    "1097": {"supertype": "Trainer", "subtypes": "Item"},
    "1116": {"supertype": "Trainer", "subtypes": "Item"},
    "1121": {"supertype": "Trainer", "subtypes": "Item"},
    "1123": {"supertype": "Trainer", "subtypes": "Item"},
    "1182": {"supertype": "Trainer", "subtypes": "Supporter"},
    "1213": {"supertype": "Trainer", "subtypes": "Supporter"},
}

if __name__ == "__main__":
    if not os.path.exists(RAW_PATH):
        print(f"ERROR: {RAW_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(RAW_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    patched = 0
    for row in rows:
        cid = str(row.get("card_id", "")).strip()
        if cid in PATCHES:
            for field, value in PATCHES[cid].items():
                if field in row:
                    row[field] = value
            patched += 1

    with open(RAW_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"Patched {patched} rows in {RAW_PATH}")
