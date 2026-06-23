# Submission Package Validation 001

## Purpose

PR #132 完了後の最初の提出候補として、submission package を検証する。

## Base

- main after PR #132
- ML default disabled
- attack_plan diagnostics completed
- conservative attack boost not applied

## Checks

| Check | Result | Notes |
|-------|--------|-------|
| git status clean (before docs) | OK | only untracked docs + modified core_param_search.csv |
| artifacts/logs not committed | OK | .gitignore covers artifacts/, logs/ |
| main.py syntax check | OK | py_compile pass |
| compileall agent | OK | all compile |
| test_turn_rule_engine | OK | 90/90 |
| test_attack_plan | OK | 45/45 |
| test_attack_plan_diagnostics | OK | 51/51 |
| test_collect_attack_plan_diagnostics | OK | 121/121 |
| test_damage_predictor | OK | 29/29 |
| test_ml_features | OK | 32/32 |
| test_ml_policy | OK | 20/20 |
| test_params | OK | 16/16 |
| 50g smoke | OK | 0 errors, 0 timeouts, score=200 (4.0/g) |

## Critical Finding: agent/params.py missing from submission

`build_submission.py` does NOT include `agent/params.py`.
`policy.py` imports `from agent.params import get as _p` at lines 471, 481, 972
**without try/except**. On Kaggle, this will crash with `ModuleNotFoundError`.

### Affected imports

| File | Line | In try/except? | Impact |
|------|------|----------------|--------|
| agent/policy.py | 471 | **NO** | **CRASH** on zero_damage_attack_penalty |
| agent/policy.py | 481 | **NO** | **CRASH** on ko_opponent_bonus |
| agent/policy.py | 972 | **NO** | **CRASH** on boss_can_ko |
| agent/damage_predictor.py | 203 | YES | Safe (fallback to hardcoded) |
| agent/attack_plan.py | N/A | Not in submission | N/A |
| agent/ml_policy.py | N/A | Not in submission, try/except | N/A |

### Resolution options

1. **Add agent/params.py + configs/params/default_params.json to build_submission.py** — cleanest
2. **Wrap policy.py params imports in try/except with hardcoded fallbacks** — safer fallback
3. **Both** — recommended

### Also not in submission (safe)

| File | Used in submission? | Protected? |
|------|--------------------| --------|
| agent/attack_plan.py | policy.py imports it | try/except → bonus=0 |
| agent/ml_policy.py | policy.py imports it | try/except → score=0 |
| agent/ml_features.py | ml_policy imports it | ml_policy in try/except |
| agent/params.py | policy.py imports it | **NOT protected** |
| agent/policy_router.py | Not imported in submission | N/A |

## Package Contents (build_submission.py)

### Included

- main.py, deck.csv
- agent/__init__.py, advantage.py, card_knowledge.py, concept_weights.py
- agent/ionos_rules.py, evaluator.py, fallback.py, logger.py
- agent/opponent_model.py, planner.py, policy.py, rollout.py
- agent/turn_plan.py, win_condition.py, effect_engine.py, turn_rule_engine.py
- agent/card_metadata.py, damage_predictor.py
- data/card_knowledge.csv, deck_profile.json, card_effects JSON, weights.json
- cg/ (from reference/extracted/cg)

### Not included (correct)

- docs/, experiments/, tests/, artifacts/, logs/, .git/, __pycache__/

### Missing (needs fix)

- **agent/params.py** — required by policy.py without fallback
- **configs/params/default_params.json** — params.py reads this (has fallback to hardcoded)

## 50g Smoke Result

| Metric | Value |
|--------|-------|
| Games | 50 |
| Errors | 0 |
| Timeouts | 0 |
| Total score | 200 |
| Score/game | 4.0 |
| Avg ms/game | 4465 |

## Decision

**Not submit yet** — agent/params.py missing from submission will cause crash on Kaggle.

### Next action

Create a fix PR to either:
1. Add agent/params.py to build_submission.py
2. Wrap policy.py params imports in try/except with hardcoded fallbacks
3. Rebuild submission.tar.gz
4. Re-verify with 50g smoke after fix

## Runtime / Safety

- policy behavior unchanged
- score/ranking/action selection unchanged
- ML default disabled
- configs/default_params/weights/deck/submission 変更なし (this PR)
- Generated artifacts/logs not committed
