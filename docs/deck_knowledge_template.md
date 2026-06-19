# [デッキ名] — ナレッジテンプレート

記録日: YYYY-MM-DD
バージョン: v1

---

## 0. デッキリスト

> deck.csv 再現用。カードIDは cabt の `all_card_data()` で確認。

| 枚数 | カード名 | カードID | 備考 |
|------|---------|---------|------|
| x    | Pokemon  | 000     |      |
| x    | Trainer  | 000     |      |
| x    | Energy   | 0       |      |

**合計: 60枚 / ACE SPEC: なし or [カード名] x1**

---

## 1. 勝ち筋 (Win Condition)

> 何をゴールとして戦うか。「〇〇でプライズを取る」レベルで簡潔に。

### メインプラン

- 手順1: ...
- 手順2: ...
- 手順3: ...

### サブプラン / 代替ルート

- ...

### ゲームの流れ (フェーズ)

| フェーズ | ターン目安 | やること |
|---------|-----------|---------|
| 序盤 (SETUP) | T1-T3 | ベンチ展開、エネ付け |
| 中盤 (MID)   | T4-T6 | 進化、攻撃開始 |
| 終盤 (LATE)  | T7+   | プライズレース締め |

---

## 2. デッキ全体の役割分担

> ポケモン / トレーナー / エネルギーそれぞれが「なぜ入っているか」を一言で。

### アーキタイプ

- **攻撃スタイル**: 単打 / 多面KO / ワンショット / 耐久
- **勝利条件**: 6プライズ先取 / デッキアウト / ...
- **ペース**: アグロ / ミッドレンジ / コントロール

### 主要シナジー

1. [カードA] + [カードB] → 効果
2. ...

---

## 3. card_knowledge の考え方

> `data/card_knowledge.csv` の role / score / tags をどう設定するか。

### role 設計方針

| role 値 | このデッキでの意味 | 代表カード |
|---------|-----------------|-----------|
| `main_attacker` | メイン攻撃役 | |
| `sub_attacker` | サブ攻撃役 | |
| `evolution_base` | 進化前ライン | |
| `search_engine` | 展開サポート | |
| `basic_setup` | 序盤スターター | |
| `disruption` | 妨害 | |
| `draw` | ドロー | |
| `energy_accel` | エネ加速 | |
| `tool` | どうぐ | |

### スコア設計方針

- `use_score`: プレイする優先度 (0-10)
- `search_score`: サーチで持ってくる優先度 (0-10)
- `bench_score`: ベンチに置く優先度 (0-10)
- `energy_attach_score`: エネルギーを貼る優先度 (0-10)
- `discard_penalty`: 捨てたくない度 (0-10)

---

## 4. ポケモン別 knowledge

> 各ポケモンの role / score / タグ / 特記事項。

### [ポケモン名] (ID: XXX)

- **role**: `main_attacker`
- **use_score**: 9
- **bench_score**: 9
- **energy_attach_score**: 9
- **discard_penalty**: 9
- **tags**: `ex`, `main_attacker`
- **攻撃**: [攻撃名] — コスト [X][Y] / ダメージ Z
- **特記事項**: ...

### [ポケモン名] (ID: XXX)

- **role**: `evolution_base`
- **use_score**: 7
- **bench_score**: 8
- **energy_attach_score**: 0
- **discard_penalty**: 6
- **tags**: `basic`
- **特記事項**: ...

---

## 5. Trainer / Supporter の knowledge

> 各トレーナーの role と使いどころ。

| カード名 | ID | role | use_score | 使いどころ / 条件 |
|---------|-----|------|-----------|-----------------|
|          |     | `search` | 8 | 序盤ポケモン展開 |
|          |     | `draw` | 7 | 手札 ≤4 の時 |
|          |     | `energy_accel` | 8 | メインアタッカーにエネ不足時 |
|          |     | `disruption` | 6 | 終盤・残りプライズ ≤2 |
|          |     | `evolve` | 8 | 進化ライン揃った時 |

### サポーター制限 (1ターン1枚)

- supporter_played チェックが必要: `sub_role = "supporter"` を設定する

---

## 6. エネルギーの knowledge

> 種類・枚数・役割・配分方針。

| エネルギー | ID | 枚数 | energyType | 貼り先 |
|-----------|-----|-----|-----------|--------|
| Basic {X} | X  | XX  | X         | [ポケモン名] |

