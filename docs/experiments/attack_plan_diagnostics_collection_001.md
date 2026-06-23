# Attack Plan Diagnostics Collection 001

## Purpose

PR #122 で追加した attack_plan diagnostics を、実対戦ログから集計できるようにした。
通常 policy 挙動は変更しない。

## Added Runner

`experiments/collect_attack_plan_diagnostics.py`

### Usage

```bash
# Run games then analyze:
python experiments/run_matches_real.py --n 50 --start-game 97000
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 97000 \
    --output artifacts/attack_plan_diagnostics_50g.json

# Or combined:
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 97000 --run-games --use-wsl \
    --output artifacts/attack_plan_diagnostics_50g.json
```

## Metrics

| Metric | Description |
|--------|-------------|
| decisions | Total decision points analyzed |
| plans_available | Decision points with at least 1 attack plan |
| chosen_matches_best | Chosen action matched best plan |
| chosen_matches_any | Chosen action matched any plan |
| missed_ko_plan | KO plan available but not matched |
| missed_high_value_plan | Plan score >= 800 but not matched |
| end_with_plan_available | End chosen despite plan available |
| has_winning_ko / active_ko / boss_ko | KO plan existence counts |
| has_zero_damage_escape | Zero damage escape plan existence |
| diagnostic_errors | Errors during diagnostics (skipped) |

## Output Format

- Rates: missed_ko_plan_rate, chosen_matches_best_rate, etc.
- Examples: up to 20 notable cases with game_id, turn, plan type, notes
- No personal data, no large state dumps

## Runtime Impact

- Normal policy unchanged
- No stdout in normal execution
- Diagnostics only when runner is explicitly invoked
- Generated JSON goes to artifacts/ (not committed)

## Known Limitations

- 現在の diagnostics は attack / end 系の検出を主目的とする
- boss_ko / switch / retreat 系の missed 判定は、ログに raw option fields
  (`area`, `index`, `playerIndex`, `attackId`, `inPlayArea`, `inPlayIndex`)
  が不足しているため参考値
- それらの精度向上は次 PR で candidate log に詳細フィールドを追加して対応する
- このPRでは通常 policy 挙動・ログ形式・runtime default は変更しない

## Next Steps

1. Collect 50g/100g diagnostics to measure baseline missed_ko rate
2. Identify which plan types are most commonly missed
3. Enrich candidate log with raw option fields for boss/switch/retreat accuracy
4. Consider safe policy corrections in next PR
