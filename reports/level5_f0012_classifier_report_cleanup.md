# F0012: Classifier / Report Cleanup

## 変更概要

classifier と fix prompt 生成を整理し、F0009/F0010 で rejected な分類を修正候補から除外。

## 変更ファイル

| File | Change |
|------|--------|
| `tools/classify_anomalies.py` | 分類カテゴリ追加、fix prompt 除外ロジック |
| `tools/generate_fix_prompt.py` | レポート表示を3セクションに分離 |
| `agent/` | **変更なし** |
| `deck.csv` | **変更なし** |
| `submission.tar.gz` | **変更なし** |

## 分類カテゴリ定義

| Category | Action | Fix Prompt |
|----------|--------|-----------|
| `voltorb_over_wattrel_missed` | scoring_adjustment | **含む** |
| `voltorb_over_kilowattrel_missed` | scoring_adjustment | **含む** |
| `bellibolt_over_voltorb_high_damage` | scoring_adjustment | **含む** |
| `bellibolt_attack_probably_correct` | no_fix_needed | **除外** |
| `bb_240_259_no_actionable_fix` | no_actionable_fix_game_flow | **除外** |
| `kw_120_179_no_actionable_fix` | no_actionable_fix_game_flow | **除外** |
| `unknown_due_to_missing_pivot_or_energy_info` | logging_improvement | **除外** |

## Fix Candidates MD 表示

3セクションに分離：

1. **Fix Candidates** — 修正候補（actionable のみ）
2. **No Fix Needed** — 現在の行動が妥当
3. **No Actionable Fix** — ゲーム展開の制約で修正不能

## 再実行結果 (200g)

| Classification | Count | Action |
|----------------|-------|--------|
| bellibolt_attack_probably_correct | 551 | **excluded** (no_fix_needed) |
| voltorb_over_kilowattrel_missed | 260 | scoring_adjustment |
| bb_240_259_no_actionable_fix | 67 | **excluded** (no_actionable_fix) |
| bellibolt_over_voltorb_high_damage | 66 | scoring_adjustment |
| voltorb_over_wattrel_missed | 31 | scoring_adjustment |
| kw_120_179_no_actionable_fix | 23 | **excluded** (no_actionable_fix) |

- **real_fix_candidate**: voltorb_over_wattrel (31) + voltorb_over_kilowattrel (260) + bellibolt_over_voltorb (66) = 357件
- ただし F0007 で既に対応済み（pivot >=260/>=180）。追加の behavior 修正なし。
- **excluded**: 641件（no_fix_needed 551 + no_actionable_fix 90）

## F0009/F0010 再提案防止

`bb_240_259_no_actionable_fix` と `kw_120_179_no_actionable_fix` は fix prompt に含まれない。root_cause に「F0009/F0010 rejected」と明記。

## 最終判断

### Level 5 完了扱いできるか

**はい。** F0001-F0012 で以下を達成：
- L5 behavior 修正: F0007 (pivot >=260/>=180) が accepted
- L5 不採用記録: F0009/F0010
- L5 classifier 整備: F0012 (本PR)

### Level 6 重み探索に進んでよいか

**条件付きで可。** ただし：
- 残りの actionable anomaly (357件) は F0007 の既存 pivot 範囲内
- これ以上の retreat-based 改善は見込み薄
- Level 6 では retreat 以外のアプローチ（エネルギー配分、アクティブ選択改善等）を検討すべき

### classifier / logger の追加整備が必要か

**現時点では不要。** F0012 で分類は十分整理された。将来的にベンチ詳細ログが追加されれば、logging_improvement 分類が活用できる。
