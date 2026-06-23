# Attack Decision Diagnostics Eval 001

## Purpose

PR #131 で追加した attack decision diagnostics を使い、legal attack option が存在する
decision に絞った missed KO を再評価する。

## Setup

- Base: main after PR #131
- Runner: `experiments/collect_attack_plan_diagnostics.py`
- Mode: default policy / rule_based runtime
- ML policy: disabled
- Generated artifacts: not committed

## Commands

```bash
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 104000 --run-games --use-wsl \
    --output artifacts/attack_decision_diagnostics_50g_001.json

python experiments/collect_attack_plan_diagnostics.py \
    --n 100 --start-game 105000 --run-games --use-wsl \
    --output artifacts/attack_decision_diagnostics_100g_001.json
```

## Results

| run | games | decisions | plans_avail | atk_dec_count | atk_dec_missed_ko | atk_dec_missed_ko_energy_ready | atk_dec_missed_ko_energy_not_ready | non_atk_missed_ko_energy_ready | sel_atk | sel_non_atk_w_legal_atk | sel_end_w_legal_atk | diag_err |
|-----|-------|-----------|-------------|---------------|-------------------|-------------------------------|-----------------------------------|-------------------------------|---------|------------------------|--------------------|----|
| 50g | 50 | 9,530 | 9,021 | 688 | 18 | **18** | 0 | 1,021 | 613 | 75 | 0 | 0 |
| 100g | 100 | 19,406 | 18,405 | 1,436 | 49 | **46** | 0 | 2,441 | 1,253 | 183 | 0 | 0 |

## Rates

| run | atk_dec_missed_ko_rate | atk_dec_missed_ko_energy_ready_rate | atk_dec_missed_ko_energy_not_ready_rate |
|-----|----------------------|------------------------------------|-----------------------------------------|
| 50g | 2.6% | **2.6%** | 0.0% |
| 100g | 3.4% | **3.2%** | 0.0% |

## Key Findings

### 1. 真の missed KO は非常に少ない (2.6-3.2%)

attack decision (legal attack option がある decision) に絞ると、
missed KO energy_ready は **18/688 (50g) = 2.6%**, **46/1436 (100g) = 3.2%**。

PR #130 の全体 missed_ko_energy_ready 11.3% のうち、大半 (1,021/1,039 = 98%) は
**attack decision 外のノイズ** (ability/attach/play 中に plan が KO 可能と判定)。

### 2. attack_decision_missed_ko_energy_not_ready = 0

attack option がある場面では、エネルギー不足の plan/simulator gap は発生していない。
simulator が attack option を出すのはエネルギーが足りている時のみ。

### 3. selected_end_with_legal_attack = 0

引き続き End 抑制は不要。

### 4. selected_non_attack_with_legal_attack = 75-183

attack option があるのに ability/attach/play を選んだケース。
これは正常動作 — ターン中に ability → attach → attack と複数ステップがあるため。

## Noise Breakdown

| PR #130 metric | Value (100g) | Of which attack_decision | Of which noise |
|----------------|-------------|--------------------------|----------------|
| missed_ko_energy_ready | ~2,056 | **46 (2.2%)** | 2,441 (97.8%) |

## Decision

- **conservative attack boost はまだ不要**: 真の missed KO は 2.6-3.2% と低い
- **attack_plan diagnostics は一区切り**: ノイズ分離に成功し、true missed KO を特定
- **提出候補確認に進む**: 安全な状態

## Submission Candidate Check

| 条件 | 結果 |
|------|------|
| diagnostic_errors = 0 | **OK** |
| selected_end_with_legal_attack = 0 | **OK** |
| attack_decision_missed_ko_energy_ready が低い | **OK (2.6-3.2%)** |
| policy / score / ranking 変更なし | **OK** |
| artifacts / logs 混入なし | **OK** |

**→ submission package validation に進める**

## Next Steps

1. submission package 確認 PR へ進む
2. attack_plan boost は、将来的に 2-3% の true missed KO を改善する候補として保留
3. runtime default はまだ変更しない

## Runtime / Safety

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- End 抑制なし、attack boost なし、Energy attach 補正なし
- ML default disabled
- configs/ml_policy_weights.json 変更なし
- default_params / weights / deck / submission 変更なし
- Generated artifacts/logs not committed
