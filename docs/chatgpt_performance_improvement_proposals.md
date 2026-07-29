# ChatGPTからの性能改善提案メモ

更新日: 2026-07-26

## 背景

- 現在は Kohavi の書籍を参考に A/A テストを実施中。
- Kohavi は主に「改善を正しく測る」ために使う。
- 次は「何を改善候補にするか」を増やす。
- 現行エージェントの構成は、ルールベースのヒューリスティック、浅い先読み、UCB1、対戦ログ分析。
- 現状の主な課題候補は、探索回数そのものよりも以下。
  - 相手の手札・山札など、隠れ状態の推定誤差
  - 盤面評価関数の誤差
  - 初回攻撃と再攻撃までの遅さ
  - 限られた探索予算の配分

## 優先度の高い改善テーマ

### 1. Information Set Monte Carlo Tree Search

参考:

- Cowling, Powley, Whitehouse, "Information Set Monte Carlo Tree Search", 2012
- https://doi.org/10.1109/TCIAIG.2012.2200894
- https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf

提案:

- 相手の手札や山札を1通りに決め打ちせず、複数のあり得る hidden state を生成する。
- 各 hidden state で行動を評価し、同一の情報集合として価値を集約する。
- 相手デッキの既知情報に合う状態ほど高い重みを付ける。

最初の比較:

- A: 現行の単一hidden-state推定
- B1: 4サンプル
- B2: 8サンプル
- B3: 相手デッキ推定による重み付き4サンプル

見る指標:

- 対戦勝率
- Boss使用後のKO率
- 攻撃エネルギー消費後の返しのKO率
- Energy Retrievalなど資源回収の選択品質
- 1手あたりp95実行時間

### 2. POMCP型のbelief / particle管理

参考:

- Silver and Veness, "Monte-Carlo Planning in Large POMDPs", 2010
- https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps.pdf

提案:

- 相手の手札・山札・エネルギー構成をparticle集合として持つ。
- 相手がカードを公開・使用するたびにparticleの重みを更新する。
- デッキタイプ、残りエネルギー、次ターン最大打点を確率分布として扱う。

期待する効果:

- ベンチダメージとKOリスクの推定改善
- 過剰な守備行動の削減
- Boss、Retreat、エネルギー消費判断の改善

### 3. 対局ログからafterstate valueを学習

参考:

- Sutton and Barto, "Reinforcement Learning: An Introduction", 2nd ed.
- Tesauro, "Temporal Difference Learning and TD-Gammon", 1995
- https://mitpress.mit.edu/9780262039246/reinforcement-learning/
- https://doi.org/10.1145/203330.203343

提案:

1. 意思決定直後の盤面特徴と最終勝敗を保存する。
2. 線形モデル、LightGBMなど軽量モデルで盤面価値を学習する。
3. まず既存ヒューリスティックを置換せず、補正値として混ぜる。

比較:

- `final_value = heuristic + alpha * learned_value`
- `alpha = 0, 0.05, 0.1, 0.2`

注意:

- 同じ対戦ログを学習と評価の両方に使わない。
- 対戦単位でtrain/validation/testを分割する。
- 相手デッキ単位のholdout評価も行う。

### 4. UCB1の係数調整からProgressive Biasへ進む

参考:

- Browne et al., "A Survey of Monte Carlo Tree Search Methods", 2012
- https://doi.org/10.1109/TCIAIG.2012.2186810

提案:

- 現在のヒューリスティックスコアを探索のpriorとして利用する。
- 訪問回数が少ない間はpriorを強く使い、探索が進むほど実測rollout価値を優先する。
- 明らかに弱い行動を探索から除外する安全なmove pruningも比較する。

候補:

- Progressive bias
- Progressive widening
- Transposition table
- 同一ターン内のtree reuse
- heuristic-guided rollout

### 5. Macro action

提案:

- 1アクション単位だけでなく、戦術的な一連の行動を探索候補にする。

例:

- サーチ → ベンチ展開 → エネルギー加速
- Energy Retrieval → Teal Dance → ATTACH → 攻撃
- Boss → 攻撃 → KO
- 逃げる → 後続アタッカーで攻撃

期待する効果:

- 探索深度が浅くてもコンボの最終価値を認識できる。
- 中間状態だけを見ると低評価になる行動列を発見できる。

### 6. 局面重要度による探索予算配分

参考:

- Lattimore and Szepesvári, "Bandit Algorithms"
- Kochenderfer, Wheeler, Wray, "Algorithms for Decision Making"
- https://www.cambridge.org/core/books/bandit-algorithms/8E39FD004E6CE036680F90DD0C6F09FC
- https://mitpress.mit.edu/9780262047012/algorithms-for-decision-making/

提案:

