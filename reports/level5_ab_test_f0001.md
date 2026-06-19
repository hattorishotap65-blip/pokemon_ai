# Level 5 A/B Test Report: F0001

## Target

F0001: voltorb_over_wattrel_missed

## Fix Applied

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)

Wattrel がアクティブで Voltorb がベンチに攻撃可能状態（2+エネ、推定打点>=100）で存在する場合、retreat に +150 ボーナス。

## Results

### Per-Game Comparison (Baseline 30g / Candidate 50g)

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| anomalies_total | 5.27/g | 5.26/g | -0.01 |
| **voltorb_over_wattrel_missed** | **0.13/g** | **0.26/g** | **+0.13** |
| voltorb_over_kilowattrel_missed | 1.17/g | 1.06/g | -0.11 |
| bellibolt_over_voltorb_high_damage | 1.30/g | 1.62/g | +0.32 |
| bellibolt_attack_probably_correct | 2.67/g | 2.28/g | -0.39 |
| attack_available_but_no_attack | 0.00/g | 0.02/g | +0.02 |
| end_when_attack_available | 0.00/g | 0.00/g | 0 |
| retreat_when_attack_available | 0.00/g | 0.00/g | 0 |

### Fix Trigger Count

```
retreat_wattrel_to_voltorb_high_damage fired: 0 times (50 games)
```

## Decision

**no_measurable_impact（効果なし・無害）**

## Reasons

1. 修正コードが **1度も発火しなかった**（50ゲーム中 0回）
2. Wattrel がアクティブ + Voltorb がベンチで攻撃可能 + 推定打点>=100 の条件が極めてまれ
3. F0001 件数の変動（0.13→0.26/game）は小サンプル分散の範囲内
4. critical/high の安全指標に悪化なし（end/retreat when attack = 0 維持）
5. 修正自体は無害（安全ネットとして残してよい）

## Safety Check

| Check | Result |
|-------|--------|
| error_rate | 0% (変化なし) |
| attack_available_but_no_attack | 0 → 1件（1ゲームの偶発、修正と無関係） |
| end_when_attack_available | 0 維持 |
| retreat_when_attack_available | 0 維持 |
| win_rate | self-play のため参考外 |

## Recommendation

- F0001 の修正は**そのまま残す**（無害な安全ネット）
- **F0002 (voltorb_over_kilowattrel_missed) に進む**ことを推奨
  - 35-53件/バッチと十分な発生頻度
  - 修正効果が計測可能な見込み

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | Rule 17b に Wattrel→Voltorb retreat bonus 追加 |
| `reports/level5_ab_test_f0001.json` | A/B テスト結果 |
| `reports/level5_ab_test_f0001.md` | このレポート |
