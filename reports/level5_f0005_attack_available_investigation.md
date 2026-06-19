# F0005 Investigation: attack_available_but_no_attack / ability_without_followup_attack

## 対象 Anomaly

| ID | Type | Severity | Game | Turn |
|---|---|---|---|---|
| A0001 | attack_available_but_no_attack | high | g1801 | t=3 |
| A0002 | attack_available_but_no_attack | high | g1809 | t=3 |
| (関連) | ability_without_followup_attack | medium | g1801 | t=3 |
| (関連) | ability_without_followup_attack | medium | g1809 | t=3 |

## 調査結果

### g1801 game_turn=3（14イベント）

- Active: Tadbulb (268) → 進化後 Bellibolt ex (269)
- **全14イベントで type=13 + attackId の攻撃 option は 0件**
- type=13 が存在するが **attackId=None**（シミュレータが攻撃不可として提示）
- 選択: Canari → Bellibolt進化 → Voltorb展開 → Ability → End

### g1809 game_turn=3（13イベント）

- Active: Tadbulb (268) → 進化後 Bellibolt ex (269)
- **全13イベントで type=13 + attackId の攻撃 option は 0件**
- 同じく type=13 + attackId=None のパターン
- 選択: エネ添付 → Canari → Bellibolt進化 → Ability → End

### 根本原因

**Detector の誤検知。** `detect_anomalies.py` の `normalize_event()` が `is_attack=True` フィールドだけをチェックしており、`attackId=None` のケースを攻撃可能と誤判定していた。

```python
# 修正前（誤）
has_attack = any(
    (c.get("is_attack") or (_is_attack(c))) for c in candidates
)
```

ログ候補の `is_attack=True` は cabt シミュレータが type=13 に付けるフラグだが、`attackId=None` の場合は実際に攻撃を実行できない。正しくは:

```
type=13 AND attackId is not None → 攻撃可能
type=13 AND attackId=None → 攻撃不可
```

## 修正内容

**`tools/detect_anomalies.py`** の `normalize_event()` 内に `_candidate_is_real_attack()` ヘルパーを追加。`is_attack` フラグだけでなく `attackId is not None` を必ず確認。

```python
def _candidate_is_real_attack(c):
    opt_type = c.get("option_type") or c.get("type")
    attack_id = c.get("attackId") or c.get("attack_id")
    if opt_type == 13 and attack_id is not None:
        return True
    if c.get("is_attack") and attack_id is not None:
        return True
    return False
```

## 修正後の結果

| 指標 | 修正前 | 修正後 |
|------|--------|--------|
| anomalies_total | 295 | **291** |
| attack_available_but_no_attack | 2 (high) | **0** |
| ability_without_followup_attack | 2 (medium) | **0** |
| high anomalies | 2 | **0** |
| medium anomalies | 2 | **0** |
| best_damage_attacker_not_selected | 291 | 291 (変化なし) |

## 最終判断

**detector_refinement**

- agent 本体の不具合ではない
- シミュレータは攻撃 option を提示していなかった（attackId=None）
- detector が `is_attack=True` だけを見て誤判定していた
- 修正は detector のみ（`tools/detect_anomalies.py`）
- agent 本体（`agent/`）は変更なし

## 変更ファイル

| ファイル | 変更 |
|---------|------|
| `tools/detect_anomalies.py` | `_candidate_is_real_attack()` 追加、`has_attack` 判定修正 |
| `reports/level5_f0005_attack_available_investigation.md` | 新規（このレポート） |
| `reports/level5_f0005_attack_available_investigation.json` | 新規 |
| `agent/` | **変更なし** |
| `deck.csv` | **変更なし** |
| `submission.tar.gz` | **変更なし** |