- 全局面で同じrollout数を使わない。
- 候補上位2手の価値差が小さい局面へ追加予算を与える。
- 攻撃、Boss、Retreat、最終サイド、エネルギー大量消費を重要局面とする。
- 明白な行動は早期終了する。

## 中長期の候補

- 探索結果を軽量方策へ蒸留するExpert Iteration
- 相手デッキタイプ別の評価関数・方策
- 勝敗期待値だけでなく結果分布を扱うDistributional RL
- opponent modelを使った相手行動rollout
- 探索木のtransposition共有
- デッキ未知時のオンラインデッキタイプ推定

全面的なDeep RLへの置換は現時点では優先しない。まず既存ヒューリスティックを活かせる補正・探索改善から試す。

## 実験方法の補足

### Common Random Numbers

参考:

- Yang and Nelson, "Using Common Random Numbers and Control Variates in Multiple-Comparison Procedures", 1991
- https://doi.org/10.1287/opre.39.4.583

旧版と新版で以下を可能な限り共通化する。

- 初期乱数
- 山札順
- 先後
- 相手側の乱数系列
- hidden-stateサンプルの乱数系列

これによりA/B差の分散を減らし、少ない試合数で差を検出しやすくする。解析は独立した勝率2標本ではなく、対応のある比較として扱う。

## 推奨実施順

1. A/AとCommon Random Numbersによる評価基盤の確認
2. ISMCTS 4サンプル
3. Progressive bias
4. afterstate learned valueを5〜10%混合
5. particle belief
6. macro action
7. 局面別探索予算

最初に同時実装せず、各テーマを単独でablationする。

## Claude Codeへ渡す依頼例

```text
このメモの「1. Information Set Monte Carlo Tree Search」だけを対象にしてください。
まだ実装せず、現行コードへの最小導入案、変更候補ファイル、状態サンプルの生成方法、
計算量、失敗条件、A/AおよびA/B検証計画を作成してください。
既存ヒューリスティックとUCB1は維持し、他テーマへ進まないでください。
```

```text
このメモの「3. 対局ログからafterstate valueを学習」だけを対象にしてください。
データリークを防ぐ分割方法、特徴量、教師信号、既存評価値との混合方法、
alpha=0/0.05/0.1/0.2の比較計画を提案してください。
まだ本番方策には組み込まないでください。
```

## 再開時の判断

最も期待値が高い最初の性能改善候補は `ISMCTS 4サンプル`。
次点は `afterstate learned valueをalpha=0.05〜0.1で補正利用`。
前者は隠れ情報の誤差、後者は盤面評価の誤差を独立に検証できる。

---

## 追加提案: 特定相手に依存しない性能改善

### 設計原則

特定の相手agentやデッキを識別して専用ロジックへ分岐する実装は採用しない。
多様な相手は評価集合としてのみ利用し、実戦では全相手に同一方策を使う。

入力に使ってよい情報:

- 現在観測できる盤面
- 公開されたカード
- 自分の手札
- 残りサイド
- 合法手
- 対戦中に観測した行動履歴
- 公開情報から計算できる次ターン打点やKOリスク

避ける実装:

- 相手agent名やデッキ名による分岐
- 特定ベンチマーク専用ボーナス
- 特定相手専用パラメータ
- 少数の相手だけに勝つためのカードID決め打ち

目標は「特定相手に勝つロジック」ではなく、「多様な相手で壊れない一般原則」を作ること。

### 1. 反実仮想リグレット分析

参考:

- Zinkevich et al., "Regret Minimization in Games with Incomplete Information", 2007
- https://papers.nips.cc/paper_files/paper/2007/hash/08d98638c6fcd194a4b1e6992063e944-Abstract.html

各意思決定で、実際に選んだ行動と他の合法手を同じ条件で短く再シミュレーションする。

```text
regret = 最良代替行動の推定価値 - 実際に選んだ行動の推定価値
```

分析対象:

- エネルギー貼り先
- 攻撃時のエネルギー消費量
- Boss使用タイミング
- ベンチ展開
- Retreat
- サーチ対象
- 攻撃選択

CFR全体を実装するのではなく、最初は「どの判断で価値を失ったか」を特定するログ分析として導入する。

見る指標:

- 平均counterfactual regret
- 高regret判断/ゲーム
- 最初の不可逆な高regret判断
- 判断カテゴリ別regret合計

### 2. League評価

候補を単一ベンチマークだけで評価せず、戦い方の異なる複数方策へ同一ロジックで対戦させる。

評価相手の例:

- 高速攻撃型
- ベンチ攻撃型
- 資源温存型
- Boss積極型
- 現行安定版
- 過去の安定版

重要:

- Leagueは評価と過適合検出にだけ使う。
- 相手ごとの専用分岐やパラメータは持たない。

評価例:

