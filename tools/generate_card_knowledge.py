"""
Generate data/card_knowledge.csv from data/card_detail_raw.csv.

Rules are purely heuristic (keyword + stat based).
The output CSV is designed to be hand-edited after generation.

Usage:
    python tools/generate_card_knowledge.py
    python tools/generate_card_knowledge.py --details data/card_detail_raw.csv --out data/card_knowledge.csv
    python tools/generate_card_knowledge.py --merge   # Merge into existing CSV (keep hand-edited rows)
"""
import argparse
import csv
import json
import os
import re
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

KNOWLEDGE_FIELDS = [
    "card_id", "card_name_en", "card_type",
    "role", "sub_role",
    "priority", "phase",
    "keep_score", "use_score", "search_score",
    "discard_penalty", "bench_score", "energy_attach_score",
    "attack_score", "evolution_score", "risk_score",
    "tags", "notes",
]

DEFAULTS = {f: "" for f in KNOWLEDGE_FIELDS}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(val, default: int = 0) -> int:
    try:
        return int(str(val or "").replace("+", "").replace("×", "").replace("x", "").strip())
    except (ValueError, TypeError):
        return default


def _lower(val) -> str:
    return (val or "").lower()


def _contains(text: str, *keywords) -> bool:
    t = _lower(text)
    return any(k in t for k in keywords)


def _max_damage(attack_damage_str: str) -> int:
    """Parse '60 | 120+' → 120."""
    best = 0
    for part in re.split(r"[|,]", attack_damage_str or ""):
        part = part.strip()
        nums = re.findall(r"\d+", part)
        for n in nums:
            best = max(best, int(n))
    return best


def _count_attacks(attacks_json: str) -> int:
    try:
        data = json.loads(attacks_json or "[]")
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def _ability_text(abilities_json: str) -> str:
    try:
        data = json.loads(abilities_json or "[]")
        if isinstance(data, list):
            return " ".join(a.get("text", "") for a in data)
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Pokemon classifier
# ---------------------------------------------------------------------------

