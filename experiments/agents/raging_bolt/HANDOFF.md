# Raging Bolt エージェント 引き継ぎドキュメント

最終更新: 2026-07-28 / 最終コミット: `bf194b4`（+ PR0-A.1/PR0-B は本コミットで反映）

## ⚠️ 2026-07-23: 本番Kaggle提出物として採用済み

このエージェント（`experiments/agents/raging_bolt/main.py`）は、リポジトリルートの `main.py` / `deck.csv` / `params.json` にコピーされ、**Kaggle提出パイプラインの本体**になりました（コミット `24cb25e`）。以前のルカリオ1084ベース提出物（`agent/` パッケージ + `data/` 以下のCSV/JSON）は置き換えられ、参照専用として残っています。

- 提出ビルド: `python build_submission.py`（`main.py`/`deck.csv`/`params.json`/`cg/`の4点のみ）
- 隔離環境での単独動作を確認済み（開発リポジトリの文脈なしでフルゲーム完走）
- **以後、このファイルへの変更は提出物に直接影響する。** ベンチマークで確認せずにコミットしないこと（このドキュメントの検証プロトコルを厳守）
- 詳細は `CLAUDE.md` の「提出フォーマット」セクション参照

## 現在の到達点

| 対戦相手 | 勝率 (100戦) | 備考 |
|----------|:---:|------|
| top_lucario_1084 | **25.0%** | 最強ベンチマーク。セッション開始時6.5% |
| dragapult (sandbox) | **25.3%** | ベンチダメージ評価導入前は10%（UCB1予算増後は未再測定） |
| megastarmie (sandbox) | **55%** | 導入前41%（UCB1予算増後は未再測定） |

（2026-07-08時点の17〜18%→第9章(相手エネルギー推定+終盤深読み)で20.0%→UCB1予算較正(下記)で25.0%。1ゲームあたり計算コストは約45〜90秒（旧版の約26秒から増加）。dragapult/megastarmieは新設定での再ベンチマーク未実施 — 次回セッションの優先タスク）

アーキテクチャ: デッキ専用ヒューリスティック + **エンジン公式探索API による実1ターン先読み**（`search_begin`/`search_step`、`_engine_search_choose`）。MAIN決定で上位5候補+最良ATTACHを実際にエンジン上で進め、ターン終了時盤面を静的評価 `_eval_search_state` で採点して選択。

## 検証プロトコル（必ず守る）

1. 変更は1テーマずつ。**ミラー(旧版vs新版)100戦 + vsルカリオ100戦**で検証
2. 判定: ミラー45%未満=リグレッション棄却 / ルカリオは±7pt(100戦)が誤差帯
3. **ユーザーは特定相手への過適合を望まない** — 大きな変更は複数デッキで測る
4. ベンチマークはWSL内で `experiments/head_to_head.py`（libcg.so=Linux専用）
5. エージェント変種はディレクトリコピー（main.py+deck.csv+params.json）で作る。`POKEMON_AI_PARAMS_PATH` 環境変数は両エージェントを汚染するので使わない

## 効いたもの（再現された勝ち筋）

- **エンジン探索の導入** (6.5%→15%) — 最大の突破口
- **リーリエのコンボ保留** (`rule_lillie_combo_defer`) — ユーザー発案。ablateで無効化すると崩壊(fitness 58→15)する最重要ルール
- **ベンチダメージ評価** (`se_bench_damage`/`se_bench_ko_risk`) — dragapult 10%→25%
- **ハンドプレイ乖離マイニング** — Live Tuning Panel でユーザーと対局→乖離レビュー→修正。3ラウンドで一致率が大きく向上
- **UCB1予算の増量** (`ucb1_extra_rollouts` 3→8, `ucb1_endgame_extra_rollouts` 8→12) — ルカリオ20.0%→25.0%。ミラーは中立(51-49)で「ミラー特化」の兆候なし。既定でON（`rule_ucb1_search=1`）。計算コスト増(約26秒→45〜90秒/ゲーム)はユーザー確認済みで許容範囲

## 効かなかったもの（再試行禁止 — 根拠つき）

