# Area Fix Only Submission Candidate 001

## Purpose

Prepare submission candidate with `area_fix_only` as default, based on #154 300g ablation results.

## Background

| PR | Description |
|----|-------------|
| #148 | ML hybrid bonus=10 — previous submission candidate |
| #151 | Bonus sweep — bonus=10 confirmed optimal |
| #153 | Area fix + attack compensation — experiment |
| #154 | 300g ablation — area_fix_only matches baseline, attack compensation worsens miss_KO |

## Why area_fix_only

300g ablation (#154) showed:

| Config | miss_KO | KO Capture |
|--------|---------|------------|
| A baseline (broken 0/1) | 22 | 96.5% |
| **B area_fix_only (correct 4/5)** | **21** | **96.8%** |
| C attack_comp (correct + attack +0.15) | 30 | 95.5% |

- B matches baseline — area fix is safe
- C worsens miss_KO by 36% — attack compensation is harmful
- Area fix correctly enables `attach_to_active` / `attach_to_bench` features (previously dead code)

## Why NOT attack compensation

The +0.15 attack bonus intended to compensate for the area fix score rebalance. 300g showed it overshoots and causes more miss_KO than either baseline or area fix alone.

## Configuration

| Setting | Value |
|---------|-------|
| `POKEMON_AI_ML_HYBRID` | 1 (ON by default) |
| `POKEMON_AI_ML_BONUS_RATIO` | 10.0 |
| `POKEMON_AI_AREA_FIX_MODE` | `area_fix_only` (default) |
| attack_plan.py | excluded |

## Submission Package

- **Size**: 565 KB
- **Build**: `python build_submission.py`

### Included
- main.py, deck.csv
- agent/ (including ml_hybrid.py with area_fix_only default)
- configs/params/default_params.json
- data/ (card_knowledge.csv, deck_profile.json, etc.)
- cg/ (libcg.so, api.py, etc.)

### Excluded
- attack_plan.py
- experiments/
- artifacts/
- logs/
- docs/
- .git/

## Smoke Test (50g)

| Metric | Value |
|--------|-------|
| Games | 50 |
| Errors | 0 |
| Timeouts | 0 |
| End+legal_attack | 0 |
| zero_damage | 0 |
| miss_KO | 1 |
| KO Capture | 120/121 (99.2%) |
| ATTACK | 608 |
| ATTACH | 600 |
| END | 515 |
| RETREAT | 162 |
| Decisions | 9613 |

## Decision

This submission candidate is ready for leaderboard test. If score drops vs #148, revert.