def _classify_pokemon(row: dict) -> dict:
    name       = row.get("card_name_en", "")
    hp         = _safe_int(row.get("hp"))
    subtypes   = row.get("subtypes", "")
    evolves_from = row.get("evolvesFrom", "")
    attack_dmg = _max_damage(row.get("attack_damage", ""))
    attack_txt = _lower(row.get("attack_text", ""))
    ability_txt = _ability_text(row.get("abilities", "[]"))
    n_attacks  = _count_attacks(row.get("attacks", "[]"))

    is_ex      = bool(re.search(r"\bex\b|\bEX\b|\bVMAX\b|\bVSTAR\b|\bV-UNION\b", name))
    is_stage2  = "Stage 2" in subtypes
    is_stage1  = "Stage 1" in subtypes
    is_basic   = "Basic" in subtypes
    has_ability = bool(ability_txt.strip())

    # ----- Role -----
    if is_ex and hp >= 200:
        role = "main_attacker"
    elif is_stage2 and attack_dmg >= 100:
        role = "main_attacker"
    elif is_stage1 and attack_dmg >= 80 and not has_ability:
        role = "main_attacker"
    elif has_ability and _contains(ability_txt, "search", "look at", "put a card"):
        role = "engine"
    elif has_ability:
        role = "support_pokemon"
    elif evolves_from:
        role = "evolution_bridge"
    else:
        role = "evolution_base"

    # ----- Sub-role -----
    if evolves_from:
        sub_role = f"evolves_from_{re.sub(r'[^a-z0-9]', '_', evolves_from.lower())}"
    elif role == "engine":
        sub_role = "search_engine" if _contains(ability_txt, "search", "look at") else "draw_engine"
    elif role == "support_pokemon":
        sub_role = "bench_support"
    else:
        sub_role = ""

    # ----- Priority -----
    priority = (
        "high"   if role in ("main_attacker", "engine") else
        "medium" if role in ("support_pokemon", "evolution_bridge") else
        "medium"
    )

    # ----- Phase -----
    phase = (
        "early"     if is_basic and not evolves_from else
        "early_mid" if is_stage1 or role == "engine" else
        "mid"       if role == "main_attacker" else
        "any"
    )

    # ----- Scores -----
    attack_score    = min(10, attack_dmg // 20) if attack_dmg else 0
    bench_score     = 8 if role == "evolution_base" else (9 if role == "engine" else 5)
    energy_attach   = 9 if role == "main_attacker" else 3
    evolution_score = (
        9 if is_basic and not evolves_from else
        8 if is_stage1 else
        7 if is_stage2 else 5
    )
    discard_penalty = (
        9 if role in ("main_attacker", "engine") else
        7 if role in ("evolution_bridge", "support_pokemon") else
        5
    )
    keep_score = max(1, discard_penalty - 1)
    use_score  = attack_score + 2 if role == "main_attacker" else 4
    risk_score = 3 if is_ex else 1  # Giving up 2 prizes if KO'd

    # ----- Tags -----
    tags = []
    if is_ex:          tags.append("ex")
    if has_ability:    tags.append("ability")
    if attack_dmg >= 100: tags.append("high_damage")
    if hp >= 200:      tags.append("high_hp")
    if is_stage2:      tags.append("stage2")
    elif is_stage1:    tags.append("stage1")
    if evolves_from:   tags.append(f"from_{re.sub(r'[^a-z0-9]', '_', evolves_from.lower())}")

    return {
        "card_type":          "Pokemon",
        "role":               role,
        "sub_role":           sub_role,
        "priority":           priority,
        "phase":              phase,
        "keep_score":         keep_score,
        "use_score":          use_score,
        "search_score":       8 if role in ("main_attacker", "engine") else 6,
        "discard_penalty":    discard_penalty,
        "bench_score":        bench_score,
        "energy_attach_score": energy_attach,
        "attack_score":       attack_score,
        "evolution_score":    evolution_score,
        "risk_score":         risk_score,
        "tags":               ",".join(tags),
        "notes":              f"HP:{hp} DMG:{attack_dmg}",
    }


# ---------------------------------------------------------------------------
# Trainer classifier
# ---------------------------------------------------------------------------

def _classify_trainer(row: dict) -> dict:
    name     = row.get("card_name_en", "")
    subtypes = row.get("subtypes", "")
    rules    = row.get("rules", "")
    atk_txt  = row.get("attack_text", "")
    full_txt = _lower(f"{name} {rules} {atk_txt}")

    is_supporter = "Supporter" in subtypes
    is_item      = "Item" in subtypes or (not is_supporter and "Supporter" not in subtypes and "Stadium" not in subtypes)
    is_tool      = "Pokémon Tool" in subtypes or "Pokemon Tool" in subtypes
    is_stadium   = "Stadium" in subtypes

    # ----- Role -----
    if _contains(full_txt, "search your deck", "look at the top", "put it into your hand from your deck",
                 "put a card from your deck", "find a", "search for"):
        role = "search"
    elif _contains(full_txt, "draw until", "draw a card", "draw 3", "draw 4", "draw 5",
                   "draw 2 card", "draw 3 card", "draw 4 card"):
        role = "draw"
    elif _contains(full_txt, "switch", "retreat cost", "from your bench"):
        role = "switch"
    elif _contains(full_txt, "recover", "retrieve", "return", "from your discard pile",
                   "from your discard", "pick up"):
        role = "recovery"
    elif _contains(full_txt, "discard from your opponent", "your opponent discards",
                   "put a card from your opponent", "opponent's hand", "lost zone"):
        role = "disruption"
    elif is_tool:
        role = "tool"
    elif is_stadium:
        role = "stadium"
    elif _contains(full_txt, "energy", "attach"):
        role = "energy_support"
    else:
        role = "support"

    sub_role = (
        "supporter" if is_supporter else
        "tool"      if is_tool else
        "stadium"   if is_stadium else
        "item"
    )

    priority = (
        "high"   if role in ("search", "draw", "disruption") and is_supporter else
        "high"   if role == "search" and is_item else
        "medium"
    )

    phase = (
        "early" if _contains(full_txt, "basic pokemon", "bench", "put onto your bench") else
        "late"  if role == "recovery" else
        "any"
    )

    # ----- Scores -----
    use_score   = 9 if role == "search" else (8 if role == "draw" else (7 if role == "disruption" else 5))
    search_score = 9 if role == "search" else (5 if role == "draw" else 3)
    keep_score  = 7 if is_supporter else 5
    discard_penalty = 7 if is_supporter else 4
    risk_score  = (
        3 if is_supporter else           # 1 per turn limit
        2 if _contains(full_txt, "discard", "lost zone") else
        0
    )

    tags = []
    if is_supporter: tags.append("supporter")
    if is_item:      tags.append("item")
    if is_tool:      tags.append("tool")
    if is_stadium:   tags.append("stadium")
    tags.append(role)

    return {
        "card_type":          "Trainer",
        "role":               role,
        "sub_role":           sub_role,
        "priority":           priority,
        "phase":              phase,
        "keep_score":         keep_score,
        "use_score":          use_score,
        "search_score":       search_score,
        "discard_penalty":    discard_penalty,
        "bench_score":        0,
        "energy_attach_score": 0,
        "attack_score":       0,
        "evolution_score":    0,
        "risk_score":         risk_score,
        "tags":               ",".join(tags),
        "notes":              "",
    }


# ---------------------------------------------------------------------------
# Energy classifier
# ---------------------------------------------------------------------------

def _classify_energy(row: dict) -> dict:
    name     = row.get("card_name_en", "")
    subtypes = row.get("subtypes", "")
    rules    = _lower(row.get("rules", ""))

    is_special = "Special" in subtypes

    # Detect colour from name
    colour_tags = []
    for colour in ("Grass", "Fire", "Water", "Lightning", "Psychic",
                   "Colorless", "Darkness", "Metal", "Fighting", "Dragon", "Fairy"):
        if colour.lower() in name.lower():
            colour_tags.append(colour.lower())

    tags = ["energy"]
    if is_special:
        tags.append("special_energy")
    tags.extend(colour_tags)

    return {
        "card_type":          "Energy",
        "role":               "energy",
        "sub_role":           "special" if is_special else "basic",
        "priority":           "high" if is_special else "medium",
        "phase":              "any",
        "keep_score":         6 if is_special else 4,
        "use_score":          0,
        "search_score":       7,
        "discard_penalty":    7 if is_special else 3,
        "bench_score":        0,
        "energy_attach_score": 9 if not is_special else 8,
        "attack_score":       0,
        "evolution_score":    0,
        "risk_score":         1 if is_special else 0,
        "tags":               ",".join(tags),
        "notes":              "",
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _infer_supertype(row: dict) -> str:
    """
    Infer supertype when the API didn't return one.
    Uses card_id range convention for this card pool:
      1-20   → Energy
      21-1076 → Pokémon
      1077+  → Trainer
    Also checks card name as secondary signal.
    """
    name = _lower(row.get("card_name_en", ""))
    try:
        cid = int(str(row.get("card_id", 0)).strip())
    except (ValueError, TypeError):
        cid = 0

    if " energy" in name or name.startswith("basic "):
        return "Energy"
    if 1 <= cid <= 20:
        return "Energy"
    if 21 <= cid <= 1076:
        return "Pokémon"
    if cid >= 1077:
        return "Trainer"
    return ""


def _infer_subtypes(row: dict, supertype: str) -> str:
    """
    Fill in subtypes when API left them blank.
    For Pokémon: Basic / Stage 1 / Stage 2 inferred from evolvesFrom and name.
    For Trainer: Item / Supporter / Stadium inferred from name keywords.
    """
    existing = row.get("subtypes", "")
    if existing.strip():
        return existing

    name_lower = _lower(row.get("card_name_en", ""))
    evolves_from = row.get("evolvesFrom", "").strip()

    if "pokémon" in supertype.lower() or "pokemon" in supertype.lower():
        # Rough stage inference
        if re.search(r"\bex\b|\bEX\b|\bVMAX\b|\bVSTAR\b", row.get("card_name_en", "")):
            # ex Pokémon can be Basic or Stage 2; if evolves_from is set → Stage 2
            if evolves_from:
                return "Stage 2"
            return "Basic"
        if evolves_from:
            # Check how many evolution steps by looking at name (rough heuristic)
            # If the name itself suggests a final stage: assume Stage 2 for lines with 2 pre-evos
            return "Stage 1"
        return "Basic"

    if "trainer" in supertype.lower():
        supporter_keywords = ("judge", "boss", "order", "iono", "arven", "penny",
                              "cook", "crispin", "hassel", "kieran", "carmine",
                              "briar", "drayton", "cyrano", "lacey", "perrin",
                              "cassiopeia", "canari", "colress", "janine", "dawn",
                              "firebreather", "lucian", "salvatore", "eri",
                              "kofu", "bianca", "morty", "explorer", "lana")
        stadium_keywords  = ("tower", "lab", "gym", "arena", "stadium", "jungle",
                              "grounds", "mine", "ruins", "garden", "city",
                              "center", "cave", "factory", "underdepths", "mountain",
                              "beach", "castle", "postwick", "levincia")
        if any(k in name_lower for k in supporter_keywords):
            return "Supporter"
        if any(k in name_lower for k in stadium_keywords):
            return "Stadium"
        return "Item"

    return existing


def classify(row: dict) -> dict:
    """Route to the correct classifier based on supertype."""
    supertype = row.get("supertype", "").strip()
    name = row.get("card_name_en", "")

    # Infer missing supertype from card_id range / name
    if not supertype:
        supertype = _infer_supertype(row)
        row = dict(row)  # avoid mutating caller's dict
        row["supertype"] = supertype

    # Infer missing subtypes
    inferred_subtypes = _infer_subtypes(row, supertype)
    if not row.get("subtypes", "").strip() and inferred_subtypes:
        row = dict(row)
        row["subtypes"] = inferred_subtypes

    out = dict(DEFAULTS)
    out["card_id"]      = row.get("card_id", "")
    out["card_name_en"] = name

    st = supertype.lower()
    if "pokémon" in st or "pokemon" in st:
        out.update(_classify_pokemon(row))
    elif "trainer" in st:
        out.update(_classify_trainer(row))
    elif "energy" in st:
        out.update(_classify_energy(row))
    else:
        out["card_type"] = "Unknown"
        out["role"]      = "unknown"
        out["notes"]     = f"supertype='{supertype}' — needs manual review"

    return {k: out.get(k, "") for k in KNOWLEDGE_FIELDS}


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def _load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(rows: list[dict], path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KNOWLEDGE_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="card_detail_raw.csv → card_knowledge.csv")
    parser.add_argument("--details", default=os.path.join(_ROOT, "data", "card_detail_raw.csv"))
    parser.add_argument("--out",     default=os.path.join(_ROOT, "data", "card_knowledge.csv"))
    parser.add_argument("--merge", action="store_true",
                        help="Merge: keep existing hand-edited rows, only add/update new card_ids")
    args = parser.parse_args()

    raw_rows = _load_csv(args.details)
    if not raw_rows:
        print(f"ERROR: No data in {args.details}", file=sys.stderr)
        print("  Run fetch_card_details.py first.", file=sys.stderr)
        sys.exit(1)

    # If merge mode, load existing knowledge and only update new cards
    existing: dict[str, dict] = {}
    if args.merge and os.path.exists(args.out):
        for r in _load_csv(args.out):
            existing[str(r.get("card_id", ""))] = r
        print(f"Merge mode: {len(existing)} existing rows will be preserved")

    new_rows = []
    skipped  = 0
    for raw in raw_rows:
        cid = str(raw.get("card_id", ""))
        if args.merge and cid in existing:
            new_rows.append(existing[cid])
            skipped += 1
        else:
            result = classify(raw)
            new_rows.append(result)
            role = result.get("role", "")
            print(f"  #{cid:<5} {result['card_name_en']:<30} → {role}")

    _write_csv(new_rows, args.out)
    print(f"\nDone: {len(new_rows) - skipped} generated"
          + (f", {skipped} preserved" if skipped else "")
          + f" → {args.out}")
    print("Review the CSV and adjust roles/scores manually as needed.")
