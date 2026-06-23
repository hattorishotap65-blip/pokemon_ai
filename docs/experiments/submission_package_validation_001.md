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

## Finding and Fixes

### Fix 1: agent/params.py was missing from submission

Initial check found `agent/params.py` missing from `build_submission.py`.
`policy.py` imported params without try/except — would crash on Kaggle.

Applied:
1. Added `agent/params.py`, `configs/params/default_params.json` to `build_submission.py`
2. Wrapped policy.py params imports in try/except with hardcoded fallbacks (500/20/30)

通常時は `agent.params` から値を読む。import 失敗時のみ hardcoded fallback を使う。
通常の score/ranking 意図は変えない。

### Fix 2: agent/attack_plan.py を提出から除外

ログ 81461232 の確認で、attack_plan.py が提出版に含まれると
attack_plan_bonus が有効化され、エネルギー添付先が変わり挙動が悪化する
可能性が確認された。

- Turn 9/11 で active Kilowattrel にエネルギーを貼らず bench Voltorb に貼り、
  active が攻撃できず End するケースが発生
- attack_plan_bonus は実験用の advisory scoring で、提出版では無効が安全

Applied:
- `build_submission.py` から `agent/attack_plan.py` を除外
- policy.py の attack_plan import は try/except で保護済み → bonus=0 にフォールバック
- 提出版では PR #104 以前と同じ挙動（attack_plan_bonus なし）

### Import safety summary (final)

| File | Import | Protected? | In submission? | Fallback |
|------|--------|-----------|---------------|----------|
| agent/policy.py | agent.params | YES | YES | hardcoded 500/20/30 |
| agent/policy.py | agent.attack_plan | YES | **NO** | bonus=0 |
| agent/policy.py | agent.ml_policy | YES | NO | score=0 |
| agent/damage_predictor.py | agent.params | YES | YES | hardcoded 800/200 |

## Package Contents (build_submission.py, final)

### Included

- main.py, deck.csv
- agent/__init__.py, advantage.py, card_knowledge.py, concept_weights.py
- agent/ionos_rules.py, evaluator.py, fallback.py, logger.py
- agent/opponent_model.py, planner.py, policy.py, rollout.py
- agent/turn_plan.py, win_condition.py, effect_engine.py, turn_rule_engine.py
- agent/card_metadata.py, damage_predictor.py
- **agent/params.py** (added)
- data/card_knowledge.csv, deck_profile.json, card_effects JSON, weights.json
- **configs/params/default_params.json** (added)
- cg/ (from reference/extracted/cg)

### Not included (correct)

- **agent/attack_plan.py** (removed — attack_plan_bonus causes regression)
- agent/ml_policy.py, agent/ml_features.py, agent/policy_router.py (ML disabled)
- docs/, experiments/, tests/, artifacts/, logs/, .git/, __pycache__/

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
| submission.tar.gz rebuilt | OK (563 KB) |
| params.py included | OK |
| attack_plan.py excluded | OK (regression avoidance) |
| configs/params/default_params.json included | OK |
| 50g smoke after final fix | OK (0 errors, 0 timeouts, score=20, 3492ms/game) |
| policy.py params fallback | OK (try/except + hardcoded) |
| policy.py attack_plan fallback | OK (try/except → bonus=0) |

## Decision

**Submit candidate** — params.py 追加 + attack_plan.py 除外で安全な提出候補。
submission.tar.gz を意図的に更新。

## Runtime / Safety

- 通常時は agent.params から値を読む（score/ranking 意図は変えない）
- params import 失敗時のみ hardcoded fallback (500/20/30) を使用
- attack_plan_bonus は提出版では 0（try/except → import 失敗 → bonus=0）
- ML default disabled
- Generated artifacts/logs not committed