```text
fitness = 0.7 * 全相手平均勝率 + 0.3 * 最悪相手勝率
```

平均性能だけでなくworst-case性能を考慮し、未知相手への頑健性を高める。

### 3. MAP-Elitesによる方策多様性の保持

参考:

- Mouret and Clune, "Illuminating Search Spaces by Mapping Elites", 2015

重み探索で単一の最高勝率個体だけを残さず、行動特性が異なる高性能個体を保存する。

行動特性の例:

- 初回攻撃ターン
- Boss使用頻度
- 平均ベンチ数
- エネルギー温存量
- Raging Bolt攻撃比率
- Ogerpon攻撃比率
- 平均探索時間

用途:

- 局所解と評価ノイズへの過適合を防ぐ
- 同等勝率だが異なる戦術の候補を比較する
- 未知相手でも安定する単一の汎用方策を選ぶ

実戦中に相手別で個体を切り替える用途には使わない。

### 4. 局面フェーズ別Mixture of Experts

単一のスコア関数ですべての局面を扱わず、局面の目的ごとに評価を分ける。

候補:

- setup expert
- attack expert
- energy economy expert
- prize-race expert
- survival expert
- endgame expert

相手デッキではなく、公開された盤面状態だけでexpertを選ぶ。

最小実験:

- 通常局面
- 残りサイド2以下の終盤

序盤と終盤で同じ重みが逆効果になる干渉を減らせるか検証する。

### 5. 資源の機会費用

カードや行動へ固定点を付けるだけでなく、「今使うことで失う将来価値」を評価する。

評価対象:

- 手札1枚
- 山札1枚
- 場のエネルギー1枚
- 手札のエネルギー1枚
- ベンチ枠1つ
- Supporter権
- Retreat権
- 探索時間

攻撃評価例:

```text
attack_value
  = KO価値
  + 与ダメージ価値
  - 消費エネルギーの将来価値
  - 次アタッカーが停止する危険
```

Raging Boltでは「今KOできるか」だけでなく、「攻撃後に再攻撃できるか」を重視する。

### 6. Off-Policy Evaluationによる候補選別

参考:

- Dudík, Langford, Li, "Doubly Robust Policy Evaluation and Learning", 2011
- Jiang and Li, "Doubly Robust Off-policy Value Evaluation for Reinforcement Learning", 2016
- https://proceedings.mlr.press/v48/jiang16.html

過去ログ上の局面に候補方策を適用し、実対戦前に明らかに弱い候補を除外する。

用途:

```text
多数の候補
  -> ログ評価
  -> 30戦スクリーニング
  -> 100戦以上の確認
  -> 大規模検証
```

Off-Policy Evaluationだけで採用を決めず、対戦前の計算量削減に使う。

---

## 追加提案: 人間トレース70%と残り30%の乖離

### 現状に対する仮説

単純な模倣精度70%は、勝率との対応が弱い可能性がある。
残り30%には以下が混在していると考えられる。

1. 人と違うが価値がほぼ同じ等価手
2. 数ターン後に回復できる軽微な乖離
3. KOやサイドレースを左右する重大な乖離
4. AI自身の以前の判断により、人間データにない盤面へ到達した分布外局面
5. 人の行動は記録されているが、その戦術意図が特徴量に含まれていない局面

70%を75%へ上げること自体ではなく、重大な乖離を減らすことを目的にする。

### 1. 乖離30%の分類

各乖離を次のカテゴリへ分ける。

| 分類 | 判断基準 | 学習上の扱い |
|---|---|---|
| 等価手 | 代替手との推定価値差が小さい | 弱い重み、または正解集合に含める |
| 軽微 | 数ターン後に回復できる | 低い重み |
| 重大 | KO、攻撃開始、サイドレースへ影響 | 高い重み |
| 分布外 | 人間データに類似局面がない | 人による追加レビュー |
| 意図不明 | 行動だけでは目的を説明できない | 意図ラベルを追加 |

一致率に代わる主要指標:

```text
重大局面での良手選択率
平均counterfactual regret
致命的判断ミス/ゲーム
乖離後の回復率
最初の不可逆な乖離ターン
```

### 2. 行動分類から行動ランキングへ

人が選んだ1つの行動IDだけを正解にすると、等価手まで誤りになる。
全合法手を次のように順位付けする。

```text
A: 人の選択、または同価値の最良手
B: ほぼ同価値の代替手
C: 少し悪い手
D: 勝敗を大きく損なう手
```

目標を「人の行動IDを完全一致させる」から、
「重大な悪手より良い行動を上位に置く」へ変更する。

### 3. Regret-weighted imitation

参考:

- Peng et al., "Advantage-Weighted Regression", 2019
- https://arxiv.org/abs/1910.00177

各乖離局面で短いrolloutまたは評価関数を使って価値差を推定する。

