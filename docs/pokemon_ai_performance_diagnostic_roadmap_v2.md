# ポケカAI 性能改善・診断ロードマップ v2

更新日: 2026-07-26  
対象リポジトリ: `hattorishotap65-blip/pokemon_ai`  
対象エージェント: Raging Bolt ex + Teal Mask Ogerpon ex  
位置づけ: 方策を一度に大改造せず、診断結果に応じて最小の変更を選ぶための実装・研究メモ

## 0. 結論

最初に実装するのはISMCTS、DAgger、Value Model、POMCPではない。
最優先は、現行エージェントの判断ミスを次の原因へ分解できるDecision Audit基盤である。

1. 探索候補漏れ
2. 盤面評価関数の誤差
3. hidden state推定の誤差
4. 人間データにない分布外局面
5. 探索予算不足
6. rollout policyのbias
7. 同価値の別手を誤り扱いしている
8. 学習モデルの不確実性を無視している

診断後、原因に応じて改修を1つずつ行う。

| 原因 | 改修候補 |
|---|---|
| 候補漏れ | 行動タイプ別候補保証 |
| 評価誤差 | 評価特徴改善 / afterstate value |
| hidden state誤差 | Weighted Determinization / Public Belief State |
| 分布外 | Critical-Regret DAgger |
| 重要度不足 | Regret-weighted ranking |
| 探索予算不足 | Simple Regret / Sequential Halving |
| 学習値の不確実性 | SPIBB型fallback / ensemble gate / calibration |
| 時間方向の原因特定 | RUDDER型return decomposition |

全面的なDeep RL、Full ISMCTS、POMCP、MAP-Elitesなどは、診断結果が必要性を示した場合だけ進める。

## 1. 現状認識

現行エージェントは次を組み合わせたデッキ特化型ハイブリッドAIである。

- デッキ固有のヒューリスティック
- エンジンAPIによる浅い先読み
- 線形盤面評価
- hidden stateの再サンプリング
- UCB1による追加rollout配分
- Human Trace / Disagreement Review
- Counterfactual Analyzer
- Live Tuning Panel
- Value Modelの実験基盤

主な問題候補:

- 相手の手札・山札・サイドの推定が粗い
- rolloutのleaf評価が正しい保証がない
- ヒューリスティック上位候補から最善手が漏れる可能性がある
- 人間との不一致30%に、等価手と致命的判断が混在している
- AI自身の誤りによって、人間トレースにない盤面へ進む
- 現行UCB1は最終的な1手選択より累積regret寄りの配分である
- 学習モデルを使う場合、低信頼局面で退行する危険がある
- 敗戦直前ではなく、数ターン前の資源判断が真因の場合がある

## 2. 最終目的

目的は、人間との完全一致率を上げることではない。

> 勝敗へ影響する最初の重大な判断ミスを特定し、その原因へ最小の変更を当て、複数の相手に同じ方策で改善する。

改善対象:

- 確定KOを逃す
- Bossの使用時機を誤る
- 攻撃後に次のアタッカーが止まる
- エネルギーを過剰消費する
- 回収対象を誤る
- ベンチ枠を低価値なポケモンで埋める
- Retreatすべき局面で残る
- Retreat不要な局面で資源を使う
- 相手の返しのKOを過小評価する
- 序盤展開が遅れ、総攻撃回数を失う

改善対象としないもの:

- 人と違うが期待価値がほぼ同じ手
- 相手agent名を見て専用分岐する実装
- 少数ベンチマークにだけ勝つパラメータ
- 一致率だけを上げ、勝率やregretが改善しない変更

# Part I: 評価基盤

## 3. Phase 0 — Baselineの固定

固定する情報:

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

### 3.1 A/Aテスト

同一エージェントを同一条件で比較し、評価基盤自体のノイズを確認する。

- 勝率
- 先攻・後攻別勝率
- 同一seed結果一致率
- paired win/loss/tie
- 1手p50/p95/p99時間
- ゲーム全体p50/p95時間
- 探索fallback率
- rollout失敗率
- candidate count

### 3.2 Common Random Numbers

旧版と新版で可能な限り共通化する。

- 初期山札順
- サイド配置
- 先後
- 相手側の乱数系列
- hidden stateの乱数系列
- rollout seed

独立2標本だけでなく、同一seedペアの差を解析する。

### 3.3 固定League

最低限、戦い方の異なる複数相手を評価に使う。

