# F0009: Turn Rule Pivot Exception — Extended Validation

## Target

F0002/F0003 mild retreat bonus を +1100 に引き上げ、turn_rule -1000 を超えて pivot 可能に。

## Implementation

**File:** `agent/ionos_rules.py` (turn_rule_engine 変更なし)

| Active | Range | Before | After |
|--------|-------|--------|-------|
| Bellibolt ex | est 240-259 | +80 (blocked) | +1100 (F0009) |
| Kilowattrel | est 120-179 | +100 (blocked) | +1100 (F0009) |

## 200g vs 200g Comparison

| Metric | Baseline (200g, F0007 only) | Candidate (200g, F0007+F0009) | Delta |
|--------|----------------------------|-------------------------------|-------|
| bellibolt_attack_probably_correct | 2.75/g | 2.85/g | +0.09 |
| **bellibolt_over_voltorb_high_damage** | **0.67/g** | **0.82/g** | **+0.16 (+22%)** |
| voltorb_over_kilowattrel_missed | 1.42/g | 1.47/g | +0.05 |
| **voltorb_over_wattrel_missed** | **0.15/g** | **0.34/g** | **+0.19 (+127%)** |
| attack_available_but_no_attack | 0 | **0** | safe |
| end_when_attack_available | 0 | **0** | safe |
| retreat_when_attack_available | 0 | **0** | safe |

### Per-Batch Consistency (Candidate)

| Batch | Total | bb_high/g | kw_miss/g | bb_ok/g |
|-------|-------|-----------|-----------|---------|
| g28xx | 252 | 0.96 | 1.24 | 2.56 |
| g29xx | 298 | 0.76 | 1.68 | 3.18 |
| g30xx | 271 | 0.76 | 1.46 | 2.96 |
| g31xx | 276 | 0.82 | 1.50 | 2.68 |

### Trigger Count (200g)

| Type | Count | /game |
|------|-------|-------|
| F0009 BB pivot (240-259) | 310 | 1.55 |
| F0009 KW pivot (120-179) | 41 | 0.20 |
| F0007 KW pivot (>=180) | 178 | 0.89 |
| F0007 BB pivot (>=260) | 79 | 0.40 |
| **F0009 total new** | **351** | **1.75** |

## Decision

**hold**

### 根拠

**良い点:**
- Safety metrics **all 0** — retreat/end/attack 誤判定なし
- F0009 が **351回発火 (1.75/g)** — 実際に機能している
- bellibolt_attack_probably_correct は安定 (2.75→2.85)

**懸念点:**
- bellibolt_over_voltorb_high_damage: **0.67→0.82 (+22%)** — 50g では分散だったが、200g でも微増傾向
- voltorb_over_wattrel_missed: **0.15→0.34 (+127%)** — retreat が増えたことでゲーム展開が変わり、Wattrel がアクティブになるケースが増えた可能性
- 全体の anomalies_total は改善していない

### 分析

F0009 の pivot は BB 240-259 で 310回 (1.55/g) と高頻度で発火。しかしこの範囲は Bellibolt (230) と Voltorb (240-259) の打点差が小さい (最大29ポイント)。

retreat → Voltorb 攻撃のシーケンスでは:
1. Retreat cost (エネルギーロス) が発生
2. ゲームのテンポが変わる
3. 結果として Wattrel がアクティブになるケースが増える

打点差 10-29 のために retreat cost を払う価値が不十分な可能性がある。

### 推奨

F0009 の BB 240-259 範囲は **revert すべき** (打点差が小さすぎる)。  
F0009 の KW 120-179 範囲は **keep** (KW 70 vs VT 120-179 で打点差が十分)。

または、両方とも revert して F0007 のみに戻す。

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | F0002/F0003 mild bonus +80/+100 → +1100 |
| `reports/level5_f0009_turn_rule_pivot_exception.md` | 更新（200g検証追加） |
| `reports/level5_f0009_turn_rule_pivot_exception.json` | 更新 |
| `submission.tar.gz` | 再生成済み |
