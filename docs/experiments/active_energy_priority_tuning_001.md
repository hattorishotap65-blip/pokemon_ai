# Active Energy Priority Tuning 001

## Purpose

#159 の Top Episodes 比較で見えた attach_to_active rate の差 (81.3% vs 49.7%) を改善する実験。
ml_hybrid.py の heuristic score に小さな bonus/penalty を加えて効果を測定する。

## Background

| Metric | Top Agents | Our Agent | Gap |
|--------|-----------|-----------|-----|
| Attach to active | 81.3% | 49.7% | -31.6 pt |
| Active energy starved | 0 | 188 | -188 |
| Bench oversetup | 1 | 37 | -36 |

#153 では大きな補正 (+0.15) で miss_KO が悪化した。今回は小さな補正 (+0.03〜0.08) で試す。

## Variants

| Variant | ACTIVE_ATTACH_BONUS | BENCH_ATTACH_PENALTY | Description |
|---------|--------------------|--------------------|-------------|
| A | 0.00 | 0.00 | Baseline (default) |
| B | 0.03 | 0.00 | Small active bonus |
| C | 0.05 | 0.00 | Medium active bonus |
| D | 0.05 | 0.03 | Medium bonus + small penalty |
| E | 0.08 | 0.03 | Larger bonus + small penalty |

All variants: `POKEMON_AI_ML_HYBRID=1`, `POKEMON_AI_ML_BONUS_RATIO=10.0`, `POKEMON_AI_AREA_FIX_MODE=area_fix_only`

## 100g Results

### Core Metrics

| Variant | attach_to_active | starved | oversetup | miss_KO | KO capture |
|---------|-----------------|---------|-----------|---------|------------|
| A baseline | 50.6% | 375 | 42 | 13 | 94.9% |
| B +0.03 | 48.2% | 394 | 90 | 8 | 95.9% |
| C +0.05 | 48.8% | 384 | 109 | 11 | 95.4% |
| D +0.05/-0.03 | 50.6% | 381 | 42 | 11 | 95.5% |
| E +0.08/-0.03 | 48.7% | 399 | 76 | 12 | 94.8% |

### Safety Metrics (all pass)

All variants: errors=0, timeouts=0, zero_damage=0

### Action Distribution

| Variant | ATTACK | ATTACH | END | RETREAT | Decisions |
|---------|--------|--------|-----|---------|-----------|
| A | 1281 | 1272 | 950 | 331 | 20093 |
| B | 1231 | 1272 | 1014 | 370 | 20446 |
| C | 1246 | 1237 | 991 | 328 | 19103 |
| D | 1322 | 1279 | 968 | 359 | 20704 |
| E | 1332 | 1305 | 1026 | 382 | 20914 |

## Key Finding: ML Hybrid Bonus は Attach 先に影響しない

**attach_to_active rate は全 variant で 48-51% の範囲にとどまり、有意な改善が見られなかった。**

### 原因分析

1. **ionos_rules.py のルールスコアが支配的**: attach 先の決定は `ionos_rules.py` の `score_energy_attachment()` で 100-300 点のスコアが付く。ml_hybrid の bonus は正規化後 0-10 の範囲で加算されるため、+0.03〜0.08 の heuristic 変化は全体スコアに対して無視できるほど小さい。

2. **ML hybrid は相対順位しか変えない**: `_heuristic_ml_score` の変化は候補間の相対スコアに影響するが、ionos_rules が active attach と bench attach に同程度のスコアを付けている場合、ML bonus の微小な変化では逆転できない。

3. **attach_to_active の決定は ionos_rules 層で完結している**: ここを変えずに ML hybrid 層だけ調整しても、根本的な attach 優先度は変わらない。

## Conclusion

**ml_hybrid.py への小さな bonus/penalty では attach_to_active rate を改善できない。**

改善するには `ionos_rules.py` の `score_energy_attachment()` を直接調整する必要がある。具体的には:

1. active が main attacker で未完成 (energy_needed > 0) の場合、active への attach スコアを引き上げる
2. active 未完成時の bench attach スコアを引き下げる

ただし、ionos_rules の変更は runtime policy への直接変更となるため、慎重に別PRで実施すべき。

## Next Steps

1. **ionos_rules.py の attach scoring 調整** — `score_energy_attachment()` で active 優先度を上げる実験 PR
2. `ml_hybrid.py` の env flag はそのまま残す (将来の組み合わせ実験用)
3. default は 0.0 のまま — 挙動変更なし

## What This PR Does NOT Do

- default 挙動を変更しない (bonus=0, penalty=0)
- ionos_rules.py を変更しない
- submission.tar.gz を変更しない
- main.py / policy.py を変更しない
