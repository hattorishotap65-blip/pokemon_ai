"""
Validate consistency across all data files and report issues.

Checks:
  1. All deck.csv card_ids exist in card_master.csv
  2. All deck.csv card_ids have a row in card_detail_raw.csv
  3. All deck.csv card_ids have a row in card_knowledge.csv
  4. card_knowledge.csv has all required columns
  5. Duplicate card_ids within each file
  6. Missing or empty critical fields

Usage:
    python tools/validate_card_data.py
    python tools/validate_card_data.py --deck data/deck.csv --master data/card_master.csv \\
        --details data/card_detail_raw.csv --knowledge data/card_knowledge.csv
"""
import argparse
import csv
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# ---------------------------------------------------------------------------
# Required columns per file
# ---------------------------------------------------------------------------

REQUIRED_KNOWLEDGE_COLS = [
    "card_id", "card_name_en", "card_type",
    "role", "priority", "phase",
    "keep_score", "use_score", "discard_penalty",
    "energy_attach_score", "attack_score",
    "tags",
]

REQUIRED_RAW_COLS = [
    "card_id", "card_name_en", "api_card_id", "source_api",
    "supertype", "hp", "attacks",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _id_set(rows: list[dict], key: str = "card_id") -> set[str]:
    return {str(r.get(key, "")).strip() for r in rows if r.get(key, "").strip()}


def _duplicates(rows: list[dict], key: str = "card_id") -> list[str]:
    seen, dupes = set(), []
    for r in rows:
        v = str(r.get(key, "")).strip()
        if v in seen:
            dupes.append(v)
        seen.add(v)
    return sorted(set(dupes))


def _missing_cols(rows: list[dict], required: list[str]) -> list[str]:
    if not rows:
        return required
    headers = set(rows[0].keys())
    return [c for c in required if c not in headers]


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

class Report:
    def __init__(self, title: str):
        self.title  = title
        self.issues: list[str] = []
        self.oks:    list[str] = []

    def ok(self, msg: str):
        self.oks.append(msg)

    def warn(self, msg: str):
        self.issues.append(f"  WARN  {msg}")

    def error(self, msg: str):
        self.issues.append(f"  ERROR {msg}")

    def print(self):
        print(f"\n{'─'*50}")
        print(f"  {self.title}")
        print(f"{'─'*50}")
        for line in self.issues:
            print(line)
        for line in self.oks:
            print(f"  OK    {line}")
        if not self.issues and not self.oks:
            print("  (no data)")


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate(deck_path, master_path, details_path, knowledge_path):
    deck_rows      = _load(deck_path)
    master_rows    = _load(master_path)
    details_rows   = _load(details_path)
    knowledge_rows = _load(knowledge_path)

    deck_ids    = _id_set(deck_rows)
    master_ids  = _id_set(master_rows)
    detail_ids  = _id_set(details_rows)
    know_ids    = _id_set(knowledge_rows)

    print(f"\n{'═'*50}")
    print(f"  Card Data Validation Report")
    print(f"{'═'*50}")
    print(f"  deck.csv         : {len(deck_rows)} rows  ({len(deck_ids)} unique card IDs)")
    print(f"  card_master.csv  : {len(master_rows)} rows")
    print(f"  card_detail_raw  : {len(details_rows)} rows")
    print(f"  card_knowledge   : {len(knowledge_rows)} rows")

    # ── 1. Deck → Master ─────────────────────────────────────────────────
    r1 = Report("1. deck.csv → card_master.csv coverage")
    missing_master = sorted(deck_ids - master_ids)
    if missing_master:
        r1.error(f"{len(missing_master)} deck cards NOT in card_master.csv: {missing_master}")
    else:
        r1.ok(f"All {len(deck_ids)} deck card IDs found in card_master.csv")
    r1.print()

    # ── 2. Deck → Details ────────────────────────────────────────────────
    r2 = Report("2. deck.csv → card_detail_raw.csv coverage")
    if not details_rows:
        r2.warn("card_detail_raw.csv is empty — run fetch_card_details.py first")
    else:
        missing_detail = sorted(deck_ids - detail_ids)
        if missing_detail:
            r2.error(f"{len(missing_detail)} deck cards missing from card_detail_raw.csv: {missing_detail}")
        else:
            r2.ok(f"All {len(deck_ids)} deck card IDs have detail data")

        # Pending check
        pending_path = os.path.join(os.path.dirname(details_path), "pending_match.csv")
        pending_rows = _load(pending_path)
        pending_ids  = _id_set(pending_rows)
        deck_pending = sorted(deck_ids & pending_ids)
        if deck_pending:
            r2.warn(f"{len(deck_pending)} deck cards still in pending_match.csv: {deck_pending}")
            r2.warn("  → Check pending_match.csv and resolve manually or re-run fetch")
    r2.print()

    # ── 3. Deck → Knowledge ──────────────────────────────────────────────
    r3 = Report("3. deck.csv → card_knowledge.csv coverage")
    if not knowledge_rows:
        r3.warn("card_knowledge.csv is empty — run generate_card_knowledge.py first")
    else:
        missing_know = sorted(deck_ids - know_ids)
        if missing_know:
            r3.error(f"{len(missing_know)} deck cards missing from card_knowledge.csv: {missing_know}")
        else:
            r3.ok(f"All {len(deck_ids)} deck card IDs have knowledge entries")
    r3.print()

    # ── 4. Schema checks ─────────────────────────────────────────────────
    r4 = Report("4. Schema completeness")
    if knowledge_rows:
        missing_kcols = _missing_cols(knowledge_rows, REQUIRED_KNOWLEDGE_COLS)
        if missing_kcols:
            r4.error(f"card_knowledge.csv missing columns: {missing_kcols}")
        else:
            r4.ok(f"card_knowledge.csv has all {len(REQUIRED_KNOWLEDGE_COLS)} required columns")

    if details_rows:
        missing_rcols = _missing_cols(details_rows, REQUIRED_RAW_COLS)
        if missing_rcols:
            r4.error(f"card_detail_raw.csv missing columns: {missing_rcols}")
        else:
            r4.ok(f"card_detail_raw.csv has all {len(REQUIRED_RAW_COLS)} required columns")
    r4.print()

    # ── 5. Duplicate checks ───────────────────────────────────────────────
    r5 = Report("5. Duplicate card_id detection")
    for label, rows in [
        ("deck.csv",         deck_rows),
        ("card_master.csv",  master_rows),
        ("card_detail_raw",  details_rows),
        ("card_knowledge",   knowledge_rows),
    ]:
        dupes = _duplicates(rows)
        if dupes:
            r5.error(f"{label}: duplicate card_ids: {dupes}")
        elif rows:
            r5.ok(f"{label}: no duplicates")
    r5.print()

    # ── 6. Empty critical fields in knowledge ────────────────────────────
    r6 = Report("6. Empty critical fields in card_knowledge.csv")
    if knowledge_rows:
        crit_fields = ["role", "card_type", "priority"]
        for field in crit_fields:
            empties = [r.get("card_id") for r in knowledge_rows
                       if not str(r.get(field, "")).strip()]
            if empties:
                r6.warn(f"'{field}' is empty for card_ids: {empties}")
            else:
                r6.ok(f"'{field}' filled for all {len(knowledge_rows)} knowledge rows")

        # Check for 'unknown' roles
        unknowns = [r.get("card_id") for r in knowledge_rows
                    if str(r.get("role", "")).strip() == "unknown"]
        if unknowns:
            r6.warn(f"role='unknown' for card_ids: {unknowns} — manual review needed")
    r6.print()

    # ── 7. deck.csv count sanity ─────────────────────────────────────────
    r7 = Report("7. deck.csv sanity")
    total_cards = sum(_safe_int(r.get("count", 1)) for r in deck_rows)
    if total_cards == 60:
        r7.ok(f"Total card count = {total_cards} ✓ (legal deck size)")
    else:
        r7.warn(f"Total card count = {total_cards} (should be 60)")
    r7.print()

    # ── Summary ───────────────────────────────────────────────────────────
    all_errors = [r for rep in [r1,r2,r3,r4,r5,r6,r7] for r in rep.issues if "ERROR" in r]
    all_warns  = [r for rep in [r1,r2,r3,r4,r5,r6,r7] for r in rep.issues if "WARN" in r]
    print(f"\n{'═'*50}")
    print(f"  Summary: {len(all_errors)} errors, {len(all_warns)} warnings")
    if not all_errors and not all_warns:
        print("  All checks passed!")
    print(f"{'═'*50}\n")


def _safe_int(val, default=0):
    try:
        return int(str(val or "").strip())
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate PTCG AI card data files")
    # deck.csv lives at project root (submission file); data/deck.csv is a copy for tools
    _deck_default = (
        os.path.join(_ROOT, "data", "deck.csv")
        if os.path.exists(os.path.join(_ROOT, "data", "deck.csv"))
        else os.path.join(_ROOT, "deck.csv")
    )
    parser.add_argument("--deck",      default=_deck_default)
    parser.add_argument("--master",    default=os.path.join(_ROOT, "data", "card_master.csv"))
    parser.add_argument("--details",   default=os.path.join(_ROOT, "data", "card_detail_raw.csv"))
    parser.add_argument("--knowledge", default=os.path.join(_ROOT, "data", "card_knowledge.csv"))
    args = parser.parse_args()

    validate(args.deck, args.master, args.details, args.knowledge)
