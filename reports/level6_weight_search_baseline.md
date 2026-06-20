# Level 6: Weight Search Baseline

## Purpose

既存ルールの重みを data/weights.json に外出しし、安全に探索できる基盤を構築。

## Added Files

| File | Purpose |
|------|---------|
| `data/weights.json` | 重み設定ファイル（初期値 = 既存コードと同等） |
| `experiments/weight_search.py` | 小規模重み探索スクリプト |

## Modified Files

| File | Change |
|------|--------|
| `agent/policy.py` | `_load_weights()` 追加、`w()` ヘルパー、重み参照箇所を外出し |
| `build_submission.py` | `data/weights.json` を submission に含める |

## Weights Defined

| Weight | Default | Description |
|--------|---------|-------------|
| `advantage_weight` | 0.4 | concept_weighted_advantage の乗数 |
| `energy_to_plan_bonus` | 5.0 | 計画アタッカーへのエネルギー添付ボーナス（need_energy=true） |
| `energy_to_plan_bonus_no_need` | 2.0 | 同上（need_energy=false） |
| `attack_suppress_penalty` | -30.0 | pre-attack action 未完了時のアタック抑制 |

## Search Grid

| Weight | Values |
|--------|--------|
| `advantage_weight` | 0.3, 0.4, 0.5 |
| `energy_to_plan_bonus` | 3.0, 5.0, 7.0 |

3 x 3 = 9 パターン。初回は小規模で安全性を確認。

## Safety

- weights.json がなくても `_DEFAULT_WEIGHTS` にフォールバック
- schema_version が異なっても無視して読み込み
- Kaggle 環境パス (`/kaggle_simulations/agent/data/weights.json`) も探索
- 既存テスト 77/77 全パス
- 30g テスト走行: エラー 0、タイムアウト 0

## Not Changed

| File | Status |
|------|--------|
| `agent/ionos_rules.py` | 変更なし |
| `agent/turn_rule_engine.py` | 変更なし |
| `deck.csv` | 変更なし |
| `submission.tar.gz` | 変更なし（accept まで更新しない） |

## Next Steps

1. `python experiments/weight_search.py --games 30 --patterns 3` で小規模探索実行
2. 安全指標 all 0 の候補を特定
3. 有望候補を 50-200g で追加検証
4. accept 判断後に submission.tar.gz を更新