| 施策 | 結果 | 原因 |
|------|------|------|
| ベンチへのエネ退避 (Fix N) | ミラー45.5% | BTはベンチのエネも打点燃料として消費するため配置は無意味 |
| 攻撃スコアのキャップでエネ貼り強制 | ミラー45% | **ヒューリスティック順位を歪めると探索候補から攻撃が漏れる**。介入は候補セット注入で行うこと |
| 相手ターンシミュレーション (`engine_search_opp_turn`, 既定OFF) | 中立 | 相手手札がフィラーなので情報が増えない |
| 探索の量的拡大 (samples=2 / top_k=7) | 中立 | 現評価関数の下で飽和 |
| 数値の自動チューニング (12候補) | 全て基準以下 | 手動調整済みの値が局所最適 |
| デッキ微調整 (v2a/v2b: エネサーチ増強) | 14% (基準17-18%) | ボトルネックは手札アクセスでなく**盤面装填スループット**(手貼り1/ターン+アカマツ)。このプールに汎用エネ加速なし |
| PRML3章+14章: リッジ回帰で評価重み学習+手動重みとのブレンド | ミラー55-45勝ち越しだがルカリオ15% (基準20%) | 多重共線性で符号反転(`se_can_ko`等)。**「ミラーで改善、ルカリオで悪化」パターンが3回連続で再現** — ミラーのみの改善は要疑い |
| AIMA第5章: UCB1バンディット配分・小予算(extra=3/8) | ルカリオ16%/ミラー53-47、共に有意差なし | 予算不足で一様配分とほぼ同じだった可能性。**予算を3→8に増やした版は採用済み**（上記「効いたもの」参照） |
| Sutton&Barto第2章: UCB1のCを実測σでスケーリング(`C_norm×σ̂×√(ln N/N_i)`) | ルカリオ21.0%（現行25.0%を下回る）/ミラー40-60で現行に負け越し | **両指標が同方向で明確に悪化** — 固定`C=200`より劣る。理由は未特定（該当コードは`git checkout`で元に戻し未コミット）。再挑戦するなら`sigma_floor`や`c_norm`の値を変えて再検証すること、同じ設定の再試行は不要 |

**重要な再発パターン**: ミラー戦の改善だけを根拠にコミットしない。必ずルカリオ戦で個別確認すること。

## 構造的な負け筋（エージェント改善では消えない）

100戦分析 (`analyze_lucario_losses.py`): 初攻撃は互角(T4.5 vs T3.7)だが攻撃回数が半分(2.05 vs 4.23回/ゲーム)。BT後の再装填2ターン > 相手のKOサイクル2.3ターン → サイド交換が構造的に2:4。

## 今後の性能向上の選択肢（優先度順）

1. **UCB1予算のブラケッティング完了（2026-07-24）— extra=8/12で確定、これ以上の単純増量は不要**。4点で60戦スクリーニング: 3/8→16.0%(100戦), **8/12→33.3%(60戦)/25.0%(100戦、採用中)**, 12/16→20.0%, 16/20→18.3%。山型カーブで8/12が明確な頂点。予算軸のチューニングはここで打ち止め、次に伸ばすなら`ucb1_exploration_c`(既定200、未較正)や配分アルゴリズム自体の見直しが筋（Sutton&Barto流の分散正規化は既に不採用、別アプローチが必要）
1b. **dragapult/megastarmieの再ベンチマーク** — UCB1予算増(8/12)後は未実施。提出前に必ず実施すること（過適合していないかの確認）
2. **相手アーキタイプ推定** — 公開情報(場・トラッシュ)から相手デッキを分類し、`_predict_hidden` の相手ゾーンを実カードで埋める。これにより休止中の相手ターンシミュレーションが実効化し、Boss/進化を含む応手を先読みできる
3. **価値モデル学習** — `use_value_model` 基盤が休眠中 (`value_model.py`, `value_dataset_*.csv`)。ch.3の反省(多重共線性・データ量不足)を踏まえ、10k+ゲーム規模で特徴量を整理してから再挑戦
4. **アーキタイプ変更** — サイド交換2:4はこのデッキの構造。トップメタ(ルカリオ系等)への乗り換えは最大のジャンプだが、ヒューリスティック層(カードID+戦術ルール)の書き直しが必要。探索基盤・評価骨格・パネル・auto_tuneはそのまま流用可能。デッキ変更は phase_plan_profile_strategy.md のプロセスに従い、**ユーザーの明示指示が必要**
5. **乖離マイニング継続** — 一致率は高いが、敗北ゲームのレビュー(まだ少ない)に残り情報がある
6. **rollforward深度+ビーム** — max_steps 14で長いコンボターンが打ち切られる。ビーム幅2やstep 20への拡張は未検証

## 自動化ツール

