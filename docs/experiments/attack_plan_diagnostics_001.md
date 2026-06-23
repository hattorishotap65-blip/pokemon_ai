# Attack Plan Diagnostics 001

## Purpose

attack_plan の改善前に、KO逃し・高価値plan逃し・zero damage回避などを
検出できる診断関数を追加した。通常実行の挙動は変更しない。

## Added Diagnostics

| Function | Purpose |
|----------|---------|
| `summarize_attack_plans(plans)` | Plan一覧の要約（count, types, KO flags） |
| `diagnose_attack_plan_choice(plans, chosen_action, state)` | 選択actionとbest planの一致/逃し診断 |

## What It Detects

| Detection | Condition |
|-----------|-----------|
| missed_winning_ko | winning_ko plan があるのに別行動を選択 |
| missed_active_ko | active_ko plan があるのに別行動を選択 |
| missed_boss_ko | boss_ko plan があるのに別行動を選択 |
| missed_high_value_plan | plan_score >= 800 の plan を逃した |
| end_with_plan_available | 有効な plan があるのに End を選択 |

## Runtime Impact

- 通常実行では挙動変更なし
- stdout への常時出力なし
- diagnostics はテスト・評価時の補助関数

## Next Steps

1. 実対戦ログから missed_ko_plan が多い場面を収集
2. policy側で安全な補正を追加するか検討
3. ML feature として diagnostics 結果を使える可能性あり