```text
weight = max(0, human_action_value - ai_action_value)
```

- 価値差がほぼ0の不一致は弱く学習する
- 小さな悪化は通常の重みで学習する
- KOを逃すなど重大な悪化を強く学習する

容易な70%へ学習容量を使わず、勝敗に影響する数%へ集中させる。

### 4. DAgger型データ収集

参考:

- Ross, Gordon, Bagnell, "A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning", 2011

人間プレイだけを学習すると、AIが一度間違えた後の盤面を学べない。

手順:

1. AI自身に実際にプレイさせる
2. AIと人の判断が乖離した局面を保存する
3. AIが到達したその盤面で、人が良い行動をラベルする
4. 既存データへ追加して再学習する
5. 新しいAIでもう一度収集する

Human Trace / Disagreement Review基盤があるため、この方式と相性がよい。

全局面を再ラベルせず、次を優先する。

- 高regret候補
- モデルの確信度が低い
- 上位2行動のスコア差が小さい
- 敗戦につながった最初の不可逆な乖離

### 5. 人の行動ではなく戦術意図を学ぶ

二段階の方策を検討する。

```text
盤面
  -> 戦術意図
  -> 具体的な合法手
```

意図の候補:

- 今ターンKO
- 次ターンの攻撃準備
- 後続アタッカー確保
- エネルギー温存
- 手札改善
- サイドレース優先
- 相手の返しを生存
- 詰み回避

異なる行動でも意図が同じなら重大な乖離ではない。
逆に行動が偶然一致していても、意図や価値評価が誤っていれば将来の局面で崩れる。

### 6. 模倣モデルはpriorとして使う

人間模倣を最終決定器にせず、探索と盤面評価のpriorとして利用する。

```text
final_score
  = heuristic_or_search_value
  + imitation_prior
  - predicted_regret
```

人間選択確率が高くても、次の安全条件に反する場合はoverride候補とする。

- 今ターンの確定KOを逃す
- 攻撃後に後続が停止する
- 返しで敗北する
- サイドを取り切れる行動を見送る

人を完全コピーするのではなく、人の判断を初期priorとして探索で改善する。

### 7. 乖離分析で保存する項目

```text
state_id
turn
select_context
legal_actions
human_action
ai_action
human_intent
ai_confidence
human_action_value
ai_action_value
best_alternative_value
estimated_regret
equivalent_action_group
out_of_distribution_score
recovered_after_divergence
final_result
first_irreversible_divergence
```

敗戦直前の判断だけでなく、そこへ至る最初の不可逆な乖離を特定する。

## 追加後の推奨実施順

1. 乖離30%を等価・軽微・重大・分布外・意図不明へ分類
2. counterfactual regretを記録
3. 重大乖離だけを対象に行動ランキングを作成
4. Regret-weighted imitationを比較
5. AIが到達した分布外局面へDAgger型の人間ラベルを追加
6. 模倣モデルを最終決定ではなく探索priorとして使用
7. League評価で同一方策の頑健性を確認
8. その後にISMCTS、afterstate value、Mixture of Expertsを個別検証

## Claude Codeへ渡す追加依頼例

```text
docs/chatgpt_performance_improvement_proposals.md の
「追加提案: 人間トレース70%と残り30%の乖離」だけを対象にしてください。
まだ方策を変更せず、既存ログから乖離を
等価・軽微・重大・分布外・意図不明へ分類する設計を作ってください。
単純一致率ではなくcounterfactual regretと最初の不可逆な乖離を測定してください。
特定の相手agentやデッキ専用の特徴・分岐は追加しないでください。
```

```text
乖離分類済みデータを使い、行動IDの単純分類と
regret-weighted action rankingを比較する実験計画を作ってください。
人の選択とほぼ同価値の合法手は等価な正解として扱ってください。
評価指標は重大局面での良手選択率、平均regret、
致命的判断ミス/ゲーム、対戦勝率としてください。
```

---

## ChatGPT私案: Critical-Regret DAgger

### 結論

私なら、最初にISMCTSやDeep RLへ全面移行せず、次の閉ループを作る。

```text
AIに対戦させる
  -> 敗戦につながった最初の重大な乖離を検出
  -> 同じ局面の合法手を短く反実仮想評価
  -> 人が上位候補だけレビュー
  -> 等価手を許容したランキングデータを追加
  -> regretの大きい局面を重点学習
  -> 模倣モデルを探索priorとして再利用
  -> 同じ条件で再評価
```

この案を `Critical-Regret DAgger` と呼ぶ。

理由:

