# Submission Package Validation 002

## Purpose

#133 をクローズし、main 最新から clean に作り直した提出候補を検証する。

## Why #133 was closed

#133 は以下が混在し、提出候補PRとして見通しが悪くなった。

- submission package validation
- agent/params.py missing の発見と修正
- attack_plan.py を提出物に含めたことによる挙動悪化疑い
- score 記録の混線（score=200 / score=20）
- docs / PR本文の不整合

本PRでは最終状態のみを clean に記録する。

## Final Submission Policy

| File | Include? | Reason |
|------|---------|--------|
| agent/params.py | **YES** | policy.py が import、なければクラッシュ |
| configs/params/default_params.json | **YES** | params.py が読む（hardcoded fallback もあり） |
| agent/attack_plan.py | **NO** | attack_plan_bonus 有効化で挙動悪化疑い |
| agent/ml_policy.py | NO | ML disabled |
| agent/ml_features.py | NO | ML disabled |
| agent/policy_router.py | NO | ML disabled |

## policy.py Changes

- params import を try/except で保護（3箇所）
- fallback: zero_damage_attack_penalty=500, ko_opponent_bonus=20, boss_can_ko=30
- 通常時は agent.params の値を使う。fallback は import 失敗時のみ
- attack_plan import は既存の try/except のまま → 提出版では bonus=0

## Package Contents

### Included (563 KB)

- main.py, deck.csv
- agent/__init__.py, advantage.py, card_knowledge.py, concept_weights.py
- agent/ionos_rules.py, evaluator.py, fallback.py, logger.py
- agent/opponent_model.py, planner.py, policy.py, rollout.py
- agent/turn_plan.py, win_condition.py, effect_engine.py, turn_rule_engine.py
- agent/card_metadata.py, damage_predictor.py, **params.py**
- data/card_knowledge.csv, deck_profile.json, card_effects JSON, weights.json
- **configs/params/default_params.json**
- cg/ (from reference/extracted/cg)

### Excluded

- **agent/attack_plan.py** (attack_plan_bonus regression)
- agent/ml_policy.py, ml_features.py, policy_router.py (ML disabled)
- docs/, experiments/, tests/, artifacts/, logs/, .git/, __pycache__/

## Tests

| Check | Result |
|-------|--------|
| py_compile main.py | OK |
| compileall agent | OK |
| test_params | 16/16 |
| test_turn_rule_engine | 90/90 |
| test_damage_predictor | 29/29 |
| test_attack_plan | 45/45 |
| params.py in package | OK |
| default_params.json in package | OK |
| attack_plan.py NOT in package | OK |
| ml_policy.py NOT in package | OK |

## Smoke Test

```bash
wsl -d Ubuntu -e bash -c "cd /mnt/c/Users/shclo/projects/pokemon_card_ai && \
    PYTHONPATH=.../reference/extracted \
    python3 experiments/run_matches_real.py --n 50 --start-game 110000"
```

| Metric | Value |
|--------|-------|
| Games | 50 |
| Start game | 110000 |
| P0 wins | 23 |
| P1 wins | 27 |
| Errors | **0** |
| Timeouts | **0** |
| Total score | -40 |
| Score/game | -0.80 |
| Avg ms/game | 3762 |

Self-play のため score は 0 周辺で正常。errors=0, timeouts=0 を確認。

### 100g Smoke

```bash
wsl -d Ubuntu -e bash -c "cd /mnt/c/Users/shclo/projects/pokemon_card_ai && \
    PYTHONPATH=.../reference/extracted \
    python3 experiments/run_matches_real.py --n 100 --start-game 111000"
```

| Metric | Value |
|--------|-------|
| Games | 100 |
| Start game | 111000 |
| P0 wins | 43 |
| P1 wins | 57 |
| Errors | **0** |
| Timeouts | **0** |
| Total score | -140 |
| Score/game | -1.40 |
| Avg ms/game | 4107 |

Self-play のため P0/P1 非対称はゲームごとの分散。
errors=0, timeouts=0 を 100g でも確認。

## 81461232 Regression Check

- attack_plan.py は提出パッケージに含まれていない
- attack_plan_bonus は提出版では 0（import 失敗 → fallback）
- active Kilowattrel / bench Voltorb エネルギー添付の regression リスクは排除
- params.py は含まれており Kaggle import crash は回避

## Decision

**Submit candidate** — errors=0, timeouts=0, package contents OK,
attack_plan.py excluded, params.py included.
