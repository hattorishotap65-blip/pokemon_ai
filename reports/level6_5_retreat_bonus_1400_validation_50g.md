# Level 6.5: retreat_to_better_attacker_bonus=1400 Validation 50g

## Candidate

retreat_to_better_attacker_bonus=1400 (30g で -12%、50g 検証候補)

## 50g vs 50g Results

| Metric | Baseline (1100) | Candidate (1400) | Delta |
|--------|----------------|-----------------|-------|
| **anomalies_total** | **5.76/g** | **4.74/g** | **-1.02 (-18%)** |
| attack_available_but_no_attack | 0 | **0** | safe |
| end_when_attack_available | 0 | **0** | safe |
| retreat_when_attack_available | 0 | **0** | safe |
| ability_without_followup_attack | 0 | **0** | safe |

### Classification Breakdown

| Category | Baseline (/g) | Candidate (/g) | Delta |
|----------|-------------|---------------|-------|
| bellibolt_attack_probably_correct | 2.84 | 2.22 | **-0.62** |
| **kw_f0007_range_game_flow** | **1.84** | **1.14** | **-0.70 (-38%)** |
| bb_f0007_range_no_retreat | 0.28 | 0.58 | +0.30 |
| bb_240_259 | 0.42 | 0.48 | +0.06 |
| kw_120_179 | 0.26 | 0.20 | -0.06 |
| wt_game_flow | 0.12 | 0.12 | 0 |

### F0007 Pivot Triggers

| | Count | /game |
|--|-------|-------|
| Baseline (1100) | 111 | 2.22 |
| Candidate (1400) | 109 | 2.18 |

Trigger 回数はほぼ同等。1400 でも不自然な増加なし。

## Analysis

### 改善した指標

- **anomalies_total -18%** — 30g (-12%) より改善幅が拡大
- **kw_f0007_range_game_flow -38%** — KW がアクティブに留まるケースが大幅減少
- **bellibolt_attack_probably_correct -22%** — BB 正当攻撃の検知も減少（pivot の効果でゲーム展開が変わり BB 攻撃自体が減った）

### 悪化した指標

- **bb_f0007_range_no_retreat +0.30** — retreat をより試みるが手段がないケースが増加。これは pivot bonus を上げた直接的な副作用だが、実際の挙動としては retreat option がなければ従来通り攻撃するため安全

### 30g vs 50g の一貫性

| Scale | 1400 /game | vs baseline |
|-------|-----------|-------------|
| 30g | 5.07 | **-12%** |
| **50g** | **4.74** | **-18%** |

**Level 6 で初めて、30g の改善が 50g で維持・拡大した。**

## Decision

**200g 検証候補として推奨**

### 根拠

1. **Safety all 0** — 全安全指標が 0 維持
2. **anomalies_total -18%** — 明確な改善
3. **30g → 50g で改善拡大** — Level 6 の adv=0.3/e=7.0 や e=4.0 とは異なり、分散ではない
4. **kw_f0007_range_game_flow -38%** — KW 関連の最大課題が改善
5. **F0007 trigger 数は安定** (2.22→2.18) — 不自然な増加なし
6. **bb_no_retreat +0.30** は副作用だが安全（retreat 手段がなければ攻撃するため）

### 注意点

- bb_f0007_range_no_retreat の増加が 200g でも続くか要確認
- bb_240_259 の微増 (+0.06) は許容範囲だが 200g で監視

## weights.json

**元の値 (1100.0) に復元済み。**

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| data/weights.json | **復元済み (1100.0)** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level6_5_retreat_bonus_1400_validation_50g.md | 新規 |
| reports/level6_5_retreat_bonus_1400_validation_50g.json | 新規 |
