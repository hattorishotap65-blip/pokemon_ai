# Level 6.5: retreat_to_better_attacker_bonus A/B Test 30g

## Command

```bash
python experiments/weight_search.py --grid-file reports/level6_5_retreat_bonus_grid.json --games 30 --use-wsl --start-game 7300
```

## Results (30g per pattern)

| Value | Anomalies | /game | Safety | F0007 Triggers | /game |
|-------|-----------|-------|--------|----------------|-------|
| 800 | 182 | 6.07 | OK | 51 | 1.70 |
| **1100** | **173** | **5.77** | **OK** | **73** | **2.43** |
| **1400** | **152** | **5.07** | **OK** | **70** | **2.33** |

## Classification Breakdown

| Category | 800 (/g) | 1100 (/g) | 1400 (/g) |
|----------|---------|-----------|-----------|
| bellibolt_attack_probably_correct | 2.70 | 2.97 | 2.63 |
| kw_f0007_range_game_flow | 1.67 | 1.63 | **0.97** |
| wt_game_flow | 0.60 | 0.37 | 0.00 |
| bb_f0007_range_no_retreat | 0.50 | 0.37 | 0.77 |
| bb_240_259 | 0.37 | 0.30 | 0.63 |
| kw_120_179 | 0.20 | 0.13 | 0.07 |

## Safety Metrics

全3パターン:
- attack_available_but_no_attack: **0**
- end_when_attack_available: **0**
- retreat_when_attack_available: **0**
- ability_without_followup_attack: **0**

## Analysis

### 800 (weaker pivot)

- anomalies 6.07/g — **baseline より悪化**
- F0007 triggers 1.70/g — baseline 2.43 から **減少**（pivot が弱まった）
- kw_f0007_range_game_flow は微増
- wt_game_flow が 0.60/g に増加
- **50g 候補にしない**

### 1100 (baseline)

- anomalies 5.77/g — 基準値
- F0007 triggers 2.43/g
- 安定

### 1400 (stronger pivot)

- anomalies **5.07/g** — baseline 5.77 から **-12%**
- F0007 triggers 2.33/g — baseline とほぼ同等
- kw_f0007_range_game_flow が **0.97/g** に改善（baseline 1.63 から -40%）
- wt_game_flow が 0.00/g に改善
- ただし bb_f0007_range_no_retreat が 0.77/g に増加（retreat 不可ケースが増える = より多くの場面で retreat を試みるが手段がない）
- bb_240_259 も 0.63/g に増加

## 50g 検証候補

| Value | 30g /game | Candidate? | Reason |
|-------|-----------|-----------|--------|
| 800 | 6.07 | **No** | baseline より悪化 |
| 1100 | 5.77 | baseline | — |
| **1400** | **5.07** | **Yes** | -12%, safety OK, kw_game_flow 改善 |

### 1400 の注意点

- kw_f0007_range_game_flow -40% は大きな改善
- ただし bb_no_retreat +0.40/g は、retreat をより試みるが手段がないケースの増加を示す
- 30g は分散が大きい（Level 6 Run 001/002 で実証済み）
- **50g で確認すべき**

## Decision

**1400 を 50g 検証候補にする。採用判断はまだしない。**

## weights.json

**元の値 (1100.0) に復元済み。**

## Changed Files

| File | Change |
|------|--------|
| reports/level6_5_retreat_bonus_grid.json | 探索グリッド |
| reports/level6_5_retreat_bonus_ab_test_30g.md | 新規 |
| reports/level6_5_retreat_bonus_ab_test_30g.json | 新規 |
| agent/ | **変更なし** |
| data/weights.json | **復元済み (1100.0)** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
