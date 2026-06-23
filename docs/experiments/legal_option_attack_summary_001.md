# Legal Option Attack Summary 001

## Purpose

PR #126 では top_candidates 内に attack candidate があるかを見た。
このPRでは legal options 全体の attack option count をログに追加し、
End 選択時に本当に legal attack option が存在したかを診断できるようにする。

## Added Log Fields (agent/logger.py)

`legal_option_summary` block:

| Field | Description |
|-------|-------------|
| total | legal options 総数 |
| attack | type=13 の数 |
| end | type=14 の数 |
| attach | type=8 の数 |
| ability | type=10 の数 |
| play | type=3,7 の数 |
| has_attack | attack > 0 |
| has_end | end > 0 |

Full legal action list は保存しない。count/boolean のみ。

## Added Diagnostics

| Metric | Description |
|--------|-------------|
| selected_end_with_legal_attack | End 選択 + legal attack あり |
| end_with_plan_and_legal_attack | End + plan + legal attack あり |
| end_with_plan_no_legal_attack | End + plan + legal attack なし |
| end_with_ko_plan_and_legal_attack | End + KO plan + legal attack あり |

## Backward Compatibility

- `legal_option_summary` がないログでは top_candidates fallback
- `get_legal_attack_info()` が source を判定
- 古いログでもクラッシュしない

## Why This Matters

top_candidates は絞り込み後の候補であり、legal options 全体ではない。
`legal_option_summary` を使えば、End を選んだ時に legal attack option が
本当に存在したかを正確に判定できる。

## Runtime Impact

- 通常 policy 挙動変更なし
- score/ranking/action selection 変更なし
- logs に count/boolean summary のみ追加
- full legal action list は保存しない
- Generated artifacts/logs not committed

## Next Steps

このPR後、新ログで diagnostics を再実行し、
`end_with_plan_and_legal_attack` が存在するか確認する。
- 存在しなければ: End 抑制ではなく attack_plan の readiness 精度改善に進む
- 存在すれば: 安全な End 抑制補正を検討する
