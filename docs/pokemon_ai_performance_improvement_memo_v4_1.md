# ポケカAI 性能改善・診断・実装基盤ロードマップ（第4.1版）

更新日: 2026-07-26  
対象リポジトリ: `hattorishotap65-blip/pokemon_ai`  
対象エージェント: Raging Bolt ex + Teal Mask Ogerpon ex  
位置づけ: 内部実装の整合性・再現性・監視性を先に固め、診断結果に応じて最小の性能改修だけを選ぶための実装・研究メモ

第4版から第4.1版への主要修正:

- Coverage成功側を`confirmed`ではなく`no_failure_observed`へ統一
- Common Random Numbers用seedから`action_id`と`algorithm_version`を除外
- version付きsemantic action IDと乱数源別streamを追加
- Replayの決定性エラーと評価sampling noiseを分離
- Stage 1をスクリーニング専用、Stage 2をhidden state単位の階層推定へ変更
- 敗戦100 + 勝利100をcase-control標本として扱い、全体比率は実勝率で補正
- Human Traceのheuristic pickとactual engine pickを分離
- hidden-state flipとhidden-state推定誤差を分離
- blindな複数人レビューとOOD参照データのleakage防止を追加
- 原因分類の循環を検査するGolden Decision Suiteを追加
- JSONL schemaをversion 4へ更新

---

## 0. 結論

最初に実装するのは、ISMCTS、DAgger、Value Model、POMCPではない。

最優先は、現行エージェントの判断ミスを次の原因へ分解できる **Decision Audit 基盤**である。

```text
1. 探索候補漏れ
2. 盤面評価関数の誤差
3. 複数の評価ロジックが異なる目的を最適化している
4. params.json・コード内default・ハードコード値の不整合
5. hidden state 推定の誤差
6. 人間データにない分布外局面
7. 探索予算不足
8. rollout policy の bias疑い（証拠がある場合のみ）
9. 同価値の別手を誤り扱いしている
10. 学習モデルや探索結果の不確実性を無視している
11. 例外fallbackや探索失敗が観測できていない
12. 乱数系列が局面単位で再現できない
13. 同一盤面への重複探索で計算予算を失っている
14. 戦術的な安全条件を線形スコアが相殺している
15. 相手の次ターン脅威を直接推定していない
16. デッキ構造上の限界を方策だけで解こうとしている
```

その後、原因に応じて次の改修を1つずつ行う。

```text
内部不整合         -> Evaluator Unification / Parameter Contract Audit
再現性不足         -> Deterministic Replay / Common Random Numbers
観測不能な失敗     -> Strict Benchmark Mode / Search Telemetry
候補漏れ           -> 行動タイプ別候補保証
評価誤差           -> 評価特徴改善 / Multi-head Evaluator / afterstate value
hidden state 誤差  -> Weighted Determinization / Public Belief State
分布外             -> Critical-Regret DAgger
重要度不足         -> Regret-weighted ranking
探索予算不足       -> Simple Regret / Sequential Halving
重複計算           -> State Cache / Transposition / 可換行動の重複排除
安全性不足         -> Tactical Safety Layer / 信頼度付き探索上書き
相手脅威の誤差     -> Lightweight Opponent Threat Model
学習値の不確実性   -> SPIBB型 fallback / ensemble gate / calibration
時間方向の原因特定 -> RUDDER型 return decomposition
構造的デッキ限界   -> 限定枠でのDeck–Agent Co-optimization
```

全面的なDeep RL、Full ISMCTS、POMCP、MAP-Elitesなどは、診断結果が必要性を示した場合だけ進める。

---

## 1. 現状認識

現行エージェントは次を組み合わせたデッキ特化型ハイブリッドAIである。

- デッキ固有のヒューリスティック
- エンジンAPIによる浅い先読み
- 線形盤面評価
- hidden state の再サンプリング
- UCB1による追加rollout配分
- Human Trace / Disagreement Review
- Counterfactual Analyzer
- Live Tuning Panel
- Value Modelの実験基盤

現在の主な問題候補は、単純な探索回数不足だけではない。

- 相手の手札・山札・サイドの推定が粗い
- rolloutのleaf評価が正しい保証がない
- ヒューリスティック上位候補から最善手が漏れる可能性がある
- 人間との不一致30%に、等価手と致命的判断が混在している
- AI自身の誤りによって、人間トレースにない盤面へ進む
- 現行UCB1は最終的な1手選択より累積regret寄りの配分である
- 学習モデルを使う場合、低信頼局面で退行する危険がある
- 敗戦直前ではなく、数ターン前の資源判断が真因の場合がある
- `evaluate_state()`、`_eval_search_state()`、`_estimate_action_impact()`、行動別スコアが別々の評価目的を持つ可能性がある
- `params.json`を変更しても、ハードコード値や未使用キーのため実際の順位へ効かない可能性がある
- グローバル乱数列の消費順により、同じ局面でも再現条件がずれる可能性がある
- 例外時に静かにfallbackするため、探索を使った勝率なのかルールベースの勝率なのか判別しにくい
- 異なる行動順で同じ盤面へ到達しても別々に探索し、限られた予算を重複消費する可能性がある
- 返しの確定敗北や後続停止が、手札・盤面加点で相殺される可能性がある
- 相手の具体的な手札推定より、次ターンのKO・gust・進化打点を直接予測した方が実用的な場合がある
- 攻撃回数・再装填速度の差がデッキ構造に由来する場合、方策改善だけでは上限がある

---

## 2. 最終目的

目的は、人間との完全一致率を上げることではない。

```text
勝敗へ影響する最初の重大な判断ミスを特定し、
その原因へ最小の変更を当て、
複数の相手に同じ方策で改善する。
```

### 改善対象となる判断

- 確定KOを逃す
- Bossの使用時機を誤る
- 攻撃後に次のアタッカーが止まる
- エネルギーを過剰消費する
- 回収対象を誤る
- ベンチ枠を低価値なポケモンで埋める
- Retreatすべき局面で残る
- Retreat不要な局面で資源を使う
- 相手の返しのKOを過小評価する
- 序盤の盤面展開が遅れ、総攻撃回数を失う

### 改善対象としないもの

- 人と違うが期待価値がほぼ同じ手
- 相手agent名を見て専用分岐する実装
- 少数ベンチマークにだけ勝つパラメータ
- 一致率だけを上げ、勝率やregretが改善しない変更

---

# Part I: 評価基盤

## 3. Phase 0 — Baselineの固定

### 3.1 固定する情報

```text
baseline_commit
agent_version
deck_hash
params_hash
engine_version
python_version
random_seed_set
hidden_state_seed_set
benchmark_opponents
timeout_limit
```

エージェント、デッキ、パラメータ、評価相手、エンジンを同時に変更しない。

### 3.2 A/Aテスト

A/Aを次の2種類へ分ける。

```text
Determinism A/A
  同一Snapshot・artifact・seedを別プロセスで反復する
  legal actions、候補値、選択、結果の完全一致が必須

Experiment-pipeline A/A
  同一artifactをA/Bへランダム割付し、独立game seedと先後入替ペアで比較する
  A/Bラベル効果が0付近か、集計・割付・CIの偏りを確認する
```

前者の差はsampling noiseではなく基盤エラーである。後者のgame間変動と、独立hidden-state / rollout標本による評価変動をsampling uncertaintyとして測る。

記録する指標:

| 指標 | 目的 |
|---|---|
| Determinism mismatch rate | 0であること |
| A/Bラベル別の勝率差 | 同一artifact間の差が0付近か |
| 先攻・後攻入替ペア差 | 先後の偏りと相殺状況 |
| 同一bundle出力一致率 | 再現性確認 |
| paired win/loss/tie | 対応あり比較 |
| 1手p50/p95/p99時間 | 性能基準 |
| ゲーム全体p50/p95時間 | Kaggle制限への余裕 |
| 探索fallback率 | 探索が実際に機能しているか |
| rollout失敗率 | 評価値の信頼性 |
| candidate count | 候補数の変動 |

### 3.3 Common Random Numbers

旧版と新版で可能な限り共通化する。

- 初期山札順
- サイド配置
- 先後
- 相手側の乱数系列
- hidden stateの乱数系列
- rollout seed

解析は独立2標本だけでなく、同一seedペアの差を使う。

ただし現行engine APIが乱数stream注入を提供しない範囲では「完全なCRN」と表現しない。まず共有できるhidden-stateサンプルとrollout側乱数を固定し、engine内部乱数はReplay可能性とAPI制約を明記する。完全CRNのために`libcg.so`変更が必要なら、Decision Audit PRとは別の明示承認対象にする。

### 3.4 固定League

最低限、戦い方の異なる複数相手を評価に使う。

```text
top_lucario_1084
dragapult
megastarmie
現行Raging Bolt
過去の安定Raging Bolt
```

Leagueは評価と過適合検出にのみ使う。実戦方策は相手名・デッキ名を入力にしない。

---

## 4. Phase 1 — Decision Audit

### 4.1 目的

現在の判断ミスが次のどこにあるかを判定する。

```text
A. 最善手が探索候補に入っていない、またはCoverageを確認できていない
B. 候補には入っているが評価関数が誤る
C. hidden stateによって最善手が変わる
D. AIが人間ログにない盤面へ到達する
E. rollout予算を増やすとvarianceが下がり判断が改善する
F. rollout評価に系統的なbiasが疑われる
G. 人間と違うが等価な手を誤りとして数えている
H. 学習モデルの高確信が実際には校正されていない
```

`rollout_bias_suspected`は、単にseed数を増やして値が変動しただけでは付与しない。biasは後述する複数の独立した証拠が揃った場合だけ疑う。

### 4.2 対象データ

初回診断:

```text
敗戦 100ゲーム
勝利 100ゲーム
```

敗戦だけを見ると、勝利時にも発生する無害な乖離を重大と誤認するため、勝利対局も比較する。

この200件は勝敗を1:1に固定したcase-control標本であり、そのまま全対局の原因構成比にはできない。まず`P(cause | loss)`と`P(cause | win)`を別々に出す。全体推定が必要なら、抽出前に凍結した未選別評価バッチの実敗率`p_loss`を使い、次で復元する。

```text
P(cause)
  = p_loss * P(cause | loss)
  + (1 - p_loss) * P(cause | win)
```

局面数の多い対局を過大評価しないよう、集計単位とbootstrapの最上位クラスタはgameとする。判断単位の率も併記する場合は、1ゲーム当たりの重みを固定する。生の200件比率、勝敗別比率、母集団補正比率を混同せず別フィールドで出力する。

対象は原則としてMAINコンテキスト。ただし、以下は選択コンテキストも追跡する。

- Energy Retrievalの回収対象
- Ultra Ball等のdiscard対象
- Bellowing Thunderのエネルギー消費
- Bossの対象
- Retreat先
- サーチ対象

### 4.3 Coverage Probeと二段階の反実仮想評価

Candidate Coverageは上位候補だけを評価しても確認できない。そこで、通常のStage 1とは別に、全合法手を粗く見る **Coverage Probe** を設ける。

#### Coverage Probe — 全合法手の粗い候補確認

```text
候補: 全合法手
hidden state: 1種類
rollout seed: 1種類
```

目的は全合法手の精密順位を決めることではなく、上位候補集合の外に明らかに有望な手が存在するかを検出すること。

Coverage判定は二値にせず、次の3値とする。

```text
no_failure_observed
  Coverage Probe上の有望手がStage 1候補へ含まれ、独立seedによる追加確認でも
  候補漏れが観測されない。候補漏れが存在しないことの証明とは扱わない

observed_failure
  Coverage Probeで候補外の有望手が見つかり、対応あり再評価または人間確認でも優位が残る

unknown
  Probeが失敗、評価差がノイズ範囲内、合法手数・時間制約で全手を確認できない、
  または粗い1サンプルだけでは判定不能
```

Coverage Probe単独の順位を最終的な最善手とはみなさない。Probe単独では原則`unknown`とし、`observed_failure`候補は独立seedのStage 2または人間レビューへ送る。

MAIN以外の複数選択コンテキストでは、「合法手」は単一optionではなくoptionの組合せになる場合がある。組合せを全列挙できない場合は、単一option coverageと完全selection coverageを分け、後者を自動的に`no_failure_observed`へしない。