- top_lucario_1084
- dragapult
- megastarmie
- 現行Raging Bolt
- 過去の安定Raging Bolt

Leagueは評価と過適合検出にのみ使う。実戦方策は相手名・デッキ名を入力にしない。

## 4. Phase 1 — Decision Audit

### 4.1 目的

現在の判断ミスが次のどこにあるかを判定する。

- A: 最善手が探索候補に入っていない
- B: 候補には入っているが評価関数が誤る
- C: hidden stateによって最善手が変わる
- D: AIが人間ログにない盤面へ到達する
- E: rollout予算を増やすと改善する
- F: rollout予算を増やすほど悪化する
- G: 人間と違うが等価な手を誤りとして数えている
- H: 学習モデルの高確信が実際には校正されていない

### 4.2 対象データ

初回診断:

- 敗戦100ゲーム
- 勝利100ゲーム

敗戦だけを見ると、勝利時にも発生する無害な乖離を重大と誤認するため、勝利対局も比較する。

原則MAINコンテキストを対象とし、以下の選択コンテキストも追跡する。

- Energy Retrievalの回収対象
- Ultra Ball等のdiscard対象
- Bellowing Thunderのエネルギー消費
- Bossの対象
- Retreat先
- サーチ対象

### 4.3 二段階の反実仮想評価

Stage 1:

- 候補: 上位3手
- hidden state: 4種類
- rollout seed: 1種類
- 最大12評価/判断

Stage 2対象条件:

- 推定regretが大きい
- 上位2手が僅差
- hidden stateで最善手が変わる
- 人とAIが不一致
- 敗戦経路上
- 確定KO、Boss、Retreat、大量エネルギー消費を含む
- モデル不確実性が高い
- 探索fallbackが発生した

Stage 2:

- 候補: 上位2〜3手
- hidden state: 8種類
- rollout seed: 2種類
- 最大48評価/判断

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
  "first_persistent_critical_divergence_candidate": false,
  "return_contribution_score": null,
  "final_result": "",
  "final_prize_diff": 0,
  "decision_runtime_ms": 0,
  "game_runtime_ms": 0
}
```

## 5. 評価指標

- Mean Critical Regret
- P90 Critical Regret
- Fatal Mistakes / Game
- Candidate Coverage Rate
- Hidden-state Flip Rate
- Human–Rollout Rank Agreement
- Best-arm Identification Accuracy
- First Persistent Critical Divergence
- Recovery Rate
- Baseline Fallback Rate
- Calibration Error
- Win Rate
- p95 Decision Time

単純な人間行動一致率は補助指標へ下げる。

### 5.1 最初の継続的重大乖離

「不可逆」と断定しない。

```text
mean_value_gap >= delta
alternative_improvement_probability >= 0.70
later_recovery_probability <= 0.30
```

`delta`は固定値ではなく、A/Aで観測した評価ノイズを基準に決める。

# Part II: 人間レビューと診断分岐

## 6. Phase 2 — 評価関数の人間校正

現在の評価関数でregretを作り、それを教師にすると、評価誤差を自己増幅する可能性がある。学習前に固定局面で人間校正を行う。

初回レビュー100局面:

- 高regret: 40
- hidden-state flip率が高い: 20
- AIと人が不一致: 20
- AIと人が一致したが敗戦に寄与: 20

ラベル:

- Aが明確に良い
- Bが明確に良い
- ほぼ同等
- どちらも悪い
- 判断不能

校正が不合格なら、regret学習より先に評価関数・状態特徴を修正する。

## 7. 原因別の改修Branch

### Branch A — Candidate Coverage

発動条件:

- 探索候補外に最良手が存在する割合が重大局面の10%以上

改修:

```text
ヒューリスティック上位3手
+ 最良ATTACH
+ 最良ATTACK
+ 最良Supporter
+ 最良RetreatまたはEND
```

重複除外後、最大6候補程度。

### Branch B — Evaluator Error / Afterstate Value

発動条件:

- Human–Rollout Rank Agreementが低い
- rollout予算を増やしても人間順位へ近づかない
- 資源消費後の再攻撃可能性を誤る

改修順:

1. 特徴量の不足と重複を確認
2. 攻撃後の資源機会費用
3. 後続アタッカー確保
4. サイドレース・次回攻撃までのターン数
5. afterstate learned valueを少量混合

```text
final_value = heuristic_value + alpha * learned_afterstate_value
alpha = 0 / 0.05 / 0.10 / 0.20
```

対局単位split、相手アーキタイプholdout、時系列holdout、baseline commit holdoutを行う。

### Branch C — Hidden State Error

最初の改修はFull ISMCTSではなくWeighted Determinization。

公開情報:

- 場とトラッシュ
- 公開エネルギー
- 使用済みサポート・グッズ
- 進化状況
- 山札・手札枚数
- 対戦中の行動履歴

```text
action_value = Σ hidden_state_weight * rollout_value
```

改善が確認された場合のみ、Public Belief State、情報集合統計、tree reuse、Full ISMCTS、POMCPへ進む。

### Branch D — OOD / Critical-Regret DAgger

発動条件:

- 重大判断ミスの30%以上が既存人間トレースに類似局面のない状態で発生

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

### Branch E — Regret-weighted Action Ranking

```text
state
preferred_action
non_preferred_action
regret_gap
human_intent
```

```text
score(preferred) > score(non_preferred)
pair_weight = clip(regret_gap, min_weight, max_weight)
```

`best_value - action_value <= epsilon`を同一正解集合へ含める。

### Branch F — Search Budget / Best-Arm Identification

比較:

- A: 現行UCB1
- B: Sequential Halving
- C: Simple-regret型2段階配分
- D: VOI近似による早期停止

固定総予算:

- 12 / 20 / 32 rollouts

評価:

- Best-arm Identification Accuracy
- Mean / P90 regret
- hidden-state別安定性
- p95時間
- League勝率

改善確認後、必要に応じてProgressive Biasを使う。

### Branch G — Safe Policy Improvement

SPIBBの考え方を設計原則として使う。

```python
if support_count < minimum_support:
    use_baseline_policy()
