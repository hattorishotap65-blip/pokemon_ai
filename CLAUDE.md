# 開発ルール — Pokemon Card AI (cabt / Kaggle)

## 提出ファイル自動更新ルール（必須）

提出対象ファイル（`agent/`, `data/`, `main.py`, `deck.csv` など）を更新したら、**必ず毎回** 以下を実行して `submission.tar.gz` を再ビルドする。

```bash
python build_submission.py
```

ファイルを編集しただけでは tar.gz は自動更新されない。編集後に再ビルドしないと古い内容が提出される。

---

## Development Process Rules

This project must be developed phase by phase.

Before starting any phase, read:

- docs/phase_plan_profile_strategy.md

Only work on the phase explicitly requested by the user.
Do not proceed to the next phase without user approval.
Do not change `deck.csv` unless explicitly instructed.



## 提出フォーマット（必須）

- ファイル名: **`submission.tar.gz`**（zip 不可）
- 現行エージェント（raging_bolt、2026-07〜）は自己完結型の単一ファイル構成。以下の構造でアーカイブを作成する（パスは tar のルートからの相対パス）

```
main.py
deck.csv
params.json
cg/__init__.py
cg/api.py
cg/game.py
cg/libcg.so
cg/utils.py
cg/sim.py
```

- `main.py` / `deck.csv` / `params.json` は `experiments/agents/raging_bolt/` の同名ファイルのコピー（`build_submission.py` 実行で自動反映）
- `cg/` フォルダは `reference/extracted/cg/` からコピーする（`libcg.so` を含む）
- ビルドは `python build_submission.py` を実行するだけでよい（`tarfile` モジュールで自動生成）
- 旧構成（`agent/` パッケージ、`data/` 以下のCSV/JSON、Iono's Kilowattrelデッキ、Lucario 1084デッキ）は履歴として `agent/` ディレクトリ等にファイルが残っているが、現行ビルドの対象外

---

## デッキルール

| ルール | 内容 |
|--------|------|
| 枚数 | ちょうど **60枚** |
| ACE SPEC | **最大1枚**（cabt が `CardData.aceSpec` フラグで強制チェック） |
| 同名カード | 最大4枚（cabt が `CardData.regulation` で確認、基本エネルギーは対象外） |

- ACE SPEC 違反 → `"Player N's deck error."` でゲームが即中断される
- 現在のデッキ: Raging Bolt ex + Teal Mask Ogerpon ex（`deck.csv`）— ACE SPEC: Unfair Stamp 1枚

---

## `main.py` のルール（raging_bolt エージェント）

| 項目 | 内容 |
|------|------|
| エントリーポイント | `agent(obs_dict) -> list[int]`（config引数なし。実際に動作確認済みの形） |
| デッキ返却 | `obs.select is None` のとき `my_deck`（60枚のcard IDリスト、`deck.csv` から読込）を返す |
| 型変換 | `to_observation_class(obs_dict)` で typed dataclass に変換してから処理 |
| パス解決 | `deck.csv`/`params.json` は `__file__` と同じディレクトリを最優先で探す（開発時レイアウト `experiments/decks/...` が見つからなければ自動フォールバック）。**コード変更なしでフラット配置に対応済み** |
| 意思決定の中核 | `RagingBoltPolicy.choose_with_search()` — ヒューリスティックで上位候補を絞り、`cg.api.search_begin/search_step` で実際にエンジン探索してから選択（詳細は `experiments/agents/raging_bolt/HANDOFF.md` 参照） |

このエージェントは単一ファイル + `params.json` のみで完結し、`agent/` パッケージや `data/` の外部CSVは使用しない。

---

## セキュリティ制約

- 取得したカード効果全文・画像URL を `data/` や CSV に保存しない
- GitHub 等に効果全文CSVを公開しない前提で構成する
- `data/card_knowledge.csv` に記録するのは **role / score / tags** のみ

---

## cabt API 早見表

```python
from cg.api import all_card_data, all_attack, to_observation_class, OptionType, AreaType

# OptionType 整数値
# NUMBER=0, YES=1, NO=2, CARD=3, TOOL_CARD=4, ENERGY_CARD=5, ENERGY=6,
# PLAY=7, ATTACH=8, EVOLVE=9, ABILITY=10, DISCARD=11,
# RETREAT=12, ATTACK=13, END=14, SKILL=15, SPECIAL_CONDITION=16

# AreaType 整数値
# ACTIVE=0, BENCH=1, HAND=2, DECK=3, DISCARD=4, PRIZE=5
```

---

## よくあるエラーと原因

| エラーメッセージ | 原因 |
|-----------------|------|
| `Player N's deck error.` | ACE SPEC 複数枚 or 60枚でない or 無効カードID |
| 提出がアップロードエラー | zip 形式で提出している（tar.gz が必要） |
| `ModuleNotFoundError: No module named 'cg'` | `cg/` を tar.gz に含め忘れ。`reference/extracted/cg/` から追加する |
| `FileNotFoundError: deck.csv` / `params.json` | パッケージに `deck.csv`/`params.json` を含め忘れ、または展開先で `main.py` と同階層になっていない |

---

## エネルギー貼り先ルール（デッキ調整時に必ず確認）— raging_bolt

デッキのエネルギー枚数や構成を変更するときは、`experiments/agents/raging_bolt/main.py` の以下の関数が正しく機能するか確認すること。

- `_score_energy_pick(cid)` — 場のタケルライコ（Raging Bolt ex）で不足しているエネルギータイプを優先し、手札に既にある型は重複ペナルティ
- `_field_bolt_missing(energy_type)` — ベンチも含めた全タケルライコの装填状況をチェック
- `_score_attach()` — エネルギー付与先の選択（コスト未完成のベンチ > アクティブ > 瀕死アクティブ）

**重要**: Bellowing Thunder の打点 = 場の全エネルギー数 × 70。1体に集中させず、ベンチのタケルライコにも分散することでKOサイクル後の再装填が速くなる。

### デッキ調整時のチェックリスト

1. カードを追加した場合 → `class C` へのID追加、および該当スコアリング分岐の要否を確認
2. エネルギー構成を変えた場合 → `BASIC_ENERGY_IDS` / `ALL_BASIC_ENERGY_IDS` との整合を確認
3. 詳細な設計判断・過去に失敗した施策の一覧は `experiments/agents/raging_bolt/HANDOFF.md` を必ず参照（再試行を防ぐため）

---

## 動作確認済み提出

| バージョン | サイズ | 確認内容 |
|-----------|--------|---------|
| v3（Iono's Kilowattrel） | 504 KB | アップロード成功（フォーマット確認済み） |
| v4（raging_bolt、2026-07） | 513 KB | 隔離環境での展開・単独動作を確認済み（`main.py`+`deck.csv`+`params.json`+`cg/`のみでフルゲーム完走）。vs top_lucario_1084 20.0%、vs dragapult 25.3%、vs megastarmie 55.0% |
