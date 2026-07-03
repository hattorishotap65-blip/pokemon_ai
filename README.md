# Pokemon TCG AI — Kaggle Competition Agent

Kaggle コンペ [PTCG AI Battle Challenge Simulation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle) 向けの
ルールベース AI エージェントです。

## ゴール（フェーズ 1）

強い AI より **落ちない AI** を最初に作る。

- 違法手を出さない
- タイムアウトしない
- ログが全試合残る
- 100 戦単位で改善比較できる
- `data/card_knowledge.csv` を編集するだけで戦略を調整できる

---

## ディレクトリ構成

```
pokemon_card_ai/
├── main.py                      # 提出エントリポイント (Kaggle から呼ばれる)
├── deck.csv                     # 提出デッキ 60 枚
├── agent/
│   ├── __init__.py
│   ├── policy.py                # 行動スコアリング (AI の中心)
│   ├── evaluator.py             # 盤面評価関数
│   ├── card_knowledge.py        # card_knowledge.csv の読み込み (v1/v2 両対応)
│   ├── logger.py                # 対戦ログ出力
│   └── fallback.py              # エラー時の安全行動選択
├── data/
│   ├── card_master.csv          # カード ID 一覧 (PDF → build_card_master.py で生成)
│   ├── card_detail_raw.csv      # API 取得済みカード詳細 (fetch_card_details.py で生成)
│   ├── pending_match.csv        # 照合できなかったカード (要確認)
│   ├── card_knowledge.csv       # AI 判断用スコア DB ← ここを編集して強化
│   └── matchup_notes.csv        # 対面メモ
├── tools/                       # データ整備パイプライン
│   ├── requirements.txt         # pip install -r tools/requirements.txt
│   ├── build_card_master.py     # PDF → card_master.csv
│   ├── fetch_card_details.py    # API 取得 → card_detail_raw.csv + pending_match.csv
│   ├── match_card_details.py    # 照合エンジン (fetch から import)
│   ├── generate_card_knowledge.py  # card_detail_raw.csv → card_knowledge.csv
│   └── validate_card_data.py    # データ整合性チェック
├── experiments/
│   ├── agents/raging_bolt/      # 実験用 RagingBolt agent と params.json
│   ├── web/                     # 対戦サンドボックス / human trace / live tuning UI
│   ├── learning/                # 学習・分析用スクリプト
│   ├── run_matches.py           # ローカル大量対戦シミュレーション
│   ├── analyze_logs.py          # ログ分析・改善指標の出力
│   └── test_*.py                # 実験機能の回帰テスト
└── logs/                        # 自動生成される対戦ログ (*.jsonl, *.csv)
```

---

## クイックスタート

### Step 1 — カードデータパイプラインのセットアップ

```bash
# 依存ライブラリ
pip install -r tools/requirements.txt

# PDF から card_master.csv を生成 (PDF は別途用意)
python tools/build_card_master.py --pdf Card_ID_List_EN.pdf --out data/card_master.csv

# Pokemon TCG API からデッキ 60 枚の詳細を取得
# (無料 API キーを https://dev.pokemontcg.io/ で取得すると安定)
python tools/fetch_card_details.py --api-key YOUR_KEY

# カード詳細 → AI 判断用スコア CSV を生成
python tools/generate_card_knowledge.py

# データ整合性チェック
python tools/validate_card_data.py
```

### Step 2 — ローカル対戦シミュレーション

```bash
# 100 戦シミュレーション
python experiments/run_matches.py --n 100

# ログ分析
python experiments/analyze_logs.py
```

### Step 3 — AI チューニングサイクル

```
card_knowledge.csv を編集
  ↓
python experiments/run_matches.py --n 100 --output logs/after.csv
  ↓
python experiments/analyze_logs.py
  ↓
改善点を確認してまた編集
```

### Step 4 — 実験用 Web サンドボックスを起動する

`experiments/web` には、AI と人間の判断差を記録・確認しながら RagingBolt agent を改善するための実験用 UI があります。

```bash
# WSL想定。デフォルトは http://localhost:8000
python3 experiments/web/launch.py

# ポート指定
python3 experiments/web/launch.py --port 8001
```

必要に応じて以下を先に実行します。