- `experiments/auto_tune.py --mode tune` : パラメータ摂動山登り（適応度=ミラー+2×ルカリオ+mega、逐次淘汰つき）
- `experiments/auto_tune.py --mode ablate` : ルールゲート(`rule_*`)を1つずつOFFにして寄与測定
- `experiments/analyze_lucario_losses.py` : 敗因統計 / `experiments/analyze_deck_usage.py` : 敗北時の死蔵カード統計
- Live Tuning Panel: WSLで `python3 experiments/web/launch.py --port 8000`。緑ハイライト=探索の推奨(`agent()`)、スコア数字=ヒューリスティック。ログは `session_tuning_log.jsonl`（`select_context`/`ai_search_pick` 記録済み）

## 運用上の注意（ハマりどころ）

- ベンチマーク出力はPythonのバッファリングで**完了まで見えない**（正常）
- Git Bash→WSLのパスは `MSYS_NO_PATHCONV=1 wsl bash -c '...'` で。ヒアドキュメントが安全
- **ACE SPECは1枚まで**。現デッキのACE SPECは Unfair Stamp (1080)。違反は battle_start が errorType=4 で失敗
- dragapult sandbox agent は約10エラー/100戦（先方のバグ、無視してよい）
- WSLはメモリ4GB弱でクラッシュ歴あり → `C:\Users\shclo\.wslconfig` で memory=3GB + swap=6GB 設定済み
- `experiments/` の作業は Kaggle 提出ビルド (`python build_submission.py`) の対象外
- PR #199 はユーザーの明示指示なしにマージしない
- 451ファイルに改行コードだけの差分がある（実害なし、コミット時は対象ファイルを明示指定）

## Decision Audit ロードマップ（2026-07-26〜）— 新しい作業方針

`docs/pokemon_ai_performance_improvement_memo_v4_1.md` がこれ以降の作業を統括する権威文書。核心思想: **「どの根本原因で意思決定ミスが起きているか」を計測してから、対応するアルゴリズム的修正を選ぶ**（ISMCTS/DAgger/価値モデル/POMCPなどをいきなり実装しない）。PR0-A→PR0-B→PR0-C→PR0-D→PR1-A→…の順で進める。Part I〜II（評価基盤・実装基盤の整合性）は**監査とインフラのみ**で、方策・スコア・探索ロジックへの変更は一切含まない。

### PR0-A: パラメータ契約監査 + 厳格テレメトリ（完了）

- `experiments/audit_parameter_contract.py` で `params.json` の全キーと `self.p()` 呼び出しをクロスリファレンス（ACTIVE/UNUSED/SHADOWED/未永続化/ハードコード値を分類）
- `EXEC_MODE`（PRODUCTION/BENCHMARK/DEBUG）+ `_TELEMETRY` カウンタ + `_record_exception()` を導入。PRODUCTIONでは制御フロー・戻り値に**一切変化なし**（Baseline Fingerprint Gate、diffレビュー+スモークテストで確認済み）
- コミット: `bfdc712`（監査）, `bf194b4`（テレメトリ）

### PR0-A.1: パラメータ契約監査の正確性修正（Codexによる、2026-07-28）

PR0-Aの監査は `self.p()` 参照があれば無条件で `ACTIVE` と分類していたが、これは静的スキャンとして過大主張だった。**具体的な誤検出を1件確認**: `choose_with_search()` 内の `current_eval = self.evaluate_state()`（1902行目）が**戻り値を一切使用していない**（`current_eval` はその後どこにも読まれない、`grep`で確認済み）。つまり `evaluate_state()` が参照する **`eval_*` 系19キー全て**（`eval_prize_taken`, `eval_bt_ready`, `eval_can_ko`, `eval_bench_liability` 等）は**現在のエージェントの意思決定に一切影響しない死んだコード**。

修正版監査 (`experiments/audit_parameter_contract.py`, PR0-A.1) は次を分離して報告する:

1. コード参照の有無
2. スコアリング結果が実際に呼び出し元で消費されているか（`decision_effect`: `STATICALLY_DECISION_RELEVANT` / `NO_OBSERVED_DECISION_EFFECT`）
3. 現在の設定下でのガード到達可能性（`current_config_reachability`: 例えば `rule_ucb1_search=1` により `engine_search_samples`/`endgame_samples` は現行設定下で到達不能と正しく判定）
4. ランタイム反実仮想的証拠（`ACTIVE` は今後この証拠が得られるまで使わない。静的参照のみは `REFERENCED_UNVERIFIED`）
5. Live Tuning Panel の実際の型安全性（整数キーも小数を受け付ける等、71キーで宣言型が保証されない）

検証済み: `python experiments/audit_parameter_contract.py --source-ref bf194b44... --check` でアーティファクトはバイト単位で再現。`python -m unittest experiments.test_audit_parameter_contract` で14件のユニットテスト全通過（独自に再実行して確認済み）。詳細は `experiments/agents/raging_bolt/audit/PR0_A_1_REVIEW.md`。

