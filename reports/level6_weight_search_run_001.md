# Level 6: Weight Search Run 001

## Command

```bash
python experiments/weight_search.py --games 30 --patterns 0 --use-wsl --start-game 4200
```

## Search Grid

| Weight | Values |
|--------|--------|
| advantage_weight | 0.3, **0.4** (default), 0.5 |
| energy_to_plan_bonus | 3.0, **5.0** (default), 7.0 |

9 patterns x 30 games = 270 total games

## Results (sorted by anomalies/game)

| # | adv_weight | energy_bonus | Games | Anomalies | /game | Safety |
|---|-----------|-------------|-------|-----------|-------|--------|
| 1 | **0.3** | **7.0** | 30 | 121 | **4.03** | OK |
| 2 | 0.3 | 5.0 | 30 | 135 | 4.50 | OK |
| 3 | **0.4** | **5.0** | 30 | 146 | 4.87 | **baseline** |
| 4 | 0.4 | 3.0 | 30 | 158 | 5.27 | OK |
| 5 | 0.5 | 3.0 | 30 | 159 | 5.30 | OK |
| 6 | 0.4 | 7.0 | 30 | 175 | 5.83 | OK |
| 7 | 0.3 | 3.0 | 30 | 188 | 6.27 | OK |
| 8 | 0.5 | 7.0 | 30 | 193 | 6.43 | OK |
| 9 | 0.5 | 5.0 | 30 | 206 | 6.87 | OK |

## Safety Metrics

全9パターンで以下が **0**:
- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available

## Analysis

### Baseline (adv=0.4, energy=5.0): 4.87/g

### Best candidate: adv=0.3, energy=7.0 → 4.03/g (-17%)

| 観点 | 値 |
|------|-----|
| anomalies/game | 4.03 (baseline 4.87 の -17%) |
| Safety | all 0 |
| advantage_weight | 0.3 (baseline 0.4 から減少) |
| energy_to_plan_bonus | 7.0 (baseline 5.0 から増加) |

**解釈**: advantage 評価の影響を抑え、エネルギー計画添付を強化する方向が有望。

### Trends

- **advantage_weight 0.3 が最も良い** (全3パターンが上位)
- **advantage_weight 0.5 は最も悪い** (全3パターンが下位)
- **energy_to_plan_bonus の影響は adv_weight に依存** (adv=0.3 では高い方が良い、adv=0.5 では逆)

### 注意

30g は小サンプル。ゲーム分散が大きいため、上位候補は 50-200g で追加検証が必要。

## Candidates for Next Validation

| Priority | Pattern | /game | 次のステップ |
|----------|---------|-------|------------|
| **1** | adv=0.3, energy=7.0 | 4.03 | 50-200g 検証 |
| 2 | adv=0.3, energy=5.0 | 4.50 | 比較対象 |
| hold | adv=0.4, energy=5.0 | 4.87 | baseline |

## weights.json Restoration

実行後に元の内容に **復元済み**。

## Final Judgment

- **小規模探索は成功**: 9パターン全て safety OK で完了
- **有望な候補あり**: adv=0.3, energy=7.0 が baseline -17%
- **次は 50g で追加検証すべき**: 30g では分散が大きい
- **200g 検証はまだ不要**: まず 50g で傾向を確認してから
- **探索範囲**: 現時点で十分。adv=0.3 方向が有望と分かったため、0.2-0.35 の細分化は次段階

## WSL Path Conversion

WSL path conversion fixed: `_to_wsl_path()` で Windows パスと既存 WSL/Linux パスの両方をサポート。

## Changed Files

| File | Change |
|------|--------|
| `experiments/weight_search.py` | バグ修正（エンコーディング、WSLパス、ログglob） |
| `reports/level6_weight_search_run_001.md` | 新規 |
| `reports/level6_weight_search_run_001.json` | 新規 |
| agent/ | **変更なし** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