- 現在すでに約70%は人の操作を追えている。
- 残り30%すべてを直す必要はなく、勝敗へ影響する少数の乖離を直せばよい。
- 通常の行動一致学習は、等価手まで誤りとして扱う。
- 人間トレースだけでは、AIが自分の誤りによって到達した盤面を学べない。
- 既存のHuman Trace、Disagreement Review、rollout、評価関数を再利用できる。
- 特定相手専用ロジックを作らず、公開盤面から一般的な判断規則を改善できる。

### 中核となる変更

#### 1. 一致率を主目的にしない

従来:

```text
human_action == ai_action
```

新しい目的:

```text
人の行動と同等以上の価値を持つ行動を選べたか
重大な悪手を上位から除外できたか
```

主要指標:

- critical decision accuracy
- mean critical regret
- p90 critical regret
- fatal mistake count/game
- first irreversible divergence turn
- divergence recovery rate
- win rate

70%の単純一致率は補助指標へ下げる。

#### 2. 最初の不可逆な乖離を探す

敗戦直前の誤りだけを直さない。
対局を後ろから調べ、別の選択なら敗戦経路を回避できた最初の局面を探す。

例:

```text
T7: 攻撃できず敗北
T6: 必要エネルギー不足
T4: 回収対象を誤った
T3: ベンチ枠を不要なポケモンで埋めた  <- 最初の不可逆な乖離
```

この場合、学習対象の中心はT7ではなくT3。

#### 3. 等価手集合を作る

人の1手だけを正解にせず、合法手を短いrolloutまたはafterstate評価で比較する。

```text
best_value - action_value <= epsilon
```

を満たす行動を等価手集合へ入れる。

epsilonは固定値だけでなく、評価誤差を考慮して決める。
最初は上位行動間の価値差分布を見て、複数候補を比較する。

#### 4. 行動分類をランキングへ変える

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

重大な価値差を持つpairほど強く学習する。

```text
pair_weight = clip(regret_gap, min_weight, max_weight)
```

#### 5. 人間レビューを高価値局面へ限定する

人へ提示する優先順位:

1. 高regretと推定された局面
2. 敗戦につながった最初の不可逆な乖離
3. モデルの上位2手が僅差
4. モデルの確信度が低い
5. 分布外スコアが高い

人に全合法手の完全順位を付けてもらう必要はない。

提示内容:

- 公開盤面
- 人が実際に選んだ手
- AIの手
- AIが推定した上位3手
- 各手の短いrollout結果
- 「同等」「Aが良い」「Bが良い」「判断不能」の簡単なラベル
- 戦術意図

#### 6. 模倣モデルを探索priorに降格する

模倣モデル単独で最終行動を決めない。

```text
candidate_score
  = search_or_afterstate_value
  + beta * imitation_prior
  - gamma * predicted_regret
```

最初は小さい値から比較する。

```text
beta = 0, 0.05, 0.1, 0.2
```

人の知識を候補絞り込みと初期順位に使い、最終的には盤面価値で判断する。

### 実施フェーズ

#### Phase A: 計測だけ

方策を変更しない。

- 乖離を5分類する
- 最初の不可逆な乖離を抽出する
- 合法手ごとの短い反実仮想価値を保存する
- regret上位100局面を人が確認する

終了条件:

- 乖離30%の内訳が分かる
- 敗戦の何%が上位少数カテゴリで説明できるか分かる
- rollout評価と人の判断の一致度が分かる

#### Phase B: ランキング学習

- 単純な人間行動分類をbaselineとする
- 等価手を許容する
- regret-weighted pairwise rankingを学習する
- まだ本番方策へ混ぜず、固定局面test setで比較する

採用候補条件:

- 単純一致率が少し下がってもよい
- critical decision accuracyが改善
- mean/p90 regretが改善
- 相手別分岐を含まない

#### Phase C: DAgger収集

- 新モデルに対戦させる
- 新たに到達した分布外・高regret局面だけ人が追加レビューする
- 1回の大量収集より、小さい反復を複数回行う

例:

```text
100局面レビュー
  -> 再学習
  -> 対戦
  -> 新規100局面レビュー
```

#### Phase D: 探索priorとして統合

- `beta=0`をbaselineとする
- `beta=0.05/0.1/0.2`を比較する
- 30戦では安全性と大退行だけを見る
- 100戦以上で候補を絞る
- 複数の戦術タイプへ同一方策で評価する

#### Phase E: その後にISMCTS

Critical-Regret DAggerで評価関数とpriorを改善してから、ISMCTS 4サンプルへ進む。
探索だけ高度化しても、leaf評価やrollout policyが弱いと誤った判断を高い確信で選ぶため。

### 成功・失敗の判定

成功:

- 人との単純一致率ではなくcritical regretが下がる
- 最初の不可逆な乖離が遅くなる
- 攻撃回数と再攻撃率が改善する
- 多様な相手への平均・worst-case勝率が改善する
- 特定相手用分岐なしで改善する

失敗:

