# Attack Plan Energy Readiness Eval 001

## Purpose

PR #129 で追加した energy_ready / energy_required / energy_attached を使い、
missed_ko_plan の内訳を再評価する。

## Setup

- Base: main after PR #129
- Runner: `experiments/collect_attack_plan_diagnostics.py`
- Mode: default policy / rule_based runtime
- ML policy: disabled
- Generated artifacts: not committed

## Commands

```bash
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 102000 --run-games --use-wsl \
    --output artifacts/attack_plan_energy_readiness_50g_001.json

python experiments/collect_attack_plan_diagnostics.py \
    --n 100 --start-game 103000 --run-games --use-wsl \
    --output artifacts/attack_plan_energy_readiness_100g_001.json
```

## Results

| run | games | decisions | plans_avail | missed_ko | missed_ko_energy_ready | missed_ko_energy_not_ready | ko_plan_energy_ready | ko_plan_energy_not_ready | end_with_legal_atk | diag_errors |
|-----|-------|-----------|-------------|-----------|------------------------|---------------------------|---------------------|------------------------|--------------------|-------------|
| 50g | 50 | 9,464 | 8,983 | 4,757 | **1,020** | 3,675 | 1,212 | 3,675 | 0 | 0 |
| 100g | 100 | 19,235 | 18,254 | 9,107 | **2,056** | 6,778 | 2,454 | 6,778 | 0 | 0 |

## Rates

| run | missed_ko_rate | missed_ko_energy_ready_rate | missed_ko_energy_not_ready_rate |
|-----|----------------|----------------------------|---------------------------------|
| 50g | 53.0% | **11.4%** | 40.9% |
| 100g | 49.9% | **11.3%** | 37.1% |

## missed_ko_plan の内訳

| 内訳 | 50g | 100g | 割合 |
|------|-----|------|------|
| energy_ready (真の missed) | 1,020 | 2,056 | ~21% of missed_ko |
| energy_not_ready (plan/sim gap) | 3,675 | 6,778 | ~77% of missed_ko |
| energy_ready=None (unknown card) | 62 | 273 | ~2% of missed_ko |

## Representative Examples

| game_id | turn | best_plan | chosen | energy_ready | e_req | e_attached | notes |
|---------|------|-----------|--------|-------------|-------|------------|-------|
| 102000 | 1 | active_attack | 14 (end) | False | 2 | 1 | end_with_plan, energy not ready |
| 102000 | 6 | active_ko | 10 (ability) | False | 4 | 0 | missed_active_ko, energy not ready |
| 102000 | 6 | active_ko | 3 (card) | False | 4 | 0 | missed_active_ko, energy not ready |

## Interpretation

1. **missed_ko の大半 (~77%) は energy_not_ready**: エネルギー不足で攻撃できない場面を
   plan が KO 可能と判定しているギャップ。policy 補正は不要。

2. **energy_ready な missed KO は ~11% (約21% of missed_ko)**: エネルギーが足りているのに
   KO plan に沿った行動を選んでいない。ただし、これらの大半は「ターン中の非攻撃 decision」
   （ability=10, attach=8, play=7 → 攻撃前の準備行動）であり、
   最終的に攻撃しているケースが含まれる。

3. **selected_end_with_legal_attack は引き続き 0**: End 抑制は不要。

4. **diagnostic_errors = 0**: 結果は信頼できる。

## Decision

- **End 抑制は不要** (selected_end_with_legal_attack = 0)
- **energy_not_ready plan の過剰生成が主因** → plan 生成時にエネルギー条件でフィルタ/重み付けを検討
- **energy_ready missed KO (11%) は次の調査対象**: attack decision (type=13) だけに絞った missed_ko_energy_ready を計測すれば、真の逃しを特定可能
- 当面は policy 補正よりも plan 精度改善を優先

## Next Steps

1. attack decision (type=13) だけに絞った missed_ko_energy_ready rate を計測
2. energy_not_ready plan の plan_score を下げる / diagnostics から除外する
3. missed_ko_energy_ready が type=13 decision でも高ければ conservative boost 検討
4. runtime default はまだ変更しない

## Runtime / Safety

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- End 抑制なし、Energy attach 補正なし
- ML default disabled
- configs/ml_policy_weights.json 変更なし
- default_params / weights / deck / submission 変更なし
- Generated artifacts/logs not committed
