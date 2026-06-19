"""
Fetch card details from Pokemon TCG API (primary) / TCGdex API (fallback).

Pipeline:
  deck.csv + card_master.csv
      → Pokemon TCG API  (https://api.pokemontcg.io/v2)
      → TCGdex API       (https://api.tcgdex.net/v2/en)  [fallback]
      → card_detail_raw.csv   (confidence >= threshold)
      → pending_match.csv     (low confidence or not found)

Usage:
    python tools/fetch_card_details.py
    python tools/fetch_card_details.py --deck data/deck.csv --master data/card_master.csv
    python tools/fetch_card_details.py --api-key YOUR_PTCG_API_KEY

Get a free API key at: https://dev.pokemontcg.io/
(Without key: 1 000 req/day;  With key: much higher limit)

Rate limiting: 0.5 s between requests by default (--delay to adjust).
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.match_card_details import MatchEngine, PENDING_FIELDS, RAW_FIELDS, THRESHOLD_AUTO_ACCEPT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PTCG_BASE  = "https://api.pokemontcg.io/v2"
TCGDEX_BASE = "https://api.tcgdex.net/v2/en"

ENERGY_SYMBOL_MAP = {
    "{G}": "Grass", "{R}": "Fire", "{W}": "Water",
    "{L}": "Lightning", "{P}": "Psychic", "{C}": "Colorless",
    "{D}": "Darkness", "{M}": "Metal", "{F}": "Fighting",
    "{N}": "Dragon", "{Y}": "Fairy",
}

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, headers: dict | None = None, timeout: int = 12) -> dict | list | None:
    """GET request with error handling. Returns parsed JSON or None."""
    try:
        req = Request(url, headers=headers or {"User-Agent": "ptcg-ai-bot/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"    HTTP {e.code}: {url}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"    URL error: {e.reason} — {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    Error: {e} — {url}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _norm_name(name: str) -> str:
    """Replace {X} energy symbols with English type names for API search."""
    for sym, word in ENERGY_SYMBOL_MAP.items():
        name = name.replace(sym, word)
    return name.strip()


# ---------------------------------------------------------------------------
# Pokemon TCG API
# ---------------------------------------------------------------------------

def _ptcg_search(
    name: str,
    expansion: str = "",
    number: str = "",
    api_key: str = "",
    delay: float = 0.5,
) -> list[dict]:
    """
    Search Pokemon TCG API for candidates.
    Tries: (name + set + number) → (name + number) → (name only).
    """
    headers = {}
    if api_key:
        headers["X-Api-Key"] = api_key

    def _fetch(q: str) -> list[dict]:
        url = f"{PTCG_BASE}/cards?q={quote(q)}&pageSize=8"
        data = _get(url, headers)
        time.sleep(delay)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []

    api_name = _norm_name(name).replace('"', '\\"')

    # Try most specific first
    if expansion and number:
        results = _fetch(f'name:"{api_name}" number:{number} set.ptcgoCode:{expansion}')
        if results:
            return results

    if number:
        results = _fetch(f'name:"{api_name}" number:{number}')
        if results:
            return results

    # Broadest: name only (may return multiple)
    results = _fetch(f'name:"{api_name}"')
    return results


# ---------------------------------------------------------------------------
# TCGdex API (fallback)
# ---------------------------------------------------------------------------

def _tcgdex_search(
    name: str,
    expansion: str = "",
    number: str = "",
    delay: float = 0.5,
) -> list[dict]:
    """Search TCGdex API. Converts to PTCG-like format for MatchEngine."""
    api_name = _norm_name(name)
    url = f"{TCGDEX_BASE}/cards?name={quote(api_name)}"
    if number:
        url += f"&localId={quote(str(number))}"

    data = _get(url)
    time.sleep(delay)

    results = []
    raw = data if isinstance(data, list) else (data.get("cards", []) if isinstance(data, dict) else [])

    for c in raw:
        # Convert TCGdex format → PTCG-like dict for uniform processing
        results.append({
            "id": c.get("id", ""),
            "name": c.get("name", ""),
            "supertype": c.get("category", ""),
            "subtypes": c.get("types", []),
            "hp": str(c.get("hp", "")),
            "types": c.get("types", []),
            "evolvesFrom": "",
            "evolvesTo": [],
            "rules": [],
            "abilities": [],
            "attacks": [
                {
                    "name": a.get("name", ""),
                    "cost": a.get("cost", []),
                    "damage": str(a.get("damage", "")),
                    "text": a.get("effect", ""),
                }
                for a in (c.get("attacks") or [])
            ],
            "weaknesses": [],
            "resistances": [],
            "retreatCost": [],
            "convertedRetreatCost": 0,
            "regulationMark": "",
            "set": {
                "id": expansion.lower(),
                "name": expansion,
                "ptcgoCode": expansion,
            },
            "number": str(c.get("localId", number)),
            "rarity": "",
            "images": {
                "small": c.get("image", ""),
                "large": c.get("image", ""),
            },
            "_source": "tcgdex",
        })
    return results


# ---------------------------------------------------------------------------
# Flatten API card → flat CSV row
# ---------------------------------------------------------------------------

def _flatten(card: dict, card_id: str, card_name_en: str) -> dict:
    """Flatten a PTCG API card dict into our raw CSV schema."""
    source = card.pop("_source", "ptcg")

    abilities = card.get("abilities") or []
    attacks   = card.get("attacks") or []

    attack_costs  = " | ".join("/".join(a.get("cost", [])) for a in attacks)
    attack_damage = " | ".join(str(a.get("damage", "")) for a in attacks)
    attack_text   = " | ".join(a.get("text", "") for a in attacks if a.get("text"))

    set_info = card.get("set") or {}
    images   = card.get("images") or {}

    # Build URL from images or API endpoint
    api_card_id = card.get("id", "")
    source_url  = (images.get("large")
                   or images.get("small")
                   or (f"{PTCG_BASE}/cards/{api_card_id}" if source == "ptcg" and api_card_id else ""))

    return {
        "card_id":              card_id,
        "card_name_en":         card_name_en,
        "api_card_id":          api_card_id,
        "source_api":           source,
        "source_url":           source_url,
        "supertype":            card.get("supertype", ""),
        "subtypes":             ",".join(card.get("subtypes") or []),
        "hp":                   card.get("hp", ""),
        "types":                ",".join(card.get("types") or []),
        "evolvesFrom":          card.get("evolvesFrom", ""),
        "evolvesTo":            ",".join(card.get("evolvesTo") or []),
        "rules":                " | ".join(card.get("rules") or []),
        "abilities":            json.dumps(abilities, ensure_ascii=False),
        "attacks":              json.dumps(attacks, ensure_ascii=False),
        "attack_costs":         attack_costs,
        "attack_damage":        attack_damage,
        "attack_text":          attack_text,
        "weaknesses":           json.dumps(card.get("weaknesses") or [], ensure_ascii=False),
        "resistances":          json.dumps(card.get("resistances") or [], ensure_ascii=False),
        "retreatCost":          ",".join(card.get("retreatCost") or []),
        "convertedRetreatCost": str(card.get("convertedRetreatCost", "")),
        "regulationMark":       card.get("regulationMark", ""),
        "set_name":             set_info.get("name", ""),
        "set_id":               set_info.get("id", ""),
        "set_ptcgoCode":        set_info.get("ptcgoCode", ""),
        "number":               card.get("number", ""),
        "rarity":               card.get("rarity", ""),
        "images_small":         images.get("small", ""),
        "images_large":         images.get("large", ""),
    }


# ---------------------------------------------------------------------------
# CSV I/O
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


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    deck_path: str,
    master_path: str,
    out_raw: str,
    out_pending: str,
    api_key: str = "",
    delay: float = 0.5,
    skip_existing: bool = True,
):
    engine = MatchEngine()

    # Load deck (unique card IDs only)
    deck_rows = _load_csv(deck_path)
    deck_ids  = {str(r["card_id"]) for r in deck_rows}
    print(f"Deck: {len(deck_ids)} unique card IDs from {deck_path}")

    # Load card master
    master_rows = _load_csv(master_path)
    master = {str(r["card_id"]): r for r in master_rows}
    print(f"Master: {len(master)} cards from {master_path}")

    # Cards already in raw output (skip-existing mode)
    existing_raw = {}
    if skip_existing and os.path.exists(out_raw):
        for r in _load_csv(out_raw):
            existing_raw[str(r["card_id"])] = r
        print(f"Skipping {len(existing_raw)} already-fetched cards")

    targets = [cid for cid in sorted(deck_ids) if cid not in existing_raw]
    missing_from_master = [cid for cid in targets if cid not in master]
    if missing_from_master:
        print(f"WARNING: {len(missing_from_master)} card IDs not in card_master.csv: "
              f"{missing_from_master}", file=sys.stderr)

    raw_rows: list[dict] = list(existing_raw.values())
    pending_rows: list[dict] = []
    stats = {"accept": 0, "pending": 0, "no_match": 0, "error": 0}

    to_fetch = [cid for cid in targets if cid in master]
    print(f"\nFetching {len(to_fetch)} cards (delay={delay}s between requests)...")
    print(f"  API key: {'YES' if api_key else 'NO (1000 req/day limit)'}")
    print()

    for idx, card_id in enumerate(to_fetch, 1):
        info   = master[card_id]
        name   = info.get("card_name_en", "")
        expn   = info.get("expansion", "")
        col_no = info.get("collection_no", "")

        print(f"  [{idx:>3}/{len(to_fetch)}] #{card_id} {name} ({expn} {col_no})", end=" ")

        try:
            # --- Primary: Pokemon TCG API ---
            candidates = _ptcg_search(name, expn, col_no, api_key=api_key, delay=delay)
            source = "ptcg"

            if not candidates:
                # --- Fallback: TCGdex ---
                candidates = _tcgdex_search(name, expn, col_no, delay=delay)
                source = "tcgdex"

            decision, best, score = engine.decide(candidates, name, expn, col_no)
            print(f"→ {decision.upper()} ({score:.2f}) [{source}]")

            if decision == "accept" and best:
                best["_source"] = source
                raw_rows.append(_flatten(best, card_id, name))
                stats["accept"] += 1

            else:
                reason = "no_match" if decision == "no_match" else f"low_confidence({score:.2f})"
                pending_rows.append({
                    "card_id":          card_id,
                    "card_name_en":     name,
                    "expansion":        expn,
                    "collection_no":    col_no,
                    "reason":           reason,
                    "candidate_name":   (best or {}).get("name", ""),
                    "candidate_set":    ((best or {}).get("set") or {}).get("ptcgoCode", "") if isinstance((best or {}).get("set"), dict) else "",
                    "candidate_number": (best or {}).get("number", ""),
                    "candidate_url":    ((best or {}).get("images") or {}).get("large", ""),
                    "confidence_score": f"{score:.3f}",
                })
                stats["pending" if decision == "pending" else "no_match"] += 1

        except Exception as exc:
            print(f"→ ERROR: {exc}")
            pending_rows.append({
                "card_id": card_id, "card_name_en": name,
                "expansion": expn, "collection_no": col_no,
                "reason": f"exception: {exc}",
                "candidate_name": "", "candidate_set": "",
                "candidate_number": "", "candidate_url": "",
                "confidence_score": "0.000",
            })
            stats["error"] += 1

    # Write outputs
    _write_csv(raw_rows, out_raw, RAW_FIELDS)
    _write_csv(pending_rows, out_pending, PENDING_FIELDS)

    print(f"\n{'='*44}")
    print(f"  Fetched : {stats['accept']:>4} accepted")
    print(f"  Pending : {stats['pending']:>4} low-confidence")
    print(f"  No match: {stats['no_match']:>4}")
    print(f"  Errors  : {stats['error']:>4}")
    print(f"  → Raw    : {out_raw}")
    print(f"  → Pending: {out_pending}")

    if pending_rows:
        print(f"\nReview {out_pending}, then re-run or manually fill details.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_ROOT = os.path.join(os.path.dirname(__file__), "..")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch card details from Pokemon TCG API")
    parser.add_argument("--deck",    default=os.path.join(_ROOT, "data", "deck.csv"))
    parser.add_argument("--master",  default=os.path.join(_ROOT, "data", "card_master.csv"))
    parser.add_argument("--out",     default=os.path.join(_ROOT, "data", "card_detail_raw.csv"))
    parser.add_argument("--pending", default=os.path.join(_ROOT, "data", "pending_match.csv"))
    parser.add_argument("--api-key", default=os.environ.get("PTCG_API_KEY", ""),
                        help="Pokemon TCG API key (or set PTCG_API_KEY env var)")
    parser.add_argument("--delay",   type=float, default=0.5,
                        help="Seconds between API requests (default 0.5)")
    parser.add_argument("--no-skip", action="store_true",
                        help="Re-fetch even if card already in card_detail_raw.csv")
    args = parser.parse_args()

    run(
        deck_path    = args.deck,
        master_path  = args.master,
        out_raw      = args.out,
        out_pending  = args.pending,
        api_key      = args.api_key,
        delay        = args.delay,
        skip_existing= not args.no_skip,
    )
