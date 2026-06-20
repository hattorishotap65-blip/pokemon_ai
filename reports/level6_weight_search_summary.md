# Level 6: Weight Search Summary

## 1. Level 6 で実装したこと

### 基盤 (PR #21)

| Component | Description |
|-----------|-------------|
| `data/weights.json` | 重み設定ファイル。デフォルト値 = 既存ハードコード値 |
| `experiments/weight_search.py` | 小規模重み探索スクリプト（grid / grid-file / WSL 対応） |
| `agent/policy.py` `_load_weights()` | weights.json 読み込み。未存在時はデフォルトにフォールバック |
| `build_submission.py` | weights.json を submission に含める |

### 設計原則

- weights.json がなくても既存動作と同一
- Kaggle 環境パス対応
- 探索前に weights.json を退避、終了時に必ず復元（finally）
- `--grid-file` でカスタム探索パターンを指定可能
- agent behavior は探索中のみ一時的に変更、採用判断前に復元

## 2. 検証した候補

### Run 001 (PR #22): Grid Search 3x3

| adv_weight | energy_bonus | 30g /game |
|-----------|-------------|-----------|
| 0.3 | 3.0 | 6.27 |
| 0.3 | 5.0 | 4.50 |
| **0.3** | **7.0** | **4.03 (best)** |
| 0.4 | 3.0 | 5.27 |
| **0.4** | **5.0** | **4.87 (baseline)** |
| 0.4 | 7.0 | 5.83 |
| 0.5 | 3.0 | 5.30 |
| 0.5 | 5.0 | 6.87 |
| 0.5 | 7.0 | 6.43 |

### Run 001 50g Validation (PR #23)

| Candidate | 30g | 50g | Decision |
|-----------|-----|-----|----------|
| adv=0.3, e=7.0 | 4.03 (-17%) | 5.54 (+2%) | **not adopted** |

### Run 002 (PR #24): Near-Default 1-Axis Scan

| Changed Weight | Value | 30g /game |
|---------------|-------|-----------|
| **energy_to_plan_bonus** | **4.0** | **4.20 (best)** |
| advantage_weight | 0.35 | 4.43 |
| advantage_weight | 0.45 | 4.53 |
| attack_suppress_penalty | -20.0 | 5.10 |
| attack_suppress_penalty | -40.0 | 5.30 |
| energy_to_plan_bonus_no_need | 3.0 | 5.83 |
| energy_to_plan_bonus | 6.0 | 5.97 |
| energy_to_plan_bonus_no_need | 1.0 | 6.03 |

### Run 002 50g Validation (PR #25)

| Candidate | 30g | 50g | Decision |
|-----------|-----|-----|----------|
| energy=4.0 | 4.20 (-14%) | 4.96 (+11%) | **not adopted** |

## 3. 結論

### 採用候補なし

| Finding | Detail |
|---------|--------|
| 30g 探索の改善は 50g で再現しない | 2 候補とも同パターン |
| デフォルト重みは安定的な最適付近 | 微調整では改善不可 |
| data/weights.json の値は変更しない | adv=0.4, e=5.0, e_no_need=2.0, suppress=-30.0 |
| Level 6 重み探索はいったん完了 | 基盤は維持、将来の探索に使える |

### 30g vs 50g の教訓

| 候補 | 30g | 50g | 乖離 |
|------|-----|-----|------|
| adv=0.3 e=7.0 | -17% | +2% | 19pp |
| e=4.0 | -14% | +11% | 25pp |

**30g は小サンプル分散が大きく、採用判断には不十分。** 50g 以上で検証しないと信頼できない。

## 4. 今後の方針

既存重みの微調整では改善が見込めないため、次の改善は以下のどちらかに進むべき。

### 案 A: 新しい重みパラメータの追加

現在 weights.json に外出しされていないスコアを制御可能にする。

| 候補パラメータ | 対象 | 現在の状態 |
|-------------|------|----------|
| retreat_to_better_attacker_bonus | pivot 判断 | ionos_rules にハードコード (+1100) |
| voltorb_ko_bonus | KO 判断 | effect_engine にハードコード |
| bellibolt_correct_attack_bonus | BB 攻撃補正 | ionos_rules にハードコード (+23) |
| early_game_setup_bonus | 序盤展開 | policy にハードコード |
| late_game_prize_push_bonus | 終盤サイドレース | win_condition にハードコード |

**追加は 1 つずつ行い、必ず Level 5 形式で A/B 検証する。**

### 案 B: ルール構造改善

重みだけではなく、ゲームフェーズや盤面条件で判定を分ける。

| 候補 | 内容 |
|------|------|
| Phase 別スコア | early/mid/late で重みを切り替え |
| Retreat 条件付き評価 | retreat 可能時だけ pivot を評価 |
| Energy 不足補正 | 攻撃不可時のセットアップ優先度 |
| Prize race 連動 | 残りサイド数で攻撃優先度を変動 |

## 5. Level 6 完了判断

| 項目 | 状態 |
|------|------|
| 基盤（weights.json + weight_search.py） | **完了** |
| 探索（Run 001 + Run 002） | **完了** |
| 50g 検証（2 候補） | **完了（両方不採用）** |
| 採用候補 | **なし** |
| data/weights.json | **デフォルト値のまま** |
| agent behavior | **変更なし** |
| **Level 6 status** | **完了** |