```bash
pip install pymupdf pillow numpy
python3 experiments/web/setup_agents.py
```

カード画像が不足している場合は、`reference/Card_ID List_EN.pdf` を用意したうえで以下を実行します。

```bash
python3 experiments/web/extract_card_images.py
```

### Kaggle に提出するファイル

```
main.py
deck.csv
agent/
data/card_knowledge.csv   # カード知識は最新版を毎回含める
```

`experiments/` 配下は調査・分析・UI・学習補助用であり、通常の提出物には含めません。

---

## 実験用 Web サンドボックスの現在仕様

`experiments/web` は、RagingBolt agent を人間操作と比較しながら改善するためのサンドボックスです。目的は、AI をその場で本番修正することではなく、判断差を観察し、仮調整し、ログを残して、後続 PR で安全に検証・反映することです。

### 全体方針

- `params.json` は直接書き換えない
- `experiments/agents/raging_bolt/main.py` の行動ロジックは直接変更しない
- `submission.tar.gz` は作らない / 更新しない
- セッション中だけ有効な runtime override で仮調整する
- 正式反映は、ログ集計と勝率検証後に別 PR で行う
- UI 上の表示値は `escapeHtml()` でエスケープし、XSS を避ける

### Human Trace

記録 ON の状態でプレイすると、人間の選択・AI の推奨・候補行動・スコア・思考タグが JSONL に保存されます。

記録される主な情報:

- turn / context
- AI 推奨行動
- 人間が選択した行動
- 候補行動一覧
- 候補スコア
- strategy tag
- risk flag
- human considered action

この trace は、後続の disagreement review / action value learning / params 調整の入力になります。

### Live Disagreement Review

`/select` で人間が行動を確定したあと、AI と人間の判断差がある場合に `live_review` が返ります。

表示対象は、すべての不一致ではなく、勝敗に効きやすい優先カテゴリに絞っています。

代表カテゴリ:

- `no_next_attacker`
- `boss_missed`
- `boss_used_too_early`
- `agreement_bad_risk`
- `opponent_return_ko_underestimated`

UI に表示される主な情報:

- category
- AI の推奨行動
- 人間の選択行動
- score gap
- risk flags
- message

重要な設計として、`live_review` は **行動確定後** にのみ表示されます。行動前に表示すると人間の選択にバイアスが入るためです。

### Live Tuning Panel

Live Tuning Panel は、`live_review.show == true` のときだけ表示されます。

できること:

- 判断差に関連しそうなパラメータ候補を表示する
- 各パラメータの現在値を確認する
- パラメータの意味を UI 上で確認する
- 値を入力して「一時適用」する
- runtime override 適用前後の AI 推奨を preview する
- runtime override を reset する
- reviewer label / confidence / note を付けてログ保存する

できないこと:

- `params.json` を直接更新する
- `main.py` を自動修正する
- 調整値をそのまま本番採用する
- 勝率検証なしで正式反映する

### Runtime Override

runtime override は、サーバープロセス内だけに保持される一時パラメータです。

優先順位:

1. runtime override
2. `params.json` 由来の base params
3. コード内 default 値

実装上は、`experiments/web/live_tuning.py` の `_OVERRIDES` に保持されます。`server.py` は deck load 時に `ME['base_params']` として `params.json` 由来の値を snapshot し、override 適用時だけ `ME['mod'].P` を `effective_params` に差し替えます。

runtime override は以下で消えます。

- `/runtime_params/reset`
- `/new` で新対戦を開始したとき
- サーバー再起動

### Runtime Params API

#### `GET /runtime_params`

現在の base params と runtime overrides を返します。

```json
{
  "params": {
    "impact_crispin_bolt_bonus": 200
  },
  "overrides": {
    "impact_crispin_bolt_bonus": 50
  }
}
```

UI はこの API を使って、一時適用後・リセット後の表示値を再同期します。

#### `POST /runtime_params`

1 つの runtime override を設定します。

入力例:

```json
{
  "param": "impact_crispin_bolt_bonus",
  "value": 50
}
```

仕様:

- 存在しない param は拒否する
- 非数値は拒否する
- `bool` / `NaN` / `Infinity` は拒否する
- 任意コード実行につながるような param 名は拒否する
- 成功時に before / after preview も返す
- `params.json` は変更しない

