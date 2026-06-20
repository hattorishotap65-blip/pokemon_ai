# Level 6.5: Adopt retreat_to_better_attacker_bonus=1400

## Adopted Value

| Parameter | Before | After |
|-----------|--------|-------|
| retreat_to_better_attacker_bonus | 1100.0 | **1400.0** |

## Reason

30g / 50g / 200g の全スケールで baseline 1100 より改善が確認された。

| Scale | Baseline (1100) | Candidate (1400) | Delta | PR |
|-------|----------------|-----------------|-------|-----|
| 30g | 5.77/g | 5.07/g | -12% | #28 |
| 50g | 5.76/g | 4.74/g | -18% | #29 |
| **200g** | **5.43/g** | **4.97/g** | **-8.5%** | **#30** |

## 200g Key Metrics

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| anomalies_total | 5.43/g | 4.97/g | **-8.5%** |
| kw_f0007_range_game_flow | 1.66/g | 1.10/g | **-33%** |
| bellibolt_attack_probably_correct | 2.73/g | 2.25/g | -18% |
| F0007 triggers | 2.42/g | 2.19/g | stable |

## Safety (200g)

| Metric | Value |
|--------|-------|
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

## Known Side Effects (accepted)

| Metric | Delta | Risk |
|--------|-------|------|
| bb_f0007_range_no_retreat | +0.30/g | Safe: retreat unavailable cases, agent still attacks |
| wt_game_flow | +0.23/g | Safe: game flow variation, no safety impact |

## Changes

| File | Change |
|------|--------|
| data/weights.json | retreat_to_better_attacker_bonus: 1100.0 → **1400.0** |
| submission.tar.gz | **Rebuilt** (python build_submission.py) |
| deck.csv | **unchanged** |
| agent/ionos_rules.py | **unchanged** (logic) |
| agent/policy.py | **unchanged** (logic) |
| agent/turn_rule_engine.py | **unchanged** |
