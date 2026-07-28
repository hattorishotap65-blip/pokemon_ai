# ポケカAI 性能改善・診断・実装基盤ロードマップ（第3版）

更新日: 2026-07-26  
対象リポジトリ: `hattorishotap65-blip/pokemon_ai`  
対象エージェント: Raging Bolt ex + Teal Mask Ogerpon ex  
位置づけ: 内部実装の整合性・再現性・監視性を先に固め、診断結果に応じて最小の性能改修だけを選ぶための実装・研究メモ

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
8. rollout policy の bias
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

同一エージェントを同一条件で比較し、評価基盤自体のノイズを確認する。

記録する指標:

| 指標 | 目的 |
|---|---|
| 勝率 | 50%付近になるか |
| 先攻・後攻別勝率 | 先後の偏り確認 |
| 同一seed結果一致率 | 再現性確認 |
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
A. 最善手が探索候補に入っていない
B. 候補には入っているが評価関数が誤る
C. hidden stateによって最善手が変わる
D. AIが人間ログにない盤面へ到達する
E. rollout予算を増やすと改善する
F. rollout予算を増やすほど悪化する
G. 人間と違うが等価な手を誤りとして数えている
H. 学習モデルの高確信が実際には校正されていない
```

### 4.2 対象データ

初回診断:

```text
敗戦 100ゲーム
勝利 100ゲーム
```

敗戦だけを見ると、勝利時にも発生する無害な乖離を重大と誤認するため、勝利対局も比較する。

対象は原則としてMAINコンテキスト。ただし、以下は選択コンテキストも追跡する。

- Energy Retrievalの回収対象
- Ultra Ball等のdiscard対象
- Bellowing Thunderのエネルギー消費
- Bossの対象
- Retreat先
- サーチ対象

### 4.3 二段階の反実仮想評価

#### Stage 1 — 軽量スクリーニング

```text
候補: 上位3手
hidden state: 4種類
rollout seed: 1種類
最大: 12評価 / 判断
```

#### Stage 2 — 重要局面の再評価

対象条件:

- 推定regretが大きい
- 上位2手が僅差
- hidden stateで最善手が変わる
- 人とAIが不一致
- 敗戦経路上にある
- 確定KO、Boss、Retreat、大量エネルギー消費を含む
- モデル不確実性が高い
- 探索fallbackが発生した

```text
候補: 上位2〜3手
hidden state: 8種類
rollout seed: 2種類
最大: 48評価 / 判断
```

### 4.4 保存スキーマ

```json
{
  "schema_version": 2,
  "game_id": "",
  "state_id": "",
  "turn": 0,
  "context": "MAIN",
  "baseline_commit": "",
  "deck_hash": "",
  "params_hash": "",
  "game_seed": 0,
  "hidden_state_seed_group": "",
  "replay_bundle_id": "",
  "execution_mode": "BENCHMARK",
  "evaluator_version": "",
  "feature_schema_hash": "",
  "parameter_contract_version": "",
  "algorithm_version": "",

  "selected_action": "",
  "human_action": "",
  "legal_actions": [],
  "candidate_actions": [],

  "candidate_source": {
    "heuristic_top_k": [],
    "forced_attach": [],
    "action_type_quota": [],
    "human_action_injected_for_analysis": []
  },

  "action_values": {
    "action_id": {
      "mean": 0.0,
      "std": 0.0,
      "median": 0.0,
      "min": 0.0,
      "max": 0.0,
      "q10": 0.0,
      "q90": 0.0,
      "best_probability": 0.0,
      "rollout_success_count": 0,
      "rollout_error_count": 0,
      "hidden_state_values": []
    }
  },

  "estimated_regret": 0.0,
  "constraint_violation_flags": [],
  "multi_head_values": {
    "win_probability": null,
    "expected_prize_swing_2turn": null,
    "next_turn_attack_probability": null,
    "next_attacker_ready_probability": null,
    "opponent_active_ko_probability": null,
    "opponent_bench_ko_probability": null,
    "energy_after_attack": null
  },
  "opponent_threat": {
    "active_ko_probability": null,
    "bench_ko_probability": null,
    "gust_probability": null,
    "evolution_spike_probability": null,
    "expected_max_damage": null
  },
  "regret_confidence_low": 0.0,
  "regret_confidence_high": 0.0,
  "hidden_state_flip_rate": 0.0,
  "candidate_coverage_failure": false,
  "evaluation_uncertainty": 0.0,
  "search_budget_sensitivity": {},

  "model_prediction": null,
  "model_ensemble_mean": null,
  "model_ensemble_std": null,
  "model_calibrated_confidence": null,
  "baseline_fallback_used": false,

  "human_label": "",
  "human_intent": "",
  "equivalent_action_group": [],
  "ood_score": 0.0,

  "later_recovery_probability": null,
  "persistent_critical_divergence_candidate": false,
  "return_contribution_score": null,

  "final_result": "",
  "final_prize_diff": 0,
  "search_telemetry": {
    "attempts": 0,
    "successes": 0,
    "fallbacks": 0,
    "override_applied": false,
    "override_rejection_reason": null,
    "rollout_errors": 0,
    "cache_hits": 0,
    "cache_misses": 0
  },
  "decision_runtime_ms": 0,
  "game_runtime_ms": 0
}
```

---

## 5. 評価指標

### 5.1 主指標

| 指標 | 意味 |
|---|---|
| Mean Critical Regret | 重大局面で失った平均価値 |
| P90 Critical Regret | 最悪側10%の判断品質 |
| Fatal Mistakes / Game | 致命的判断数 |
| Candidate Coverage Rate | 最良手が探索対象に含まれる割合 |
| Hidden-state Flip Rate | hidden stateで最善手が変わる割合 |
| Human–Rollout Rank Agreement | 人間判断とrollout順位の一致 |
| Best-arm Identification Accuracy | 固定局面で最良手を選べた割合 |
| First Persistent Critical Divergence | 最初の継続的重大乖離 |
| Recovery Rate | 乖離後に立て直した割合 |
| Baseline Fallback Rate | 不確実局面で現行方策へ戻った割合 |
| Calibration Error | 予測確率と実測のずれ |
| Win Rate | 最終性能 |
| p95 Decision Time | 1手の実行時間 |

単純な人間行動一致率は補助指標へ下げる。

### 5.2 最初の継続的重大乖離

「不可逆」と断定せず、診断段階では次の名称を使う。

```text
First Persistent Critical Divergence
最初の継続的な重大乖離
```

候補条件:

```text
mean_value_gap >= delta
alternative_improvement_probability >= 0.70
later_recovery_probability <= 0.30
```

`delta`は固定値ではなく、A/Aで観測した評価ノイズを基準に決める。

---

# Part II: 実装基盤の整合性・再現性・安全性

このPartは、新しい探索アルゴリズムを追加する前に実施する。目的は性能を直接上げることだけではなく、以降の実験結果を信用できる状態へ整えることである。

実施順は次の通り。

```text
Phase F0: 方策非変更の監査・計測
  Parameter Contract Audit
  Deterministic Replay
  Strict Benchmark Mode