elif model_uncertainty > threshold:
    use_baseline_policy()
elif calibrated_confidence < threshold:
    use_baseline_policy()
else:
    use_small_learned_correction()
```

元論文の安全性保証を現在のゲームへそのまま主張しない。

### Branch H — Uncertainty / Calibration

Deep Ensemble:

```text
learned_value = ensemble_mean
uncertainty = ensemble_std
```

記録:

- Brier score
- log loss
- Expected Calibration Error
- reliability diagram
- opponent holdout calibration
- OOD vs in-distribution uncertainty

Temperature Scalingなどはvalidationデータだけで調整する。

### Branch I — Delayed Credit / RUDDER型分析

```text
対局中の判断列
-> 最終勝敗 / 最終サイド差を予測
-> 予測値が大きく変化した判断を抽出
-> 反実仮想rolloutと人間レビューで確認
```

保存値:

- predicted win probability before/after action
- return contribution score
- action category
- estimated counterfactual regret
- human confirmation

contribution scoreは因果関係の確定ではない。RUDDER全体を本番RLとして実装せず、まずオフライン分析に限定する。

# Part III: 探索時間とメタ推論

## 8. 探索予算の制御

追加探索条件:

- 上位2手が僅差
- hidden-state flip率が高い
- Boss使用
- Retreat
- 確定KO候補
- 大量エネルギー消費
- 残りサイド2以下
- 返しで敗北する可能性
- モデルとヒューリスティックが不一致
- ensemble uncertaintyが中程度

早期終了:

```text
best_lower_confidence_bound
  > second_upper_confidence_bound + margin
```

時間上限:

- 通常局面: 現行p95以内
- 重要局面: 現行p95の1.5倍以内
- ゲーム全体: 現行比1.25倍以内

メタ推論:

```text
expected_value_of_computation
  = expected_decision_improvement - computation_cost
```

# Part IV: 検証手順

## 9. 固定局面テスト

- 通常局面
- 確定KO
- Boss
- Retreat
- 攻撃後再装填
- 資源回収
- hidden-state依存
- 分布外
- 終盤
- 候補漏れ

## 10. 30戦スクリーニング

改善確認ではなく大退行の除外に使う。

- 違法手
- 例外
- タイムアウト
- fallback急増
- 明白な勝率崩壊
- 1手時間超過

## 11. 100戦確認

- Common Random Numbers
- 対応あり比較
- mirror + 強敵
- 採用条件を事前固定

## 12. 300戦以上の最終確認

```text
fitness
  = 0.7 * 全相手平均勝率
  + 0.3 * 最悪相手勝率
