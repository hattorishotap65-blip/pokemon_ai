# Attack Decision Diagnostics 001

## Purpose

PR #130 の結果、missed_ko_plan_energy_ready が約 11% あったが、
その中には ability / attach / play など攻撃前の準備行動が含まれる可能性がある。
このPRでは legal attack option が存在する decision を attack_decision として分離し、
真の missed KO を測れるようにする。

## Added Metrics

| Metric | Description |
|--------|-------------|
| attack_decision_count | legal attack option が存在した decision |
| attack_decision_missed_ko | attack decision で KO plan を逃した |
| attack_decision_missed_ko_energy_ready | energy ready な真の missed KO |
| attack_decision_missed_ko_energy_not_ready | energy 不足の plan/sim gap |
| non_attack_decision_missed_ko_energy_ready | attack decision 外の missed (ノイズ) |
| selected_attack_count | attack (type=13) を選択した回数 |
| selected_non_attack_with_legal_attack | legal attack ありで非攻撃を選択 |

## Design

- `classify_attack_decision()`: legal_option_summary を使い attack option 有無を判定
- 旧ログでは top_candidates fallback
- Policy behavior unchanged, score/ranking unchanged
- No End suppression, no attack boost, no energy attach boost

## Why This Matters

missed_ko_plan_energy_ready の全体 rate (~11%) には、攻撃前の
準備行動 (ability→attach→attack) が含まれ、policy 補正の根拠にならない。
attack_decision に絞ることで「攻撃可能だったのに逃した」場面だけを抽出できる。

## Next Steps

1. 50g/100g で再計測し attack_decision_missed_ko_energy_ready rate を確認
2. rate が高ければ conservative attack-plan boost 検討
3. rate が低ければ plan/simulator gap が主因と確定
