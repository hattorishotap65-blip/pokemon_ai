# Ionos Energy Attach Scoring 001

## Purpose

ionos_rules.py の attach scoring に active 優先を加え、attach_to_active rate を改善する。

## Background

- #159: Top agents attach to active 81.3% vs our 49.7%
- #160: ml_hybrid bonus (+0.03-0.08) では効果なし — ionos_rules (100-300 pt) が支配的
- 今回: ionos_rules.py の `score_energy_attachment()` に直接 bonus/penalty を追加

## Implementation

`ionos_rules.py` の ATTACH scoring ブロック (opt_type=8) に追加:

- Active が main attacker (Voltorb/Bellibolt ex/Kilowattrel) かつ energy_needed > 0 の場合:
  - active への attach: `+IONOS_ACTIVE_ATTACH_BONUS` pt
  - bench への attach: `-IONOS_BENCH_ATTACH_PENALTY` pt
- Default: bonus=0, penalty=0 (挙動変更なし)
- Env: `POKEMON_AI_IONOS_ACTIVE_ATTACH_BONUS`, `POKEMON_AI_IONOS_BENCH_ATTACH_PENALTY`

## 100g Results

| Variant | Active Bonus | Bench Penalty | attach_active | starved | oversetup | miss_KO | KO capture |
|---------|-------------|---------------|--------------|---------|-----------|---------|------------|
| A baseline | 0 | 0 | 47.3% | 422 | 107 | 7 | 96.7% |
| B | +20 | 0 | 52.8% | 343 | 58 | 6 | 97.7% |
| C | +40 | 0 | 55.8% | 357 | 36 | 12 | 96.0% |
| **D** | **+40** | **-20** | **54.2%** | **328** | **53** | **2** | **99.2%** |
| E | +60 | -20 | 53.1% | 350 | 68 | 14 | 93.9% |

All: errors=0, timeouts=0, zero_damage=0, End+legal_attack not measured (separate metric)

### 100g Analysis

- B-E all improve attach_to_active (+5-8 pt) and reduce starved (-65 to -94)
- D (+40/-20) has best KO capture (99.2%) and lowest miss_KO (2)
- E (+60/-20) overshoots — miss_KO=14, KO capture drops to 93.9%
- C (+40/0) has best attach_active (55.8%) but miss_KO=12

## 300g Confirmation (A vs D)

| Metric | A baseline (300g) | D +40/-20 (300g) | Change |
|--------|------------------|-----------------|--------|
| attach_to_active | 49.5% | **52.8%** | **+3.3 pt** |
| active_energy_starved | 1122 | **990** | **-132 (-12%)** |
| bench_oversetup | 210 | **183** | **-27 (-13%)** |
| miss_KO | 33 | **26** | **-7 (-21%)** |
| KO capture | 95.5% | **96.2%** | **+0.7 pt** |

All: errors=0, timeouts=0, zero_damage=0

### 300g Analysis

- D improves all target metrics vs baseline at 300g scale
- attach_to_active: +3.3 pt (49.5% → 52.8%)
- active_energy_starved: -12% (1122 → 990)
- bench_oversetup: -13% (210 → 183)
- miss_KO improves: 33 → 26 (-21%)
- KO capture improves: 95.5% → 96.2%
- No safety regressions

## Conclusion

**D (+40 active bonus, -20 bench penalty) is safe and improves all target metrics at 300g.**

- attach_to_active は 49.5% → 52.8% に改善 (top agents の 81.3% にはまだ遠いが着実な改善)
- miss_KO / KO capture も改善
- Safety metrics は全て維持

## Recommendation

**D variant を submission candidate に進める価値あり。**

Next steps:
1. D settings をデフォルトに変更する PR を作成
2. submission.tar.gz を再作成
3. leaderboard で検証
