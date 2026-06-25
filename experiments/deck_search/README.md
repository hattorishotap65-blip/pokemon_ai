# Deck Search Foundation

## Purpose

Build a foundation for discovering strong deck archetypes through
automated search, rather than manually copying known decks.

## Design Principles

- **Independent of past Iono/Kilowattrel assets.** Past agent/ modules,
  ionos_rules, and Iono-specific tuning results are not referenced.
  They were optimized for a specific (weak) archetype and would
  bias exploration toward suboptimal regions of the search space.

- **Archetype-agnostic.** The card pool, constraints, and features
  are designed to work across any deck type — not hardcoded to
  Lucario, Crustle, or any single strategy.

- **Lucario 1084 is a reference, not a target.** It serves as a
  known-strong comparison point to validate that the search can
  reach competitive archetypes. The goal is to discover, not copy.

- **Incremental build.** This PR covers candidate generation and
  feature extraction only. Evaluation and ML follow in later PRs.

## Components

### cards.py
Card pool loaded from `artifacts/all_cards.json` (1267 cards from cabt).
Provides typed `CardInfo` with classification helpers.

### deck_constraints.py
Validates candidate decks against cabt rules:
- Exactly 60 cards
- Max 4 copies of non-basic-energy cards
- At most 1 ACE SPEC
- Configurable Pokemon/Energy/Trainer ranges

### generate_candidates.py
CLI to generate randomized valid deck candidates:
```bash
python experiments/deck_search/generate_candidates.py \
    --num 100 --seed 42 \
    --out experiments/deck_search/results
```
Outputs per-candidate: `deck.csv`, `counts.json`, and a `manifest.jsonl`.

### features.py
Extracts ML-ready feature vectors from deck lists:
- Composition: pokemon/energy/trainer counts, evolution stages
- Support: draw/search/switch/gust/disruption counts
- Heuristic scores: consistency, attack readiness, counterplay

## Roadmap

1. **This PR:** candidate generation + feature extraction
2. **Next:** connect to head-to-head evaluation (run candidates vs Lucario 1084)
3. **Then:** ML surrogate model trained on (features, win_rate) pairs
4. **Then:** guided search (genetic, Bayesian, etc.) using surrogate
5. **Goal:** find archetypes that beat or match Lucario 1084 via search

## Usage

```bash
# Generate 100 candidates
python experiments/deck_search/generate_candidates.py \
    --num 100 --seed 42 --out experiments/deck_search/results

# Extract features for a specific deck
python -c "
from experiments.deck_search.features import extract_features
deck = [int(l) for l in open('experiments/decks/top_lucario_1084.csv')]
print(extract_features(deck))
"
```