- 一致率だけ上がり勝率が変わらない
- 人間レビュー済み局面だけ改善する
- rollout評価の誤差をそのまま学習して悪化する
- imitation priorが強すぎて探索結果を上書きする
- 同じ状態表現なのに人の判断が大きく割れる

最後のケースでは学習器より先に、履歴、既使用Supporter、残り資源、戦術意図など状態特徴の不足を疑う。

### 私が付ける参考文献の順位

#### 1位: DAgger

Ross, Gordon, Bagnell,
"A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning"

最優先の理由:

- AI自身が到達する盤面と人間トレースの分布差を直接扱う。
- 現在の70%/30%問題に最も直接対応する。
- 既存の人間レビュー環境を活用できる。

#### 2位: Advantage-Weighted Regression

Peng et al.,
"Advantage-Weighted Regression: Simple and Scalable Off-Policy Reinforcement Learning"

理由:

- すべての人間行動を同じ重みで模倣しない考え方を提供する。
- regret-weighted rankingへ応用しやすい。
- 既存ログを利用できる。

#### 3位: Information Set Monte Carlo Tree Search

Cowling, Powley, Whitehouse,
"Information Set Monte Carlo Tree Search"

理由:

- ポケモンカードの隠れ情報へ直接対応する。
- ただし、先に評価関数と重大乖離を改善した方が探索の効果を測りやすい。

#### 4位: TD-Gammon / Sutton and Barto

Tesauro,
"Temporal Difference Learning and TD-Gammon"

Sutton and Barto,
"Reinforcement Learning: An Introduction"

理由:

- 人の行動そのものではなく、勝敗へつながる盤面価値を学べる。
- afterstate valueを既存ヒューリスティックへ少量混ぜる用途が有望。

#### 5位: MCTS Survey

Browne et al.,
"A Survey of Monte Carlo Tree Search Methods"

理由:

- Progressive bias、tree reuse、move pruningなどの改善候補が豊富。
- 現段階では個別手法より、Critical-Regret DAggerの後に使う探索改善カタログとして有用。

#### 6位: POMCP

Silver and Veness,
"Monte-Carlo Planning in Large POMDPs"

理由:

- belief/particle管理は理論的に適合する。
- 実装と計算量が大きいため、ISMCTSの小規模実験後に判断する。

#### 7位: Bandit Algorithms

Lattimore and Szepesvári,
"Bandit Algorithms"

理由:

- 探索予算配分の理論には有用。
- 現在の主要ボトルネックはUCB係数より、評価誤差と分布外局面だと考える。

### 私なら最初に行う1つの実験

過去の敗戦から100件を抽出し、各対局について「最初の不可逆な乖離」を1件だけ人が確認する。

比較するモデル:

```text
A: 現行の単純模倣
B: 等価手を許容したランキング
C: regret-weightedランキング
```

固定test setで比較する指標:

- 人の行動との完全一致率
- 等価手を含む一致率
- critical decision accuracy
- mean regret
- p90 regret

ここでCがAよりcritical regretを明確に下げた場合だけ、対戦へ進める。
この実験は比較的小さく、現在勝ち切れない原因が「残り30%の重大判断」にあるかを直接検証できる。

---

## 分析用メモ: なぜこの順番で改善するのか

### 基本方針

この順位は「高度なアルゴリズムの順」ではない。
性能向上を妨げている原因を、安価かつ他の要因と混同しにくい順に切り分けるための暫定順位。

現時点で観測されている情報:

- 人間操作を約70%トレースできている。
- 残り約30%の乖離が残っている。
- 模倣方法や調整を変えても、勝ち切れない感触がある。

この情報だけでは、30%すべてが弱さの原因とは限らない。
30%の内訳と勝敗への寄与を測ってから、実際の改善順位を確定する。

### 性能停滞の原因ツリー

```text
勝てない
├─ 重要局面の判断を間違える
│  ├─ 学習目的が人の行動IDとの完全一致になっている
│  ├─ 同価値の別手まで誤りとして学習している
│  ├─ AIが人間データにない盤面へ進む
│  ├─ 状態特徴が不足している
│  ├─ 人間の戦術意図を表現できていない
│  └─ 頻度の低い致命的判断が通常局面に埋もれている
├─ 盤面価値を誤っている
│  ├─ 短期評価と最終勝率が一致しない
│  ├─ 攻撃後の資源価値を過小評価している
│  └─ 後続アタッカーやサイドレースを評価できていない
├─ 隠れ情報の扱いが弱い
│  ├─ 相手の手札・山札を1通りに決め打ちしている
│  └─ hidden stateによって最良手が変わる
└─ 探索の問題
   ├─ 探索予算が不足している
   ├─ rollout policyが弱い
   ├─ leaf評価が弱い
   └─ 重要でない局面へ予算を使っている
```

