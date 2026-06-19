"""
Clean card_master_raw.csv → card_master.csv
Fixes:
  - UTF-8 BOM
  - Energy symbol tokens: {G} {R} {W} {L} {P} {F} {D} {M}
  - Mojibake: â → ' (RIGHT SINGLE QUOTATION MARK mangled as Latin-1)
              Ã© → é
Usage:
    python tools/clean_card_master.py
    python tools/clean_card_master.py --in data/card_master_raw.csv --out data/card_master.csv
"""
import argparse
import os
import sys

ENERGY_MAP = {
    "Basic {G} Energy": "Basic Grass Energy",
    "Basic {R} Energy": "Basic Fire Energy",
    "Basic {W} Energy": "Basic Water Energy",
    "Basic {L} Energy": "Basic Lightning Energy",
    "Basic {P} Energy": "Basic Psychic Energy",
    "Basic {F} Energy": "Basic Fighting Energy",
    "Basic {D} Energy": "Basic Darkness Energy",
    "Basic {M} Energy": "Basic Metal Energy",
    "Basic {C} Energy": "Basic Colorless Energy",
    "Basic {N} Energy": "Basic Dragon Energy",
}

_ROOT = os.path.join(os.path.dirname(__file__), "..")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in",  dest="src", default=os.path.join(_ROOT, "data", "card_master_raw.csv"))
    parser.add_argument("--out", dest="dst", default=os.path.join(_ROOT, "data", "card_master.csv"))
    args = parser.parse_args()

    with open(args.src, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    # Fix mojibake apostrophe (â from U+2019 UTF-8 bytes read as Latin-1)
    text = text.replace("â", "'")
    # Fix é (Ã© from U+00E9 UTF-8 bytes read as Latin-1)
    text = text.replace("Ã©", "é")
    # Fix any remaining Ã sequences
    text = text.replace("Ã", "")

    # Energy symbols
    for sym, name in ENERGY_MAP.items():
        text = text.replace(sym, name)

    with open(args.dst, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    lines = text.strip().splitlines()
    print(f"Wrote {len(lines)-1} card rows to {args.dst}")
