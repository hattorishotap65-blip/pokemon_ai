"""
Generate candidate decks for exploration.

Supports multi-color energy splits (1-3 types) via templates.

Usage:
  python experiments/deck_search/generate_candidates.py \
      --num 100 --seed 42 \
      --out experiments/deck_search/results
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter
from typing import Dict, List, Set

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.deck_search.cards import (
    CardInfo, card_db, all_basic_pokemon, all_trainers, all_energies,
    all_ace_specs, BASIC_ENERGY_IDS,
)
from experiments.deck_search.deck_constraints import (
    DeckConstraints, validate_deck, deck_composition,
)


# ---------------------------------------------------------------------------
# Multi-color energy generation
# ---------------------------------------------------------------------------

ENERGY_SPLIT_TEMPLATES = {
    1: [[1.0]],
    2: [[0.75, 0.25], [0.65, 0.35], [0.5, 0.5]],
    3: [[0.6, 0.2, 0.2], [0.5, 0.3, 0.2], [0.4, 0.3, 0.3]],
}


def _pick_energy_mix(rng: random.Random, n_energy: int) -> Dict[int, int]:
    """Pick 1-3 basic energy types and allocate n_energy cards among them."""
    n_types = rng.choice([1, 2, 2, 2, 3])
    n_types = min(n_types, n_energy, len(BASIC_ENERGY_IDS), 3)

    types = rng.sample(BASIC_ENERGY_IDS, n_types)
    template = rng.choice(ENERGY_SPLIT_TEMPLATES[n_types])

    counts: Dict[int, int] = {}
    allocated = 0
    for i, t in enumerate(types):
        n = max(1, round(template[i] * n_energy))
        counts[t] = n
        allocated += n

    diff = n_energy - allocated
    if diff != 0:
        counts[types[0]] = max(1, counts[types[0]] + diff)

    final_sum = sum(counts.values())
    if final_sum != n_energy:
        counts[types[0]] += n_energy - final_sum

    if sum(counts.values()) != n_energy or any(v < 1 for v in counts.values()):
        raise ValueError("energy mix invariant violated: %s (expected %d)" % (counts, n_energy))

    return counts


def energy_metadata(card_ids: List[int]) -> Dict:
    """Compute energy distribution metadata from a final deck."""
    dist: Dict[int, int] = {}
    for cid in card_ids:
        if cid in BASIC_ENERGY_IDS:
            dist[cid] = dist.get(cid, 0) + 1
    sorted_types = sorted(dist.keys())
    return {
        "energy_types": sorted_types,
        "energy_type_count": len(sorted_types),
        "energy_distribution": {str(k): v for k, v in sorted(dist.items())},
    }


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def _generate_one(rng: random.Random, constraints: DeckConstraints) -> List[int]:
    """Generate a single random deck satisfying constraints."""
    db = card_db()
    deck: List[int] = []
    counts: Dict[int, int] = Counter()

    def add(cid: int, n: int = 1):
        card = db.get(cid)
        if card is None:
            return False
        current = counts.get(cid, 0)
        if current + n > card.max_copies:
            return False
        for _ in range(n):
            deck.append(cid)
            counts[cid] = counts.get(cid, 0) + 1
        return True

    basics = all_basic_pokemon()
    trainers = all_trainers()
    ace_specs = all_ace_specs()
    non_ace_trainers = [t for t in trainers if not t.is_ace_spec]

    n_pokemon = rng.randint(constraints.min_pokemon, min(20, constraints.max_pokemon))
    n_energy = rng.randint(max(constraints.min_energy, 8), min(20, constraints.max_energy))
    n_trainer = constraints.total_cards - n_pokemon - n_energy

    if n_trainer < constraints.min_trainer:
        n_energy -= (constraints.min_trainer - n_trainer)
        n_trainer = constraints.min_trainer
    if n_trainer > constraints.max_trainer:
        n_energy += (n_trainer - constraints.max_trainer)
        n_trainer = constraints.max_trainer

    n_basic_lo = max(constraints.min_basic_pokemon, 2)
    n_basic_hi = max(n_basic_lo, min(n_pokemon, 8))
    n_basic = rng.randint(n_basic_lo, n_basic_hi)
    chosen_basics = rng.sample(basics, min(n_basic, len(basics)))

    for b in chosen_basics:
        copies = rng.randint(2, 4)
        added = 0
        for _ in range(copies):
            if len([x for x in deck if db.get(x, CardInfo(0, "")).is_pokemon]) < n_pokemon:
                if add(b.id):
                    added += 1
        if added == 0:
            add(b.id, 1)

    pokemon_so_far = sum(1 for x in deck if db.get(x, CardInfo(0, "")).is_pokemon)
    if pokemon_so_far < n_pokemon:
        extra_basics = [b for b in basics if b.id not in counts]
        rng.shuffle(extra_basics)
        for b in extra_basics:
            if pokemon_so_far >= n_pokemon:
                break
            copies = rng.randint(1, 3)
            for _ in range(copies):
                if pokemon_so_far >= n_pokemon:
                    break
                if add(b.id):
                    pokemon_so_far += 1

    use_ace = rng.random() < 0.5 and ace_specs
    if use_ace:
        ace = rng.choice(ace_specs)
        add(ace.id)
        n_trainer -= 1

    trainer_so_far = sum(1 for x in deck if db.get(x, CardInfo(0, "")).is_trainer)
    needed_trainers = n_trainer - trainer_so_far
    if needed_trainers > 0:
        available = [t for t in non_ace_trainers if t.id not in counts or counts[t.id] < t.max_copies]
        rng.shuffle(available)
        for t in available:
            if needed_trainers <= 0:
                break
            copies = rng.randint(1, min(4, needed_trainers))
            for _ in range(copies):
                if needed_trainers <= 0:
                    break
                if add(t.id):
                    needed_trainers -= 1

    remaining = constraints.total_cards - len(deck)
    if remaining > 0:
        energy_mix = _pick_energy_mix(rng, remaining)
        for eid, cnt in energy_mix.items():
            add(eid, cnt)

    if len(deck) < constraints.total_cards:
        shortfall = constraints.total_cards - len(deck)
        existing_energy = [cid for cid in counts if cid in BASIC_ENERGY_IDS]
        fallback = rng.choice(existing_energy) if existing_energy else rng.choice(BASIC_ENERGY_IDS)
        add(fallback, shortfall)
    elif len(deck) > constraints.total_cards:
        deck = deck[:constraints.total_cards]

    rng.shuffle(deck)
    return deck


def _deck_hash(card_ids: List[int]) -> str:
    sig = ",".join(str(x) for x in sorted(card_ids))
    return hashlib.md5(sig.encode()).hexdigest()[:12]


def generate_candidates(
    num: int, seed: int, constraints: DeckConstraints = None,
    max_attempts: int = 10000,
) -> List[Dict]:
    """Generate num unique valid deck candidates."""
    if constraints is None:
        constraints = DeckConstraints()

    rng = random.Random(seed)
    seen_hashes: Set[str] = set()
    candidates = []
    attempts = 0

    while len(candidates) < num and attempts < max_attempts:
        attempts += 1
        deck = _generate_one(rng, constraints)
        h = _deck_hash(deck)

        if h in seen_hashes:
            continue

        result = validate_deck(deck, constraints)
        if not result.valid:
            continue

        seen_hashes.add(h)
        comp = deck_composition(deck)
        e_meta = energy_metadata(deck)
        candidates.append({
            "index": len(candidates),
            "hash": h,
            "cards": deck,
            "counts": dict(Counter(deck)),
            "composition": comp,
            "energy_meta": e_meta,
        })

    return candidates


def save_candidates(candidates: List[Dict], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    manifest_path = os.path.join(out_dir, "manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        for cand in candidates:
            idx = cand["index"]
            deck_dir = os.path.join(out_dir, "candidate_%04d" % idx)
            os.makedirs(deck_dir, exist_ok=True)

            deck_path = os.path.join(deck_dir, "deck.csv")
            with open(deck_path, "w") as df:
                df.write("\n".join(str(c) for c in cand["cards"]) + "\n")

            counts_path = os.path.join(deck_dir, "counts.json")
            with open(counts_path, "w", encoding="utf-8") as cf:
                json.dump({
                    "hash": cand["hash"],
                    "counts": cand["counts"],
                    "composition": cand["composition"],
                    "energy_types": cand["energy_meta"]["energy_types"],
                    "energy_type_count": cand["energy_meta"]["energy_type_count"],
                    "energy_distribution": cand["energy_meta"]["energy_distribution"],
                }, cf, indent=2)

            entry = {
                "index": idx,
                "hash": cand["hash"],
                "deck_csv": os.path.relpath(deck_path, out_dir),
                "composition": cand["composition"],
                "energy_types": cand["energy_meta"]["energy_types"],
                "energy_type_count": cand["energy_meta"]["energy_type_count"],
                "energy_distribution": cand["energy_meta"]["energy_distribution"],
            }
            mf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print("Saved %d candidates to %s" % (len(candidates), out_dir))


def main():
    parser = argparse.ArgumentParser(description="Generate deck candidates")
    parser.add_argument("--num", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="experiments/deck_search/results")
    args = parser.parse_args()

    print("Generating %d candidates (seed=%d)..." % (args.num, args.seed))
    candidates = generate_candidates(args.num, args.seed)
    print("Generated %d unique valid candidates" % len(candidates))

    type_dist = Counter()
    for c in candidates:
        type_dist[c["energy_meta"]["energy_type_count"]] += 1
    print("Energy type distribution: %s" % dict(sorted(type_dist.items())))

    save_candidates(candidates, args.out)


if __name__ == "__main__":
    main()