```

fitnessだけで採用せず、各相手の勝率、信頼区間、regret、時間を個別保存する。

# Part V: PR分割

## PR1 — Decision Audit基盤

方策変更なし。

- candidate coverageログ
- rollout成功・失敗数
- hidden-state別価値
- mean/std/quantile
- hidden-state flip率
- regret推定
- budget sensitivity
- decision runtime
- JSONL出力
- 単体テスト

採用条件:

- 現行行動が変わらない
- 同一seedで再現可能
- 本番経路のオーバーヘッドがほぼない
- 既存テストがすべて通る

## PR2 — Audit Report / Human Review

- 敗戦100 + 勝利100分析CLI
- 原因構成比
- 高regret局面一覧
- 人間レビュー画面
- 次に進むBranchの提案

## PR3 — Search Allocation Experiment

探索予算不足が確認された場合のみ。

- UCB1
- Sequential Halving
- Simple-regret型
- 総rollout数固定

## PR4 — Safe Learned Correction

評価誤差または分布外が確認された場合のみ。

- afterstate value / ranking model
- ensemble uncertainty
- calibration
- SPIBB型baseline fallback

## PR5 — Credit Assignment

First Persistent Critical Divergenceの抽出精度が低い場合のみ。

- RUDDER型return contribution
- 反実仮想評価との照合
- 人間レビュー

## PR6 — Weighted Determinization

hidden-state flipが主要原因の場合のみ。

- 公開情報からbeliefを生成
- 重み付きhidden state評価
- 現行uniform determinizationとの比較

## PR7以降

- Full ISMCTS
- Public Belief State
- POMCP
- ReBeL型設計
- Set Transformer
- tree reuse
- Macro action

# Part VI: 論文・書籍マップ

## 13. 最優先で読む論文

1. Tolpin & Shimony, [MCTS Based on Simple Regret](https://doi.org/10.1609/aaai.v26i1.8126), AAAI 2012
2. Karnin, Koren, Somekh, [Almost Optimal Exploration in Multi-Armed Bandits](https://proceedings.mlr.press/v28/karnin13.html), ICML 2013
3. Laroche et al., [Safe Policy Improvement with Baseline Bootstrapping](https://proceedings.mlr.press/v97/laroche19a.html), ICML 2019
4. Castellini et al., [Scalable Safe Policy Improvement via Monte Carlo Tree Search](https://proceedings.mlr.press/v202/castellini23a.html), ICML 2023
5. Arjona-Medina et al., [RUDDER](https://proceedings.neurips.cc/paper/2019/hash/16105fb9cc614fc29e1bda00dab60d41-Abstract.html), NeurIPS 2019
6. Lakshminarayanan et al., [Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles](https://proceedings.neurips.cc/paper_files/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html), NeurIPS 2017
7. Guo et al., [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html), ICML 2017

## 14. 中期的に読む論文

1. Cowling et al., [Information Set Monte Carlo Tree Search](https://doi.org/10.1109/TCIAIG.2012.2200894), 2012
2. Silver & Veness, [POMCP](https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps.pdf), 2010
3. Brown et al., [ReBeL](https://proceedings.neurips.cc/paper/2020/hash/c61f571dbd2fb949d3fe5ae1608dd48b-Abstract.html), NeurIPS 2020
4. Lee et al., [Set Transformer](https://proceedings.mlr.press/v97/lee19d.html), ICML 2019
5. Ross, Gordon, Bagnell, DAgger, 2011
6. Peng et al., [Advantage-Weighted Regression](https://arxiv.org/abs/1910.00177), 2019
7. Sutton & Barto, *Reinforcement Learning: An Introduction*, 2nd ed.; Tesauro, *Temporal Difference Learning and TD-Gammon*, 1995

## 15. おすすめ書籍

1. Russell & Wefald, [Do the Right Thing](https://mitpress.mit.edu/9780262513821/do-the-right-thing/)
2. Fu編, [Handbook of Simulation Optimization](https://link.springer.com/book/10.1007/978-1-4939-1384-8)
3. Bechhofer, Santner, Goldsman, [Design and Analysis of Experiments for Statistical Selection, Screening, and Multiple Comparisons](https://www.asc.ohio-state.edu/santner.1/REB-TJS-DMG/describe.html)
4. Lattimore & Szepesvári, *Bandit Algorithms*
5. Kochenderfer, Wheeler, Wray, *Algorithms for Decision Making*

# Part VII: 文献から見た推奨実施順

## 16. 現時点の優先順位

0. A/A + Common Random Numbers
1. Decision Audit
2. 人間校正
3. 原因別の最小改修
4. Simple Regret / Sequential Halving
5. SPIBB型baseline fallback
6. Ensemble uncertainty + calibration
7. RUDDER型credit assignment
8. Weighted Determinization
9. afterstate learned value
10. Critical-Regret DAgger
11. Full ISMCTS / Public Belief State
12. POMCP / ReBeL型設計
13. Set Transformer / 大規模学習

順位は固定せず、敗戦100件 + 勝利100件の原因構成比で変更する。

例A:

```text
candidate coverage      35%
evaluator error         30%
out-of-distribution     20%
hidden state error      10%
search budget            5%
```

優先: Candidate Coverage → Evaluator → DAgger → Weighted Determinization

例B:

```text
hidden state error      45%
evaluator error         25%
search budget           20%
その他                  10%
```

優先: Weighted Determinization → Evaluator → Simple Regret / Sequential Halving → ISMCTS

例C:

```text
equivalent action       50%
importance weighting    25%
OOD                     15%
その他                  10%
```

優先: 複数正解ランキング → Regret-weighted ranking → DAgger

# Part VIII: 保留・非推奨

## 17. 診断なしで実装しないもの

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

## 18. 実験上の注意

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

# Part IX: Codexへ渡す依頼

## 19. 最初の依頼 — 調査と実装計画のみ

```text
pokemon_aiリポジトリの現行Raging Boltエージェントについて、
性能改善アルゴリズムはまだ実装せず、Decision Audit基盤の実装計画だけを作成してください。

