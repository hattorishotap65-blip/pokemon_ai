# Attack Plan Energy Readiness 001

## Purpose

PR #128 の結果、End 抑制ではなく attack_plan readiness 精度改善が次の課題と分かった。
このPRでは attack_plan に energy readiness 情報を追加し、KO plan が実際に攻撃可能そうかを区別できるようにする。

## Added AttackPlan Fields

| Field | Type | Description |
|-------|------|-------------|
| energy_ready | bool/None | 攻撃に必要なエネルギーが足りているか |
| energy_required | int/None | 攻撃に必要なエネルギー枚数 |
| energy_attached | int/None | 現在のエネルギー枚数 |

Known cards: Voltorb(265)=2, Bellibolt ex(269)=4, Kilowattrel(271)=3.
Unknown card: energy_ready=None (plan 生成は止めない).

## Added Diagnostics

| Metric | Description |
|--------|-------------|
| missed_ko_plan_energy_ready | missed KO + エネルギー足りている |
| missed_ko_plan_energy_not_ready | missed KO + エネルギー不足 |
| ko_plan_energy_ready | KO plan でエネルギー OK の数 |
| ko_plan_energy_not_ready | KO plan でエネルギー不足の数 |
| energy_ready_plans | 全 plan 中エネルギー OK |
| energy_not_ready_plans | 全 plan 中エネルギー不足 |

## Design

- Policy behavior unchanged — plan 生成も score も変えない
- Unknown card は energy_ready=None でフォールバック
- energy_not_ready plan は削除しない（互換性維持）
- Diagnostics で区別するだけ

## Why This Matters

従来の missed_ko_plan はエネルギー不足で攻撃できない場面も missed として数えていた。
energy readiness を見ることで、真の missed KO と plan/simulator gap を分離できる。

## Runtime / Safety

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- End 抑制なし、Energy attach 補正なし
- Generated artifacts/logs not committed

## Next Steps

1. 新しい diagnostics で 50g/100g を再計測
2. missed_ko_plan_energy_ready が多ければ policy 補正候補
3. missed_ko_plan_energy_not_ready が多ければ plan/simulator gap（補正不要）
