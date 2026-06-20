# Level 6.5: Externalize retreat_to_better_attacker_bonus

## What Was Done

F0007 系の pivot 判断で使われている `+1100` ハードコードを `retreat_to_better_attacker_bonus` として `data/weights.json` に外出し。

## Changes

| File | Change |
|------|--------|
| `data/weights.json` | `retreat_to_better_attacker_bonus: 1100.0` 追加 |
| `agent/policy.py` | `_DEFAULT_WEIGHTS` に追加 |
| `agent/ionos_rules.py` | `_load_ionos_weights()` で読み込み、2箇所のハードコード 1100.0 を変数に置換 |

## Default Value

```json
"retreat_to_better_attacker_bonus": 1100.0
```

既存の F0007 ハードコード値と同一 → **既存挙動に変更なし**。

## Replaced Hardcoded Values

| Location | Before | After |
|----------|--------|-------|
| Rule 17b BB >=260 | `return 1100.0` | `return _retreat_to_better_attacker_bonus` |
| Rule 17b KW >=180 | `return 1100.0` | `return _retreat_to_better_attacker_bonus` |

## Safety

- weights.json なし → `_RETREAT_BONUS_DEFAULT = 1100.0` にフォールバック
- Kaggle パス対応
- テスト 77/77 全パス
- 30g smoke test: エラー 0、タイムアウト 0

## Next A/B Candidates

今回のPRでは検証しない。次のPRで以下を比較可能：

| retreat_to_better_attacker_bonus | 想定 |
|--------------------------------|------|
| 800 | turn_rule -1000 を超えない（retreat 発生しない） |
| **1100** | **baseline（現在値）** |
| 1400 | より強く retreat を優先 |

## Not Changed

| File | Status |
|------|--------|
| deck.csv | unchanged |
| submission.tar.gz | unchanged |
| turn_rule_engine.py | unchanged |
