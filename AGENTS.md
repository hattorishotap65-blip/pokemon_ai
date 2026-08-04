# 開発ルール — Pokemon Card AI (cabt / Kaggle)

> 対象ツール: **Codex**。Claude Code向けの同等ルールは [`CLAUDE.md`](CLAUDE.md) を参照（現行構成・安全ルールはこのファイルと一致させている）。

## 現在の正本

現在の正本は **Raging Bolt ex + Teal Mask Ogerpon ex** 構成（`experiments/agents/raging_bolt/` で開発）。旧 Iono's Kilowattrel構成（`agent/` パッケージ + `data/` 配下）は履歴として残っているが、現行の提出物・現行の開発ルールの対象ではない。旧構成に関する記述は本ファイル内の「旧構成（Iono's Kilowattrel、現行対象外）」セクションを参照。

## 提出ファイル更新ルール（必須）

提出対象は **リポジトリルート直下** の `main.py` / `deck.csv` / `params.json` と `cg/`（`reference/extracted/cg/` からコピー）のみ。これらを更新したら、**必ず毎回** 以下を実行して `submission.tar.gz` を再ビルドする。

```bash
python build_submission.py
```

`build_submission.py` はルート直下の3ファイルをそのまま使用するだけで、`experiments/agents/raging_bolt/` からの自動コピーは行わない。ファイルを編集しただけでは tar.gz は自動更新されない。編集後に再ビルドしないと古い内容が提出される。

旧構成の `agent/` パッケージ・`data/` 配下は現行ビルド対象外（`build_submission.py` は参照しない）。

---

## Development Process Rules

This project must be developed phase by phase.

Before starting any phase, read:

- docs/phase_plan_profile_strategy.md

Only work on the phase explicitly requested by the user.
Do not proceed to the next phase without user approval.
Do not change `deck.csv` unless explicitly instructed.
Do not change policy, scores, parameters, or submission files (`main.py`/`deck.csv`/`params.json`) beyond what was explicitly requested.
For investigation, audit, or design-only requests, do not change code.

## Outcome Improvement Cycle

成果へ影響する変更（policy / scoring / search / rollout / evaluation function / parameter / deck / opponent prediction / decision feature）には、ユーザーが別の進め方を明示しない限り、[`docs/agent-workflow/outcome-improvement-cycle.md`](docs/agent-workflow/outcome-improvement-cycle.md) を参照する。Pokemon AI用の導入例は [`profiles/outcome/pokemon-ai.example.json`](profiles/outcome/pokemon-ai.example.json)、Profile契約は [`docs/agent-workflow/app-profile.md`](docs/agent-workflow/app-profile.md) を参照する。

このPokemon Profileは`example_only`であり、本番の閾値・baseline・datasetを規定しない。必須値を推測で補わず、active Profileが確定するまでは評価・採用をBLOCKEDとする。docs/comment/挙動非影響CI/挙動非影響formattingだけの変更には、フルサイクルを強制しない。

## Git安全ルール（必須）

- `git add .` は使用しない。対象ファイルだけを個別に `git add <file>` でstageする。
- 未コミットの変更を `stash` / `reset` / `checkout` で破棄しない。
- commit・push・PR作成は、依頼された範囲だけを行う。マージは明示指示がない限り行わない。

## 検証・報告ルール

- ドキュメントと実装が矛盾する場合、勝手に判断せず報告する。
- 実行していないテストを「成功」と報告しない。
- 推測と確認済みの事実を明確に区別して報告する。

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

