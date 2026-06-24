# Attack Plan Ablation with Ionos Active Attach 001

## Purpose

#162 ionos active attach candidate に attack_plan.py を組み合わせた場合の性能を検証。

## Implementation

`agent/ml_hybrid.py` の `apply_hybrid_bonus()` に env-gated で attack plan bonus を追加。

- `POKEMON_AI_ATTACK_PLAN=0` (default): attack plan 無効 = #162 と同じ挙動
- `POKEMON_AI_ATTACK_PLAN=1`: attack plan 有効 — `plan_matches_action()` の bonus を加算

## 100g Results

| Metric | A (#162 baseline) | B (#162 + attack plan) | Change |
|--------|------------------|----------------------|--------|
| attach_to_active | 50.1% | **52.7%** | +2.6 pt |
| starved | 384 | **326** | -58 (-15%) |
| oversetup | 106 | **59** | -47 (-44%) |
| miss_KO | 11 | **8** | -3 |
| KO capture | 94.9% | **96.4%** | +1.5 pt |
| Attack when legal | 87.7% | **89.8%** | +2.1 pt |
| END when legal attack | 0 | 0 | same |
| zero_damage | 0 | 0 | same |

## 300g Confirmation

| Metric | A baseline (300g) | B attack plan (300g) | Change |
|--------|------------------|---------------------|--------|
| attach_to_active | 52.3% | **54.1%** | **+1.8 pt** |
| starved | 1007 | **910** | **-97 (-10%)** |
| oversetup | 194 | **155** | **-39 (-20%)** |
| miss_KO | 25 | **24** | -1 |
| KO capture | 96.2% | **96.7%** | +0.5 pt |
| Attack when legal | 87.4% | **88.6%** | +1.2 pt |
| END when legal attack | 0 | 0 | same |
| zero_damage | 0 | 0 | same |

All: errors=0, timeouts=0

## Conclusion

**Attack plan improves all metrics at both 100g and 300g.** Consistent improvement across attach_to_active, starved, oversetup, and KO capture. No safety regressions.

## Recommendation

Attack plan ON を submission candidate に進める価値あり。

Next steps:
1. `POKEMON_AI_ATTACK_PLAN` default を 1 に変更
2. `build_submission.py` に `agent/attack_plan.py` を追加
3. submission.tar.gz を再作成
4. leaderboard で検証
