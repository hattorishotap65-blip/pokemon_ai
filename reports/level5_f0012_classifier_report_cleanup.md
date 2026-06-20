# F0012: Classifier / Report Cleanup

## 変更概要

F0011 の結論（real_fix_candidate 0件）と整合するよう、classifier の分類を修正。F0007 で既に対応済み・ゲーム展開で再発するもの・retreat 不可のものを fix prompt から完全に除外。

## 変更ファイル

| File | Change |
|------|--------|
| `tools/classify_anomalies.py` | 分類カテゴリ 5種追加、全 best_damage を no_actionable_fix に |
| `tools/generate_fix_prompt.py` | 3セクション表示維持 |
| `agent/` | **変更なし** |
| `deck.csv` | **変更なし** |
| `submission.tar.gz` | **変更なし** |

## 分類カテゴリ

| Category | Count | Action | Fix Prompt |
|----------|-------|--------|-----------|
| bellibolt_attack_probably_correct | 551 | no_fix_needed | **excluded** |
| kw_f0007_range_game_flow | 260 | no_actionable_fix | **excluded** |
| bb_240_259_no_actionable_fix | 67 | no_actionable_fix | **excluded** |
| bb_f0007_range_no_retreat | 66 | no_actionable_fix | **excluded** |
| wt_game_flow | 31 | no_actionable_fix | **excluded** |
| kw_120_179_no_actionable_fix | 23 | no_actionable_fix | **excluded** |
| **Behavior Fix Candidates** | **0** | — | — |

## F0011 との整合

| F0011 Category | Count | F0012 Classification |
|---------------|-------|---------------------|
| no_fix_needed | 551 | bellibolt_attack_probably_correct (**excluded**) |
| kw_f0007_range_game_flow | 260 | kw_f0007_range_game_flow (**excluded**) |
| bb_240_259_proven_unreachable | 96→67 | bb_240_259_no_actionable_fix (**excluded**) |
| bb_f0007_range_but_no_retreat | 37→66 | bb_f0007_range_no_retreat (**excluded**) |
| wt_game_flow | 31 | wt_game_flow (**excluded**) |
| kw_120_179_proven_unreachable | 23 | kw_120_179_no_actionable_fix (**excluded**) |

no_fix_needed (551) + no_actionable_fix (447) = 998 = 全件。Behavior Fix = 0。

## Fix Prompt 出力

```
Behavior Fix Candidates: 0
No Fix Needed: 551
No Actionable Fix: 447
  kw_f0007_range_game_flow: 260
  bb_240_259: 67
  bb_f0007_no_retreat: 66
  wt_game_flow: 31
  kw_120_179: 23
```

target: **none** — behavior 修正候補なし。

## 最終判断

- **Level 5: 完了** (behavior_fix_candidates == 0)
- **Level 6: 進行可能** (fix prompt が behavior 候補 0 件)
- **classifier/logger 追加整備: 現時点では不要**