### 70%一致という指標の注意点

30%の不一致が、例えば次の構成である可能性がある。

```text
29%: 人とは違うが同価値の別手
 1%: 勝敗を決める重大な悪手
```

または、

```text
10%: 同価値の別手
20%: 攻撃準備や資源管理を壊す重大な誤り
```

この2ケースでは必要な改善が異なる。
したがって、単純一致率を上げる前に、不一致を価値差と将来影響で分類する。

## 各手法の順位と診断根拠

### 1位: DAgger

最初に疑う原因:

- AIが一度異なる判断をした後、人間トレースに存在しない盤面へ移動する分布シフト。

```text
人間:
良い判断 -> 人間がよく到達する盤面 -> 学習データが豊富

AI:
小さな誤り -> 人間データに少ない盤面 -> 次も誤る
          -> さらに人間データから離れる
```

人間による正常なプレイログを追加するだけでは、AI自身が作る異常・分布外盤面を十分に学べない。
DAggerはAIを実際に動かし、AIが到達した盤面へ人間ラベルを追加するため、この原因へ直接対応する。

1位にする追加理由:

- 現在のHuman Trace / Disagreement Review基盤を再利用できる。
- 方策全体の大改造が不要。
- 分布外局面だけを選んで人に確認できる。
- 特定相手専用ロジックを必要としない。

判定:

- 重大乖離局面と訓練データ内状態との類似度を測る。
- 重大乖離の多くが分布外ならDAggerを優先する。
- 分布内でも間違えるなら、学習目的、特徴量、ラベルを疑う。

### 2位: Advantage / Regret-weighted ranking

疑う原因:

- すべての不一致を同じ損失で学習している。
- 頻度の高い簡単な判断が、少数の致命的判断を学習上で埋めている。

```text
同価値の別手             regret ≈ 0
少し順序が悪い           regret = 小
次ターンの攻撃を失う     regret = 大
確定KOを逃す             regret = 非常に大
```

完全一致学習ではこれらが同じ1件の誤りになる。
Regret-weighted rankingでは、価値差の大きい判断を重点的に学習できる。

2位にする理由:

- 既存ログを利用できる。
- モデルや探索を全面変更せず比較できる。
- 70%の容易な一致を増やすより、勝敗へ影響する少数の乖離へ学習容量を集中できる。

判定:

- 人とAIの不一致手を短くrolloutし、価値差を測る。
- 不一致率は高いがregretが小さいなら、一致率自体は主要問題ではない。
- 少数局面へregretが集中するなら、重み付きランキングが有望。
- rollout価値と人間評価が一致しないなら、先に評価関数を改善する。

### 3位: ISMCTS

疑う原因:

- 相手の手札、山札、サイドなどを単一状態へ決め打ちしている。
- hidden stateの推定誤差で最良行動が変わる。

3位にする理由:

- ポケモンカードの不完全情報性へ直接対応する。
- ただしleaf評価やrollout policyが弱い状態で探索を増やすと、誤った価値へ強く収束する可能性がある。
- 先に重大乖離、模倣prior、盤面評価の信頼性を確認した方が効果を分離しやすい。

判定:

- 同じ公開盤面から複数hidden stateを生成する。
- hidden stateごとに最良手が変わる割合を測る。
- 頻繁に変わるならISMCTSを優先する。
- ほとんど変わらないなら、隠れ情報は主要原因ではない。

### 4位: TD / afterstate value

疑う原因:

- 模倣モデルは人の行動を予測しているが、最終的な勝ちやすさを直接学んでいない。
- 現在のヒューリスティックが、攻撃後の資源、後続、サイドレースを誤評価している。

4位にする理由:

- 最終勝敗から盤面価値を学び、人間模倣とヒューリスティックを補正できる。
- 一方で大量かつ多様なデータが必要。
- データリーク、相手分布への過適合、自己対戦特有の偏りが起きやすい。
- まず小さい診断で模倣側の問題を除外する方が安価。

判定:

固定局面で以下の行動順位相関を比較する。

- 人間評価
- 現行ヒューリスティック
- 学習value
- 短いrollout結果
- 最終結果

未知対局・未使用相手でも学習valueが安定して優位なら、少量混合する。

### 5位: MCTS改善

候補:

- Progressive bias
- tree reuse
- move pruning
- Progressive widening
- 探索予算の局面別配分

5位にする理由:

- 現在の原因が探索量不足ではなく、状態表現や評価関数の誤りなら効果がない。
- 弱いrolloutを効率よく大量実行しても、誤った判断を強化する可能性がある。

判定:

```text
探索予算を0.5倍 / 1倍 / 2倍 / 4倍
```

として固定局面のregretと対戦性能を測る。