#### `POST /runtime_params/reset`

runtime override をすべて消し、base params に戻します。

#### `POST /runtime_params/preview`

現在の runtime override を使って、対象の判断場面に対する AI 推奨の before / after を比較します。

返却例:

```json
{
  "before": {
    "recommended_action": "Bellowing Thunder",
    "top_candidates": []
  },
  "after": {
    "recommended_action": "Crispin",
    "top_candidates": []
  },
  "changed": true
}
```

#### `POST /runtime_params/log`

現在の preview 結果に reviewer label / confidence / note を付けて `session_tuning_log.jsonl` に保存します。

### Frozen Review Snapshot

Live Tuning preview は、現在の `GAME['obs_dict']` ではなく、レビュー対象の判断直前の盤面 snapshot を使います。

理由:

- 人間が `/select` で行動を確定する
- その後、サーバーは `_select()` と `_advance_opponent()` でゲームを次の判断へ進める
- もし preview が現在の `obs_dict` を使うと、レビュー対象の不一致場面ではなく、次の場面を評価してしまう

このため、`server.py` は `/select` 前に `GAME['frozen_review_obs']` を保存します。`_tuning_compute_fn()` と `_log_tuning_event()` は、可能ならこの frozen snapshot を使います。

### Suggested Params

`live_review` の category / risk flags に応じて、調整候補の param を heuristic に提示します。

例:

| category / risk | suggested params |
|---|---|
| `no_next_attacker` | `impact_crispin_per_energy`, `impact_crispin_bolt_bonus`, `impact_energy_retrieval_per`, `impact_attach_bt_req`, `search_weight_future` |
| `boss_missed` | `impact_boss_prize_mult`, `search_weight_future` |
| `boss_used_too_early` | `impact_boss_prize_mult`, `search_weight_future` |
| `active_may_be_ko_next_turn` | `impact_retreat_safety`, `impact_retreat_penalty`, `search_weight_risk` |
| `not_enough_energy` | `impact_crispin_per_energy`, `impact_energy_retrieval_per`, `impact_search_item`, `score_play_pokemon_ogerpon`, `impact_attach_bt_req` |

UI には param 名だけでなく、`describe_param()` による説明も表示されます。

### Session Tuning Log

Live Tuning の一時適用・preview・明示保存は、`experiments/web/session_tuning_log.jsonl` に append-only で記録されます。

形式例:

```json
{
  "timestamp": "2026-06-30T12:34:56",
  "game_id": "20260630_123456",
  "turn": 3,
  "category": "no_next_attacker",
  "risk_flags": ["no_next_attacker"],
  "ai_action_before": "Bellowing Thunder",
  "human_action": "Crispin",
  "param": "impact_crispin_bolt_bonus",
  "old_value": 200,
  "new_value": 50,
  "ai_action_after": "Crispin",
  "top_candidates_before": [],
  "top_candidates_after": [],
  "review_label": "human_better",
  "confidence": "high",
  "note": "次アタッカー不在を避けるためCrispin優先が妥当"
}
```

review label:

- `human_better`
- `agent_better`
- `both_ok`
- `both_bad`
- `unclear`

confidence:

- `high`
- `medium`
- `low`

このログは、後続 PR で以下に使います。

- よく出る調整候補の集計
- `params.json` への正式反映候補の選定
- 勝率比較
- Action Value Learning 用の教師データ候補

### 関連テスト

```bash
python experiments/test_live_tuning_panel.py
python experiments/test_runtime_param_overrides.py
python experiments/test_live_disagreement_review.py
python experiments/test_disagreement_review_builder.py
python experiments/test_disagreement_label_analyzer.py
```

CI では Live Tuning / Runtime Override 系テストも実行します。

---

## データパイプライン詳細

### 照合の仕組み

`tools/match_card_details.py` の `confidence_score()` が照合を行います。

| 条件 | スコア |
|------|--------|
| 名前完全一致 + セット一致 + 番号一致 | 1.00 |
| 名前完全一致 + 番号一致 | 0.90 |
| 名前 ≒ 似ている + セット一致 + 番号一致 | 0.75 |
| 名前完全一致 + セット一致 | 0.78 |
| 名前完全一致のみ | 0.60 |
| 名前 ≒ 似ているのみ | 0.35 |

