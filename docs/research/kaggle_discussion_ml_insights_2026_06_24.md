# Kaggle Discussion ML Insights (2026-06-24)

Kaggle competition `pokemon-tcg-ai-battle` のディスカッションから、ML アプローチに関する知見を収集・整理したもの。

## 1. RL/PPO/MCTS の実戦レポート

Source: [Topic 711644](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711644) — "How has your experience been with RL/PPO/MCTS in this competition so far?" (6 votes, 2 comments)

### Nur Srijan の実験結果

#### Behavioral Cloning (BC)

- トップの Lucario heuristic を模倣する state-transformer policy/value network を事前学習
- 行動予測精度: **66%**
- BC のみ (greedy, 探索なし) での対 heuristic 勝率: **10%**

#### PPO Self-Play Fine-Tuning

- BC モデルを初期値として PPO で fine-tuning
- 20 iteration の self-play loop
- 50% self-play + 50% vs heuristic の league training
- KL divergence ペナルティで BC prior からの逸脱を防止 (KL = 0.01 - 0.09)
- 対 heuristic 勝率: **25%** (探索なし)

#### MCTS のボトルネック

- Kaggle 推論環境は **1 秒のタイムアウト** (per move)
- この制約下で MCTS は **~10 rollouts/turn** が限界
- 標準 UCT は 10 rollouts では実質無意味
- 対策: 学習済み policy を PUCT の prior に使い、top-2/3 候補に集中

#### インフラ課題

- libcg.so に C++ メモリリークあり
- 対策: 25-50 ゲームごとにワーカープロセス再起動
- macOS (Apple Silicon) は linux/amd64 Docker エミュレーションが必要

### CoreyJamesLevinson のコメント

- Imitation learning で **~85%** の行動予測精度を達成
- しかし RL に移行しても「先生」(heuristic) を超えられなかった
- PPO に切り替えたら rule-based teacher に勝てるようになった
- AlphaZero スタイルの RL + MCTS rollouts も試行中

### 示唆

- 純粋 ML はまだ heuristic に勝てていない (最高でも 25% 勝率)
- 我々の heuristic + ML hybrid 路線は合理的
- BC → PPO の移行パスは有望だが、policy collapse を防ぐ KL penalty が重要

## 2. Self-play / Human-play ログの利用可否

Source: [Topic 712119](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712119) (9 votes, 7 comments)

### 質問

- 自分で手動プレイしたログは訓練に使えるか？
- PTCGL 等の外部プラットフォームの対戦ログは使えるか？
- 外部データとして公開義務はあるか？

### 公式回答 (Addison Howard, Kaggle Staff)

> Those datasets are allowed for use in training and aren't considered a violation of the rules.

- **自己生成ログ**: 使用可
- **外部対戦ログ**: 使用可 (権利がある前提)
- **公開義務**: なし

### 示唆

- Kaggle の Daily Top Episodes データセットを訓練データとして活用可能
- 自前の self-play ログも制限なく使える
- 上位エージェントの行動パターンを BC データとして使うことが正式に許可されている

## 3. MCTS / 探索エージェントの API 制約

Source: [Topic 711329](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711329) — "Proposal: an official API extension for simulation / search-based agents" (17 votes)

### 問題: デッキ順序の千里眼

- libcg の SearchBegin/SearchStep でデッキ順序が固定される
- 途中の draw ability (Psychic Draw 等) 後にデッキをシャッフル再ランダム化する API がない
- 探索が「デッキ順序を知った上で」最適化してしまい、期待値を過大評価する

### 現在の制約

- 同一 SearchId 内の draw は常に決定的 (同じカードが引かれる)
- 中間状態からの SearchBegin (re-determinization) はできない
- `search_begin_input` は real battle observation にしか存在しない

### 示唆

- 現時点で MCTS を正しく実装するのは API の制約上困難
- heuristic ベースの軽量評価が現実的な選択肢
- API 拡張が来れば MCTS の価値が大幅に上がる可能性がある

## 4. 推論環境の制約

Source: [Topic 708810](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708810) (33 votes, 6 comments)

### 公式回答 (Bovard Doerschuk-Tiberi, Kaggle Staff)

> Each team has 600 seconds TOTAL for the entire game. There is no per turn increment.

- **ゲーム全体で 600 秒**、ターンごとの増分なし
- 1ゲーム ~150-200 ターンとすると、平均 3-4 秒/ターン
- 我々の agent は ~5ms/turn なので **余裕は十分** (120倍以上)
- 重い ML 推論 (例: transformer) を入れても時間的には可能

## 5. Daily Top Episodes データセット

Source: [Topic 709160](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709160) (44 votes)

- Kaggle が毎日トップエピソードのデータセットを公開
- Index: https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index
- replay 確認や agent 訓練に使える
- 上位エージェントの行動をBC/IL のデータソースとして活用可能

## 我々のプロジェクトへの影響と次の検討事項

### 現在の方針は合理的