Phase F1: 挙動保存リファクタ
  Evaluator Unification
  共通Feature Schema

Phase F2: 診断後に有効化する性能改善
  Search Cache / Transposition
  Tactical Safety Layer
  Multi-head Evaluator
  Search Override Confidence Gate
  Lightweight Opponent Threat Model
  Deck–Agent Co-optimization
```

---

## 6. Evaluator Unification — 評価関数の一本化

### 6.1 現在の問題

少なくとも次の評価経路が別々に存在する。

```text
evaluate_state()
_eval_search_state()
_estimate_action_impact()
各行動のヒューリスティックスコア
学習Value Modelの特徴量
Counterfactual Analyzerの評価値
```

同じ局面について、ヒューリスティックはA、エンジン探索はB、fallback探索はCを推奨する状態が起こり得る。これは単なる重み調整ではなく、内部で異なる目的関数を持つ問題である。

### 6.2 目標構造

```text
Observation / State
  -> extract_common_features()
  -> evaluate_feature_heads()
  -> aggregate_value()
  -> evaluate_action_afterstate()
```

共通Feature Schemaには最低限、次を含める。

```text
prize_state
terminal_win_loss
current_attack_value
next_turn_attack_probability
next_attacker_readiness
field_energy
energy_after_attack
refuel_resources
active_ko_risk
bench_ko_risk
expected_prize_swing
hand_quality
deck_out_risk
supporter_right_value
retreat_resource_value
```

### 6.3 実装原則

- 最初のPRでは計算式を変えず、既存値を共通インターフェースから返す挙動保存リファクタにする
- 旧評価と新評価を同一局面で比較するgolden testを作る
- 特徴量名、単位、符号、default値を一箇所で定義する
- Human Review、Decision Audit、Value Model、engine searchが同じFeature Schemaを使う
- 旧経路は移行期間中だけshadow evaluationとして残し、差分をログ化する

### 6.4 完了条件

- 固定局面で旧版と行動が完全一致する
- 評価値差が許容誤差内、または差の理由が明記される
- 同じ意味の特徴量が複数定義されていない
- 新しい評価項目を追加すると全経路へ一度に反映できる

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
- 本番採用パラメータが契約外の値を取れない

---

## 8. Deterministic Replay — 局面単位の完全再現

### 8.1 現在の問題

モジュール全体のグローバル乱数列は、前の局面でのrollout回数、例外、候補数によって消費位置が変わる。固定seedでも局面単位の再現性は保証されない。

### 8.2 seed設計

```text
seed = stable_hash(
  base_seed,
  game_id,
  state_hash,
  turn,
  select_context,
  action_id,
  hidden_state_index,
  rollout_index,
  algorithm_version
)
```

Pythonの組み込み`hash()`はプロセスごとに変わり得るため使わず、SHA-256等から固定整数を生成する。

### 8.3 保存するReplay Bundle

```text
observation snapshot
legal actions
selected action
state hash
all seeds
hidden-state sample IDs
engine version
agent commit
deck hash
params hash
exception / fallback情報
```

### 8.4 必須テスト

- 同一bundleを10回再生して結果が一致する
- 旧版と新版が同じhidden state・山札順を使う
- Candidate AとBを同じ乱数条件で比較できる
- 例外が発生した局面だけ単独再生できる

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
error_action
error_seed
decision_runtime_ms
```