現行`_engine_search_choose()`が`maxCount != 1`を探索対象外にする場合、Ultra Ball等の2枚discardを既存searchの単一option評価で代用しない。`search_step()`へ渡せる合法な選択集合を作れるまでは、複数選択contextの完全selection coverageを`unknown`とする。

#### Stage 1 — 軽量スクリーニング

```text
候補: 最終selected actionを必ず含む最大3手
hidden state: 4種類
rollout seed: 1種類
最大: 12評価 / 判断
```

各候補は同一のhidden state・seedペアで評価し、候補間の**対応差分**を保存する。

現行engine searchがheuristic上位3手より広い候補集合から選ぶ場合があるため、単純なheuristic top 3だけを使わない。候補優先順位は次とする。

```text
1. final selected action（必須）
2. actual engine pick（finalと異なる場合）
3. heuristic ranking上位から重複なしで補充
```

Human Trace手とCoverage候補はStage 1へ追加して上限を超えさせず、Stage 2送付理由として扱う。Stage 2でも最大3手を守り、`selected action > Golden / observed_failure候補 > human action > heuristic順位`の事前優先順で採用する。除外した有望候補は`excluded_priority_candidates`へ理由付きで保存し、その比較は`unknown`とする。

Stage 1の実効標本数はhidden state 4個にすぎないため、正式な信頼区間や原因確定には使わない。`ci_status=insufficient_samples`として、Stage 2へ送るスクリーニングに限定する。

#### Stage 2 — 重要局面の再評価

対象条件:

- 推定regretが大きい
- 上位2手が僅差
- hidden stateで最善手が変わる
- 人とAIが不一致
- 敗戦経路上にある
- 確定KO、Boss、Retreat、大量エネルギー消費を含む
- Coverage Probeで候補漏れが疑われる
- 探索fallbackが発生した

さらに、Stage 1の偶然の高値による選択バイアスを測るため、**全Stage 1局面の5〜10%をランダム対照としてStage 2へ送る**。ランダム対照は勝敗、序盤/中盤/終盤、context、合法手数、人間ログ有無で層別し、固定seedで抽出する。

```text
候補: 上位2〜3手。Coverage失敗候補は最大3手の枠内へ必ず含める
hidden state: 8種類
rollout seed: 2種類
最大: 48評価 / 判断を目安とする
```

`stage2_reason`は複数値を許可し、次から記録する。

```text
high_regret
close_top2
hidden_flip
human_disagreement
loss_path
coverage_probe
random_control
```

`random_control`群と選択群の差を比較し、Stage 1によるregret・不確実性の過大推定を補正する。

Stage 2の確認用hidden state seed groupは、Stage 1のトリガー判定に使ったseed groupと独立にする。8 hidden states × 2 seedsを独立16標本とは扱わず、hidden stateをクラスタとして、hidden state間分散と同一hidden state内seed分散を分離する。

Stage 2抽出は、事前定義triggerに該当する局面を包含確率1、非trigger局面を層別random control率`q_h`で抽出する二相設計にする。`stage2_inclusion_probability`と`stage2_selection_source=trigger/random_control/both`を保存し、全Stage 1母集団へ戻す集計は逆確率重みを使う。選択群とrandom controlの単純差だけを「補正済み」と呼ばない。

hidden stateクラスタが8個では局面単位CIは不安定である。Stage 2のdecision-level CIは`ci_status=exploratory_small_cluster`とし、単独で原因確定へ使わない。重大な1局面を確定する必要がある場合は、独立hidden stateを事前規定数まで増やす確認run、Golden根拠、またはblind reviewを要求する。複数gameの集計CIはgame-clusterを最上位にする。

### 4.4 保存スキーマ

Stage 1とStage 2は同じJSONLオブジェクトへ追記更新せず、stage別のimmutable recordとして保存する。Stage 2は`parent_stage1_record_id`で元記録を参照し、再実行・並列処理でStage 1の証跡を上書きしない。

```json
{
  "schema_version": 4,
  "record_type": "decision_audit",
  "audit_record_id": "",
  "parent_stage1_record_id": null,
  "game_id": "",
  "state_id": "",
  "turn": 0,
  "context": "MAIN",
  "baseline_commit": "",
  "agent_artifact_hash": "",
  "engine_version": "",
  "engine_artifact_hash": "",
  "card_table_hash": "",
  "attack_table_hash": "",
  "deck_hash": "",
  "params_hash": "",
  "params_artifact_id": "",
  "game_seed": 0,
  "hidden_state_seed_group": "",
  "confirmation_seed_group": null,
  "agent_rng_state_ref": "",
  "materialized_hidden_samples_ref": "",
  "crn_scope": {
    "hidden_sample_crn": false,
    "python_rollout_crn": false,
    "engine_internal_crn": false
  },
  "replay_bundle_id": "",
  "execution_mode": "BENCHMARK",
  "evaluator_path_id": "",
  "parameter_contract_version": "",
  "algorithm_version": "",
  "action_id_schema_version": "semantic-v1",

  "heuristic_pick": "",
  "actual_engine_pick": "",
  "selected_action": "",
  "selected_action_source": "",
  "human_action": null,
  "legal_actions": [],
  "heuristic_ranking": [],
  "engine_search_candidates": [],
  "candidate_actions": [],

  "candidate_source": {
    "selected_action_mandatory": [],
    "actual_engine_pick": [],
    "heuristic_top_k": [],
    "forced_attach": [],
    "action_type_quota": [],
    "human_action_injected_for_analysis": [],
    "excluded_priority_candidates": []
  },

  "coverage_probe": {
    "executed": false,
    "evaluated_legal_actions": [],
    "unevaluated_legal_actions": [],
    "probe_best_actions": [],
    "coverage_status": "unknown",
    "candidate_coverage_failure": null,
    "coverage_reason": ""
  },

  "stage": "stage1",
  "stage2_reason": [],
  "is_random_control": false,
  "stage2_selection_source": null,
  "stage2_inclusion_probability": null,
  "sampling_stratum": "",
  "population_weight": null,

  "normalization": {
    "normalization_version": "",
    "determinism_mismatch_rate": 0.0,
    "sampling_noise_location": null,
    "sampling_noise_scale": null,
    "sampling_noise_method": null,
    "normalization_stratum": null,
    "comparison_standard_error": null,
    "terminal_value_handling": "separate_terminal_class"
  },

  "action_values": {
    "action_id": {
      "raw_value": 0.0,
      "normalized_value": null,
      "raw_values": [],
      "normalized_values": [],
      "raw_value_mean": 0.0,
      "raw_value_std": 0.0,
      "raw_value_min": 0.0,
      "raw_value_max": 0.0,
      "raw_value_median": 0.0,
      "raw_value_q10": 0.0,
      "raw_value_q90": 0.0,
      "normalized_value_mean": null,
      "normalized_value_std": null,
      "normalized_value_min": null,
      "normalized_value_max": null,
      "best_action_probability": null,
      "rollout_success_count": 0,
      "rollout_error_count": 0,
      "hidden_state_seed_pairs": [],
      "hidden_state_values": [
        {
          "hidden_state_sample_id": "",
          "seed_values": [
            {
              "rollout_seed_id": "",
              "raw_value": 0.0,
              "normalized_value": null,
              "success": true,
              "error_type": null
            }
          ],
          "raw_value_mean": 0.0,
          "raw_value_std": 0.0
        }
      ]
    }
  },

  "paired_comparisons": [
    {
      "alternative_action": "",
      "selected_action": "",
      "paired_value_differences": [],
      "paired_mean_gap": 0.0,
      "paired_gap_ci_low": null,
      "paired_gap_ci_high": null,
      "paired_normalized_differences": [],
      "paired_normalized_gap_ci_low": null,
      "paired_normalized_gap_ci_high": null,
      "normalized_regret": null,
      "estimated_regret": 0.0,
      "paired_value_gap": 0.0,
      "alternative_improvement_probability": null,
      "ci_status": "insufficient_samples",
      "ci_method": null,
      "confirmation_seed_group": null
    }
  ],

  "hidden_state_flip_rate": 0.0,
  "hidden_state_error_status": "unknown",
  "evaluation_uncertainty": {
    "total_std": 0.0,
    "between_hidden_state_variance": 0.0,
    "within_hidden_state_seed_variance": 0.0,
    "interval_low": 0.0,
    "interval_high": 0.0
  },
  "search_budget_sensitivity": {},

  "rollout_bias_evidence": {
    "rollout_bias_suspected": false,
    "systematic_human_rank_disagreement": null,
    "observed_outcome_calibration_gap": null,
    "horizon_rank_reversal": null,
    "rollout_policy_sensitivity": null,
    "terminal_subproblem_disagreement": null,
    "evidence_count": 0
  },

  "ood_evidence": {
    "nearest_neighbor_distance": null,
    "k_neighbor_mean_distance": null,
    "feature_out_of_range_count": 0,
    "context_support_count": 0,
    "action_type_support_count": 0,
    "reference_corpus_version": "",
    "distance_scaler_version": "",
    "same_game_excluded": true,
    "future_data_excluded": true,
    "ood_status": "unknown"
  },

  "human_label": null,
  "human_intent": null,
  "human_review_blinded": null,
  "human_reviewer_count": null,
  "human_reviewer_agreement": null,
  "equivalent_action_group": [],

  "persistence": {
    "first_persistent_critical_divergence_candidate": false,
    "observed_persistence": null,
    "counterfactual_persistence": null,
    "human_confirmed_persistence": null,
    "later_recovery_probability": null
  },

  "cause_classification": null,

  "final_result": "",
  "final_prize_diff": 0,
  "search_telemetry": {
    "attempts": 0,
    "successes": 0,
    "fallbacks": 0,
    "rollout_errors": 0
  },
  "decision_runtime_ms": 0,
  "runtime_ms": 0,
  "game_runtime_ms": 0
}
```

`candidate_coverage_failure`は`observed_failure=true`、`no_failure_observed=false`、`unknown=null`の派生値とし、3値の`coverage_status`を正本とする。空文字と0が「未計測」を意味しないよう、実装スキーマではoptional値を`null`にし、必須性と単位をJSON Schemaで固定する。

フィールドの導入順も固定する。PR1-AのStage 1 recordではraw値とpaired raw differencesだけを記録し、normalized値・CIは`null`。PR1-Bでsampling-noise normalizationを導入する。PR1-CはStage 1を更新せず、独立確認標本、paired CI、`alternative_improvement_probability`を新しいStage 2 recordへ保存する。`human_confirmed_persistence`はPR2のblind review完了までは`null`とする。

PR2結果は既存`decision_audit` recordへ書き戻さず、append-onlyのcompanion recordとして保存する。

```json
{
  "schema_version": 4,
  "record_type": "human_review",
  "human_review_record_id": "",
  "audit_record_ids": [],
  "review_protocol_version": "",
  "pass1_labels": [],
  "pass2_labels": [],
  "reviewer_agreement": null,
  "human_confirmed_persistence": null
}
```

```json
{
  "schema_version": 4,
  "record_type": "cause_classification",
  "classification_record_id": "",
  "audit_record_ids": [],
  "human_review_record_ids": [],
  "candidate_causes": [],
  "primary_cause": "unknown",
  "cause_confidence": 0.0,
  "cause_evidence": {},
  "classification_version": ""
}
```

レポート生成時だけ`joined_view_version`付きのmaterialized viewを作る。元のStage 1 / Stage 2、human review、classification record IDを全て残し、再分類で過去ラベルを上書きしない。

上の`decision_audit`例にあるhuman / cause関連フィールドはjoined view上の投影先を示す。raw decision recordでは省略または`null`とし、PR2値を後から書き込まない。

### 4.5 対応差分によるRegret信頼区間

候補ごとに独立した信頼区間を作り、その差を取らない。同一のhidden state・seedペアで得た次の差分を直接扱う。

```text
paired_difference_i
  = alternative_value_i - selected_value_i
```

保存値:

```text
paired_value_differences
paired_mean_gap
paired_gap_ci_low
paired_gap_ci_high
paired_normalized_gap_ci_low
paired_normalized_gap_ci_high
```

