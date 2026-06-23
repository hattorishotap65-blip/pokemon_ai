# Runtime Hybrid Env-Gated Evaluation 001

## Purpose

#145/#146 で safety gate 付き offline hybrid が安全と確認された。
実際の policy runtime に env-gated hybrid を組み込み、self-play で評価する。

## Default Behavior: UNCHANGED

- `POKEMON_AI_ML_HYBRID` 未設定 or `0` → 既存挙動と完全に同一
- `POKEMON_AI_ML_HYBRID=1` の時だけ hybrid scoring 有効
- `POKEMON_AI_ML_BONUS_RATIO` で bonus 倍率を制御 (default 10.0)

## Integration Point

`main.py` `_select_indices()` 内、suppress_attack 後 / threshold 前に挿入:
```python
if is_hybrid_enabled():
    immediate_scores = apply_hybrid_bonus(opt_dicts, state, immediate_scores)
```
try/except で保護。エラー時は rule_score のみ。

## Safety Gates (agent/ml_hybrid.py)

| Gate | Rule |
|------|------|
| G1 | End + legal_attack → bonus=0 |
| G2 | zero_damage → bonus=0 |
| G3 | can_ko + non-attack → bonus=0 |
| G4 | Error/exception → rule only |

## ML Scorer

Heuristic scorer mimicking #144 DecisionTree patterns:
- Attack bonus +0.3, End penalty -0.1
- Energy-ready attack +0.2
- Active attach enabling attack +0.15
- Late game attack +0.1

## Status

100g self-play は並行実行中 (baseline / bonus=10 / bonus=20)。
結果は取得次第このドキュメントを更新。

## Tests

- env flag OFF: all existing tests pass (90+45+16)
- py_compile / compileall: pass
- policy.py 挙動: env OFF で変更なし確認済み
