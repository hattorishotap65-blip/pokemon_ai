# Legal Option Attack Diagnostics Eval 001

## Purpose

PR #127 で追加した legal_option_summary を使い、End 選択時に legal attack option が
本当に存在したかを実測する。

## Setup

- Base: main after PR #127
- Runner: `experiments/collect_attack_plan_diagnostics.py`
- Mode: default policy / rule_based runtime
- ML policy: disabled
- Generated artifacts: not committed

## Commands

```bash
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 100000 --run-games --use-wsl \
    --output artifacts/legal_option_attack_diagnostics_50g_001.json

python experiments/collect_attack_plan_diagnostics.py \
    --n 100 --start-game 101000 --run-games --use-wsl \
    --output artifacts/legal_option_attack_diagnostics_100g_001.json
```

## Results

| run | games | decisions | plans_available | selected_end_count | end_with_plan | selected_end_with_legal_attack | end_with_plan_and_legal_attack | end_with_plan_no_legal_attack | end_with_ko_plan_and_legal_attack | diag_errors |
|-----|-------|-----------|-----------------|-------------------|--------------|---------------------------------|-------------------------------|------------------------------|----------------------------------|-------------|
| 50g | 50 | 10,268 | 9,769 | 551 | 551 | **0** | **0** | 551 | **0** | 0 |
| 100g | 100 | 18,864 | 17,873 | 1,001 | 1,001 | **0** | **0** | 1,001 | **0** | 0 |

## Rates

| run | end_with_plan_rate | selected_end_with_legal_attack_rate | end_with_plan_and_legal_attack_rate | end_with_ko_plan_rate |
|-----|-------------------|------------------------------------|------------------------------------|-----------------------|
| 50g | 5.6% | **0.0%** | **0.0%** | 50.5% |
| 100g | 5.6% | **0.0%** | **0.0%** | - |

## Representative Examples

| game_id | turn | best_plan_type | chosen_type | has_legal_attack | legal_attack_count | legal_option_count | notes |
|---------|------|----------------|-------------|-----------------|--------------------|--------------------|-------|
| 100000 | 1 | active_attack | 14 (end) | False | 0 | 1 | end_with_plan_available |
| 100000 | 2 | active_attack | 14 (end) | False | 0 | 3 | end_with_plan_available |

End の場面では legal_option_summary に attack=0 で、legal attack option は存在しなかった。

## Key Finding

**50g + 100g の合計 1,552 End 決定のうち、legal attack option が存在したケースは 0。**

- `selected_end_with_legal_attack = 0` (50g + 100g)
- `end_with_plan_and_legal_attack = 0` (50g + 100g)
- `end_with_ko_plan_and_legal_attack = 0` (50g + 100g)

Policy が End を選ぶ場面では、simulator が attack option を出していない。
「攻撃できるのに End を選んだ」ケースは **150g で一度も確認されなかった**。

## Interpretation

1. **End 抑制補正は不要**: legal attack option がないのに End を抑制すると illegal action になる
2. **missed_ko_plan ~50% は plan/simulator ギャップ**: attack_plan は盤面上 KO 可能と判定するが、
   エネルギー不足や攻撃条件未達で simulator が attack option を出さない
3. **次の改善対象は attack_plan の readiness 精度**: エネルギー条件を考慮して
   「実際に攻撃可能か」を plan 生成に加えれば、missed_ko_plan が大幅に減る
4. **diagnostic_errors = 0**: 全行のパースに成功。結果は信頼できる

## Decision

- **End 抑制補正は行わない** — legal attack なしの End を抑制するのは unsafe
- **attack_plan の readiness 改善に進む** — エネルギー条件チェックを plan 生成に追加
- Runtime default はまだ変更しない

## Next Steps

1. attack_plan の `generate_attack_plans` にエネルギー条件チェックを追加
   - 現状: 盤面上 KO 可能かだけで plan 生成
   - 改善: `has_attack_energy` / 攻撃に必要なエネルギーが足りているかも判定
   - 効果: missed_ko_plan が実際に攻撃可能なケースのみにフィルタされる
2. missed_ko_plan rate が改善されたか再計測
3. attack_plan の plan_score を energy readiness で調整

## Runtime / Safety

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- ML default disabled
- configs/ml_policy_weights.json 変更なし
- default_params / weights / deck / submission 変更なし
- Generated artifacts/logs not committed