- `main.py` / `deck.csv` / `params.json` は **リポジトリルート直下** のファイルをそのまま使用する。`build_submission.py` は `experiments/agents/raging_bolt/` から自動コピーする処理を持たない（現状のスクリプトはルート3ファイル＋`cg/`をtarに詰めるだけ）
- 開発は `experiments/agents/raging_bolt/` で行うが、変更をルートの提出用ファイルへ反映するには**手動でコピー**する必要がある。開発元を変更しただけではルート提出用ファイルへ自動反映されない
- 提出用ファイルを更新する場合は、開発元（`experiments/agents/raging_bolt/`）とルート提出用ファイルの内容が一致していることを確認してから `python build_submission.py` を実行する
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
| `deck.csv` パス解決 | 1. 開発時レイアウト `experiments/decks/raging_bolt_ogerpon.csv` を探す → 2. 無ければ `main.py` と同じディレクトリの `deck.csv` → 3. それも無ければ `/kaggle_simulations/agent/deck.csv` |
| `params.json` パス解決 | 1. 環境変数 `POKEMON_AI_PARAMS_PATH` が設定されていればそのパス（存在しなければ次へ） → 2. 未設定、または存在しなければ `main.py` と同じディレクトリの `params.json` |
| 意思決定の中核 | `RagingBoltPolicy.choose_with_search()` — ヒューリスティックで上位候補を絞り、`cg.api.search_begin/search_step` で実際にエンジン探索してから選択（詳細は `experiments/agents/raging_bolt/HANDOFF.md` 参照） |

このエージェントは単一ファイル + `params.json` のみで完結し、`agent/` パッケージや `data/` の外部CSVは使用しない。

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

## 旧構成（Iono's Kilowattrel、現行対象外）

以下は旧エージェント（`agent/` パッケージ + `data/` 配下、Iono's Kilowattrelデッキ）に関する記述。**現行の提出物・現行の開発ルールの対象ではない**。`agent/` パッケージや `data/` の外部CSVは現行の raging_bolt エージェントでは使用しない。参照が必要な場合のみ以下を参照すること。

### 旧`main.py` のルール（Iono's Kilowattrel、参考情報）

| 項目 | 内容 |
|------|------|
| エントリーポイント | `agent(obs_dict, config=None) -> list[int]` |
| デッキ返却 | `obs.select is None` のとき `_DECK`（60枚のcard IDリスト）を返す |
| 型変換 | `to_observation_class(obs_dict)` で typed dataclass に変換してから処理 |
| オプション変換 | `_opt_to_dict(o)` で Option dataclass → dict に変換して policy へ渡す |
| state の `hand` | `me_hand_ids = [str(c.id) for c in (me.hand or [])]` を含める（PLAY/CARD scoring 用） |

### 旧`agent/policy.py` のルール（参考情報）

#### `_cid_from_hand()` — 必須ヘルパー

PLAY / CARD / ATTACH / EVOLVE オプションは `cardId` を持たない。
`area == AreaType.HAND (2)` のとき `state['hand'][action['index']]` でカードIDを引く。

```python
_AREA_HAND = 2  # AreaType.HAND

def _cid_from_hand(self, action: dict, state: dict) -> str:
    cid = str(action.get("cardId") or "")
    if cid:
        return cid
    area = action.get("area")
    idx  = action.get("index")
    if area == self._AREA_HAND and idx is not None:
        hand = state.get("hand") or []
        if idx < len(hand):
            return str(hand[idx])
    return ""
```

#### `_load_attack_data()` — `cg.api` を最初に試す

```python
from cg.api import all_attack
return {a.attackId: a.damage for a in all_attack()}
```

#### スコアリングメソッドで `role` を使うとき

`role` はメソッド内で必ず `self.knowledge.get_role(cid)` で取得する。
未定義のまま `.get(role, ...)` を呼ぶとランタイムエラー。

---

### 旧`agent/card_knowledge.py` のルール（参考情報）

- CSVパス: `../data/card_knowledge.csv`（`__file__` 相対）
- フォールバック: `/kaggle_simulations/agent/data/card_knowledge.csv`
- スキーマ v2 が前提（`energy_attach_score` 列の有無で自動判別）
- カードの効果テキストや画像URLは CSV に含めない（セキュリティ要件）

---

## セキュリティ制約

