# Loss Pattern Diagnostics 001

## Purpose

#134 提出版を baseline として、負け方・悪い判断パターンを分類する。
ML導入前に、rule-based policy のどこが弱いかを可視化する。

## Baseline

- main after #134 merge
- attack_plan.py excluded from submission
- ML disabled
- params.py included

## Commands

```bash
python experiments/loss_pattern_diagnostics.py \
    --n 50 --start-game 120000 --run-games --use-wsl \
    --output artifacts/loss_pattern_50g.json

python experiments/loss_pattern_diagnostics.py \
    --n 100 --start-game 121000 --run-games --use-wsl \
    --output artifacts/loss_pattern_100g.json
```

## Results

| Pattern | 50g (9,745 dec) | 100g (20,302 dec) | Severity |
|---------|----------------|-------------------|----------|
| selected_end_with_legal_attack | **0** | **0** | High |
| missed_ko_attack | 4 | 6 | High |
| zero_damage_attack_selected | **0** | **0** | High |
| active_attach_miss | **0** | **0** | High |
| bench_over_setup | **0** | **0** | Medium |
| timeout_or_error | **0** | **0** | High |

## Rates (per decision)

| Pattern | 50g rate | 100g rate |
|---------|----------|-----------|
| missed_ko_attack | 0.04% | 0.03% |
| all others | 0.0% | 0.0% |

## Representative Examples (missed_ko_attack)

| game_id | turn | active | selected_type | selected_reason | tags |
|---------|------|--------|---------------|-----------------|------|
| 120008 | 3 | 268 (Tadbulb) | 7 (play) | canari_use_need_basic | missed_ko_attack |
| 120008 | 3 | 268 (Tadbulb) | 9 (evolve) | evolve_first_bellibolt_engine | missed_ko_attack |
| 120035 | 7 | 268 (Tadbulb) | 7 (play) | lillie_setup_poor | missed_ko_attack |
| 120035 | 7 | 268 (Tadbulb) | 7 (play) | play_basic_empty_bench_voltorb | missed_ko_attack |

These are cases where a KO-capable attack existed but the policy chose setup
actions (play/evolve) instead. In self-play turns with multiple decisions,
the attack may have been selected in a subsequent decision within the same turn.

## Interpretation

### Policy is very clean

The submitted #134 baseline shows almost no bad decision patterns:

1. **selected_end_with_legal_attack = 0** — never ends turn when attack available
2. **zero_damage_attack_selected = 0** — never attacks for 0 damage
3. **active_attach_miss = 0** — never misattaches energy to bench when active needs it
4. **bench_over_setup = 0** — no over-setup detected
5. **timeout_or_error = 0** — no crashes or timeouts
6. **missed_ko_attack = 4-6 / 10k-20k decisions (0.03%)** — extremely rare

### missed_ko_attack is mostly noise

The 4-6 missed_ko cases are decisions where play/evolve was chosen before attacking.
In multi-step turns (play → evolve → attach → attack), setup actions before the
attack step are expected behavior, not true misses.

## Decision

- **No urgent policy fix needed** — rule-based policy is already very clean
- The submitted #134 version has no significant bad decision patterns
- 0.03% missed_ko_attack rate is within acceptable range

## Next Steps (priority order)

1. **Opponent-aware improvements** — vs different decks, the pattern may differ
2. **Kaggle leaderboard evaluation** — submit #134 and observe actual ranking
3. **attack_plan tuning** — if needed based on leaderboard results
4. **ML shadow mode** — collect features during real games for future ML training
5. **Energy attach optimization** — if active_attach_miss appears in real matches