**次のアクション（未着手）**: 19個の `eval_*` パラメータが死んでいるという事実そのものは方策変更ではないので今は放置してよいが、PR0-Cで `evaluate_state()` の呼び出し意図（本来は使うはずだったのか、リファクタで置き去りになったのか）を評価器パスマトリクスとして棚卸しする際に扱う。

### PR0-B: Observation Snapshot / Deterministic Replay / CRN capability matrix（完了）

- `_semantic_action_id()`: `obs.select.option` の生インデックスではなく、type/area/index/attackId/cardId/serial等から構成する安定なアクション識別子（リプレイ間・エンジンバージョン間で比較可能）
- `RagingBoltPolicy.__init__(obs, replay_hidden_samples=None)` + `_predict_hidden()`: キャプチャした隠しゾーンのサンプル列を順番に消費するリプレイモードを追加。`replay_hidden_samples=None`（デフォルト）ではPRODUCTION挙動は完全不変
- `build_replay_bundle()` / `_maybe_capture_replay_bundle()`: `POKEMON_AI_REPLAY_BUNDLE_PATH` 環境変数で明示的にオプトインした時のみ、1決定ごとにJSONL 1行（obs_dict + 合法手のsemantic id一覧 + 選択結果 + キャプチャした隠し情報サンプル列）を追記。未設定時は完全にno-op
- `experiments/replay_decision.py`: 保存されたリプレイバンドルを読み込み、同一の隠し情報サンプル列で決定をN回再実行し、決定性を検証するCLI

**重要な実証結果（`experiments/agents/raging_bolt/audit/crn_capability_matrix.json` に記録）**:

- ヒューリスティックのみの決定（MAIN以外のselect_context、エンジン探索を呼ばない）は**完全に決定論的**——実データで7レコード×10リプレイ=70/70件が完全一致
- **MAIN（エンジン探索）決定は決定論的でない**——同一のobs_dict・同一の隠し情報サンプル列を与えても、3/3レコードで10回中2〜3回、異なる最終アクションが選ばれた
- 単離テスト（1候補+1隠し情報サンプルだけをsearch_begin/search_step/search_endで10回繰り返す）では完全に再現された（425.0固定）→ **不整合の原因は隠し情報サンプルの不確定性ではない**
- 根本原因を特定: `cg.api.search_begin()` の `manual_coin: bool = False` パラメータ（デフォルトFalse、我々のコードは明示的に渡していない）。ドキュメント曰く「コインの表裏を選択可能にする」——つまりFalseのままだと、ロールフォワード中にコインフリップ効果（ポケモンTCGの状態異常判定など）が発生した場合、**エンジン自身の制御不能な内部乱数**で解決される。これは`libcg.so`側の仕様で、Python側からのシード注入は不可能（ctypesシグネチャに乱数ストリーム引数が存在しないことは既に確認済み）
- **Decision Audit（PR1以降）への含意**: エンジン探索を伴う決定の単発A/B比較は本質的に信頼できない。ロードマップが元々要求している複数隠し状態×複数シードのプロトコル（Stage1: 4状態×1シード、Stage2: 8状態×2シード）の必要性が、この実測で裏付けられた

## 現在のブランチ / 主要コミット

ブランチ: `fix/tuning-panel-value-revert`

| コミット | 内容 |
|----------|------|
| `2cd50f9` | エンジン探索導入 |
| `ff9c5d2` | ハンドプレイ修正R2 + 探索候補ATTACH注入 |
| `9925f08` | リーリエコンボ保留 + auto_tune基盤 |
| `3c9de68` | ベンチダメージ評価 (dragapult対策) |
| `36728b0` | デッキv2実験(不採用) + 分析ツール |
| `10634ea` | 第9章: 終盤深読み+相手エネルギー推定 (ルカリオ20.0%) |
| `0527edf` | 第3章: 評価関数リファクタ+重み学習ツール (重み自体は不採用) |
| `e75a998` | AIMA第5章: UCB1バンディット配分 (既定OFF、要較正) |
| `24cb25e` | **提出物をraging_boltに切替**（リポジトリルートmain.py/deck.csv/params.json） |
| `e6a3f8a` | CLAUDE.md提出ルールをraging_bolt向けに更新 |
| `b1f4657` | HANDOFF.md更新 |
| `1323210` | **UCB1予算増を採用・本提出物に反映** (ルカリオ25.0%) |
| `bfdc712` | PR0-A: パラメータ契約監査 |
| `bf194b4` | PR0-A: 厳格テレメトリ導入 |
