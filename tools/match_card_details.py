"""
Matching engine: score API candidates against PDF card data.

Can be imported by fetch_card_details.py, or run standalone to
re-evaluate pending_match.csv after manual inspection.

Usage (standalone):
    python tools/match_card_details.py \\
        --pending data/pending_match.csv \\
        --master  data/card_master.csv   \\
        --out     data/card_detail_raw.csv
"""
import argparse
import csv
import os
import re
import sys
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

THRESHOLD_AUTO_ACCEPT = 0.80   # >= this → write to card_detail_raw
THRESHOLD_PENDING     = 0.40   # < this AND no better → write to pending_match

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _strip_number(s: str) -> str:
    """'130/191' → '130', '001' → '1', '  130 ' → '130'."""
    return str(s or "").split("/")[0].lstrip("0").strip() or "0"


# ---------------------------------------------------------------------------
# Similarity functions
# ---------------------------------------------------------------------------

def name_similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def number_eq(pdf_no: str, api_no: str) -> bool:
    return _strip_number(pdf_no) == _strip_number(api_no)


def set_eq(pdf_set: str, api_set: str) -> bool:
    return (pdf_set or "").upper().strip() == (api_set or "").upper().strip()


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def confidence_score(
    pdf_name: str, pdf_set: str, pdf_number: str,
    api_name: str, api_set: str, api_number: str,
) -> float:
    """
    Return [0.0, 1.0].  Weights:
      name similarity  ~50%
      set match        ~25%
      number match     ~25%
    """
    sim     = name_similarity(pdf_name, api_name)
    s_match = set_eq(pdf_set, api_set)
    n_match = number_eq(pdf_number, api_number)

    if sim >= 0.99 and s_match and n_match:
        return 1.00
    if sim >= 0.99 and n_match:
        return 0.90
    if sim >= 0.95 and s_match and n_match:
        return 0.88
    if sim >= 0.99 and s_match:
        return 0.78
    if sim >= 0.80 and s_match and n_match:
        return 0.75
    if sim >= 0.99:
        return 0.60
    if sim >= 0.80 and s_match:
        return 0.55
    if sim >= 0.80 and n_match:
        return 0.50
    if sim >= 0.70:
        return 0.35
    return round(sim * 0.4, 3)


# ---------------------------------------------------------------------------
# Candidate selector
# ---------------------------------------------------------------------------

class MatchEngine:
    def __init__(
        self,
        auto_accept: float = THRESHOLD_AUTO_ACCEPT,
        pending_threshold: float = THRESHOLD_PENDING,
    ):
        self.auto_accept = auto_accept
        self.pending_threshold = pending_threshold

    def pick_best(
        self,
        candidates: list[dict],
        pdf_name: str,
        pdf_set: str,
        pdf_number: str,
    ) -> tuple[dict | None, float]:
        """
        Return (best_candidate, confidence).
        Returns (None, 0.0) if no candidates.
        """
        if not candidates:
            return None, 0.0

        scored = []
        for c in candidates:
            api_name   = c.get("name", "")
            api_set    = c.get("set", {}).get("ptcgoCode", "") if isinstance(c.get("set"), dict) else ""
            api_number = c.get("number", "")
            score = confidence_score(pdf_name, pdf_set, pdf_number,
                                     api_name, api_set, api_number)
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        return best, best_score

    def decide(
        self,
        candidates: list[dict],
        pdf_name: str,
        pdf_set: str,
        pdf_number: str,
    ) -> tuple[str, dict | None, float]:
        """
        Return (decision, best_candidate, confidence).
        decision: 'accept' | 'pending' | 'no_match'
        """
        best, score = self.pick_best(candidates, pdf_name, pdf_set, pdf_number)

        if best is None:
            return "no_match", None, 0.0
        if score >= self.auto_accept:
            return "accept", best, score
        return "pending", best, score


# ---------------------------------------------------------------------------
# Standalone: re-process pending_match.csv
# ---------------------------------------------------------------------------

def _load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(rows: list[dict], path: str, fieldnames: list[str]):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


PENDING_FIELDS = [
    "card_id", "card_name_en", "expansion", "collection_no",
    "reason", "candidate_name", "candidate_set", "candidate_number",
    "candidate_url", "confidence_score",
]

RAW_FIELDS = [
    "card_id", "card_name_en", "api_card_id", "source_api", "source_url",
    "supertype", "subtypes", "hp", "types", "evolvesFrom", "evolvesTo",
    "rules", "abilities", "attacks", "attack_costs", "attack_damage",
    "attack_text", "weaknesses", "resistances", "retreatCost",
    "convertedRetreatCost", "regulationMark", "set_name", "set_id",
    "set_ptcgoCode", "number", "rarity", "images_small", "images_large",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-evaluate pending_match.csv after manual inspection"
    )
    parser.add_argument("--pending", default="data/pending_match.csv")
    parser.add_argument("--master",  default="data/card_master.csv")
    parser.add_argument("--out",     default="data/card_detail_raw.csv")
    args = parser.parse_args()

    pending = _load_csv(args.pending)
    if not pending:
        print("No pending records found in", args.pending)
        sys.exit(0)

    engine = MatchEngine()
    still_pending = []
    promoted = []

    print(f"Reviewing {len(pending)} pending records ...")
    for row in pending:
        score = float(row.get("confidence_score") or 0)
        if score >= engine.auto_accept:
            promoted.append(row)
            print(f"  PROMOTED  {row['card_id']:>4}  {row['card_name_en']}  ({score:.2f})")
        else:
            still_pending.append(row)
            print(f"  PENDING   {row['card_id']:>4}  {row['card_name_en']}  ({score:.2f}) — needs manual review")

    _write_csv(still_pending, args.pending, PENDING_FIELDS)
    print(f"\nStill pending : {len(still_pending)} → {args.pending}")
    print(f"Promoted      : {len(promoted)}")
    print("(Promoted rows need to be merged into card_detail_raw.csv manually or by re-running fetch)")
