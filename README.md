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
│   ├── run_matches.py           # ローカル大量対戦シミュレーション
│   └── analyze_logs.py          # ログ分析・改善指標の出力
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

### Kaggle に提出するファイル

```
main.py
deck.csv
agent/
data/card_knowledge.csv   # カード知識は最新版を毎回含める
```

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

---

## 公式環境への接続

公式 API 仕様が公開されたら `main.py` の以下 2 関数だけ修正します。

```python
def _extract_state(obs) -> dict:
    # obs の形式に合わせて state dict を返す

def _extract_legal_actions(obs) -> list:
    # obs から合法手リストを返す
```

`agent/` ディレクトリ内のコードは変更不要です。

---

## 注意事項・未確定事項

> **公式 API 仕様が未確定の箇所があります。確認が取れたら更新してください。**

| 項目 | 現在の仮定 | 確認が必要な点 |
|------|-----------|----------------|
| エントリ関数名 | `agent(obs, config)` | Kaggle の公式ドキュメント参照 |
| `state` の構造 | `obs["state"]` | 公式環境で確認 |
| `legal_actions` の場所 | `obs["legal_actions"]` | 公式環境で確認 |
| `deck.csv` フォーマット | `card_id,card_name,count` | 公式仕様書参照 |
| カード ID | PDF の Card ID | Card_ID List_EN.pdf で要確認 |

---

## 締め切り

- Simulation カテゴリ: **2026 年 8 月 17 日**
- Strategy カテゴリ: 2026 年 9 月 14 日
