"""
Add adv evaluation columns to data/card_knowledge.csv.
Run once: python tools/update_card_knowledge.py
Idempotent — skips if columns already exist.
"""
import csv
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
IN_PATH = os.path.join(ROOT, "data", "card_knowledge.csv")

NEW_COLS = [
    "card_adv", "board_adv", "energy_adv", "tempo_adv", "prize_adv",
    "resource_adv", "info_adv", "risk_reduction_adv",
    "concept_tags", "win_condition_tags",
]


def _i(row, key, default=0):
    try:
        return int(str(row.get(key, default) or default).strip())
    except (ValueError, TypeError):
        return default


def _card_adv(row):
    r = row["role"]
    if r in ("draw", "energy_search"):  return 8
    if r == "search":                    return 7
    if r == "search_engine":             return 6
    if row["card_type"] == "Energy":     return 2
    return max(3, _i(row, "search_score", 5) // 2 + 1)


def _board_adv(row):
    r, ct = row["role"], row["card_type"]
    if ct == "Pokemon":
        if r in ("main_attacker", "sub_attacker"):                  return 7
        if r in ("search_engine", "basic_setup", "evolution_base",
                 "evolution_bridge", "support_pokemon"):             return 6
        return 5
    if r in ("evolve", "search", "energy_support", "switch"):       return 5
    return 3


def _energy_adv(row):
    r = row["role"]
    if r in ("energy", "energy_special", "energy_restricted"):      return 9
    if r in ("energy_support", "energy_search"):                     return 8
    if r in ("main_attacker", "sub_attacker"):                       return 4
    return 2


def _tempo_adv(row):
    r = row["role"]
    atk = _i(row, "attack_score", 0)
    if r == "main_attacker":                                         return 9
    if r == "sub_attacker":                                          return 7
    if r in ("disruption", "switch", "evolve", "energy_support"):   return 6
    if atk > 6:                                                      return 7
    if r in ("energy", "energy_special"):                            return 5
    return 3


def _prize_adv(row):
    r = row["role"]
    if r == "main_attacker":   return 8
    if r == "sub_attacker":    return 7
    if r == "disruption":      return 6
    if r == "evolve":          return 5
    if r in ("energy", "energy_special"): return 4
    return 3


def _resource_adv(row):
    r = row["role"]
    if r == "recovery":                          return 8
    if r in ("draw", "energy_search", "search"): return 6
    if r == "energy_support":                    return 6
    if r in ("energy", "energy_special"):        return 5
    return 3


def _info_adv(row):
    return 3 if row["role"] in ("disruption", "removal") else 2


def _risk_reduction_adv(row):
    r = row["role"]
    risk = _i(row, "risk_score", 0)
    if r == "recovery":                          return 8
    if r == "draw":                              return 7
    if r in ("search", "search_engine"):         return 6
    if r == "switch":                            return 6
    if risk > 2:                                 return 3
    return 4


def _concept_tags(row):
    r = row["role"]
    t = set()
    if r in ("main_attacker", "sub_attacker"):                          t |= {"aggro", "prize_race"}
    if r in ("evolve", "evolution_base", "evolution_bridge",
             "basic_setup", "search_engine"):                           t |= {"setup_midrange", "combo"}
    if r in ("search", "draw", "energy_search"):                        t |= {"aggro", "combo", "control", "setup_midrange"}
    if r in ("disruption", "removal"):                                  t |= {"control", "prize_race"}
    if r == "recovery":                                                 t |= {"control", "resource_loop"}
    if r in ("energy", "energy_special", "energy_support",
             "energy_search", "energy_restricted"):                     t.add("aggro")
    if r == "switch":                                                   t |= {"aggro", "setup_midrange"}
    if not t:
        t.add("setup_midrange")
    return ",".join(sorted(t))


def _win_condition_tags(row):
    r  = row["role"]
    sr = row.get("sub_role", "")
    t  = set()
    if r == "main_attacker":                                             t |= {"finisher", "main_attacker"}
    elif r == "sub_attacker":                                            t.add("sub_attacker")
    elif r in ("search", "energy_search"):                               t |= {"search_engine", "setup_piece"}
    elif r == "draw":                                                    t.add("draw_engine")
    elif r == "search_engine":                                           t |= {"draw_engine", "search_engine"}
    elif r in ("energy", "energy_special", "energy_support",
               "energy_search", "energy_restricted"):                    t.add("energy_engine")
    elif r in ("evolution_base", "basic_setup",
               "evolution_bridge", "evolve", "switch"):                  t.add("setup_piece")
    elif r in ("disruption", "removal"):                                 t.add("disruption")
    elif r == "recovery":                                                t.add("recovery")
    else:                                                                t.add("setup_piece")
    if sr == "conditional_draw":
        t.add("draw_engine")
    return ",".join(sorted(t))


# Manual overrides for cards that need tuning beyond heuristics
OVERRIDES = {
    "96":   {"card_adv": 7, "board_adv": 7, "energy_adv": 7, "tempo_adv": 5,
             "concept_tags": "combo,setup_midrange",
             "win_condition_tags": "draw_engine,energy_engine,search_engine"},
    "1190": {"card_adv": 9, "resource_adv": 7, "risk_reduction_adv": 7,
             "concept_tags": "combo,setup_midrange",
             "win_condition_tags": "draw_engine"},
    "1186": {"energy_adv": 9, "resource_adv": 8, "risk_reduction_adv": 7,
             "concept_tags": "resource_loop,setup_midrange",
             "win_condition_tags": "energy_engine,recovery"},
    "1116": {"energy_adv": 8, "tempo_adv": 6,
             "win_condition_tags": "energy_engine"},
    "63":   {"energy_adv": 8,
             "win_condition_tags": "energy_engine,finisher,main_attacker"},
    "345":  {"concept_tags": "aggro,prize_race,setup_midrange",
             "win_condition_tags": "finisher,main_attacker"},
    "1088": {"prize_adv": 8, "tempo_adv": 7,
             "win_condition_tags": "disruption,finisher"},
    "1182": {"prize_adv": 9,
             "win_condition_tags": "disruption,finisher"},
}

COMPUTE = {
    "card_adv":           _card_adv,
    "board_adv":          _board_adv,
    "energy_adv":         _energy_adv,
    "tempo_adv":          _tempo_adv,
    "prize_adv":          _prize_adv,
    "resource_adv":       _resource_adv,
    "info_adv":           _info_adv,
    "risk_reduction_adv": _risk_reduction_adv,
    "concept_tags":       _concept_tags,
    "win_condition_tags": _win_condition_tags,
}


def main():
    rows = []
    with open(IN_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_fields = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))

    if "card_adv" in old_fields:
        print("Columns already present — skipping.")
        sys.exit(0)

    all_fields = old_fields + NEW_COLS

    for row in rows:
        cid  = str(row.get("card_id", "")).strip()
        over = OVERRIDES.get(cid, {})
        for col, fn in COMPUTE.items():
            row[col] = over.get(col, fn(row))

    with open(IN_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {len(rows)} rows — added {len(NEW_COLS)} columns to {IN_PATH}")


if __name__ == "__main__":
    main()