`paired_comparisons`にはselected action対各alternativeの1要素を保存し、複数alternativeを平均して1つの差へ潰さない。

Stage 1はhidden stateが4個しかないため、信頼区間を出さず`ci_status=insufficient_samples`とする。Stage 2は次の階層を保ったnested / cluster bootstrapを第一選択とする。

```text
game
  └─ decision
      └─ hidden state
          └─ rollout seed
```

hidden stateを復元抽出し、その内側でseedを復元抽出する。複数判断・複数対局を集計するCIはgameを最上位クラスタとし、同一対局内の判断を独立標本と数えない。`between_hidden_state_variance`と`within_hidden_state_seed_variance`は分けて報告する。hidden stateが8個のStage 2局面単独ではbootstrapのtailを信用せず`exploratory_small_cluster`とする。分布仮定が妥当で十分なクラスタ数がある場合のみ、階層モデル等を代替としてよい。

Stage 1で選ばれた局面のStage 2推定には独立した確認用seed groupを使う。`alternative_improvement_probability`とCIはこの確認群から計算し、選択に使った標本との二重利用を避ける。

### 4.6 評価値の正規化

通常局面の数百点と、終局時の`±1,000,000`を同じregret分布へ直接混ぜない。

各値について次を保存する。

```text
raw_value
normalized_value
normalized_regret
paired_value_gap
```

完全に同一のReplay Bundle、実装、seedを再実行する決定性A/Aでは、差は理論上0でなければならない。ここで非0差や出力不一致があれば`determinism_mismatch`であり、評価ノイズとして吸収せずReplay基盤の失敗として扱う。

正規化に使うsampling uncertaintyは、独立したhidden-state / rollout seed groupによるsplit-halfまたはnested resamplingで測る。同一Replayの再実行差とは分けて保存する。hidden-state間の対応差変動と、同一hidden state内のrollout seed変動を単一分散へ潰さない。

例:

```text
normalized_gap
  = paired_raw_gap / max(comparison_standard_error, epsilon)

comparison_standard_error
  = sqrt(
      between_hidden_state_variance / H
      + within_hidden_state_seed_variance / (H * S)
    )
```

分散成分はcontext・turn帯等の事前定義stratum別にpilotから推定し、少数局面には階層的shrinkageまたは保守的な上限を使う。全局面共通の単一scaleはfallbackとしてのみ使い、どのscaleを使ったか保存する。raw gapも必ず併記し、normalized gapだけで効果量を表現しない。

終局勝敗は通常の連続評価とは別クラスとして扱い、確定勝利・確定敗北が通常局面のregret統計を歪めないようにする。正規化方式にはversionを付ける。

`determinism_mismatch_rate`の合格条件は0とする。分散成分モデル、normalization stratum、重大判定閾値、確率閾値はpilotデータで決めて凍結し、最終評価データを見て後から調整しない。

### 4.7 rollout biasの判定

seed数を増やして分かるのは主としてvarianceであり、それだけでbiasとは断定しない。

`rollout_bias_suspected=true`は、次のうち複数の証拠が同じ方向を示す場合だけ付与する。

- 人間評価との系統的な順位差
- 実際の後続結果との校正差
- horizon変更による順位反転
- rollout policy変更への過度な感度
- terminalまで正確に評価できる小規模局面との不一致

単発の不一致は`evaluation_variance`または`unknown`として扱う。

### 4.8 OODの根拠

単一のスカラー`ood_score`だけで判定しない。最低限、次を個別に保存する。

```text
nearest_neighbor_distance
k_neighbor_mean_distance
feature_out_of_range_count
context_support_count
action_type_support_count
```

距離指標とsupport countが矛盾する場合は`ood_status=unknown`とし、自動的にDAgger対象へ送らない。

参照コーパス、特徴量、距離の標準化係数にはversionを付ける。対象局面と同一game、対象判断より未来のログ、評価対象splitを参照コーパスから除外し、距離スケーラは参照側だけでfitする。OODは「学習分布から遠い」という記述であり、それだけで判断ミスの原因とは断定しない。誤差率との関連は同じcontext・turn帯・合法手数等で層別またはマッチングして確認する。

OOD算出前に、PR1-B0で次のartifactを凍結する。

```text
ood_reference_manifest.json
reference_corpus_hash
source_game_split_ledger
feature_schema_version
distance_scaler_artifact
distance_metric_version
context別support / distance閾値
leakage_audit_report
```

閾値は参照側pilotだけで決める。これらが揃わない局面はOODを推測せず`ood_status=unknown`とする。

### 4.9 Persistenceの分離

次の3種類を分けて記録する。

```text
observed_persistence
  実際の対局経路で価値低下または攻撃停止が継続したか

counterfactual_persistence
  代替行動との対応rolloutで差が後続ターンにも残ったか

human_confirmed_persistence
  人間レビューで重大かつ継続的な判断差と確認されたか
```

スキーマ名は一貫して、

```text
first_persistent_critical_divergence_candidate
```

を使用する。

### 4.10 計算量と予算gate

MAIN判断数を`D`、判断`d`の合法手数を`L_d`、Stage 2対象判断数を`D2`とすると、rollout評価回数の上限目安は次になる。

```text
Stage 1        = 3 * 4 * 1 * D              = 12D
Coverage Probe = Σ L_d * 1 * 1              = ΣL_d
Stage 2        = 3 * 8 * 2 * D2             = 48D2
Total          = 12D + ΣL_d + 48D2
```

複数選択contextの`L_d`は単一option数ではなく合法な完全selection数を意味する。完全selectionを列挙できないcontextはこの見積もりとcoverage率から分け、`unknown`として件数を報告する。

例として200ゲーム、1ゲーム平均25 MAIN判断、平均合法手8、Stage 2率15%なら、約136,000 rollout評価となる。単一評価の実測p50が20msなら直列約45分、100msなら約3.8時間であり、Snapshot I/Oと再試行時間は別途加算する。

実装前pilotで単一rolloutのp50 / p95、JSONLとReplay Bundleの1判断当たり容量、Coverage Probe失敗率を測り、次を固定する。

- 1ゲーム・1判断・全runの時間上限
- Stage 2送付率の上限。ただしrandom control 5〜10%は削らない
- Coverageの合法手上限と、打ち切り時`unknown`にする条件
- rollout error / fallback / replay invalidによるrun無効条件
- 並列化時もgame-clusterとseed対応を壊さないworker割当

時間超過時に評価できなかった候補を低価値として扱わず、`unevaluated_legal_actions`と`unknown`へ送る。

---

## 5. 評価指標

### 5.1 主指標

| 指標 | 意味 |
|---|---|
| Mean Normalized Critical Regret | 独立標本で測ったsampling noiseで正規化した重大局面の平均regret |
| P90 Normalized Critical Regret | 最悪側10%の判断品質 |
| Paired Gap CI | 同一hidden state・seedで比較した対応差分の信頼区間 |
| Fatal Mistakes / Game | 致命的判断数 |
| Candidate Coverage Status | `no_failure_observed / observed_failure / unknown`の構成比 |
| Hidden-state Flip Rate | hidden stateで最善手が変わる割合 |
| Human–Rollout Rank Agreement | 人間判断とrollout順位の一致 |
| First Persistent Critical Divergence Candidate | 最初の継続的重大乖離候補 |
| Observed / Counterfactual / Human-confirmed Persistence | 継続性の根拠別評価 |
| OOD Evidence | 距離・範囲外・support countの内訳 |
| Stage 2 Random-Control Gap | 選択局面とランダム対照局面の差 |
| Rollout Bias Evidence Rate | biasを疑う複数証拠が揃った割合 |
| Recovery Rate | 乖離後に立て直した割合 |
| Win Rate | 最終性能 |
| p95 Decision Time | 1手の実行時間 |

単純な人間行動一致率は補助指標へ下げる。

### 5.2 First Persistent Critical Divergence Candidate

診断段階では「不可逆」と断定しない。

候補条件の例:

```text
paired_normalized_gap_ci_low > preregistered_normalized_margin
alternative_improvement_probability >= preregistered_probability_threshold
observed_persistence == true または counterfactual_persistence == true
```

`delta`や`normalized_noise_margin`は固定の生点ではなく、独立標本で観測したsampling noiseを基準にpilotで決める。最終的な重大判定には`human_confirmed_persistence`を別途記録する。

---

# Part II: 実装基盤の整合性・再現性・安全性

このPartはDecision Audit前に実施するが、**baselineの判断経路を変更しない監査・観測機能だけ**に限定する。

```text
Phase F0-A: Parameter Contract調査 + Strict Telemetry
Phase F0-B: Observation Snapshot + Deterministic Replay
Phase F0-C: 評価経路マトリクス + shadow比較
Phase F0-D: Golden Decision Suite
```

Evaluator Unification、Search Cache、Tactical Safety、Multi-head Evaluator、Opponent Threat Model、Deck–Agent Co-optimizationは、PR2の診断結果を確認するまで実装しない。

---

## 6. Evaluator Path Matrix / Shadow Comparison — 統合前の評価経路監査

### 6.1 目的

Decision Audit前に評価関数を統合するとbaselineが変わり、診断対象そのものが動く危険がある。そのため最初は統合を行わず、既存経路をそのまま観測する。

対象:

```text
evaluate_state()
_eval_search_state()
_estimate_action_impact()
各行動のヒューリスティックスコア
Value Modelの特徴量・出力
Counterfactual Analyzerの評価値
```

### 6.2 評価経路マトリクス

各経路について次を一覧化する。

- 呼び出し元と使用コンテキスト
- 入力状態とhidden情報の扱い
- 特徴量
- 符号・単位・スケール
- terminal値
- params参照先
- fallback条件
- 最終行動への影響

### 6.3 Shadow Comparison

本番の選択には影響させず、同一Observation Snapshotに対して各評価経路をshadow実行し、次を記録する。

```text
path_value
path_action_ranking
ranking_disagreement
scale_ratio
terminal_handling_difference
feature_presence_difference
```

### 6.4 Audit後の分岐

PR2で評価経路の不整合が主要原因と確認された場合にだけ、Evaluator Unificationを別PRで実施する。

統合時の候補構造:

```text
Observation / State
  -> extract_common_features()
  -> evaluate_feature_heads()
  -> aggregate_value()
  -> evaluate_action_afterstate()
```

ただし、これはAudit後の候補でありPR0-Cでは実装しない。

### 6.5 完了条件

- 現行行動が一切変わらない
- 評価経路マトリクスが作成される
- 同一局面の順位不一致・スケール不一致が再現可能に保存される
- 統合候補とリスクは示すが、共通Feature Schemaへの移行は行わない

### 6.6 既存機能の再利用境界

| 既存機能 | 再利用するもの | 再利用しないもの |
|---|---|---|
| engine search | 実候補、実採用手、既存rollout入口 | live判断中の追加audit rollout |
| Human Trace | 人間行動、意図、disagreement候補 | `policy.rank()`由来`ai_pick`を実engine採用手とみなすこと |
| Disagreement Review | review UI、ラベル保存 | AI出所・結果を見せたままのPass 1 |
| Counterfactual Analyzer | persistence候補、レポート生成、既存分類補助 | 現行evaluatorだけによるoracle生成 |
| 既存feature抽出 | OOD距離用のversion付き表現 | OOD距離だけによる原因確定 |

不足するSnapshot、seed、hidden samples、engine候補は新規のside-outputとして追加する。既存ログに存在しない値を推測で補完せず、`unknown`または`not_replayable`とする。

---

## 7. Parameter Contract Audit — パラメータ有効性監査

### 7.1 目的

`params.json`、コード内default、ハードコード値、Runtime Overrideの関係を明示し、変更しても実際の判断へ効かないパラメータを排除する。

### 7.2 全キーの分類

```text
ACTIVE       実際に参照され、本番判断へ影響する
EXPERIMENTAL 実験時だけ使用する
DEPRECATED   廃止済みで互換目的に残す
UNUSED       参照されないため削除候補
SHADOWED     ハードコードや別キーに上書きされる
DUPLICATE    同じ意味の別パラメータが存在する
```

