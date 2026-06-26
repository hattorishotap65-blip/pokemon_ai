# PTCG Simulator Integration Research

## Goal

Learned advisor の評価用に、実戦または疑似実戦ログを取得できる simulator / harness を選定する。

## Candidates

| Candidate | Local Run | CLI/API | Agent Hook | Logs | License/Risk | Fit |
|-----------|-----------|---------|------------|------|-------------|-----|
| **cabt (Kaggle)** | Yes (WSL) | Python API | Yes (native) | JSONL | Competition SDK | **Best** |
| PTCG-sim / Meta PTCG-sim | Yes | Web UI only | No API | None | MIT | Poor |
| RyuuPlay | Yes | TypeScript | Bot API (TS) | Limited | MIT | Medium |
| PTCG_CL | Yes | Python | Limited | None | Study only | Poor |
| DeckGym | Yes | Rust CLI | No Python | CSV | MIT | Poor |
| Pokemon TCG Live / PCGL | No | None | Forbidden | None | ToS violation | **Excluded** |

## Candidate Details

### cabt (Kaggle Competition Engine) — BEST FIT

**概要**: Kaggle PTCG AI Battle Challenge の公式バトルエンジン。Matsuo Institute (東京大学) が開発。`libcg.so` (Linux binary) + Python SDK (`cg/api.py`, `cg/game.py`)。

**セットアップ**: 既にリポジトリに `reference/extracted/cg/` として含まれている。WSL 内で実行可能。

**実行方法**:
```bash
# WSL 内
python experiments/run_external_agent.py --agent main.py --deck deck.csv --n 100
python experiments/head_to_head.py --agent-a main.py --deck-a deck.csv --agent-b ... --deck-b ...
```

**入出力**:
- 入力: `deck.csv` (60行カードID), `main.py` (agent関数)
- 出力: 勝敗、ターン数、action type 分布 (既存スクリプトで取得可能)

**Agent 接続**: `agent(obs_dict) -> list[int]` で合法手インデックスを返す。完全にプログラマティック。

**Trace 接続**: `main.py` 内の learned advisor hook が既に trace を出力。追加の adapter は不要。

**リスク**: なし。Competition SDK として提供されており、ローカル自己対戦は許可されている。

**採用判断**: **採用**。既に動作するインフラが揃っており、追加開発は最小限。

---

### PTCG-sim / Meta PTCG-sim

**概要**: Web ベースの PTCG tabletop simulator。JavaScript/Node.js/Socket.io で実装。

**セットアップ**: npm install + node server 起動。

**問題点**:
- **Web UI 前提** — ブラウザ操作が必要で CLI/API からの自動操作はない
- **Agent hook なし** — プログラマティックに action を差し込む API がない
- **カードプール不一致** — cabt のカードプール (2000枚) と互換性がない可能性
- **ログ出力なし** — 対戦ログを JSONL で取得する仕組みがない

**採用判断**: **不採用**。Agent 自動操作が不可能。

---

### RyuuPlay

**概要**: TypeScript 製の PTCG simulator。MIT ライセンス。SimpleBot AI が組み込み済み。

**利点**:
- Bot vs Bot の自動対戦が可能
- SimpleBot は全デッキ対応の AI
- ランキングシステムあり

**問題点**:
- **TypeScript のみ** — Python から直接呼べない (subprocess でビルド済み Node を呼ぶことは可能)
- **カードプール不一致** — cabt とカードID/効果が異なる可能性が高い
- **Agent hook が TypeScript API** — Python adapter が必要
- **メンテナンス状況** — 最終更新が不明

**採用判断**: **不採用**。cabt との互換性確保コストが高すぎる。

---

### PTCG_CL (Lagyu)

**概要**: Python 製の PTCG simulator。学習目的。開発中断。

**問題点**: 開発中断、カードプール不十分、API 不安定。

**採用判断**: **不採用**。

---

### DeckGym

**概要**: Rust 製の PTCG Pocket simulator。高速 (10000 sim / 3秒)。

**問題点**: PTCG Pocket 用 (本家 PTCG とルールが異なる)。Python binding なし。

**採用判断**: **不採用**。対象ゲームが異なる。

---

### Pokemon TCG Live / PCGL

**概要**: Pokemon 公式クライアント。

**リスク**:
- **ToS 違反**: 自動操作は利用規約で禁止されている
- **API なし**: プログラマティックアクセス不可
- **アカウント停止リスク**: 自動化が検出された場合

**採用判断**: **除外**。公式クライアントの自動操作は行わない。

---

## Recommendation

### **Option A: cabt (既存インフラ) を使う — 推奨**

理由:
1. **既に動作する** — `run_external_agent.py`, `head_to_head.py` で自己対戦・対戦テストが可能
2. **Agent hook が native** — `agent(obs_dict)` で直接接続
3. **Trace 接続済み** — `main.py` の learned advisor hook が trace を出力
4. **カードプール一致** — Kaggle competition と同じ 2000枚
5. **追加開発が最小限** — 新規 simulator の導入不要

必要な追加作業:
- `run_external_agent.py` / `head_to_head.py` の出力を trace JSONL に変換する adapter
- trace analyzer / recommender との接続
- 勝敗結果を learning scaffold の `result` フィールドにマッピング

### 他 Option との比較

| Option | 追加開発量 | リスク | 評価 |
|--------|-----------|--------|------|
| A: cabt | 小 (adapter のみ) | なし | **推奨** |
| B: 外部 simulator | 大 (互換層が必要) | カードプール不一致 | 非推奨 |
| C: 自作 mock | 中 (ルール実装) | 簡略化による精度低下 | 予備 |
| D: 公式クライアント | - | ToS 違反 | 除外 |

---

## Proposed Next PR

cabt 既存インフラを使う方針で、次 PR では以下を実装:

1. **trace evaluation runner** — `head_to_head.py` を拡張し、learned advisor 有効/無効で対戦して勝率差を測定
2. **self-play trace collector** — 自己対戦中の advisor trace を自動収集し、trace analyzer に渡す
3. **result mapper** — cabt の勝敗結果を learning scaffold の `result` JSON に変換

PRタイトル案: `experiment: add cabt trace evaluation runner`

---

## Out of Scope

- simulator 本体の大規模実装
- Pokemon TCG Live / PCGL の自動操作
- account login / screen scraping
- 外部 simulator との互換層構築
