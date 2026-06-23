# Action Feature Logging 001

## Purpose

ML shadow mode に向けて、各 legal action の特徴量をログから抽出できるようにする。
policy の行動選択ロジックは変更しない。

## Baseline

- main after #136 merge
- #134 submitted version
- attack_plan.py excluded from submission
- ML disabled

## No Behavior Change

- policy.py のスコア・ランキング・行動選択は一切変更していない
- submission.tar.gz は更新していない

## Feature Schema (per candidate action)

### Identifiers
game_id, turn, action_index, action_type, selected, rule_score, rule_reason, candidate_rank

### Board State
active_card_id, active_hp, active_energy, active_energy_needed,
opponent_active_card_id, opponent_active_hp, bench_size,
prize_remaining, opponent_prize_remaining, prize_diff,
deck_count, hand_count, has_legal_attack, legal_action_count

### Attack
is_attack, can_ko, is_zero_damage_attack, attack_energy_ready

### Energy Attach
is_attach, attach_to_active, attach_to_bench, attach_target_card_id,
attach_enables_attack, active_attach_would_enable

### Evolution
is_evolve, evolve_to_card_id, evolve_to_main_attacker, evolve_to_engine

### Other Actions
is_play, is_ability, is_retreat, is_end

### Game Context
late_game, game_result

## Commands

```bash
python experiments/action_feature_logging.py \
    --n 50 --start-game 130000 --run-games --use-wsl \
    --output artifacts/action_features_50g.jsonl

python experiments/action_feature_logging.py \
    --n 100 --start-game 131000 --run-games --use-wsl \
    --output artifacts/action_features_100g.jsonl
```

## Results

| Metric | 50g | 100g |
|--------|-----|------|
| Games | 50 | 100 |
| Decisions | 9,339 | 20,247 |
| Candidate actions | 43,154 | 93,081 |
| Errors | **0** | **0** |
| Timeouts | **0** | **0** |

## Selected Action Distribution

| Type | Code | 50g | 100g |
|------|------|-----|------|
| YES | 1 | 50 | 100 |
| CARD | 3 | 4,882 | 10,609 |
| PLAY | 7 | 1,164 | 2,450 |
| ATTACH | 8 | 591 | 1,301 |
| EVOLVE | 9 | 305 | 662 |
| ABILITY | 10 | 1,484 | 3,319 |
| RETREAT | 12 | 157 | 348 |
| ATTACK | 13 | 597 | 1,246 |
| END | 14 | 501 | 1,000 |
| NUMBER | 0 | 24 | 49 |
| ENERGY_CARD | 5 | 145 | 331 |
| ENERGY | 6 | 289 | 646 |

## Key Observations

| Metric | 50g | 100g |
|--------|-----|------|
| can_ko candidates | 114 | 201 |
| selected can_ko | 109 | 200 |
| **can_ko selection rate** | **95.6%** | **99.5%** |
| attach_enables_attack | 0 | 0 |
| zero_damage candidates | 0 | 0 |
| selected zero_damage | 0 | 0 |

### Policy is highly effective at KO selection

can_ko selection rate is 95-99%. The policy almost always attacks when KO is possible.

Note: can_ko is currently detected from the `reason` string (contains "ko").
Future improvement: use `predicted_damage >= opponent_hp` for more accurate detection.

### No zero-damage attacks, no attach-enables-attack misses

Both metrics are 0, confirming the policy's safety guards work correctly.

### Game result and reward

game_result is detected from log entries (win/loss/error/timeout/unknown).
reward: win=1.0, loss=-1.0, error/timeout=-1.0, unknown=0.0.
Self-play logs show "unknown" because game result is determined externally
by run_matches_real.py, not written into per-decision logs. For ML training
with outcome labels, results CSV can be joined by game_id.

## Feature Coverage

| Category | Features | Status |
|----------|---------|--------|
| Board state | 12 | Full from state_summary |
| Attack | 4 | From candidate + reason |
| Energy attach | 6 | From inPlayArea + energy_needed |
| Evolution | 4 | From resolved_card_id |
| Other actions | 4 | From option_type |
| Game context | 2 | From log entries |
| **Total** | **32** | |

## Next Steps

### Next PR: experiment: add ML shadow scoring

1. Train simple action ranker on the JSONL features
2. Score each candidate with ML model alongside rule-based score
3. Log ML rank vs rule rank (shadow mode — no behavior change)
4. Measure agreement rate between ML and rule-based policy
5. If ML agrees >90%, consider hybrid mode testing