### 7.3 自動監査

- JSONキーがコードから参照されるか
- コードで参照するキーがJSONまたは明示defaultを持つか
- 同じ意味・単位の重複キーがないか
- ハードコードされた行動スコアがパラメータと競合しないか
- Runtime Override適用前後で対象局面の順位が変わるか
- engine search、fallback、Live Tuning Panelで同じ有効値が使われるか
- default値とドキュメントが一致するか

### 7.4 成果物

```text
parameter_contract.json
parameter_audit_report.md
unused_parameter_list.json
hardcoded_score_inventory.json
```

各パラメータへ次を持たせる。

```json
{
  "name": "impact_crispin_bolt_bonus",
  "status": "ACTIVE",
  "type": "number",
  "unit": "evaluation_point",
  "default": 200,
  "min": 0,
  "max": 1000,
  "used_by": ["fallback_action_impact"],
  "runtime_override": true,
  "description": "..."
}
```

### 7.5 完了条件

- 未使用・競合・重複パラメータが一覧化される
- Live Tuning Panelで変更した値がどの評価経路へ効くか追跡できる
- 契約外・型不一致・範囲外の値をshadow検出し、現在の実挙動とともに報告できる

PR0-Aでは契約違反をreject、clamp、default置換しない。runtime validationの強制は挙動変更になり得るため、PR2後に別PRと回帰テストを通して導入する。

---

## 8. Observation Snapshot / Deterministic Replay — 局面単位の完全再現

### 8.1 現在の問題

モジュール全体のグローバル乱数列は、前の局面でのrollout回数、例外、候補数によって消費位置が変わる。固定seedでも局面単位の再現性は保証されない。

現行Raging Boltのmodule global `_rng`は判断を跨いで消費されるため、後からstable seedを計算するだけでは元判断を再現できない。判断直前の`_rng.getstate()`と、実際に生成したhidden-state配列を保存するか、audit経路を局所RNGへ移す必要がある。

また、`battle_start()` / `search_step()`等がengine内部seedやrandom tapeの注入を受け付けない場合、Python側だけで対局全体の完全CRNを保証できない。PR0-Bの最初にAPI capabilityを記録し、`python_rollout_crn`、`hidden_sample_crn`、`engine_internal_crn`を別々にsupported / unsupportedで示す。

### 8.2 Observation Snapshot

Replay時にエンジン内部状態の再構築へ依存しすぎないよう、意思決定時点の観測をversion付きで保存する。

```text
observation payload
legal actions
select context
public action history
turn / player
state hash
serialization version
```

Snapshotは本番方策の入力を変えず、診断・再生用のside outputとして追加する。

### 8.3 seed設計

```text
comparison_sample_seed = stable_hash(
  base_seed,
  game_id,
  state_hash,
  turn,
  select_context,
  hidden_state_sample_id,
  rollout_index,
  random_source_stream,
  sampling_protocol_version
)
```

`action_id`と`algorithm_version`は比較条件から外す。これらをseedへ含めると候補間・実装間で異なる乱数を引き、Common Random Numbersにならない。両者は結果のmetadataとして保存する。

hidden stateは候補評価前に一度生成してsample IDを固定し、全候補へ同じサンプルを渡す。山札、効果、相手方策など乱数源ごとにstreamを分け、ある候補だけが乱数を1回多く消費しても別の乱数源がずれないようにする。可能なら`random_source_stream + event occurrence`で参照する固定random tapeをReplay Bundleへ保存する。

Pythonの組み込み`hash()`はプロセスごとに変わり得るため使わず、canonical serializationした入力のSHA-256等から固定整数を生成する。

`action_id`はraw option配列の順番ではなく、version付きsemantic keyにする。最低限、select context、option type、解決済みcard / attack ID、source / target areaと安定した対象ID、複数選択payloadを含める。複数選択はルール上可換と証明できるcontextだけcanonical sortし、順序で結果が変わり得る場合は順序付きsequenceとして保存する。表示順や一時的なoption indexはmetadataに残してもよいが、同一性判定の主キーにはしない。

### 8.4 保存するReplay Bundle

```text
observation snapshot
legal actions
heuristic ranking / heuristic pick
actual engine-search candidates / actual engine pick
final selected action
state hash
all seeds
hidden-state sample IDs
agent RNG state before decision
materialized hidden-state samples
random tape / random-source stream version
engine version / engine artifact hash
agent commit / packaged agent artifact hash
card table hash / attack table hash
deck hash
params hash + 実際のparams payloadまたはimmutable artifact ID
serialization / action-ID / sampling protocol versions
exception / fallback情報
```

Human Traceの既存`ai_pick`が`policy.rank()`由来なら、実際のengine search採用手として読み替えない。新規ログでは`heuristic_pick`、`actual_engine_pick`、`final_selected_action`を分離する。full observation、game / state ID、engine候補、rollout結果を持たない旧ログはHuman Trace・Disagreementの参考には使えるが、完全ReplayやDecision Auditの母集団には含めない。

### 8.5 必須テスト

- 同一bundleを別プロセスで10回再生し、legal actions、hidden state、候補順、候補値、最終選択が完全一致する
- 決定性A/Aの`determinism_mismatch_rate`が0である
- 元対局で実際に選択された行動をReplayが再現する
- 旧版と新版が同じhidden state・山札順を使う
- Candidate AとBを同じ乱数条件で比較できる
- 例外が発生した局面だけ単独再生できる
- モジュールglobal RNGを使用する箇所を列挙し、audit経路は局所RNGまたは保存済みrandom tapeだけを使用する

このgateを通らないSnapshotはregret・coverage・原因分類へ進めず、`replay_invalid`として別集計する。

engine内部乱数を注入・復元できない場合は、その範囲の完全一致テストを合格扱いにしない。Python側で共有できる条件だけを`partial_crn`として明示し、`full_crn`という名称を使わない。

### 8.6 Baseline Fingerprint Gate

Decision Auditは本番意思決定の後または完全オフラインで動かし、追加rolloutをlive選択経路へ入れない。凍結Snapshotコーパスについて、audit無効baselineとinstrumentation有効版を同じbundleで比較する。

合格条件:

- 全select contextで最終action IDが100%一致
- legal action集合、heuristic順位、実engine search候補と採用手が、観測追加前後で一致
- audit無効時に乱数状態、fallback、例外処理、候補配列の順序を変えない
- `main.py`、`params.json`、`deck.csv`と提出artifactの挙動fingerprintが基準と一致
- audit無効時のp95 overheadがpilotで定めた上限内

action不一致が1件でもあれば、性能差として評価せずinstrumentation regressionとしてPRを止める。JSONLの追加・欠損・書込失敗は本番の合法手選択を変えてはならない。

---

## 9. Strict Benchmark Mode — 例外を隠さない実行モード

### 9.1 モード分離

```text
PRODUCTION
  例外を記録し、安全な合法手へfallback

BENCHMARK
  fallbackを記録し、閾値超過時は比較結果を無効扱い
  未分類例外は試合失敗として数える

DEBUG
  observation・seed・候補・tracebackを保存
  例外を再送出して停止
```

### 9.2 必須Telemetry

```text
search_attempt_count
search_success_count
search_fallback_count
search_override_count
rollout_attempt_count
rollout_success_count
rollout_error_count
cache_hit_count
cache_miss_count
error_type
error_stage
error_action
error_seed
error_hidden_state_sample_id
error_message_hash
traceback_hash
decision_runtime_ms
```

既存の`except`でfallbackする経路も、BENCHMARKでは`search_begin / search_end`と上記の最小telemetryを必ず残す。機密情報を含む生のpayloadを例外文へ埋め込まず、再現に必要な詳細はReplay Bundle IDで参照する。

### 9.3 比較無効条件

- 新旧のfallback率差が事前閾値を超える
- 未分類例外が1件でも発生する
- rollout成功数が最小必要数を下回る局面が多い
- timeout率がbaselineより悪化する

勝率だけが改善しても、探索失敗率やfallback率が悪化した場合は採用しない。

---

# Part III: 診断後にのみ選択する性能改修

以下はPR2のHuman Calibrationと原因構成比レポートが完了するまで実装しない。Decision Audit前の先行実装は禁止する。

## 10. Search Cache / Transposition — 重複探索の削減

### 10.1 狙い

探索数を単純に増やすのではなく、異なる行動順で同じ盤面へ到達する重複を除き、同じ時間で有効な探索量を増やす。

### 10.2 Canonical State Key

```text
public board state
private sampled hidden-state ID
turn / current player
select context
hand multiset
active / bench multiset and order-sensitive slots
attached energy / tools / damage / status
supporter used
energy attached
ability usage flags
stadium
remaining deck/prize counts
```

```text
cache_key = canonical_state_hash + policy_version + evaluator_version
```

### 10.3 安全条件

- hidden stateが異なる評価は共有しない
- ランダムな将来評価は、seed集合とサンプル数もキーに含める
- 行動順が効果へ影響するカードは可換扱いしない
- cache導入前後で固定局面の選択が一致する挙動保存テストを行う

### 10.4 計測

```text
cache hit rate
重複盤面率
削減rollout数
p50 / p95時間
同一予算でのunique state評価数
```

キャッシュ効果が低い場合は複雑化を避けて採用しない。

---

## 11. Tactical Safety Layer — 戦術的安全制約

### 11.1 問題

線形加算だけでは、返しの確定敗北や後続停止の大きなリスクが、手札・場・エネルギーの加点で相殺される可能性がある。

### 11.2 二段階選択

```text
1. terminal / safety constraintsで候補を分類
2. 同一安全クラス内を詳細評価値で比較
```

優先クラス例:

```text
Tier 0: 今ターン確定勝利
Tier 1: 返しの確定敗北を回避
Tier 2: 確定KO・最終サイド獲得
Tier 3: 次ターン攻撃継続を確保
Tier 4: サイドテンポ・資源価値を最適化
```

### 11.3 初期は強制しない

最初は次のflagだけをDecision Auditへ追加する。

```text
missed_forced_win
allows_forced_loss
missed_guaranteed_ko
breaks_next_attacker
missed_final_prize_boss
wastes_once_per_turn_resource
unnecessary_end_turn
```

人間レビューと複数hidden stateで高精度と確認されたflagだけ、soft constraint、その後hard constraintへ昇格する。

### 11.4 例外対策

- 返しの確定判定は「現在観測可能な範囲」と「belief上の高確率」を区別する
- hard constraintは確定情報だけに限定する
- 不確実な危険はpenaltyまたはrisk headで扱う

---

## 12. Multi-head Evaluator — 単一値から意味のある予測へ

### 12.1 推奨ヘッド

```text
win_probability
expected_prize_swing_2turn
current_ko_probability
next_turn_attack_probability
next_attacker_ready_probability
opponent_active_ko_probability
opponent_bench_ko_probability
energy_after_attack
refuel_probability
hand_recovery_probability
deck_out_probability
```

最初は学習モデルでなく、既存ルールと短いrolloutから個別に算出してよい。

### 12.2 統合順序

```text
terminal outcome
  -> survival / forced-loss risk
  -> attack continuity
  -> prize tempo
  -> resource value
```

単純な重み付き和だけでなく、辞書順比較、制約付き最適化、Pareto候補の比較も検討する。

### 12.3 Raging Boltで最優先のヘッド

```text
current_attack_value
next_turn_attack_probability
next_attacker_ready_probability
energy_after_attack
```

今のKO価値と、攻撃後に再攻撃できる確率を分離する。

### 12.4 採用条件

- 単一評価値より人間順位との一致が上がる
- 攻撃回数と再攻撃率が改善する
- 重みを変えても各ヘッドの意味が保たれる

---

## 13. Search Override Confidence Gate — 探索結果の安全な採用

探索が結果を返しただけでヒューリスティックを無条件に上書きしない。

### 13.1 採用条件

```text
successful_rollouts >= minimum_count
rollout_error_rate <= max_error_rate
best_action_probability >= probability_threshold
best_mean - baseline_mean >= noise_adjusted_margin
confidence_interval_overlap <= threshold
```

条件を満たさない場合は、現行baseline、安定版探索、または安全候補へ戻す。

### 13.2 fallback理由

