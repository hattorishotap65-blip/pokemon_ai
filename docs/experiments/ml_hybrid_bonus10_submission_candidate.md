# ML Hybrid Bonus10 Submission Candidate

## Purpose

#147 で runtime hybrid が安全に動作することを確認した。
bonus=10 を提出候補として、submission.tar.gz を作成する。

## Difference from #134 (#147)

| Item | #134 (baseline) | This candidate |
|------|-----------------|----------------|
| agent/ml_hybrid.py | Not included | **Included** |
| Hybrid default | N/A (OFF) | **ON** (_HYBRID_DEFAULT=True) |
| Bonus ratio | N/A | 10.0 |
| attack_plan.py | Not included | Not included |

## Submission Candidate Setting

```python
_HYBRID_DEFAULT = True  # submission candidate: ON by default
_ENABLED = os.environ.get("POKEMON_AI_ML_HYBRID", "1" if _HYBRID_DEFAULT else "0") != "0"
_BONUS_RATIO = float(os.environ.get("POKEMON_AI_ML_BONUS_RATIO", "10.0"))
```

- Default: hybrid ON, bonus=10.0
- `POKEMON_AI_ML_HYBRID=0` で無効化可能
- Kaggle 環境で env 未設定 → hybrid ON

## Safety Gates

G1: End + legal_attack → bonus=0
G2: zero_damage → bonus=0
G3: can_ko + non-attack → bonus=0
G4: Error → rule only

## 100g Self-Play Result (hybrid default ON)

| Metric | Value |
|--------|-------|
| Games | 100 |
| P0 wins | 53 |
| P1 wins | 47 |
| **Errors** | **0** |
| **Timeouts** | **0** |
| Score/game | 0.60 |
| Avg ms/game | 4725 |

## Package Contents (565 KB)

### Included

- main.py, deck.csv
- agent/ml_hybrid.py (**new**)
- agent/params.py, configs/params/default_params.json
- All required agent/data/cg files

### Excluded

- agent/attack_plan.py
- agent/ml_policy.py, ml_features.py, policy_router.py
- docs/, experiments/, tests/, artifacts/, logs/

## Safety Checks

| Check | Result |
|-------|--------|
| Errors | **0** |
| Timeouts | **0** |
| ml_hybrid.py included | ✓ |
| attack_plan.py excluded | ✓ |
| experiments excluded | ✓ |
| artifacts excluded | ✓ |
| tests pass (env ON) | ✓ |

## Decision

**Submit candidate.** 0 errors, 0 timeouts, 4725ms/game.
Hybrid bonus=10 ON by default.

## Remaining Risks

- Self-play では hybrid の勝率効果は測定不可能（対称）
- Kaggle leaderboard での評価が本当のテスト
- hybrid が悪化する場合は `POKEMON_AI_ML_HYBRID=0` で無効化可能
- #134 baseline に戻すことも可能