### 9.3 比較無効条件

- 新旧のfallback率差が事前閾値を超える
- 未分類例外が1件でも発生する
- rollout成功数が最小必要数を下回る局面が多い
- timeout率がbaselineより悪化する

勝率だけが改善しても、探索失敗率やfallback率が悪化した場合は採用しない。

---

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

# Part III: 人間レビューと診断分岐

## 16. Phase 2 — 評価関数の人間校正

現在の評価関数でregretを作り、そのregretを教師として学習すると、評価関数の誤りを自己増幅する可能性がある。

そのため、学習前に固定局面で人間校正を行う。

### 16.1 初回レビュー100局面

```text
高regret                        40局面
hidden-state flip率が高い      20局面
AIと人が不一致                  20局面
AIと人が一致したが敗戦に寄与    20局面
```

### 16.2 人間へ表示する内容

- 公開盤面
- AIが選んだ手
- 人間が選んだ手
- 評価上位3手
- 各手の複数hidden state結果
- 平均値だけでなく分布
- 結果を隠した状態での評価
- 戦術意図

### 16.3 ラベル

```text
Aが明確に良い
Bが明確に良い
ほぼ同等
どちらも悪い
判断不能
```

### 16.4 校正の合格条件

- 重大局面で人間順位との一致が十分高い
- 高regret判定が人間レビューで再現される
- 等価手を過剰に悪手扱いしない
- hidden stateを変えたときの不確実性が、人間の判断困難度と対応する