```text
INSUFFICIENT_SAMPLES
HIGH_VARIANCE
LOW_VALUE_GAP
ROLLOUT_ERRORS
OUT_OF_DISTRIBUTION
MODEL_UNCALIBRATED
SAFETY_CONFLICT
```

### 13.3 SPIBBとの関係

学習モデルだけでなく、探索結果にも「信頼できないときはbaselineへ戻る」という安全改善の考え方を適用する。元論文の保証をそのまま主張せず、実験的な安全ゲートとして扱う。

---

## 14. Lightweight Opponent Threat Model — 公開行動から脅威を直接予測

### 14.1 方針

相手手札のカードIDを完全に当てる前に、意思決定に必要な次ターン脅威を直接予測する。

```text
P(active KO next turn)
P(bench KO next turn)
P(gust / Boss-like action)
P(evolution power spike)
P(retreat / switch)
expected max damage
expected prize loss
```

### 14.2 入力

- 公開されたカード
- 場・トラッシュ・ロスト等の公開領域
- エネルギー配置
- 進化ライン
- Supporter・グッズの使用履歴
- 攻撃を見送った履歴
- ベンチ展開と対象選択
- 手札・山札枚数

相手agent名・デッキ名は使用しない。

### 14.3 最初の実装

- ルールベースまたはロジスティック回帰等の軽量モデル
- 出力をMulti-head Evaluatorのrisk headとして利用
- 具体的なhidden hand生成とは独立にA/Bする
- calibrationを必須にする

### 14.4 Hidden-state modelとの使い分け

```text
Threat Model:
  次ターンに何が起こる確率が高いかを直接推定

Weighted Determinization:
  どの非公開カード構成があり得るかを生成
```

Threat Modelで十分なら、重いbelief planningへ進まない。

---

## 15. Deck–Agent Co-optimization — 構造的限界への対処

### 15.1 発動条件

- 評価・探索・候補漏れを改善しても攻撃回数差が縮まらない
- 再装填速度やサイド交換の不利が複数相手で再現する
- 死蔵カード率・手札詰まり・エネルギー供給不足が構造的に高い

### 15.2 探索範囲

60枚全体を一度に変更しない。

```text
固定枠: 48〜52枚
調整可能枠: 8〜12枚
```

制約:

- 合法な60枚構成
- コア戦術カードの最低枚数
- ACE SPEC等のデッキ制約
- エネルギー種類・枚数の上下限
- 変更枚数の上限

### 15.3 目的関数

```text
平均League勝率
worst-case勝率
初回攻撃ターン
平均攻撃回数
攻撃後の再攻撃率
死蔵カード率
手札事故率
平均判断時間
```

### 15.4 実験原則

- エージェントを固定してデッキだけ比較する
- 次にデッキを固定して方策だけ比較する
- 同時変更を避け、交互最適化する
- デッキ変更にはユーザーの明示承認を必要とする
- 特定相手専用のカード差し替えを汎用採用しない

---

# Part IV: 人間レビューと診断分岐

## 16. Phase 2 — 評価関数の人間校正

現在の評価関数でregretを作り、そのregretを教師として学習すると、評価関数の誤りを自己増幅する可能性がある。

そのため、学習前に固定局面で人間校正を行う。

### 16.1 初回レビュー100局面

```text
高regret                         30局面
hidden-state flip率が高い       15局面
AIと人が不一致                   15局面
AIと人が一致したが敗戦に寄与     15局面
非triggerからの層別random control 25局面
```

前4群は上から順に、まだ選ばれていない局面へ`primary_review_stratum`を割り当てて重複を防ぐ。全該当理由は別配列に残す。random controlは残りから勝敗、phase、context、合法手数で層別抽出する。各局面のreview包含確率を保存し、母集団校正には逆確率重みを使う。

### 16.2 人間へ表示する内容

レビューは二段階にする。

**Pass 1 — blind judgement**

- 公開盤面と合法手
- 必要な範囲の公開履歴
- 候補の表示順を固定seedでランダム化
- AI / Human / engineの出所、評価値、対局結果、後続手順を隠す
- レビュアー自身の推奨手、等価手集合、確信度、戦術意図を記録

**Pass 2 — evidence review**

- AIの最終選択、Human Trace、heuristic順位、engine search候補
- 各手の複数hidden state結果
- 平均値だけでなく分布
- Pass 1確定後に限り、実際の後続結果と反実仮想根拠

Pass 1のラベルをPass 2で上書きせず、変化した場合は理由を別保存する。

### 16.3 ラベル

```text
Aが明確に良い
Bが明確に良い
ほぼ同等
どちらも悪い
判断不能
```

### 16.4 校正の合格条件

- blindなacceptable-action一致率とそのgame-cluster CI下限が事前閾値を満たす
- 高regret判定のprecision / recallが事前閾値を満たす
- 等価手のfalse-positive率が事前上限を下回る
- 不確実性と人間の判断困難度の順位相関・校正誤差が事前閾値を満たす
- random controlを含む逆確率重み付き推定でも結論が変わらない

不合格なら、regret学習より先に評価関数・状態特徴を修正する。

閾値は本番100局面とは別のpilotレビューで決め、`calibration_threshold_version`として凍結する。100局面の結果を見て合格閾値を動かさない。

### 16.5 レビュー品質

- 重大判定に使う局面は原則2名以上が独立にblind評価する
- 一致率と、順序を考慮する場合はweighted kappa等を保存する
- 不一致は第三者adjudicationまたは`unknown`とし、多数決だけで確定しない
- レビュアー、提示順、ラベル定義、評価時点の知識をversion管理する
- 同一gameから多数の局面を出す場合も、統計上は独立レビュー件数とみなさない

### 16.6 原因分類は証拠の束として扱う

原因ラベルは単一指標から自動確定しない。`candidate_causes`には複数候補を許し、`primary_cause`は事前定義した証拠条件を満たす場合だけ付ける。満たさなければ`unknown`とする。

| 原因 | 最低限必要な証拠 |
|---|---|
| candidate_coverage | Golden / blind review等で優位とされた合法手が候補集合外で、独立確認標本でも改善が残る |
| evaluator_error | 優位手が候補内にあり、hidden stateと予算を揃えても現評価が系統的に逆順位を付ける |
| hidden_state_error | true / 後日判明hidden stateに対するbeliefの校正不良があり、その誤差で選択順位が変わる |
| out_of_distribution | version固定の参照分布から外れ、マッチした分布内対照より誤りが増える。OODだけでは因果確定しない |
| search_budget | evaluatorとrollout policyを固定し、予算増加で独立確認上のbest-arm同定とregretが改善する |
| rollout_bias | horizon × rollout policyの要因実験、terminal可解局面、人間blind評価等の複数証拠が同方向 |
| equivalent_action | blind reviewまたはGolden labelで、目的上ほぼ同等な行動集合に属する |
| unknown | Replay不成立、証拠競合、標本不足、上記条件未達 |

`hidden_state_flip_rate`はhidden stateへの**感度**であり、belief推定誤差そのものではない。`nearest_neighbor_distance`もOODの証拠であって原因の証明ではない。原因構成比レポートには、各原因の証拠件数、競合原因、unknown率、分類versionを必ず併記する。

PR1では`rollout_bias_suspected`を証拠フラグとして保存するだけにし、`primary_cause=rollout_bias`と`human_confirmed_persistence`はPR2の独立根拠が揃うまで設定しない。

---

## 17. 原因別の改修Branch

### Branch A — Candidate Coverage

Coverage Probeの判定を使用する。

```text
no_failure_observed
observed_failure
unknown
```

発動条件:

- `observed_failure`が重大局面で事前閾値を超える
- game-cluster集計した候補外行動の対応差分CI下限が事前marginを上回る
- またはGolden / blind reviewで候補漏れが確認される

`unknown`を失敗または成功へ自動変換しない。Probe失敗率が高い場合は、まず評価時間・合法手列挙・Replayを修正する。

hidden state 8個の単一Stage 2局面だけではBranchを発動せず、追加確認または集計根拠へ送る。

改修候補:

```text
ヒューリスティック上位3手
+ 最良ATTACH
+ 最良ATTACK
+ 最良Supporter
+ 最良RetreatまたはEND
```

重複除外後、最大候補数を時間制約に合わせて設定する。

成功条件:

- `no_failure_observed`比率が改善
- `observed_failure`比率が低下
- `unknown`が増えていない
- paired normalized regretが低下
- 計算時間が許容範囲

---

### Branch B — Evaluator Error / Afterstate Value

発動条件:

- Human–Rollout Rank Agreementが低い
- rollout予算を増やしても人間順位へ近づかない
- 資源消費後の再攻撃可能性を誤る

改修順:

1. 特徴量の不足と重複を確認
2. 攻撃後の資源機会費用を追加
3. 後続アタッカー確保特徴を追加
4. サイドレース・次回攻撃までのターン数を追加
5. afterstate learned valueを少量混合

```text
final_value
  = heuristic_value
  + alpha * learned_afterstate_value
```

比較:

```text
alpha = 0
alpha = 0.05
alpha = 0.10
alpha = 0.20
```

データ分割:

- 対局単位でtrain / validation / test
- 同一対局の状態を分割先へ跨がせない
- 相手アーキタイプholdout
- 時系列holdout
- baseline commit holdout

---

### Branch C — Hidden State Error

発動条件:

- 重大局面のhidden-state flip率が高い
- Boss、Retreat、攻撃、資源消費の最善手が仮説ごとに変わる
- simulatorのtrue hidden stateまたは後日判明情報に対し、beliefの校正不良が確認される

最初の2項目だけなら「hidden-state感度が高い」としか言えず、推定誤差とは分類しない。現行APIから相手手札・サイド・山札の真値を安全にexportできない場合、`hidden_state_error`は原則`unknown`に留める。その場合もrobustness実験はできるが、原因構成比では「誤差」として数えない。

校正確認では、カード/カテゴリ別のbelief probabilityと真値をBrier score、log loss、coverage等で評価し、その誤差がaction順位反転へつながったかを分けて保存する。

根拠が揃った後の最初の改修はFull ISMCTSではなく **Weighted Determinization** とする。

公開情報:

- 場とトラッシュのカード
- 公開エネルギー
- 使用済みサポート・グッズ
- 進化状況
- 山札・手札枚数
- 対戦中の行動履歴

```text
action_value
  = Σ hidden_state_weight * rollout_value
```

改善が確認された場合のみ、次へ進む。

- Public Belief State
- 情報集合単位の統計共有
- tree reuse
- strategy fusion対策
- Full ISMCTS
- particle belief / POMCP

---

### Branch D — Out-of-Distribution / Critical-Regret DAgger

発動条件:

```text
重大判断ミスの30%以上が
既存人間トレースに類似局面のない状態で発生
```

手順:

```text
AIに対戦させる
  -> 分布外かつ高regret局面を抽出
  -> 人が上位候補だけ比較
  -> 等価手集合を作成
  -> rankingデータへ追加
  -> 再学習
  -> 新AIで再収集
```

1回100局面程度の小さい反復とする。

人に全合法手の完全順位を付けてもらわない。

---

### Branch E — Regret-weighted Action Ranking

発動条件:

- 少数判断へregretが集中
- 現行学習がすべての不一致を同じ重みで扱う

学習データ:

```text
state
preferred_action
non_preferred_action
regret_gap
human_intent
```

学習目標:

```text
score(preferred) > score(non_preferred)
```

重み:

```text
pair_weight = clip(regret_gap, min_weight, max_weight)
```

等価手:

```text
best_value - action_value <= epsilon
```

を同一正解集合へ含める。

---

### Branch F — Search Budget / Best-Arm Identification

発動条件:

- 予算増加で固定局面の最良手選択率が上がる
- ただし単純なrollout増加は時間制約で難しい

ここで現行UCB1と、最終手の選択を目的にした手法を比較する。

#### 比較対象

```text
A: 現行UCB1
B: Sequential Halving
C: Simple-regret型2段階配分
D: VOIを近似した早期停止
```

#### 理由

現行UCB1は累積regretを抑える設計に近い。一方、ゲーム探索では探索中の各試行報酬ではなく、最後に選ぶ1手が重要である。