- 予算増加で判断品質が上がる -> MCTS効率化が有望
- 予算増加で変わらない -> 評価関数または状態表現が原因
- 予算増加で悪化する -> rollout biasやlookahead pathologyを疑う

### 6位: POMCP

疑う原因:

- 対戦中の観測を使ってbeliefを継続更新できていない。

6位にする理由:

- 理論的には隠れ情報ゲームへよく適合する。
- ただし実装負荷と計算量が大きい。
- まずISMCTS 4サンプルで「複数hidden stateが実際に性能へ効くか」を検証できる。
- ISMCTSに効果がなければ、POMCPも費用対効果が低い可能性がある。

判定:

- ISMCTSで明確な改善が出る。
- 観測履歴に応じてparticle重みを更新する価値が確認できる。
- 制限時間内に必要なparticle数を処理できる。

この条件が揃った場合に進める。

### 7位: Bandit Algorithms

疑う原因:

- 探索候補間の予算配分が不適切。

7位にする理由:

- UCB係数やrollout数の調整より、評価誤差、分布外局面、状態表現の方が主要原因である可能性が高い。
- 過去に探索予算を増やした際の改善が限定的なら、単純な探索不足とは考えにくい。

判定:

- 追加rolloutにより行動順位が正しい方向へ安定する。
- 上位2手の不確実性が実測regretと対応する。
- 局面別予算配分で、同じ総計算量のまま性能が上がる。

## 最初に行う診断

### 対象

過去の敗戦から100件を抽出する。
可能なら勝利対局も比較群として同数抽出する。

### 各対局で調べること

1. 人とAIが最初に異なる行動を選んだ局面
2. 最初の不一致が等価手だったか
3. 最初の高regret判断
4. 最初の不可逆な乖離
5. 敗戦直前の誤り
6. AIがその局面へ到達した原因
7. 訓練データに類似状態が存在したか
8. hidden stateを変えると最良行動が変わるか
9. 探索予算を増やすと選択が改善するか

「最初の不一致」「最初の高regret判断」「最初の不可逆な乖離」「敗戦直前の誤り」は同一とは限らないため、分けて保存する。

## 原因分類と次の改善

| 原因 | 判断方法 | 次の改善 |
|---|---|---|
| 等価手 | 人の手とAIの手の価値差が小さい | 一致率から除外、複数正解化 |
| 分布外 | 類似訓練状態がない | DAgger |
| 重要度不足 | regretの大きい手を外す | Regret-weighted ranking |
| 状態特徴不足 | 同じ観測入力で人の判断が割れる | 履歴・資源・意図特徴を追加 |
| 評価関数誤差 | rolloutと人の評価が不一致 | afterstate value、評価特徴改善 |
| hidden state誤差 | 仮説ごとに最良手が変わる | ISMCTS |
| belief更新不足 | 観測後も誤った仮説を保持する | POMCP / particle更新 |
| 探索不足 | 予算増加で判断が改善する | MCTS効率化、予算配分 |
| rollout bias | 予算増加で悪化する | rollout policyとleaf評価を修正 |

## 原因構成比による優先順位の変更

提示した順位は固定しない。
敗戦100件の原因構成比に応じて変更する。

例A:

```text
分布外                 40件
重大判断の重み不足     30件
状態特徴不足           15件
hidden state誤差       10件
探索不足                5件
```

この場合:

1. DAgger
2. Regret-weighted ranking
3. 状態特徴改善
4. ISMCTS
5. MCTS改善

例B:

```text
hidden state誤差       50件
評価関数誤差           30件
分布外                 10件
その他                 10件
```

この場合:

1. ISMCTS
2. afterstate value
3. DAgger
4. POMCP検討

例C:

```text
等価手                 55件
状態特徴不足           20件
重大判断の重み不足     15件
その他                 10件
```

この場合:

1. 一致率評価を廃止して複数正解ランキングへ変更
2. 状態特徴を追加
3. Regret-weighted ranking

DAggerや探索を先に大きく変更する必要はない。

## 分析上の注意

- 敗戦だけを見ると、勝利時にも発生する無害な乖離を重大と誤認する可能性がある。
- そのため勝利対局も比較する。
- 最終勝敗だけでは運の影響が大きいため、複数hidden stateと複数rolloutで価値差を見る。
- rollout評価自体が誤っている可能性があるため、人間レビューとの一致度を先に測る。
- 相手ごとの原因件数は評価するが、相手専用ロジックへ変換しない。
- 特定相手でしか再現しない改善は、汎用採用候補と分けて扱う。
- 一度に複数手法を導入せず、原因仮説ごとに単独ablationする。

## この分析の最終目的

```text
一致率を上げる
```

ことではなく、

```text
勝敗へ影響する最初の重大な判断ミスを特定し、
その原因へ最小の変更を当て、
多様な相手に同じ方策で改善する
```

こと。