不合格なら、regret学習より先に評価関数・状態特徴を修正する。

---

## 17. 原因別の改修Branch

### Branch A — Candidate Coverage

発動条件:

```text
探索候補外に最良手が存在する割合が
重大局面の10%以上
```

改修:

```text
ヒューリスティック上位3手
+ 最良ATTACH
+ 最良ATTACK
+ 最良Supporter
+ 最良RetreatまたはEND
```

重複除外後、最大6候補程度に制限する。

成功条件:

- Candidate Coverage Rateが改善
- 計算時間が許容範囲
- 勝率だけでなくcritical regretが低下

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

最初の改修はFull ISMCTSではなく **Weighted Determinization** とする。

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

- First Persistent Critical Divergence候補のランキング
- レビュー対象の優先順位付け
- 数ターン前の資源判断へのcredit assignment

注意:

- contribution scoreは因果関係の確定ではない
- 必ず反実仮想評価と人間レビューで検証する
- RUDDER全体を本番RLとして実装せず、まずオフライン分析に限定する

---

# Part IV: 探索時間とメタ推論

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

# Part V: 検証手順

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

- Common Random Numbers
- 対応あり比較
- mirror + 強敵
- 事前に採用条件を固定

## 22. 300戦以上の最終確認

複数相手へ同一方策で評価する。

```text
fitness
  = 0.7 * 全相手平均勝率
  + 0.3 * 最悪相手勝率
```

ただし、fitnessだけで採用せず、各相手の勝率・信頼区間・regret・時間を個別保存する。

---

# Part VI: PR分割

## PR0-A — Parameter Contract + Strict Telemetry

**方策変更なし。最初に実施する。**

追加:

- 全パラメータのACTIVE / EXPERIMENTAL / DEPRECATED / UNUSED / SHADOWED分類
- ハードコードスコア一覧
- Runtime Overrideの到達経路テスト
- PRODUCTION / BENCHMARK / DEBUGモード
- search・rollout・fallback・例外Telemetry

完了条件:

- 未使用・競合キーがレポートされる
- BENCHMARKで未分類例外を隠さない
- 現行の選択行動が変わらない

## PR0-B — Deterministic Replay

**方策変更なし。**

追加:

- stable hashによる局面・行動・hidden state・rollout単位seed
- Replay Bundle保存
- 同一局面のCLI再生
- Common Random Numbers対応

完了条件:

- 同一bundleを反復して完全再現できる
- 旧版・新版で同一乱数条件を共有できる

## PR0-C — Evaluator Unification（挙動保存）

**計算経路を統合するが、選択行動は変えない。**

追加:

- 共通Feature Schema
- 共通評価インターフェース
- 旧評価とのshadow diff
- 固定局面golden tests

完了条件:

- 旧版と全golden局面の選択が一致
- 同義特徴・重複評価が一覧化される

## PR1 — Decision Audit基盤

方策変更なし。

追加:

- candidate coverageログ
- rollout成功・失敗数
- hidden-state別価値
- mean/std/quantile
- hidden-state flip率
- regret推定
- constraint violation flags
- multi-head shadow values
- opponent threat shadow values
- budget sensitivity
- decision runtime
- JSONL出力
- 単体テスト

採用条件:

- 現行行動が変わらない
- 同一Replay Bundleで再現可能
- 本番経路のオーバーヘッドがほぼない
- 既存テストがすべて通る

## PR2 — Audit Report / Human Review

追加:

- 敗戦100 + 勝利100分析CLI
- 原因構成比
- 高regret局面一覧
- 人間レビュー画面
- rollout評価の校正レポート
- 次に進むBranchの提案

## PR3-A — Search Cache / Transposition Experiment

重複盤面率が十分高い場合だけ実施。

比較:

- cacheなし
- exact-state cache
- 可換行動の代表化あり

採用条件:

- 固定局面の選択が一致
- p95時間またはunique state評価数が改善
- hidden stateを跨いだ誤共有がない

