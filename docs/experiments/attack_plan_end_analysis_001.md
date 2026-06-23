# Attack Plan End Analysis 001

## Purpose

PR #125 で end_with_plan_available が約 5.3% あることが分かった。
このPRでは、End を選んだ場面で legal attack option が存在したかを追加分析できるようにした。

## Added Metrics

| Metric | Description |
|--------|-------------|
| selected_end_count | End (type=14) を選択した回数 |
| end_with_plan_and_attack_available | End + plan + attack candidate あり |
| end_with_plan_no_attack_available | End + plan + attack candidate なし |
| end_with_ko_plan_available | End + KO plan あり |
| end_with_high_value_plan_available | End + high-value plan あり |
| end_with_plan_and_attack_rate | (and_attack / end_count) |
| end_with_ko_plan_rate | (ko_plan / end_count) |

## Quick Validation (10g, start=99000)

| Metric | Value |
|--------|-------|
| decisions | 1,930 |
| selected_end_count | 98 |
| **end_with_plan_and_attack** | **0** |
| end_with_plan_no_attack | 98 |
| end_with_ko_plan | 56 |
| end_with_high_value_plan | 0 |

## Key Finding

**end_with_plan_and_attack = 0**: End を選んだ decision point で、
同時に attack candidate (type=13) が存在するケースは **ゼロ** だった。

つまり、End を選んだ場面では simulator が attack option を提供していなかった。
policy は「攻撃できるのに End を選んだ」のではなく、
「攻撃 option がないから End を選んだ」。

### missed_ko_plan が高い理由

attack_plan は「盤面上 KO 可能」と判定するが、
simulator が attack option を出すかは別問題（エネルギー不足、条件未達など）。
plan は理想的な攻撃可能性を示し、simulator の合法手は実際の制約を反映する。

## Runtime Impact

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- diagnostics runner のみ変更
- Generated artifacts/logs not committed

## Next Steps

1. **policy 側の End 抑制は不要**: attack option がないのに End を抑制すると illegal action になる
2. **attack_plan の plan 生成精度を改善**: エネルギー条件を考慮して
   「実際に攻撃可能か」を判定に加えると missed_ko_plan が減る
3. エネルギー付きの attack readiness check を plan 生成に組み込む候補
4. diagnostics の attack decision フィルタ（type=13 の decision のみ集計）を次 PR で検討