### エネルギー総数の考え方

- 攻撃コスト: [X][Y][Z] = N枚
- 加速手段: [カード名]で補える場合は少なめ可
- 引ける確率: 初手7枚中 X枚が目安

---

## 7. エネルギー添付ロジック

> `score_energy_attachment(energy_cid, target_cid, state)` の設計。
> ファイル: `agent/[deck_name]_rules.py`

### 付けてよいポケモン (Beneficial)

| エネルギー | → 対象 | スコア | 理由 |
|-----------|--------|-------|------|
| ID=X      | ID=Y   | +20   | 攻撃コスト |
| ID=X      | ID=Y   | +8    | 能力発動条件 |

### 付けてはいけないポケモン (Harmful)

| エネルギー / 対象 | スコア | 理由 |
|-----------------|-------|------|
| Any → ID=Z     | -20   | 攻撃役でない |
| ID=X → ID=Y   | -15   | 色ミスマッチ |

### 攻撃可能判定 (色条件)

> 単純な枚数ではなく色条件が必要な場合に記述。

```python
# [ポケモン名] の攻撃条件
def can_attack_now(pokemon):
    etypes = get_energy_types(pokemon)
    return (
        TYPE_A in etypes       # 必須色1
        and TYPE_B in etypes   # 必須色2
        and len(etypes) >= N   # 必要枚数
    )
```

### `_dragapult_energy_ready` 相当の関数

> Dragapult では `_dragapult_energy_ready` を使用。
> このデッキでは → `_[pokemon]_energy_ready(state)`

---

## 8. 攻撃・ターゲット方針

> `turn_plan.py` / `dragapult_rules.py` のスコアリングに反映する内容。

### 攻撃優先ターゲット

1. **最優先**: [条件] → 理由 (例: ゲームエンドKO、2プライズ)
2. **次点**: [条件] → 理由
3. **ベンチ狙い**: Boss's Orders が必要な場合の条件

### ターゲットスコアリング (turn_plan.py)

```
prizes * 1000           # プライズ数で重み
+ len(energies) * 150   # エネルギー付きを優先
+ hp                    # HPが高い = 価値が高い
ゲームエンドKO → 50000  # 最優先
```

### 特定ターゲットへの優先ボーナス (deck_rules.py)

| 条件 | ボーナス | 理由 |
|------|---------|------|
| [ポケモン名] がベンチにいる | +X | 進化前・放置不可 |
| 相手残りプライズ ≤ 2 | +X | プライズレース決め |

---

## 9. AIの行動優先度

> 各ターンの意思決定の優先順。`score_bonus` の返り値とあわせて整理。

### 行動優先順位 (高い方が先)

1. **ゲームエンドKO が可能** → 即攻撃 (score +50)
2. **2枚プライズが取れるKO** → 攻撃 (score +20)
3. **進化** → Dragapult line 最優先、サポートライン次点
4. **サーチ / ドロー** → 手札が少ない場合
5. **エネルギー付与** → メインアタッカーが未充足
6. **妨害** → 残りプライズ差が縮まっている時
7. **ベンチ展開** → 次ターンの攻撃・進化準備
8. **ターン終了** → これ以上有効なアクションがない

### セットアップ優先順位 (SETUP_ACTIVE / TO_BENCH)

```
初期Active: [ポケモンA] (+30) > [ポケモンB] (+20) > [ポケモンC] (+10)
ベンチ展開: [ポケモンA] 最優先 → [ポケモンB] 次点
```

### 抑制ルール (suppress)

- **Attack 抑制**: 以下のアクションが残っている場合は攻撃スコアを -30
  - [ ] Boss's Orders が必要で手札にある
  - [ ] エネルギーが未付与でアタッカーが不足
  - [ ] スイッチが必要でリトリートが可能

---

## 10. 実装チェックリスト (デッキ切り替え時の確認手順)

> このデッキに切り替える際に変更・確認が必要なファイルと手順。全13ステップ。

### Step 1: deck.csv 確認

完了条件:

- [ ] 合計 60枚
- [ ] メインアタッカー × N
- [ ] 進化元 × N
- [ ] エネルギー × N (種類・枚数を確認)
- [ ] ACE SPEC ≤ 1枚

### Step 2: data/deck_profile.json 更新

完了条件:

- [ ] `deck_id` を更新
- [ ] `primary_win_condition` を更新
- [ ] `main_attackers`, `sub_attackers`, `setup_cards`, `energy_engine` を設定

### Step 3: data/card_knowledge.csv 登録

完了条件:

- [ ] 全ポケモンに `role`, `bench_score`, `energy_attach_score`, `evolution_score` を登録
- [ ] メインエネルギーの `priority`, `energy_attach_score`, `keep_score`, `search_score` を設定
- [ ] 全トレーナーに `role`, `use_score`, `keep_score` を登録

### Step 4: agent/[deck_name]_rules.py 作成

完了条件:

- [ ] ファイル `agent/[deck_name]_rules.py` を作成
- [ ] カードID定数を定義 (`_MAIN_ATTACKER`, `_ENERGY_XXX`, `DECK_POKEMON_IDS` など)
- [ ] 以下の関数を実装:
  - `score_bonus(action, state, knowledge) -> tuple[float, str]`
  - `score_energy_attachment(energy_cid, target_cid, state) -> tuple[float, str]`
  - デッキ固有のダメージ計算関数 (スケーリング攻撃がある場合)
  - デッキ固有のエネルギー加速スコア関数 (加速能力がある場合)

### Step 5: score_energy_attachment 実装

完了条件:

- [ ] 貼り先ポケモンごとのスコア表を実装
- [ ] 過剰添付ペナルティを実装
- [ ] 非対象ポケモンへのペナルティを実装 (-20 など)
- [ ] `return (score, reason_str)` 形式で返す

### Step 6: ダメージスケーリング実装 (スケーリング攻撃がある場合)

完了条件:

- [ ] ダメージ計算に必要な状態カウント関数を実装
- [ ] 推定ダメージ計算関数を実装
- [ ] 攻撃スコアリング関数を実装 (KO可能時の加点含む)

### Step 7: エネルギー加速スコア実装 (加速能力がある場合)

完了条件:

- [ ] 加速先ポケモンの優先順位をスコア化
- [ ] 過剰添付ペナルティを含める
- [ ] `(score, reason_str)` 形式で返す

### Step 8: agent/policy.py インポート変更

完了条件:

- [ ] `from agent.[deck_name]_rules import score_bonus` に変更
- [ ] 旧デッキのインポートを削除

### Step 9: agent/turn_plan.py 更新

完了条件:

- [ ] `_SETUP_MON_IDS` を更新 (純粋な進化前のみ。攻撃役は含めない)
- [ ] `_ATTACK_REQUIREMENTS` を更新 (fallback用の必要エネ数)

  ```python
  _ATTACK_REQUIREMENTS = {
      [ATTACKER_A_ID]: N,
      [ATTACKER_B_ID]: N,
  }
  ```

- [ ] 前デッキ固有の定数・関数を削除

### Step 10: main.py 更新

完了条件:

- [ ] `DECK_NAME` を新デッキ名に更新

### Step 11: build_submission.py 更新

完了条件:

- [ ] `('agent/[deck_name]_rules.py', 'agent/[deck_name]_rules.py')` をリストに追加
- [ ] 旧デッキの `_rules.py` をリストから削除

### Step 12: 旧デッキ固有ロジックの削除・無効化

完了条件:

- [ ] 旧 `_rules.py` を `build_submission.py` のリストから除外
- [ ] `turn_plan.py` から旧デッキ固有コードを削除 (Step 9 で実施)
- [ ] `policy.py` のインポートを更新 (Step 8 で実施)
- [ ] `data/deck_profile.json` を新デッキ用に書き換え (Step 2 で実施)
- [ ] `CLAUDE.md` のエネルギー配分ルールセクションを更新

### Step 13: ロギング

完了条件:

- [ ] ターン開始時にダメージ推定値 (スケーリング攻撃がある場合) をログ出力
- [ ] 特殊Ability使用時に加速先・枚数をログ出力
- [ ] エネルギー添付時にスコアと reason_str をログ出力
- [ ] `agent/logger.py` に必要なログ追加

---

## 11. 対面メモ (後から追記)

> 実戦で気づいた対策パターン。

| 対面デッキ | 有効な対策 | 注意点 |
|-----------|-----------|--------|
|            |           |        |

---

## 更新履歴

| 日付 | 変更内容 |
|------|---------|
| YYYY-MM-DD | 初版作成 |
