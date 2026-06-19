"""
Extract Card ID list from PDF → data/card_master.csv

PDF columns expected: Card ID | Card Name | Expansion | Collection No. | Link

Usage:
    python tools/build_card_master.py --pdf Card_ID_List_EN.pdf
    python tools/build_card_master.py --pdf Card_ID_List_EN.pdf --out data/card_master.csv -v

Requires:
    pip install pdfplumber
"""
import argparse
import csv
import os
import re
import sys

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def _require_pdfplumber():
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        print("ERROR: pdfplumber not installed.\n  Run: pip install pdfplumber", file=sys.stderr)
        sys.exit(1)

# ---------------------------------------------------------------------------
# Energy symbol normalisation
# ---------------------------------------------------------------------------

ENERGY_SYMBOL_MAP = {
    "{G}": "Grass",
    "{R}": "Fire",
    "{W}": "Water",
    "{L}": "Lightning",
    "{P}": "Psychic",
    "{C}": "Colorless",
    "{D}": "Darkness",
    "{M}": "Metal",
    "{F}": "Fighting",
    "{N}": "Dragon",
    "{Y}": "Fairy",
}


def normalize_name(name: str) -> str:
    """Replace {X} energy symbols with English type names."""
    if not name:
        return ""
    for sym, word in ENERGY_SYMBOL_MAP.items():
        name = name.replace(sym, word)
    return name.strip()


# ---------------------------------------------------------------------------
# Row parsing helpers
# ---------------------------------------------------------------------------

def _is_card_id(val) -> bool:
    return bool(val and re.match(r"^\d+$", str(val).strip()))


def _parse_row(row: list) -> dict | None:
    """
    Parse one table row into a card entry.
    Expected columns: Card ID | Card Name | Expansion | Collection No. [| Link]
    """
    if not row or len(row) < 4:
        return None
    cells = [str(c).strip() if c is not None else "" for c in row]
    if not _is_card_id(cells[0]):
        return None
    return {
        "card_id": cells[0],
        "card_name_en": normalize_name(cells[1]),
        "expansion": cells[2],
        "collection_no": cells[3],
        "link": cells[4] if len(cells) > 4 else "",
    }


def _parse_text_line(line: str) -> dict | None:
    """
    Fallback parser for plain-text lines when table extraction returns nothing.
    Accepts tab-separated or multi-space-separated values.
    """
    parts = re.split(r"\t|  +", line.strip())
    if len(parts) < 4 or not _is_card_id(parts[0]):
        return None
    return {
        "card_id": parts[0].strip(),
        "card_name_en": normalize_name(parts[1].strip()),
        "expansion": parts[2].strip(),
        "collection_no": parts[3].strip(),
        "link": parts[4].strip() if len(parts) > 4 else "",
    }


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: str, verbose: bool = False) -> list[dict]:
    pdfplumber = _require_pdfplumber()
    rows: list[dict] = []
    seen: set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        print(f"  Pages: {n_pages}")

        for page_idx, page in enumerate(pdf.pages, 1):
            page_count = 0

            # Strategy 1 — structured table extraction
            for table in (page.extract_tables() or []):
                for raw_row in (table or []):
                    entry = _parse_row(raw_row)
                    if entry and entry["card_id"] not in seen:
                        rows.append(entry)
                        seen.add(entry["card_id"])
                        page_count += 1

            # Strategy 2 — plain text fallback when no table found
            if page_count == 0:
                for line in (page.extract_text() or "").split("\n"):
                    entry = _parse_text_line(line)
                    if entry and entry["card_id"] not in seen:
                        rows.append(entry)
                        seen.add(entry["card_id"])
                        page_count += 1

            if verbose:
                print(f"  Page {page_idx:>3}/{n_pages}: {page_count:>4} cards")

    rows.sort(key=lambda r: int(r["card_id"]))
    return rows


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

FIELDNAMES = ["card_id", "card_name_en", "expansion", "collection_no", "link"]


def write_csv(rows: list[dict], out_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF → card_master.csv")
    parser.add_argument("--pdf", required=True, help="Path to Card_ID_List_EN.pdf")
    parser.add_argument("--out", default="data/card_master.csv", help="Output CSV path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"ERROR: File not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting: {args.pdf}")
    cards = extract_from_pdf(args.pdf, verbose=args.verbose)
    write_csv(cards, args.out)
    print(f"Done: {len(cards)} cards → {args.out}")
