# Level 5 A/B Test Report: F0002

## Target

F0002: voltorb_over_kilowattrel_missed

## Fix Applied

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)

Kilowattrel がアクティブで攻撃可能（3+エネ）でも、ベンチの Voltorb が攻撃可能（2+エネ）かつ推定打点 >= 120 の場合、retreat suppression を解除（-300 → +100）。

## Results

### Per-Game Comparison (50g vs 50g)

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| anomalies_total | 5.14/g | 4.64/g | **-0.50** |
| **voltorb_over_kilowattrel_missed** | **1.10/g** | **0.94/g** | **-0.16** |
| voltorb_over_wattrel_missed | 0.10/g | 0.04/g | -0.06 |
| bellibolt_over_voltorb_high_damage | 1.78/g | 1.64/g | -0.14 |
| bellibolt_attack_probably_correct | 2.16/g | 1.98/g | -0.18 |
| attack_available_but_no_attack | 0.00/g | 0.02/g | +0.02 |
| end_when_attack_available | 0.00/g | 0.00/g | 0 |
| retreat_when_attack_available | 0.00/g | 0.00/g | 0 |

### Fix Trigger Count

```
retreat_kilowattrel_to_voltorb_high_damage fired: 0 times (50 games)
```

## Decision

**accept_as_harmless_safety_net**

## Reasons

1. 修正コードは **50 ゲーム中 0 回発火**
2. Kilowattrel active (3+エネ) + Voltorb bench (2+エネ, 推定打点>=120) の条件が極めてまれ
3. 理由: Voltorb が 2+ エネで攻撃可能なら、通常は Voltorb がアクティブとして先に使われている
4. 異常件数の変動（257→232）はゲーム分散の範囲内
5. critical/high 安全指標に悪化なし

## Safety Check

| Check | Result |
|-------|--------|
| error_rate | 0% (変化なし) |
| end_when_attack_available | 0 (変化なし) |
| retreat_when_attack_available | 0 (変化なし) |
| attack_available_but_no_attack | 0 → 1 (noise) |
| deck.csv 変更 | なし |
| PDF 追加 | なし |
| submission.tar.gz 再生成 | 済 |

## Analysis

F0001・F0002 ともに retreat bonus アプローチでは発火しない。根本原因は:

> Voltorb が攻撃可能なら、そもそも Voltorb がアクティブになっている。  
> Kilowattrel/Wattrel がアクティブのときは、Voltorb はベンチにいても攻撃不可（エネ不足）。

retreat-based な修正は安全ネットとして残す価値はあるが、F0002 の件数を実質的に減らすには **Bellibolt ex Ability でのエネ配分**（Voltorb に優先して 2 エネ目を付ける）や、**アクティブ選択の改善**（setup 時に Voltorb を優先する）が必要。

## Recommendation

- F0002 修正はそのまま残す（無害）
- 次の改善候補は **F0003 (bellibolt_over_voltorb_high_damage)** だが、retreat アプローチの限界を踏まえ、エネルギー配分・アクティブ選択のアプローチを検討すべき
