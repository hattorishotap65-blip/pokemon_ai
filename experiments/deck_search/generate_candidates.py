"""
Generate candidate decks for exploration.

Produces randomized deck candidates within cabt constraints.
Each candidate gets a deck.csv, counts.json, and an entry in manifest.jsonl.

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
from typing import Dict, List, Set, Tuple

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


def _pick_energy_type(rng: random.Random) -> int:
    return rng.choice(BASIC_ENERGY_IDS)


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
    energies = all_energies()
    ace_specs = all_ace_specs()
    non_ace_trainers = [t for t in trainers if not t.is_ace_spec]

    primary_energy = _pick_energy_type(rng)

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
        add(primary_energy, remaining)

    if len(deck) < constraints.total_cards:
        shortfall = constraints.total_cards - len(deck)
        add(primary_energy, shortfall)
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
        candidates.append({
            "index": len(candidates),
            "hash": h,
            "cards": deck,
            "counts": dict(Counter(deck)),
            "composition": comp,
        })

    return candidates


def save_candidates(candidates: List[Dict], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    manifest_path = os.path.join(out_dir, "manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        for cand in candidates:
            idx = cand["index"]
            deck_dir = os.path.join(out_dir, f"candidate_{idx:04d}")
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
                }, cf, indent=2)

            entry = {
                "index": idx,
                "hash": cand["hash"],
                "deck_csv": os.path.relpath(deck_path, out_dir),
                "composition": cand["composition"],
            }
            mf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Saved {len(candidates)} candidates to {out_dir}")
    print(f"Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate deck candidates")
    parser.add_argument("--num", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="experiments/deck_search/results")
    args = parser.parse_args()

    print(f"Generating {args.num} candidates (seed={args.seed})...")
    candidates = generate_candidates(args.num, args.seed)
    print(f"Generated {len(candidates)} unique valid candidates")
    save_candidates(candidates, args.out)


if __name__ == "__main__":
    main()