スコアが **0.80 未満** は `pending_match.csv` に保存され、人間の確認待ちになります。

### card_knowledge.csv のスコア定義

| 列名 | 意味 | 例 |
|------|------|----|
| `keep_score` | 手札に持ち続ける優先度 | 9 = 捨てたくない |
| `use_score` | このターン使う優先度 | 9 = 最優先で使う |
| `search_score` | サーチ対象にする優先度 | 9 = 真っ先に探す |
| `discard_penalty` | 捨てたときの損失 | 9 = 捨てると致命的 |
| `bench_score` | ベンチに出す優先度 | 8 = 早めに出す |
| `energy_attach_score` | エネルギーを貼る優先度 | 9 = メインアタッカー |
| `attack_score` | 攻撃スコア (0–10) | 6 = 120ダメ相当 |
| `evolution_score` | 進化させる優先度 | 9 = 最優先進化 |
| `risk_score` | 使用リスク | 3 = exポケモン (2枚サイド) |

### pending_match.csv の対処方法

```bash
# 1. ファイルを確認
cat data/pending_match.csv

# 2. 正しい API card_id を調べる
#    https://www.pokemon.com/us/pokemon-tcg/pokemon-cards/ または https://pkmncards.com/

# 3. card_detail_raw.csv に手動で追記する

# 4. 再生成
python tools/generate_card_knowledge.py --merge

# 5. バリデーション
python tools/validate_card_data.py
```

---

## AI の仕組み

### 行動選択フロー

```
Kaggle 環境
  └→ agent(obs, config)        ← main.py
       └→ select_action(state, legal_actions)
            └→ PolicyAgent.select_action()   ← agent/policy.py
                 ├─ _score_attack()
                 ├─ _score_play_pokemon()
                 ├─ _score_attach_energy()
                 ├─ _score_play_trainer()
                 ├─ _score_evolve()
                 └─ _score_retreat()
                      └→ CardKnowledge.get_role()  ← data/card_knowledge.csv
```

エラーが起きた場合は `fallback_action()` が必ず合法手を返します。

### スコアリング優先順位

| 優先度 | 行動 | スコア目安 |
|--------|------|------------|
| 最高 | 最後のサイドを取る KO 攻撃 | 60+ |
| 高 | KO できる攻撃 | 30+ |
| 高 | メインアタッカーへ進化 | 14+ |
| 高 | メインアタッカーへエネルギー | 9 |
| 高 | サーチ系トレーナー | 7–9 |
| 中 | たねポケモンを出す | 6–9 |
| 中 | ドロー系トレーナー | 6–8 |
| 低 | 逃げる (HP < 30) | 7 |
| 最低 | ターン終了 | 0.5 |

---

## AI を強化する方法

### 1. card_knowledge.csv を編集する

`data/card_knowledge.csv` の `role` / `priority` / `timing` を変えると
コードを変えずに AI の判断が変わります。

```csv
card_id,card_name,card_type,role,priority,timing,notes
103,Dragapult ex,Pokemon,main_attacker,high,mid_game,メインアタッカー
204,Iono,Trainer,draw,high,any,手札リセット妨害
```

**role の種類**

| role | 意味 |
|------|------|
| `main_attacker` | メインアタッカー (エネルギー最優先) |
| `basic_setup` / `evolve_bridge` | 進化ライン |
| `search_engine` | 毎ターンサーチ系 |
| `search` | グッズサーチ |
| `draw` | ドロー強化 |
| `disruption` | 相手妨害 |
| `energy_search` | エネルギーサーチ |
| `evolve` | 進化補助 |
| `tool` | ポケモンのどうぐ |
| `recovery` | 回収系 |

### 2. policy.py のスコアを調整する

`agent/policy.py` の各 `_score_*()` 関数内の数値を変えると
スコアリングを細かく調整できます。

### 3. 100 戦回してログを比較する

```bash
# 変更前
python experiments/run_matches.py --n 100 --output logs/before.csv

# card_knowledge.csv を編集する

# 変更後
python experiments/run_matches.py --n 100 --output logs/after.csv

# 比較
python experiments/analyze_logs.py --results logs/after.csv
```