#### 固定総予算

```text
12 / 20 / 32 rollouts
```

総rollout数を完全に同一にして比較する。

#### 評価

- Best-arm Identification Accuracy
- Mean / P90 regret
- hidden-state別の安定性
- p95時間
- League勝率

#### Progressive Bias

Simple Regret / Sequential Halvingで改善が確認された後、必要に応じてヒューリスティックpriorを探索初期だけ使う。

```text
search_score
  = rollout_mean
  + decaying_weight(N) * heuristic_prior
```

訪問回数が増えるほどpriorの影響を下げる。

---

### Branch F2 — Rollout Bias Diagnosis

rollout数やseed数を増やして値が安定しない場合、最初に疑うのはvarianceである。biasとするには次の証拠を比較する。

```text
1. 人間評価との系統的な順位差
2. 実際の後続結果との校正差
3. horizon変更による順位反転
4. rollout policy変更への感度
5. terminalまで評価できる小規模局面との不一致
```

少なくとも複数の証拠が同方向に揃った場合だけ`rollout_bias_suspected`とする。

次の改修は証拠別に選ぶ。

```text
horizon依存          -> horizon / leaf evaluator診断
policy感度           -> rollout policy改善
terminal不一致       -> engine simulation / terminal scoring確認
人間との系統差       -> evaluator feature / objective確認
校正差               -> value calibration / outcome model確認
```

---

### Branch G — Safe Policy Improvement

学習モデルや模倣priorを直接本番方策へ混ぜると、データの少ない局面で大退行する可能性がある。

SPIBBの考え方を使い、不確実局面ではbaselineへ戻す。

```text
if support_count < minimum_support:
    use_baseline_policy()
elif model_uncertainty > threshold:
    use_baseline_policy()
elif calibrated_confidence < threshold:
    use_baseline_policy()
else:
    use_small_learned_correction()
```

注意:

- 元論文の安全性保証をそのまま現在のゲームへ主張しない
- まずは「低信頼局面でbaselineへ戻す設計原則」として使う
- 将来はMCTS-SPIBBの局所的・オンラインな安全改善も検討可能

評価:

- baselineより悪化したseedペアの割合
- worst-case相手勝率
- fallback率
- OOD局面での退行率
- learned correctionを使った局面の成功率

---

### Branch H — Uncertainty / Calibration

Value Modelやranking modelは、予測値だけでなく不確実性を出す。

#### Deep Ensemble

異なる初期値・bootstrapデータで複数モデルを学習する。

```text
learned_value = ensemble_mean
uncertainty   = ensemble_std
```

#### 使用条件

```text
if ensemble_std <= threshold
and support_count >= minimum_support
and calibrated_confidence >= threshold:
    final_value += alpha * learned_value
```

#### Calibration

accuracyやAUCだけでなく、予測確率が実測頻度と対応するか確認する。

記録:

- Brier score
- log loss
- Expected Calibration Error
- reliability diagram
- opponent holdout calibration
- OOD vs in-distribution uncertainty

Temperature Scalingなどはvalidationデータだけで調整する。

---

### Branch I — Delayed Credit / RUDDER型分析

「敗戦直前のミス」ではなく、勝敗予測を最初に大きく悪化させた判断を抽出する。

```text
対局中の判断列
  -> 最終勝敗 / 最終サイド差を予測する時系列モデル
  -> 予測値が大きく変化した判断を抽出
  -> 反実仮想rolloutと人間レビューで確認
```

保存値:

- predicted win probability before action
- predicted win probability after action
- return contribution score
- action category
- estimated counterfactual regret
- human confirmation

用途:

- First Persistent Critical Divergence Candidate候補のランキング
- レビュー対象の優先順位付け
- 数ターン前の資源判断へのcredit assignment

注意:

- contribution scoreは因果関係の確定ではない
- 必ず反実仮想評価と人間レビューで検証する
- RUDDER全体を本番RLとして実装せず、まずオフライン分析に限定する

---

# Part V: 探索時間とメタ推論

## 18. 探索予算の制御

全局面でrolloutを増やさず、「追加計算を行う価値」が高い局面へ配分する。

### 18.1 追加探索条件

- 上位2手が僅差
- hidden-state flip率が高い
- Boss使用
- Retreat
- 確定KO候補
- 大量エネルギー消費
- 残りサイド2以下
- 返しで敗北する可能性
- モデルとヒューリスティックが不一致
- ensemble uncertaintyが中程度で、追加探索により解消可能

### 18.2 早期終了

```text
best_lower_confidence_bound
  > second_upper_confidence_bound + margin
```

となったら追加rolloutを終了する。

### 18.3 時間上限

```text
通常局面: 現行p95以内
重要局面: 現行p95の1.5倍以内
ゲーム全体: 現行比1.25倍以内
```

### 18.4 メタ推論

追加rolloutそのものを行動として扱う。

```text
expected_value_of_computation
  = expected_decision_improvement
  - computation_cost
```

この設計には、有限計算資源下の合理性を扱う `Do the Right Thing` の考え方が有用。

---

# Part VI: 検証手順

## 19. 固定局面テスト

対戦前に固定局面セットで評価する。

```text
通常局面
確定KO局面
Boss局面
Retreat局面
攻撃後再装填局面
資源回収局面
hidden-state依存局面
分布外局面
終盤局面
候補漏れが起きた局面
```

### 19.1 Golden Decision Suite

Coverage Probeとregretが同じ現行evaluatorを使うだけでは、「候補漏れ」と「評価関数の誤り」を循環的に分類してしまう。そこで、現行evaluatorから独立した根拠を持つ小規模なGolden Decision SuiteをPR0-Dで先に固定する。

初期50〜100局面を次のように構成する。

```text
ルール・合法性・resource invariant
1〜2手でterminalまで厳密に列挙できる局面
確定KO / 確定敗北回避 / forced action
短いhorizonで全合法手を列挙できる局面
blindな複数人レビューで合意した戦術局面
判断不能・等価手を明示したnegative control
```

oracle根拠の優先順位:

```text
1. ルールまたはterminalまでの厳密解
2. evaluator非依存の不変条件
3. blindな複数人レビュー + adjudication
4. policy / horizon / leaf評価を変えた高予算探索の合意
```

各局面に`oracle_basis`、`oracle_version`、`acceptable_action_set`、`label_confidence`、`adjudication_status`を保存する。4は真のoracleとは呼ばず、弱い参照ラベルとして別集計する。現行evaluatorだけで作った順位をGolden labelへ採用しない。

Suiteはpilot後に凍結し、閾値調整用と最終評価用をgame単位で分ける。特定相手名・デッキ名を条件にせず、局面の戦術構造とルールで分類する。

指標:

- Best-arm Identification Accuracy
- critical regret
- human rank agreement
- candidate coverage
- fallback率
- ensemble uncertainty
- calibration
- p95時間

## 20. 30戦スクリーニング

目的は改善確認ではなく、大退行の除外。

- 違法手
- 例外
- タイムアウト
- fallback急増
- 明白な勝率崩壊
- 1手時間超過

## 21. 100戦確認

- 「100」は固定採用根拠ではなく最小スクリーニング目安
- Common Random Numbers
- 対応あり比較
- mirror + 強敵
- 事前に採用条件を固定

実行前にprimary metric、実用上の最小改善幅、片側/両側、有意水準、検出力、paired pilot分散から必要game pair数を計算する。必要数が100を超えるなら増やし、100未満でも最低運用・例外確認件数は維持する。途中結果を見て停止する場合は事前定義したsequential designを使う。

## 22. 300戦以上の最終確認

複数相手へ同一方策で評価する。

```text
fitness
  = 0.7 * 全相手平均勝率
  + 0.3 * 最悪相手勝率
```

ただし、fitnessだけで採用せず、各相手の勝率・信頼区間・regret・時間を個別保存する。

最終確認はbranch、alpha、探索予算、閾値の選択に使っていないgame-seed holdoutで行う。primary comparisonは1つに凍結し、複数候補・複数相手の副次比較にはHolm等のfamily-wise補正または事前定義したFDR制御を用いる。「300」も下限目安であり、paired効果の検出力計算を優先する。holdoutを見て設定を変えた場合、そのholdoutは消費済みとして新しい未使用holdoutを用意する。

---

# Part VII: PR分割

Audit前は方策・評価・候補生成を変更しない。各PRは前段の成果物を入力とし、同時実装しない。

## PR0-A — Parameter Contract調査 / Strict Telemetry

**方策変更なし。**

追加:

- params全キーとハードコード値の調査
- ACTIVE / EXPERIMENTAL / DEPRECATED / UNUSED / SHADOWED / DUPLICATE分類
- Runtime Override到達経路
- search / rollout / fallback / exception telemetry
- PRODUCTION / BENCHMARK / DEBUGモード

このPRではパラメータ削除やスコア変更を行わない。

## PR0-B — Observation Snapshot / Deterministic Replay

**方策変更なし。**

追加:

- Observation Snapshot
- legal actionsと選択コンテキストの保存
- action / algorithm versionを含めないstable hashによる共通sample seed
- version付きsemantic action ID
- global RNG state / materialized hidden samples
- hidden / Python rollout / engine内部のCRN capability matrix
- Replay Bundle
- Common Random Numbers
- 単独再生CLI

完了条件:

- 同一bundleを別プロセスで10回反復し、legal actions、hidden state、候補値、選択が完全一致する
- 決定性A/Aの不一致率が0
- 元対局の実選択を再現できる
- 旧版・新版で同じhidden state・seedを共有できる

## PR0-C — 評価経路マトリクス / Shadow比較

**統合しない。方策変更なし。**

追加:

- 既存評価経路の入力・出力・特徴量・単位・terminal値・呼び出し元の一覧
- 同一Snapshotでのshadow評価
- 順位不一致・スケール不一致・feature不一致ログ

禁止:

- 共通Feature Schemaへの移行
- 評価式の変更
- Evaluator Unification

## PR0-D — Golden Decision Suite

**方策変更なし。**

追加:

- terminalまで厳密に解ける局面とルール不変条件
- blindな複数人レビュー手順
- acceptable action set / equivalent action
- oracle basis / confidence / version
- pilot用と最終評価用のgame単位分割

禁止:

- 現行evaluatorだけでGolden順位を作ること
- 最終評価セットを見た後の閾値変更
- Golden Suiteに合わせた本番方策変更

## PR1-A — Stage 1 Decision Audit

**方策変更なし。**

追加:

- final selected actionを必ず含む最大3候補の対応あり評価
- hidden state 4 × seed 1
- raw value
- paired raw differences
- `ci_status=insufficient_samples`
- hidden-state flip
- rollout成功・失敗
- Stage 1 JSONL

## PR1-B0 — OOD Reference Contract

**方策変更なし。オフラインartifactのみ。**

追加:

- 参照コーパスのsource / game split manifestとhash
- feature schemaとcontext別scaler
- distance metric / support count / threshold version
- 同一game・未来情報・評価holdoutのleakage audit

完了条件:

- 参照artifactだけから同じOOD evidenceを再計算できる
- 閾値が評価対象を見る前に凍結されている
- artifact欠損時は`ood_status=unknown`になる

## PR1-B — Coverage Probe / 評価値正規化

追加:

- 全合法手をhidden state 1 × seed 1で粗く評価するCoverage Probe
- coverage_status: `no_failure_observed / observed_failure / unknown`
- paired_value_differences
- paired_mean_gap
- 決定性A/Aとsampling noiseの分離
- sampling noise基準のnormalization
- terminal値の別クラス処理
- OOD根拠の個別保存

## PR1-C — Stage 2 / Paired CI / Random Control

追加:

- hidden state 8 × seed 2の重要局面再評価
- Stage 1と独立した確認用seed group
- hidden stateをクラスタとするnested / cluster bootstrap
- hidden state間分散と同一hidden state内seed分散の分離
- paired_gap_ci_low / high
- paired_normalized_gap_ci_low / high
- alternative_improvement_probability
- decision単位は`ci_status=exploratory_small_cluster`
- `stage2_reason`
- 5〜10%の`random_control`
- stage2 inclusion probabilityとselection source
- 二相抽出の逆確率重み付き集計
- 選択群とランダム対照群の比較
- observed / counterfactual persistence
- rollout bias evidenceの保存

