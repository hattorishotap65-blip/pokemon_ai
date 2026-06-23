# Attack Plan Diagnostics Eval 001

## Purpose

PR #122-#124 で追加した attack_plan diagnostics と enriched candidate log fields を使い、
実対戦ログから missed plan の傾向を確認する。このPRでは補正は行わない。

## Setup

- Base: main after PR #124
- Runner: `experiments/collect_attack_plan_diagnostics.py`
- Mode: default policy / rule_based runtime
- ML policy: disabled
- Generated artifacts: not committed

## Commands

```bash
python experiments/collect_attack_plan_diagnostics.py \
    --n 50 --start-game 98000 --run-games --use-wsl \
    --output artifacts/attack_plan_diagnostics_50g_001.json

python experiments/collect_attack_plan_diagnostics.py \
    --n 100 --start-game 99000 --run-games --use-wsl \
    --output artifacts/attack_plan_diagnostics_100g_001.json
```

## Results

| run | games | decisions | plans_available | chosen_matches_best | chosen_matches_any | missed_ko_plan | missed_hv_plan | end_with_plan | diag_errors |
|-----|-------|-----------|-----------------|--------------------|--------------------|----------------|----------------|---------------|-------------|
| 50g | 50 | 9328 | 8838 | 588 | 672 | 4551 | 533 | 467 | 0 |
| 100g | 100 | 19991 | 19023 | 1163 | 1362 | 9446 | 829 | 1017 | 0 |

## Rates

| run | missed_ko_rate | missed_hv_rate | chosen_best_rate | end_with_plan_rate |
|-----|----------------|----------------|------------------|--------------------|
| 50g | 51.5% | 6.0% | 6.7% | 5.3% |
| 100g | 49.7% | 4.4% | 6.1% | 5.3% |

## Plan Type Counts

| run | has_winning_ko | has_active_ko | has_boss_ko | has_zero_damage_escape |
|-----|----------------|---------------|-------------|----------------------|
| 50g | 561 | 4186 | 0 | 0 |
| 100g | 887 | 8980 | 0 | 0 |

## Representative Examples

| game_id | turn | best_plan_type | best_plan_score | chosen_type | notes |
|---------|------|----------------|-----------------|-------------|-------|
| 98000 | 6 | active_ko | 250 | 10 (ability) | missed_active_ko |
| 98000 | 6 | active_ko | 250 | 14 (end) | missed_active_ko, end_with_plan_available |
| 98000 | 8 | active_ko | 250 | 8 (attach) | missed_active_ko |
| 98000 | 1 | active_attack | 55 | 14 (end) | end_with_plan_available |

## Interpretation

### missed_ko_plan_rate ~50% は想定内の高さ

`missed_ko_plan` が高い主な理由は、**ターン中の全ての decision point** を対象にしているため。
1ターンで ability → attach → play → attack と複数 decision があり、attack 以外の行動
（ability=10, attach=8, play=7, card=3）は全て「KO plan を逃した」と判定される。

**実際には最終的に攻撃しているケースが多い**ため、この数値だけでは「KO を逃した」とは言えない。

### 真に問題なのは end_with_plan_available

`end_with_plan_available` (5.3%) は、有効な plan があるのに End (type=14) を選択したケース。
これが実際に「攻撃すべきだったのにしなかった」場面を含む可能性が高い。

### boss_ko / zero_damage_escape = 0

state_summary からの plan 生成では、bench の詳細情報が不足するため
boss_ko / zero_damage_escape plan が生成されない。ログベースの診断の限界。

### diagnostic_errors = 0

全行のパースに成功。結果は信頼できる。

### chosen_matches_best_rate ~6%

低いが、ターン中の非攻撃 decision も含むため想定内。
攻撃 decision point だけに絞れば rate は大幅に上がるはず。

## Decision

- Diagnostics collection works — 0 errors, consistent across 50g/100g
- Result is usable for next policy improvement
- No runtime policy changes in this PR

## Next Steps (priority order)

1. **end_with_plan_available の分析強化**: End を選んだ場面で実際に attack option があったかを
   has_legal_attack_option フラグと突き合わせる
2. **attack decision だけに絞った missed_ko rate** を算出して真の逃しを特定
3. **boss_ko / zero_damage_escape** は state_summary の限界のため、
   full state logging か別アプローチが必要
4. 上記で問題が特定できたら、policy 側で安全な補正を次 PR で検討

## Runtime / Safety

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- ML default disabled
- configs/ml_policy_weights.json 変更なし
- default_params / weights / deck / submission 変更なし
- Generated artifacts/logs not committed