- 取得したカード効果全文・画像URL を `data/` や CSV に保存しない
- GitHub 等に効果全文CSVを公開しない前提で構成する
- `data/card_knowledge.csv` に記録するのは **role / score / tags** のみ
- APIキー・トークン・認証情報をファイルへ保存しない。`.env` の内容を出力・commitしない
- OpenAI API・Anthropic APIのAPIキー課金利用を前提にしない（ログイン済みのサブスクリプション枠を使用する）

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

### 旧構成（`agent/` パッケージ、参考情報）でのエラー

| エラーメッセージ | 原因 |
|-----------------|------|
| 攻撃ダメージが常に 0 | `_load_attack_data()` が `cg.api` を使っていない |
| PLAY/CARD スコアが全て同じ | `cardId` が None のまま `_cid_from_hand()` を通していない |
| `NameError: role` | `_score_play_pokemon()` 等で `role` を代入前に参照している |

---

## 旧エネルギー貼り先ルール（Iono's Kilowattrel、現行対象外・参考情報）

現行の raging_bolt エージェントについては上記「エネルギー貼り先ルール（デッキ調整時に必ず確認）— raging_bolt」を参照。以下は旧デッキ（Iono's Kilowattrel）向けの参考情報。

デッキのエネルギー枚数や構成を変更するときは、`agent/ionos_rules.py` の `score_energy_attachment()` が正しく機能するか確認すること。

### 基本方針（Iono's Kilowattrel デッキ）

| エネルギー | 貼り先 | 理由 |
|-----------|--------|------|
| Basic {L} (ID: 4) | Iono's Voltorb (265) | 序盤攻撃役。2枚で攻撃可能 |
| Basic {L} (ID: 4) | Iono's Bellibolt ex (269) | エンジン兼メインアタッカー |
| Basic {L} (ID: 4) | Iono's Kilowattrel (271) | サブアタッカー |
| Basic {L} (ID: 4) | Iono's Tadbulb (268) / Wattrel (270) | 進化後への引き継ぎ |

**重要**: Voltorb の打点 = 20 + 20 × (全 Iono's ポケモンの雷エネ合計枚数)。
1体に集中させず、Iono's ポケモン全体に分散することで打点が伸びる。

### 過剰添付として減点するケース

- Voltorb への 3 枚目以降 → -10〜-20（後続ラインが未展開なら特に減点）
- Bellibolt ex への 5 枚目以降 → -10
- Kilowattrel への 4 枚目以降 → -10
- 非 Iono's ポケモン → -20

### 実装の確認箇所

- `score_energy_attachment(energy_cid, target_cid, state)` — エネルギー種別×ターゲットのスコア計算
  - `agent/ionos_rules.py` で定義
  - ATTACH (OptionType=8) の Rule 7 から呼ばれる
  - `action.get("inPlayArea")` / `action.get("inPlayIndex")` でターゲットを特定（`action.get("area")` はHANDエリア=2 なので使わない）
- `_count_lightning_on_iono_pokemon(state)` — Voltorb 打点計算用
- `_estimate_voltorb_damage(state)` — 現在の推定打点

### デッキ調整時のチェックリスト

1. 新しいポケモンをデッキに加えた場合 → `_IONO_LINE` / `_SETUP_MON_IDS` への追加要否を確認
2. エネルギー構成を変えた場合 → Voltorb / Bellibolt ex / Kilowattrel の攻撃必要枚数と `_ATTACK_REQUIREMENTS` を確認
3. `agent/turn_plan.py` の `_SETUP_MON_IDS` が evolution_base のみを含んでいるか確認（Voltorb は除外）

---

## 動作確認済み提出

| バージョン | サイズ | 確認内容 |
|-----------|--------|---------|
| v3（Iono's Kilowattrel、旧構成） | 504 KB | アップロード成功（フォーマット確認済み） |
| v4（raging_bolt、2026-07〜、現行） | 513 KB | 隔離環境での展開・単独動作を確認済み（`main.py`+`deck.csv`+`params.json`+`cg/`のみでフルゲーム完走）。vs top_lucario_1084 20.0%、vs dragapult 25.3%、vs megastarmie 55.0% |
