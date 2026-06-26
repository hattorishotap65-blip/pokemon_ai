# PTCG Simulator Integration Research

## Goal

Learned advisor の評価用に、実戦または疑似実戦ログを取得できる simulator / harness を選定する。

## Candidates

| Candidate | Local Run | CLI/API | Agent Hook | Logs | License/Risk | Fit |
|-----------|-----------|---------|------------|------|-------------|-----|
| **cabt (Kaggle)** | Yes (WSL) | Python API | Yes (native) | JSONL | Competition SDK | **Best** |
| PTCG-Bench | Yes | Python | LLM agent | JSON | Apache 2.0 | Medium |
| PTCG-sim / Meta PTCG-sim | Yes | Web UI only | No API | None | MIT | Poor |
| RyuuPlay | Yes | TypeScript | Bot API (TS) | Limited | MIT | Poor |
| PTCG_CL | Yes | Python | Limited | None | Study only | Poor |
| DeckGym | Yes | Rust CLI | No Python | CSV | MIT | Poor |
| Pokemon TCG Live / PCGL | No | None | Forbidden | None | ToS violation | **Excluded** |

## Candidate Details

### cabt (Kaggle Competition Engine) — BEST FIT

**概要**: Kaggle PTCG AI Battle Challenge の公式バトルエンジン。Matsuo Institute (東京大学) が開発。`libcg.so` (Linux binary) + Python SDK。

**リポジトリ内の状態**:
- `reference/extracted/cg/` — **Git 追跡済み** (api.py, game.py, libcg.so, sim.py, utils.py)
- `experiments/run_with_experiment_deck.py` — **Git 追跡済み**
- `experiments/run_external_agent.py` — **ローカルのみ (Git 未追跡)**。次PR で追加が必要
- `experiments/head_to_head.py` — **ローカルのみ (Git 未追跡)**。次PR で追加が必要

**実測確認済み** (2026-06-26):
- タケルライコ+オーガポンデッキで 50g self-play: errors=0, timeouts=0
- Lucario deck vs タケルライコ deck: 50g head-to-head 動作確認

**実行方法** (WSL 内):
```bash
PYTHONPATH=reference/extracted python3 experiments/run_external_agent.py \
    --agent main.py --deck deck.csv --n 50
```

**Agent 接続**: `agent(obs_dict) -> list[int]` で合法手インデックスを返す。

**Trace 接続**: `main.py` 内の learned advisor hook が trace を出力。

**リスク**: なし。Competition SDK として提供。

**採用判断**: **採用** (条件付き — 未追跡スクリプトの Git 追加が前提)。

---

### PTCG-Bench — MEDIUM FIT

**概要**: LLM agent の PTCG プレイ能力を評価するベンチマーク。2025年発表。

**URL**:
- Paper: https://arxiv.org/html/2605.29653v1
- GitHub: https://github.com/zjunet/PTCG-B

**利点**:
- Python 実装
- LLM agent 向けに設計されており、action 選択の hook がある
- 自己進化 (self-evolution) の評価機能あり

**問題点**:
- **カードプール不一致** — cabt の Competition カードプール (2000枚) と異なる可能性
- **ルール差異** — cabt の Competition ルール (ACE SPEC 制限等) との互換性が不明
- **LLM 前提** — 我々の weighted scorer は LLM ではないため、adapter が必要
- **導入コスト** — 新規環境セットアップが必要

**採用判断**: **不採用** (現時点)。cabt との互換性確保コストが高い。将来的に LLM agent を検討する場合は再評価。

---

### PTCG-sim / Meta PTCG-sim

**概要**: Web ベースの PTCG tabletop simulator。

**URL**:
- PTCG-sim: https://github.com/xxmichaellong/ptcg-sim
- Meta PTCG-sim: https://meta-ptcg.org/

**問題点**: Web UI 前提、Agent hook なし、カードプール不一致、ログ出力なし。

**採用判断**: **不採用**。

---

### RyuuPlay

**概要**: TypeScript 製の PTCG simulator。MIT ライセンス。

**URL**: https://github.com/keeshii/ryuu-play

**問題点**: TypeScript のみ、カードプール不一致、Python adapter 必要。

**採用判断**: **不採用**。

---

### PTCG_CL

**概要**: Python 製の PTCG simulator。学習目的。

**URL**: https://github.com/Lagyu/PTCG_CL

**問題点**: 開発中断、カードプール不十分。

**採用判断**: **不採用**。

---

### DeckGym

**概要**: Rust 製の PTCG Pocket simulator。

**URL**: https://github.com/bcollazo/deckgym-core

**問題点**: PTCG Pocket 用 (本家 PTCG とルールが異なる)。

**採用判断**: **不採用**。

---

### Pokemon TCG Live / PCGL

**概要**: Pokemon 公式クライアント。

**リスク**: ToS 違反 (自動操作禁止)、API なし、アカウント停止リスク。

**採用判断**: **除外**。

---

## Recommendation

### **Option A: cabt (既存インフラ) を使う — 推奨 (条件付き)**

**条件**: `experiments/run_external_agent.py` と `experiments/head_to_head.py` が Git に追加されていること。現在はローカルのみ存在し Git 未追跡。次PR の最初にこれらを Git 追加する。

`reference/extracted/cg/` (cabt SDK 本体) は既に Git 追跡済み。

**必要な追加作業**:
1. `run_external_agent.py` / `head_to_head.py` を Git 追加
2. self-play 結果を trace JSONL に変換する adapter
3. 勝敗結果を learning scaffold の `result` フィールドにマッピング

### 他 Option との比較

| Option | 追加開発量 | リスク | 評価 |
|--------|-----------|--------|------|
| A: cabt | 小 (adapter + Git 追加) | なし | **推奨** |
| B: PTCG-Bench | 中 (互換層) | カードプール不一致 | 予備 |
| C: 外部 simulator | 大 | 互換性不明 | 非推奨 |
| D: 公式クライアント | - | ToS 違反 | 除外 |

---

## Proposed Next PR

1. `experiments/run_external_agent.py` / `experiments/head_to_head.py` を Git 追加
2. **human_play.py** — cabt 上で人間が対話的にプレイし、各決定を learning JSONL に記録
3. trace evaluation runner — advisor 有効/無効で対戦して勝率差を測定

PRタイトル案: `experiment: add human play CLI and cabt runner scripts`

---

## Out of Scope

- simulator 本体の大規模実装
- Pokemon TCG Live / PCGL の自動操作
- account login / screen scraping
- 外部 simulator との互換層構築