## PR2 — Human Calibration / 原因構成比レポート

追加:

- 敗戦100 + 勝利100分析
- 勝敗別の原因率と、未選別バッチの実勝敗率によるcase-control補正
- game-cluster bootstrap
- Stage 2 random-control補正
- blindな複数人レビュー
- human_confirmed_persistence
- append-only human_review / cause_classification records
- version付きjoined report view
- Coverageの3値構成比
- normalized regret
- OOD根拠
- rollout bias evidence
- 評価経路不整合
- 次に進むBranchの提案

レポートは最低限、次を分けて出力する。

```text
loss-stratum cause rate
win-stratum cause rate
raw 1:1 case-control composition
population-weighted cause estimate
game-cluster confidence interval
unknown / replay_invalid / audit_error rate
multiple-cause overlap matrix
classification version / threshold version
```

primary causeの構成比だけでなく、候補原因の重なりと証拠強度を残す。母集団補正に使った未選別バッチ、実勝敗率、抽出seedをreport metadataへ含める。

## PR2完了まで実装禁止

- Evaluator Unification
- Search Cache / Transposition
- Tactical Safety Layer
- Multi-head Evaluator
- Search Override Confidence Gate
- Lightweight Opponent Threat Model
- Weighted Determinization
- afterstate learned value
- DAgger
- Deck–Agent Co-optimization

## PR3以降 — 診断結果で1つだけ選択

```text
評価経路不整合が主要原因   -> Evaluator Unification
候補漏れ                   -> Candidate Coverage改善
評価誤差                   -> Evaluator特徴改善 / Multi-head / Afterstate
重複探索                   -> Search Cache
安全判断ミス               -> Tactical Safety
hidden-state誤差           -> Weighted Determinization
探索variance・予算不足     -> Sequential Halving / Simple Regret
rollout bias疑い           -> Rollout Policy / Horizon / Leaf評価修正
分布外                     -> Critical-Regret DAgger
相手返し評価               -> Opponent Threat Model
構造的デッキ限界           -> Deck–Agent Co-optimization
```

複数原因が同程度でも、最初のPRでは1テーマだけをablationする。

# Part VIII: 論文・書籍マップ

## 23. 最優先で読む論文

### 23.1 MCTS Based on Simple Regret

David Tolpin, Solomon Shimony, AAAI 2012  
DOI: https://doi.org/10.1609/aaai.v26i1.8126

プロジェクトへの意味:

- UCB1のcumulative regretと、ゲーム探索で重要なsimple regretの違いを整理できる
- 最後に良い1手を選ぶことへ探索配分を合わせる
- VOIを使った探索停止の考え方につながる

最小実験:

```text
現行UCB1 vs Simple-regret型
固定総rollout数
固定局面の最良手選択率で比較
```

### 23.2 Almost Optimal Exploration in Multi-Armed Bandits

Zohar Karnin, Tomer Koren, Oren Somekh, ICML 2013  
https://proceedings.mlr.press/v28/karnin13.html

プロジェクトへの意味:

- 固定予算で最良候補を識別するBest-Arm Identification
- Sequential Halvingを現行のフラット候補探索へ適用しやすい

### 23.3 Safe Policy Improvement with Baseline Bootstrapping

Romain Laroche, Paul Trichelair, Remi Tachet Des Combes, ICML 2019  
https://proceedings.mlr.press/v97/laroche19a.html

プロジェクトへの意味:

- データ不足・不確実局面では現行baseline方策へ戻す
- learned value / imitation priorの安全な導入設計に使う

### 23.4 Scalable Safe Policy Improvement via Monte Carlo Tree Search

Alberto Castellini et al., ICML 2023  
https://proceedings.mlr.press/v202/castellini23a.html

プロジェクトへの意味:

- MCTSとSPIBBを組み合わせ、訪問局面だけ局所的に安全改善する発想
- 現行engine searchとの将来的な接続候補

### 23.5 RUDDER: Return Decomposition for Delayed Rewards

Jose A. Arjona-Medina et al., NeurIPS 2019  
https://proceedings.neurips.cc/paper/2019/hash/16105fb9cc614fc29e1bda00dab60d41-Abstract.html

プロジェクトへの意味:

- 最終敗北を数ターン前の重大判断へ配分する
- First Persistent Critical Divergence Candidateの候補抽出に使う

### 23.6 Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles

Balaji Lakshminarayanan, Alexander Pritzel, Charles Blundell, NeurIPS 2017  
https://proceedings.neurips.cc/paper_files/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html

プロジェクトへの意味:

- Value Model / ranking modelの予測不確実性
- OOD局面でlearned correctionを抑制するgate

### 23.7 On Calibration of Modern Neural Networks

Chuan Guo et al., ICML 2017  
https://proceedings.mlr.press/v70/guo17a.html

プロジェクトへの意味:

- モデルの確信度と実際の正解率を対応させる
- temperature scaling等を使ったconfidence gate

---

## 24. 中期的に読む論文

### 24.1 Information Set Monte Carlo Tree Search

Cowling, Powley, Whitehouse, 2012  
https://doi.org/10.1109/TCIAIG.2012.2200894

適用条件:

- Weighted Determinizationで改善が出る
- hidden-state flip率が高い
- 情報集合単位の統計共有に価値がある

### 24.2 POMCP

Silver and Veness, 2010  
https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps.pdf

適用条件:

- 対戦中の観測でbelief更新する価値が確認される
- 必要particle数を時間内に処理できる

### 24.3 Combining Deep Reinforcement Learning and Search for Imperfect-Information Games（ReBeL）

Noam Brown et al., NeurIPS 2020  
https://proceedings.neurips.cc/paper/2020/hash/c61f571dbd2fb949d3fe5ae1608dd48b-Abstract.html

プロジェクトへの意味:

- Public Belief Stateという状態設計
- 公開盤面 + 非公開状態の分布を統合する長期的設計
- ReBeL全体ではなく、belief interfaceの設計を先に借りる

### 24.4 Set Transformer

Juho Lee et al., ICML 2019  
https://proceedings.mlr.press/v97/lee19d.html

適用条件:

- 十分な学習データがある
- 手札、場、トラッシュ、合法手を集合として学習する
- 固定順序の特徴ベクトルがボトルネックと確認される

### 24.5 DAgger

Ross, Gordon, Bagnell, 2011

プロジェクトへの意味:

- AI自身が到達した分布外盤面を人間が追加ラベルする
- Human Trace / Disagreement Review基盤を再利用できる

### 24.6 Advantage-Weighted Regression

Peng et al., 2019  
https://arxiv.org/abs/1910.00177

プロジェクトへの意味:

- すべての人間行動を同じ重みで模倣しない
- regret-weighted rankingの発想に利用する

### 24.7 Afterstate / TD Learning

- Sutton and Barto, `Reinforcement Learning: An Introduction`, 2nd ed.
- Tesauro, `Temporal Difference Learning and TD-Gammon`, 1995

プロジェクトへの意味:

- 人の行動IDではなく、行動直後の盤面価値を学ぶ
- 現行評価関数を少量補正する

---

## 25. おすすめ書籍

### 25.1 Do the Right Thing: Studies in Limited Rationality

Stuart Russell, Eric H. Wefald  
MIT Press  
https://mitpress.mit.edu/9780262513821/do-the-right-thing/

読む目的:

- どの局面へ追加rolloutを使うべきか
- いつ探索を停止すべきか
- 計算時間を含めた合理的意思決定

### 25.2 Handbook of Simulation Optimization

Michael C. Fu 編  
Springer  
https://link.springer.com/book/10.1007/978-1-4939-1384-8

読む目的:

- Ranking and Selection
- simulation budget allocation
- variance reduction
- stochastic optimization
- 多数候補を少ない対戦で絞る実験設計

### 25.3 Design and Analysis of Experiments for Statistical Selection, Screening, and Multiple Comparisons

Robert E. Bechhofer, Thomas J. Santner, David M. Goldsman, 1995  
https://www.asc.ohio-state.edu/santner.1/REB-TJS-DMG/describe.html

読む目的:

- 多数候補から有望案を選ぶ
- 弱い候補を早期にscreeningする
- 多重比較による誤採用を抑える

### 25.4 Bandit Algorithms

Lattimore and Szepesvári

読む目的:

- 固定予算の探索配分
- Best-Arm Identification
- confidence bound
- pure exploration

### 25.5 Algorithms for Decision Making

Kochenderfer, Wheeler, Wray

読む目的:

- POMDP
- belief state
- planning under uncertainty
- decision makingとsearchの統合

---

# Part IX: 文献から見た推奨実施順

## 26. 現時点の優先順位

```text
0. PR0-A Parameter Contract調査 + Strict Telemetry
1. PR0-B Observation Snapshot + Deterministic Replay
2. PR0-C 評価経路マトリクス + shadow比較。まだ統合しない
3. PR0-D Golden Decision Suite
4. PR1-A Stage 1 Decision Audit
5. PR1-B0 OOD Reference Contract、その後PR1-B Coverage Probe + 評価値正規化
6. PR1-C Stage 2 + paired CI + 5〜10% random control
7. PR2 Human Calibration + case-control補正付き原因構成比レポート
8. 診断結果で最小改修を1つ選択
9. 必要な場合のみEvaluator Unification
10. 必要な場合のみSearch Cache / Tactical Safety / Multi-head
11. 必要な場合のみSimple Regret / Sequential Halving
12. 必要な場合のみWeighted Determinization / DAgger / learned value
13. 方策改善後も構造限界が残る場合のみDeck–Agent Co-optimization
14. Full ISMCTS / POMCP / ReBeL等は最後
```

最初の4項目は性能手法ではなく、以降の結果を信用するための土台である。順位は固定せず、勝敗別比率とcase-control補正後の原因構成比で変更する。

### 例A

```text
candidate coverage      35%
evaluator error         30%
out-of-distribution     20%
hidden state error      10%
search budget            5%
```

優先:

```text
1. Candidate Coverage
2. Evaluator
3. DAgger
4. Weighted Determinization
```

### 例B

```text
hidden state error      45%
evaluator error         25%
search budget           20%
その他                  10%
```

優先:

```text
1. Weighted Determinization
2. Evaluator
3. Simple Regret / Sequential Halving
4. ISMCTS
```

### 例C

```text
equivalent action       50%
importance weighting    25%
OOD                     15%
その他                  10%
```

優先:

```text
1. 複数正解ランキング
2. Regret-weighted ranking
3. DAgger
```

---

### 例D

```text
fallback / exception        25%
parameter shadowing         20%
evaluator disagreement      20%
duplicate search            15%
その他                      20%
```

優先:

```text
1. Strict Benchmark Mode
2. Parameter Contract Audit
3. 評価経路shadow比較
4. PR2後に必要ならEvaluator UnificationまたはSearch Cache
```

### 例E

```text
forced-loss risk missed     30%
attack continuity error     25%
opponent threat error       20%
hidden state error          15%
その他                      10%
```

優先:

```text
1. Tactical Safety Layer
2. Multi-head Evaluator
3. Lightweight Opponent Threat Model
4. Weighted Determinization
```

---

# Part X: 保留・非推奨

## 27. 診断なしで実装しないもの

- Full POMCP
- Full ReBeL
- Deep RL全面移行
- Distributional RL
- MAP-Elites
- 大規模Mixture of Experts
- 相手名・デッキ名による分岐
- 特定ベンチマーク専用パラメータ
- 無条件でのValue Model混合
- 単純なrollout数の大幅増加
- 複数アルゴリズムの同時導入
- Decision Audit前のEvaluator Unification
- Decision Audit前のSearch Cache、Tactical Safety、Multi-head、Opponent Threat、Deck–Agent Co-optimization
- 評価関数を統合せずに学習値だけ追加すること
- fallback率を確認せず勝率だけで採用すること
- Python組み込みhash()をReplay seedへ使うこと
- hidden stateを跨ぐ不正確なcache共有
- 不確実情報に基づくhard safety constraint
- デッキと方策を同時に変更して原因を不明にすること

## 28. 実験上の注意

