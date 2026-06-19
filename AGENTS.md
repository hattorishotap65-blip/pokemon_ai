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
- 以下の構造でアーカイブを作成する（パスは tar のルートからの相対パス）

```
main.py
deck.csv
agent/__init__.py
agent/advantage.py
agent/card_knowledge.py
agent/concept_weights.py
agent/ionos_rules.py
agent/evaluator.py
agent/fallback.py
agent/logger.py
agent/opponent_model.py
agent/planner.py
agent/policy.py
agent/rollout.py
agent/turn_plan.py
agent/win_condition.py
agent/effect_engine.py
agent/turn_rule_engine.py
data/card_knowledge.csv
data/deck_profile.json
data/card_effects_iono_lightning_recommended_en_ja.json
cg/__init__.py
cg/api.py
cg/game.py
cg/libcg.so
cg/utils.py
cg/sim.py
```

- `cg/` フォルダは `reference/extracted/cg/` からコピーする（`libcg.so` を含む）
- アーカイブ再ビルドは `python` の `tarfile` モジュールで行う

```python
import tarfile
with tarfile.open("submission.tar.gz", "w:gz") as tar:
    tar.add("main.py", arcname="main.py")
    tar.add("reference/extracted/cg", arcname="cg")
    # ... 他ファイルも同様
```

---

## デッキルール

| ルール | 内容 |
|--------|------|
| 枚数 | ちょうど **60枚** |
| ACE SPEC | **最大1枚**（cabt が `CardData.aceSpec` フラグで強制チェック） |
| 同名カード | 最大4枚（cabt が `CardData.regulation` で確認） |

- ACE SPEC 違反 → `"Player N's deck error."` でゲームが即中断される
- 現在のデッキ: Iono's Kilowattrel（`deck.csv`）— ACE SPEC: なし

---

## `main.py` のルール

| 項目 | 内容 |
|------|------|
| エントリーポイント | `agent(obs_dict, config=None) -> list[int]` |
| デッキ返却 | `obs.select is None` のとき `_DECK`（60枚のcard IDリスト）を返す |
| 型変換 | `to_observation_class(obs_dict)` で typed dataclass に変換してから処理 |
| オプション変換 | `_opt_to_dict(o)` で Option dataclass → dict に変換して policy へ渡す |
| state の `hand` | `me_hand_ids = [str(c.id) for c in (me.hand or [])]` を含める（PLAY/CARD scoring 用） |

---

## `agent/policy.py` のルール

### `_cid_from_hand()` — 必須ヘルパー

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

### `_load_attack_data()` — `cg.api` を最初に試す

```python
from cg.api import all_attack
return {a.attackId: a.damage for a in all_attack()}
```

### スコアリングメソッドで `role` を使うとき

`role` はメソッド内で必ず `self.knowledge.get_role(cid)` で取得する。
未定義のまま `.get(role, ...)` を呼ぶとランタイムエラー。

---

## `agent/card_knowledge.py` のルール

- CSVパス: `../data/card_knowledge.csv`（`__file__` 相対）
- フォールバック: `/kaggle_simulations/agent/data/card_knowledge.csv`
- スキーマ v2 が前提（`energy_attach_score` 列の有無で自動判別）
- カードの効果テキストや画像URLは CSV に含めない（セキュリティ要件）

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
| 攻撃ダメージが常に 0 | `_load_attack_data()` が `cg.api` を使っていない |
| PLAY/CARD スコアが全て同じ | `cardId` が None のまま `_cid_from_hand()` を通していない |
| `NameError: role` | `_score_play_pokemon()` 等で `role` を代入前に参照している |
| 提出がアップロードエラー | zip 形式で提出している（tar.gz が必要） |
| `ModuleNotFoundError: No module named 'cg'` | `cg/` を tar.gz に含め忘れ。`reference/extracted/cg/` から `-C reference/extracted cg` で追加する |

---

## エネルギー貼り先ルール（デッキ調整時に必ず確認）

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
| v3 | 504 KB | アップロード成功（フォーマット確認済み） |
