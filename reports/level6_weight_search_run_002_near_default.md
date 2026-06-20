# Level 6: Weight Search Run 002 — Near-Default 1-Axis Scan

## Command

```bash
python experiments/weight_search.py --grid-file reports/level6_weight_grid_run_002.json --games 30 --use-wsl --start-game 6000
```

## Design

デフォルト値から 1 軸ずつ変更し、どの重みが効くかを確認。

| Weight | Default | Tested |
|--------|---------|--------|
| advantage_weight | **0.4** | 0.35, 0.45 |
| energy_to_plan_bonus | **5.0** | 4.0, 6.0 |
| energy_to_plan_bonus_no_need | **2.0** | 1.0, 3.0 |
| attack_suppress_penalty | **-30.0** | -20.0, -40.0 |

## Results (sorted by anomalies/game)

| # | Changed Weight | Value | /game | vs baseline (4.87*) | Safety |
|---|---------------|-------|-------|---------------------|--------|
| 1 | energy_to_plan_bonus | **4.0** | **4.20** | -14% | OK |
| 2 | advantage_weight | **0.35** | **4.43** | -9% | OK |
| 3 | advantage_weight | 0.45 | 4.53 | -7% | OK |
| 4 | attack_suppress_penalty | -20.0 | 5.10 | +5% | OK |
| 5 | attack_suppress_penalty | -40.0 | 5.30 | +9% | OK |
| 6 | energy_to_plan_bonus_no_need | 3.0 | 5.83 | +20% | OK |
| 7 | energy_to_plan_bonus | 6.0 | 5.97 | +23% | OK |
| 8 | energy_to_plan_bonus_no_need | 1.0 | 6.03 | +24% | OK |

*baseline 4.87/g は F0008 200g の値。本 Run のゲーム分散を含むため絶対比較は参考値。

## Safety Metrics

全8パターンで以下が **0**:
- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available

## Analysis

### 有望候補

| Rank | Weight | Value | /game | 所見 |
|------|--------|-------|-------|------|
| **1** | **energy_to_plan_bonus** | **4.0** | **4.20** | エネ計画ボーナスを下げる方向。Run 001 の e=7.0 とは逆 |
| **2** | **advantage_weight** | **0.35** | **4.43** | advantage を微減。Run 001 の adv=0.3 と同じ方向だが控えめ |

### 傾向

| Weight | 下げる | 上げる | 解釈 |
|--------|--------|--------|------|
| advantage_weight | 良い (0.35→4.43) | 微良い (0.45→4.53) | 30g では判断困難 |
| energy_to_plan_bonus | **良い (4.0→4.20)** | 悪い (6.0→5.97) | **下げる方向が有望** |
| energy_to_plan_bonus_no_need | 悪い (1.0→6.03) | 悪い (3.0→5.83) | デフォルト 2.0 が最適付近 |
| attack_suppress_penalty | 微悪い (-20→5.10) | 微悪い (-40→5.30) | デフォルト -30 が最適付近 |

### 注意

Run 001 では adv=0.3 e=7.0 が 30g で -17% だったが、50g で消失。今回も 30g は参考値。

## 50g 検証候補

| Priority | Pattern | 30g /game | 次のステップ |
|----------|---------|-----------|------------|
| **1** | energy_to_plan_bonus=4.0 | 4.20 | 50g 検証 |
| 2 | advantage_weight=0.35 | 4.43 | 50g 検証（Run 001 adv=0.3 と同方向） |
| hold | その他 | 5.10+ | デフォルト以下のため見送り |

## weights.json

**元の値に復元済み。**

## Final Judgment

- **Run 002 完了**: 8パターン全て safety OK
- **50g 検証候補あり**: energy_to_plan_bonus=4.0 が最有望
- **採用判断はまだしない**: 30g では分散が大きい
- **200g 検証はまだ不要**: まず 50g で傾向確認

## Changed Files

| File | Change |
|------|--------|
| experiments/weight_search.py | `--grid-file` オプション追加 |
| reports/level6_weight_grid_run_002.json | 探索グリッド定義 |
| reports/level6_weight_search_run_002_near_default.md | 新規 |
| reports/level6_weight_search_run_002_near_default.json | 新規 |
| agent/ | **変更なし** |
| data/weights.json | **復元済み** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