- rollout評価自体が誤っている可能性を常に残す
- 最終勝敗だけで判断しない
- 勝利対局にも同じ乖離があるか比較する
- 同一対局を学習と評価へ跨がせない
- hidden stateサンプル数とrollout seed数を区別する
- seed増加で分かるのは主にvarianceであり、biasと断定しない
- Candidate Coverageの`unknown`を成功扱いしない
- Stage 2には5〜10%のランダム対照を含める
- regret CIは同一hidden state・seedの対応差分から計算する
- terminal値と通常局面値を未正規化のまま混ぜない
- 同じ総計算量で比較する
- 30戦の勝率上昇を採用根拠にしない
- mirror改善だけで採用しない
- モデル確信度をそのまま信用せず校正する
- 「安全改善」の理論保証を現在の環境へ無条件で主張しない
- 評価経路・パラメータ・seed・実行モードを結果と一緒に保存する
- cache導入では選択一致とhidden-state隔離を必ず検証する
- Tactical Safetyはログ→soft→hardの順に昇格する
- Multi-head出力は校正し、単一の合成値だけを保存しない
- Deck–Agent共同最適化は方策固定とデッキ固定を交互に行う

---

# Part XI: Codexへ渡す依頼

## 29. 最初の依頼 — PR0-A〜PR0-Dの調査と実装計画

```text
pokemon_aiリポジトリの現行Raging Boltエージェントについて、
性能改善アルゴリズムと評価統合はまだ実装せず、次を順番に調査してください。

PR0-A候補:
- Parameter Contract調査
- ハードコードスコア一覧
- PRODUCTION / BENCHMARK / DEBUGモード
- search / rollout / fallback / exception telemetry

PR0-B候補:
- Observation Snapshot
- action_idとalgorithm_versionを含めない共通sample seed
- version付きsemantic action ID
- module global RNG stateと実生成hidden-state配列の保存可否
- battle_start / search_stepのseed・random stream注入可否
- Replay Bundle
- Common Random Numbers

PR0-C候補:
- evaluate_state()
- _eval_search_state()
- _estimate_action_impact()
- 行動別ヒューリスティック
- Value Model / Counterfactual Analyzer

について評価経路マトリクスを作成し、同一Snapshotでshadow比較する方法を提案してください。

PR0-D候補:
- terminalまで厳密に解ける局面
- ルール・resource invariant
- blindな複数人レビュー
- acceptable action set / equivalent action
- oracle basis / confidence / version

について、現行evaluatorだけを正解生成に使わないGolden Decision Suiteを提案してください。

重要:
- Evaluator Unificationはまだ実装しない
- 共通Feature Schemaへの移行はまだ行わない
- Parameter Contract違反は検出・報告のみとし、reject / clamp / default置換しない
- Search Cache、Tactical Safety、Multi-head Evaluator、Opponent Threat Model、
  Weighted Determinization、Deck–Agent Co-optimizationは実装しない
- main.py / params.json / deck.csvの選択結果を変更しない

成果物:
1. 現状アーキテクチャ図
2. パラメータ監査表
3. Strict Telemetry案
4. Observation Snapshot / Replay Bundle案
5. CRN capability matrix（hidden / Python rollout / engine内部）
6. 評価経路マトリクス
7. shadow比較項目
8. Golden Decision Suite案
9. PR0-A / PR0-B / PR0-C / PR0-Dの分割計画
10. baseline不変の回帰テスト計画

まだコードを変更せず、調査結果と実装計画だけを提示してください。
```

## 30. Decision Audit基盤の依頼 — PR1-A〜PR1-C（PR1-B0を含む）

```text
pokemon_aiリポジトリの現行Raging Boltエージェントについて、
方策を変更せずDecision Audit基盤の実装計画を作成してください。

PR1-A Stage 1:
- final selected actionを必ず含む最大3候補
- hidden state 4種類
- rollout seed 1種類
- 全候補で同一hidden state・seedを共有
- raw_value
- paired_value_differences
- Stage 1では正式なCIを出さずci_status=insufficient_samples
- normalized_valueとCIはnull
- heuristic_pick / actual_engine_pick / final selected_actionを分離

PR1-B0 OOD Reference Contract:
- source game split manifest / reference corpus hash
- feature schema / context別distance scaler
- distance metric / support / threshold version
- 同一game・未来情報・holdoutのleakage audit
- artifact不足時はood_status=unknown

PR1-B Coverage Probe:
- 全合法手をhidden state 1 × seed 1で粗く評価
- coverage_statusをno_failure_observed / observed_failure / unknownで保存
- Probe単独では原則unknownとし、独立確認でobserved_failureを確定
- paired_mean_gap
- 同一Replayの決定性A/Aは差0を必須とし、非0なら基盤エラー
- 独立seed groupでsampling noiseを測りnormalized_regretを計算
- terminal ±1,000,000を通常局面regretへ直接混ぜない

PR1-C Stage 2:
- hidden state 8種類
- seed 2種類
- Stage 1と独立した確認用seed groupを使用
- hidden stateをクラスタとするnested / cluster bootstrap
- hidden state間分散と同一hidden state内seed分散を分離
- paired_gap_ci_low / paired_gap_ci_high
- paired_normalized_gap_ci_low / paired_normalized_gap_ci_high
- alternative_improvement_probability
- decision単位はci_status=exploratory_small_cluster
- high_regret / close_top2 / hidden_flip / human_disagreement /
  loss_path / coverage_probeを対象
- 全Stage 1局面の5〜10%を勝敗・phase・context等で層別したrandom_controlとして含める
- stage2_reasonを保存
- stage2_inclusion_probability / stage2_selection_sourceを保存
- 全Stage 1母集団の推定は二相抽出の逆確率重みを使う

Common Random Numbers:
- comparison seedへaction_idとalgorithm_versionを含めない
- hidden stateを候補評価前に生成し全候補で共有
- 乱数源別streamまたは固定random tapeを保存
- action_idはraw option順ではなくversion付きsemantic key

保存必須:
- state_id / human_action / legal_actions
- heuristic_ranking / engine_search_candidates
- hidden-state別rollout値
- mean / std / min / max / best_action_probability
- estimated_regret / alternative_improvement_probability
- hidden_state_flip_rate / evaluation_uncertainty
- rollout_success_count / rollout_error_count / runtime_ms
- final_result / final_prize_diff

rollout bias:
seed数増加だけでbiasと断定しないでください。
次の証拠を個別保存してください。
- 人間評価との系統的順位差
- 実後続結果との校正差
- horizon変更による順位反転
- rollout policy変更への感度
- terminalまで評価できる小規模局面との不一致

OOD:
単一scoreではなく次を保存してください。
- nearest_neighbor_distance
- k_neighbor_mean_distance
- feature_out_of_range_count
- context_support_count
- action_type_support_count

Persistence:
- observed_persistence
- counterfactual_persistence
- human_confirmed_persistence
を分離し、名称は
first_persistent_critical_divergence_candidate
へ統一してください。

原因分類:
- candidate_coverage / evaluator_error / hidden_state_error /
  out_of_distribution / search_budget / rollout_bias /
  equivalent_action / unknown
- hidden_state_flipは感度でありhidden_state_errorの証明としない
- true hidden stateの安全なexportまたは後日判明情報がなければ
  hidden_state_errorはunknownに留める
- OOD距離だけで原因と断定しない
- candidate_causes / primary_cause / cause_confidence /
  cause_evidence / classification_versionを保存
- PR1ではrollout_bias_suspectedまでとし、primary_cause=rollout_biasと
  human_confirmed_persistenceはPR2完了まで設定しない

禁止:
- Evaluator Unification
- Search Cache
- Tactical Safety
- Multi-head Evaluator
- Opponent Threat Model
- Weighted Determinization
- Deck–Agent Co-optimization
- Value ModelやDAggerの本番統合

成果物:
1. PR1-A / PR1-B0 / PR1-B / PR1-Cの実装計画
2. JSONL schema version 4
3. Stage 2の階層的な対応差分CI計算方法
4. 決定性A/Aとsampling noiseを分けた正規化方法
5. random controlの抽出方法
6. 計算量と失敗条件
7. 回帰テストとReplayテスト

まだコードを変更しないでください。
```

## 31. Search Allocation実験の依頼

Decision Auditで探索予算不足が主要原因と確認された場合だけ使用する。

```text
現行UCB1と、以下の固定予算Best-Arm Identification方式を比較する実装計画を作成してください。

A. 現行UCB1
B. Sequential Halving
C. Simple-regret型2段階配分

条件:
- 総rollout数を完全に同じにする
- 12 / 20 / 32 rolloutsで比較する
- candidate set、hidden state、seedを共通化する
- まず固定局面テストだけを実装する
- 本番方策へはまだ反映しない

指標:
- best-arm identification accuracy
- mean regret
- p90 regret
- hidden-state別の選択安定性
- p50/p95 runtime
- rollout error rate

既存の_ucb1_chooseを壊さず、strategyパターンで切り替えられる設計にしてください。
```

## 32. Safe Learned Correctionの依頼

```text
既存Value Modelまたはranking modelを本番方策へ無条件に混ぜず、
SPIBB型baseline fallback、Deep Ensemble uncertainty、confidence calibrationを組み合わせる最小設計を作成してください。

条件:
- support_countが少ない局面ではbaselineへ戻す
- ensemble varianceが高い局面ではbaselineへ戻す
- validationデータでcalibrationする
- alpha=0/0.05/0.1/0.2を比較する
- 相手単位holdoutと対局単位splitを行う
- fallback率とworst-case勝率を記録する
- 元論文の安全性保証がそのまま適用されるとは記載しない

まだ本番paramsを変更せず、固定局面評価とオフラインレポートまで作成してください。
```

## 33. RUDDER型分析の依頼

```text
最終勝敗を、対局中のどの判断が大きく変化させたか分析するため、
RUDDERのreturn decompositionを参考にしたオフライン分析計画を作成してください。

目的:
- 敗戦直前ではなく、最初の継続的重大乖離候補を抽出する
- 数ターン前の資源判断へcreditを割り当てる

条件:
- contribution scoreを因果効果とは扱わない
- 反実仮想rolloutと人間レビューで検証する
- 本番方策を変更しない
- 既存human traceとdecision audit JSONLを再利用する

保存項目:
- predicted win probability before/after action
- return contribution score
- counterfactual regret
- action category
- human review label
```

---

## 34. 最終判断基準

改修を採用する条件:

- Mean / P90 Critical Regretが改善
- Candidate Coverageが改善、または原因が解消
- First Persistent Critical Divergence Candidateが遅くなる
- 攻撃回数・再攻撃率が改善
- 多様な相手への平均・worst-case勝率が改善
- 特定相手用分岐を含まない
- p95時間とゲーム全体時間が制限内
- fallback・例外・timeoutが悪化しない

採用しない条件:

- 一致率だけ上がる
- mirrorだけ改善する
- 1つの相手だけ改善する
- fixed test局面だけ改善し対戦で再現しない
- 学習モデルが高確信で大退行する
- rollout予算を増やすほどregretが悪化する
- 計算時間が許容範囲を超える

---

## 35. この計画の要点

この第3版で追加した最重要事項:

```text
1. 新アルゴリズムより先に評価経路を一本化する
2. params.jsonが実際に効いているか契約として監査する
3. すべての局面をseed付きReplay Bundleで再現する
4. ベンチマークでは例外fallbackを隠さない
5. 同一盤面の重複探索をcacheで減らす
6. 確定勝敗・後続停止を安全制約として別層で扱う
7. 盤面価値を攻撃継続・生存・サイド・資源へ分解する
8. 探索結果は信頼度が十分な場合だけbaselineを上書きする
9. 相手手札を完全推定する前に次ターン脅威を直接予測する
10. 方策の上限がデッキ構造にある場合だけ限定的な共同最適化へ進む
```


```text
高度な手法を順番に実装するのではない。

まず原因を測る。
次に原因に最も近い最小改修を1つ入れる。
同じ計算量・同じ乱数条件で比較する。
不確実な局面ではbaselineへ戻す。
最終的な1手選択と、勝敗に寄与した最初の重大判断を重視する。
```