## PR3-B — Search Allocation Experiment

Auditで探索予算不足が確認された場合だけ実施。

比較:

- UCB1
- Sequential Halving
- Simple-regret型

総rollout数は固定。

## PR4-A — Tactical Safety Layer

constraint flagの人間精度が十分高い場合だけ実施。

順序:

1. ログのみ
2. soft penalty
3. 確定情報に限るhard constraint

## PR4-B — Multi-head Evaluator

評価誤差・攻撃継続誤差が主要原因の場合だけ実施。

- attack continuity
- next attacker readiness
- prize tempo
- survival risk
- resource value

を分離して評価する。

## PR4-C — Search Override Confidence Gate

探索の不確実性やfallbackが問題の場合に実施。

- minimum samples
- value gap
- best probability
- error rate
- calibration

で上書きを制御する。

## PR5 — Safe Learned Correction

Auditで評価誤差または分布外が確認された場合だけ実施。

- afterstate value / ranking model
- ensemble uncertainty
- calibration
- SPIBB型baseline fallback

## PR6 — Credit Assignment

First Persistent Critical Divergenceの抽出精度が低い場合だけ実施。

- RUDDER型return contribution
- 反実仮想評価との照合
- 人間レビュー

## PR7-A — Lightweight Opponent Threat Model

相手の返し評価が主要原因の場合に実施。

- active KO
- bench KO
- gust
- evolution spike
- expected max damage

を公開情報から予測する。

## PR7-B — Weighted Determinization

hidden-state flipが主要原因の場合だけ実施。

- 公開情報からbeliefを生成
- 重み付きhidden state評価
- 現行uniform determinizationとの比較

## PR8 — Deck–Agent Co-optimization

方策改善後も構造的な攻撃回数差が残る場合だけ実施。

- 固定枠48〜52枚
- 可変枠8〜12枚
- デッキ固定 / 方策固定を交互に比較
- ユーザーの明示承認を必須とする

## PR9以降

診断結果と前段の成功を条件に検討。

- Full ISMCTS
- Public Belief State
- POMCP
- ReBeL型設計
- Set Transformer
- Macro action
- 大規模方策学習

---

# Part VII: 論文・書籍マップ

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
- First Persistent Critical Divergenceの候補抽出に使う

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

# Part VIII: 文献から見た推奨実施順

## 26. 現時点の優先順位

```text
0. Parameter Contract Audit + Strict Benchmark Mode
1. Deterministic Replay + Common Random Numbers
2. Evaluator Unification（挙動保存）
3. Decision Audit
4. 人間校正
5. 原因別の最小改修
6. Search Cache / Transposition（重複率が高い場合）
7. Tactical Safety Layer（flag精度が高い場合）
8. Multi-head Evaluator
9. Search Override Confidence Gate
10. Simple Regret / Sequential Halving
11. SPIBB型baseline fallback
12. Ensemble uncertainty + calibration
13. Lightweight Opponent Threat Model
14. RUDDER型credit assignment
15. Weighted Determinization
16. afterstate learned value
17. Critical-Regret DAgger
18. Deck–Agent Co-optimization
19. Full ISMCTS / Public Belief State
20. POMCP / ReBeL型設計
21. Set Transformer / 大規模学習
```

最初の3項目は性能手法ではなく、以降の結果を信用するための土台である。順位は固定せず、敗戦100件 + 勝利100件の原因構成比で変更する。

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
3. Evaluator Unification
4. Search Cache
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

# Part IX: 保留・非推奨

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

# Part X: Codexへ渡す依頼

## 29. 最初の依頼 — 実装基盤監査のみ

