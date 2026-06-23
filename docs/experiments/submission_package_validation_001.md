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

## Finding and Fix: agent/params.py was missing from submission

Initial check found `agent/params.py` missing from `build_submission.py`.
`policy.py` imported params without try/except — would crash on Kaggle.

### Fix applied (same PR)

1. Added `agent/params.py`, `agent/attack_plan.py`, `configs/params/default_params.json` to `build_submission.py`
2. Wrapped policy.py params imports (lines 471, 484, 981) in try/except with hardcoded fallbacks (500/20/30)
3. Rebuilt `submission.tar.gz` (567 KB)

通常時は `agent.params` から値を読む。import 失敗時のみ hardcoded fallback を使う。
通常の score/ranking 意図は変えない。

### Import safety summary (after fix)

| File | Import | Protected? | Fallback |
|------|--------|-----------|----------|
| agent/policy.py | agent.params | YES (try/except) | hardcoded 500/20/30 |
| agent/policy.py | agent.attack_plan | YES (try/except) | bonus=0 |
| agent/policy.py | agent.ml_policy | YES (try/except) | score=0 |
| agent/damage_predictor.py | agent.params | YES (try/except) | hardcoded 800/200 |
| agent/ml_policy.py | agent.ml_features | YES (try/except) | score=0 |

## Package Contents (build_submission.py, after fix)

### Included

- main.py, deck.csv
- agent/__init__.py, advantage.py, card_knowledge.py, concept_weights.py
- agent/ionos_rules.py, evaluator.py, fallback.py, logger.py
- agent/opponent_model.py, planner.py, policy.py, rollout.py
- agent/turn_plan.py, win_condition.py, effect_engine.py, turn_rule_engine.py
- agent/card_metadata.py, damage_predictor.py
- **agent/params.py** (added)
- **agent/attack_plan.py** (added)
- data/card_knowledge.csv, deck_profile.json, card_effects JSON, weights.json
- **configs/params/default_params.json** (added)
- cg/ (from reference/extracted/cg)

### Not included (correct)

- docs/, experiments/, tests/, artifacts/, logs/, .git/, __pycache__/
- agent/ml_policy.py, agent/ml_features.py, agent/policy_router.py (ML disabled)

## 50g Smoke Result

| Metric | Value |
|--------|-------|
| Games | 50 |
| Errors | 0 |
| Timeouts | 0 |
| Total score | 200 |
| Score/game | 4.0 |
| Avg ms/game | 4465 |

## Post-fix Verification

| Check | Result |
|-------|--------|
| submission.tar.gz rebuilt | OK (567 KB) |
| params.py included | OK |
| attack_plan.py included | OK |
| configs/params/default_params.json included | OK |
| 30g smoke after fix | OK (0 errors, 0 timeouts) |
| policy.py params fallback | OK (try/except + hardcoded) |

## Decision

**Submit candidate** — params.py 問題を修正済み。submission.tar.gz を意図的に更新。

## Runtime / Safety

- 通常時は agent.params から値を読む（score/ranking 意図は変えない）
- params import 失敗時のみ hardcoded fallback (500/20/30) を使用
- ML default disabled
- Generated artifacts/logs not committed