測定する原因:
1. 探索候補漏れ
2. 盤面評価関数の誤差
3. hidden state推定の誤差
4. 人間ログにない分布外問題
5. 探索予算不足
6. rollout policyのbias
7. 同価値の別手を誤り扱いする問題
8. 学習モデルの不確実性・未校正

本番挙動を変更せず、既存Counterfactual Analyzer、Human Trace、
Disagreement Review、engine searchを再利用してください。

Stage 1: 上位3候補 × hidden state 4 × seed 1
Stage 2: 重要局面のみ、上位2〜3候補 × hidden state 8 × seed 2

「不可逆」と断定せず、
first_persistent_critical_divergence_candidateとして記録してください。

成果物:
現行調査、重複一覧、再利用関数、実装計画、変更ファイル、
JSONLスキーマ、計算量、失敗条件、単体テスト、回帰テスト計画。

まだコードを変更しないでください。
```

## 20. Search Allocation実験

Decision Auditで探索予算不足が主要原因と確認された場合だけ使用する。

- 現行UCB1
- Sequential Halving
- Simple-regret型2段階配分
- 総rollout数12 / 20 / 32で固定
- candidate set、hidden state、seedを共通化
- 固定局面テストのみ
- 本番方策へ未反映

## 21. Safe Learned Correction

- support_count不足でbaselineへ戻る
- ensemble varianceが高ければbaselineへ戻る
- validationでcalibration
- alpha=0/0.05/0.1/0.2
- 相手単位holdout・対局単位split
- fallback率とworst-case勝率を記録
- 理論保証の直接適用を主張しない

## 22. RUDDER型分析

- predicted win probability before/after action
- return contribution score
- counterfactual regret
- action category
- human review label

contribution scoreを因果効果とは扱わず、反実仮想rolloutと人間レビューで検証する。

## 23. 最終判断基準

採用条件:

- Mean / P90 Critical Regretが改善
- Candidate Coverageが改善、または原因が解消
- First Persistent Critical Divergenceが遅くなる
- 攻撃回数・再攻撃率が改善
- 多様な相手への平均・worst-case勝率が改善
- 特定相手用分岐を含まない
- p95時間とゲーム全体時間が制限内
- fallback・例外・timeoutが悪化しない

不採用条件:

- 一致率だけ上がる
- mirrorだけ改善する
- 1つの相手だけ改善する
- 固定局面だけ改善し対戦で再現しない
- 学習モデルが高確信で大退行する
- rollout予算を増やすほどregretが悪化する
- 計算時間が許容範囲を超える

## 24. 要点

高度な手法を順番に実装するのではない。

1. まず原因を測る
2. 原因に最も近い最小改修を1つ入れる
3. 同じ計算量・同じ乱数条件で比較する
4. 不確実な局面ではbaselineへ戻す
5. 最終的な1手選択と、勝敗に寄与した最初の重大判断を重視する