```text
pokemon_aiリポジトリの現行Raging Boltエージェントについて、
性能改善アルゴリズムはまだ実装せず、次の3点だけを調査してください。

A. Evaluator Unification
- evaluate_state()
- _eval_search_state()
- _estimate_action_impact()
- 行動別ヒューリスティック
- Value Model / Counterfactual Analyzerの特徴量

これらの入力、出力、特徴量、符号、単位、呼び出し経路、重複を一覧化してください。
最初は挙動を変えず、共通Feature Schemaへ統合する計画だけを作成してください。

B. Parameter Contract Audit
- params.jsonの全キー
- コード内default
- ハードコード値
- Runtime Override

をACTIVE / EXPERIMENTAL / DEPRECATED / UNUSED / SHADOWED / DUPLICATEへ分類してください。
変更した値がheuristic、engine search、fallback、Live Tuning Panelのどこへ効くか追跡してください。

C. Strict Benchmark / Deterministic Replay
- PRODUCTION / BENCHMARK / DEBUGモード案
- search・rollout・fallback・例外Telemetry
- stable hashによるgame/state/action/hidden-state/rollout単位seed
- Replay Bundleスキーマ
- Common Random Numbersで旧版と新版を比較する方法

必須条件:
- 方策を変更しない
- main.py / params.json / deck.csvの本番挙動を変えない
- 新規探索、Value Model、DAgger、ISMCTSを実装しない
- 既存テストと固定局面golden testの追加案を示す
- 既存機能との重複と移行リスクを明記する

成果物:
1. 現状アーキテクチャ図
2. 評価経路マトリクス
3. パラメータ監査表
4. Replay Bundle案
5. 実行モードとTelemetry案
6. PR0-A / PR0-B / PR0-Cの分割計画
7. 挙動保存の検証方法

まだコードを変更せず、調査結果と実装計画だけを提示してください。
```

## 30. Decision Audit基盤の依頼 — 調査と実装計画のみ


```text
pokemon_aiリポジトリの現行Raging Boltエージェントについて、
性能改善アルゴリズムはまだ実装せず、Decision Audit基盤の実装計画だけを作成してください。

目的は、現在の判断ミスが以下のどれに由来するかを測定することです。

1. 探索候補漏れ
2. 盤面評価関数の誤差
3. hidden state推定の誤差
4. AIが人間ログにない局面へ到達する分布外問題
5. 探索予算不足
6. rollout policyのbias
7. 同価値の別手を誤り扱いしている問題
8. 学習モデルの不確実性・未校正

必須条件:
- 現行エージェントの行動結果を変更しない
- main.py、params.json、deck.csvの本番挙動を変更しない
- ISMCTS、POMCP、DAgger、Value Model統合はまだ実装しない
- 特定の相手agent名・デッキ名による分岐を追加しない
- 既存のCounterfactual Analyzer、Human Trace、Disagreement Review、engine searchを再利用する

各MAIN判断について、オフライン分析時に以下を記録できるようにしてください。

- state_id
- selected_action
- human_action
- legal_actions
- heuristic順位
- engine search候補
- candidate coverage failure
- 各候補のhidden-state別rollout値
- 候補ごとのmean/std/median/quantile
- best_action_probability
- estimated_regret
- regret confidence interval
- hidden_state_flip_rate
- rollout_success_count
- rollout_error_count
- budget sensitivity
- runtime_ms
- final_result
- final_prize_diff

評価は二段階にしてください。

Stage 1:
- 上位3候補
- hidden state 4種類
- rollout seed 1種類

Stage 2:
高regret、上位僅差、hidden-state flip、人間との不一致、敗戦経路上、
Boss、Retreat、確定KO、エネルギー大量消費の局面だけを対象に、
- 上位2〜3候補
- hidden state 8種類
- rollout seed 2種類

「不可逆な乖離」と断定せず、
first_persistent_critical_divergence_candidate
として記録してください。

成果物:
1. 現行コード調査
2. 既存機能との重複一覧
3. 再利用可能な関数一覧
4. 実装計画
5. 変更対象ファイル一覧
6. JSONLスキーマ
7. 計算量見積もり
8. 失敗条件
9. 単体テスト計画
10. 既存挙動が変わらない回帰テスト計画

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
- First Persistent Critical Divergenceが遅くなる
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
