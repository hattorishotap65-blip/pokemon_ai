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

## Results (100g self-play each)

| Metric | Baseline (OFF) | Bonus=10 | Bonus=20 |
|--------|----------------|----------|----------|
| P0 wins | 53 | 49 | 53 |
| P1 wins | 47 | 51 | 47 |
| **Errors** | **0** | **0** | **0** |
| **Timeouts** | **0** | **0** | **0** |
| Score/game | +0.60 | -0.20 | +0.60 |
| Avg selections | 185.8 | 191.1 | 215.3 |
| Avg ms/game | 6567 | 6719 | 7140 |

## Analysis

### Safety: Perfect

All 3 runs: 0 errors, 0 timeouts. No crashes from ML integration.

### Win rate: Neutral (expected in self-play)

Self-play は対称なので ~50% は期待通り。
実際の効果は対戦相手が異なる Kaggle leaderboard でのみ測定可能。

### Performance overhead

| Config | ms/game | Overhead |
|--------|---------|----------|
| Baseline | 6567 | - |
| Bonus=10 | 6719 | +152ms (+2.3%) |
| Bonus=20 | 7140 | +573ms (+8.7%) |

Bonus=20 は avg selections が 215 に増加（baseline 186）。
ML bonus で一部候補の順位が変わり、planner の探索パスが変わった可能性。

## Decision

**Runtime hybrid は安全に動作する。**

- errors/timeouts: 0 at all levels ✓
- Performance: bonus=10 で +2.3% overhead (許容範囲) ✓
- bonus=20 で +8.7% overhead (やや大きい)

## Next Steps

1. **Kaggle 提出**: bonus=10 で提出候補を検討
2. **bonus=10 で提出版を作成**: submission.tar.gz に ml_hybrid.py を含め、env flag で制御
3. **Kaggle では env flag なし → baseline 挙動**: 安全

## Tests

- env flag OFF: all existing tests pass (90+45+16)
- py_compile / compileall: pass
- policy.py 挙動: env OFF で変更なし確認済み