| 知見 | 我々の現状 | 評価 |
|------|-----------|------|
| 純粋 ML は heuristic に勝てていない | heuristic + ML hybrid | 正しい方向 |
| MCTS は 1秒で ~10 rollouts | 軽量 heuristic scorer | 正しい方向 |
| BC 85% 精度は可能 | heuristic scorer ベース | BC データで補強する余地あり |
| 600秒/ゲーム全体 | ~5ms/turn | 余裕十分 |

### 検討に値するアクション

| 優先度 | アクション | 根拠 |
|--------|-----------|------|
| 高 | Daily Top Episodes から上位エージェントの行動データを収集 | BC/IL の訓練データとして公式許可済み、上位の意思決定パターンを学べる |
| 中 | 現在の heuristic scorer の出力を BC ターゲットとして使い、軽量 NN を訓練 | 85% 精度の BC が可能という実績あり。推論時間に余裕あるため NN 推論は可能 |
| 中 | PPO fine-tuning の KL penalty 手法を参考に、hybrid bonus の学習を安定化 | KL = 0.01-0.09 で policy collapse を防げたという実績 |
| 低 | MCTS の limited rollout (top-2/3) を試す | API 制約があるが、10 rollouts でも policy prior があれば有効かもしれない |

### やらないこと

- 純粋 RL エージェントの構築 (勝率 25% が現状の限界)
- 大規模 MCTS (API 制約 + 時間制約で非現実的)
- human-play ログの収集 (コスト対効果が低い)

---

## 6. Leaderboard スコアリングの不安定性とデッキ実績

Source: [Topic 712621](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712621) — "Leaderboard Scoring Inconsistency" (20 votes, 8 comments)

### 実測データ

投稿者が同一エージェントを2回提出して観測したスコア差:

| デッキ | 提出1 | 提出2 | スコア差 |
|--------|-------|-------|----------|
| Kangaskhan/Crustle | 940.7 | 790.8 | ~150 pt |
| Festival Lead | 1104.6 | 687.4 | **>400 pt** |

- 同一エージェントでも leaderboard スコアに 150-400 pt の差が出る
- 最初の 5-10 ゲームでほぼ運命が決まる
- TCG 固有のランダム性 (初手、サイド順、マッチアップ) が原因

### 言及されたデッキ

- **Kangaskhan/Crustle**: 最近のスタンダードメタで好成績。偏りの大きいマッチアップ
- **Festival Lead**: Crustle より偏りが少ないと予想されたが、実際はさらに大きなスコア差が出た
- **Lucario**: 公式サンプルデッキの一つ。ヒューリスティックのベースライン

### コミュニティの提言

- 1エージェントあたりのゲーム数を増やすべき
- BO3 (3本先取) 形式でマッチングすべき
- レーティング収束を遅くすべき
- 現状は「ハイロールするまで再提出」が最適行動になってしまう

### 示唆

- **leaderboard スコアは 1 回の提出で判断できない** — 最低 2 回提出して比較すべき
- **我々の ~495 pt は安定した代表値とは限らない**
- デッキ選択自体がスコアに大きく影響する (Crustle は 940、Festival Lead は 1104 に到達)

## 7. マルチデッキの禁止

Source: [Topic 711741](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711741) (15 votes, 10 comments)

### 公式回答 (shige, Competition Host)

> Participants are expected to submit agents that use a single deck consistently.
> Agents should not switch between multiple decks from game to game within the same submission.

- 技術的にはゲームごとにデッキを変えることが可能
- しかし**公式ルールとして単一デッキのみ許可**
- メタゲーム戦略よりも、1 デッキでの AI 戦略に集中すべき

### 示唆

- デッキ変更による改善は 1 回のPRで完結させるべき (実験的にデッキを切り替えることは可)
- 現在の Iono's Kilowattrel デッキで AI 戦略を深める方向が正しい

## 8. デッキメタ可視化サイト

Source: [Topic 710361](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/710361) (20 votes, 7 comments)

- URL: https://ptcg-kaggle-meta.vercel.app/
- 毎日更新されるデッキメタ情報 (使用率、カード構成)
- 2026-06-23 時点のデータ: https://ptcg-kaggle-meta.vercel.app/2026-06-23

### 観測データ (コメントより)

- Day 0 → Day 3 のデッキ提出数: 2,555 → 15,632 → 13,040 → 10,855
- 総デッキ数が減少傾向 — 参加者がデッキを削除/置き換えている可能性

### 示唆

- 対戦相手のデッキ分布を把握するのに有用
- どのデッキが多いかを知ることで、マッチアップ有利なプレイを検討できる
- ただしサイトは動的レンダリングのため API 取得には工夫が必要

## 追加の影響分析

| 知見 | 我々への影響 |
|------|-------------|
| スコア 150-400 pt のブレ | 1 回の提出で改善/悪化を判断できない。複数提出 or ローカル評価を重視 |
| Crustle/Festival Lead が高スコア到達 | Iono's Kilowattrel 以外のデッキも検討価値あり (ただしルール上は単一デッキ) |
| 単一デッキルール | 現在のデッキで AI を磨く方針は正しい |
| メタサイトが存在 | 対戦相手の傾向を把握し、マッチアップ対策に活用可能 |
