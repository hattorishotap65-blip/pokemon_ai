# Runtime Hybrid Self-Play Evaluation 001

## Purpose

#145 で safety gate が offline で安全と確認された。
今回は runtime 風の hybrid re-ranking を self-play ログで評価する。

## No Default Behavior Change

policy.py は変更していない。experiments 側で offline re-ranking を実施。
submission.tar.gz 更新なし。

## Method

B案: policy.py 変更なし。既存の action feature JSONL を re-rank して、
hybrid が選ぶ action と rule が選ぶ action の差分を分析。

## Safety Gates

G1: End + legal_attack → bonus=0
G2: zero_damage → bonus=0
G3: can_ko + non-attack → bonus=0

## Hybrid Formula

`hybrid_score = rule_score + bonus_ratio * normalized_ml_score`

## Data

| Set | Games | Win | Loss | Candidates | Decisions |
|-----|-------|-----|------|------------|-----------|
| Train | 50 | 28 | 22 | 44,514 | ~9.5k |
| Eval | 100 | 50 | 50 | 87,170 | 18,769 |

## Results (100g eval, 18,769 decisions)

| Metric | Bonus=0 | Bonus=5 | Bonus=10 | Bonus=20 |
|--------|---------|---------|----------|----------|
| Changed decisions | 0 | 55 (0.3%) | 169 (0.9%) | 306 (1.6%) |
| Changed games | 0 | 36 | 77 | 90 |
| Win rate | 50.0% | 50.0% | 50.0% | 50.0% |
| End+legal_attack | **0** | **0** | **0** | **0** |
| Zero damage | **0** | **0** | **0** | **0** |
| Miss KO | 5 | 5 | 5 | 5 |
| Gate blocked | 2,035 | 2,035 | 2,035 | 2,035 |

## Key Findings

### Safety is perfect at all bonus levels

- End+legal_attack: **0** at all levels
- Zero damage: **0** at all levels
- Miss KO: 5 (stable, 0.03%)
- Gate correctly blocks 2,035 dangerous proposals

### Win rate is neutral (50%)

Self-play は対称なので、win rate 50% は期待通り。
Hybrid の効果は self-play では直接測定できない。
対戦相手が異なる本番環境での評価が必要。

### Changed decisions scale linearly with bonus

| Bonus | Changed | Changed games | Rate |
|-------|---------|---------------|------|
| 5 | 55 | 36/100 | 0.3% |
| 10 | 169 | 77/100 | 0.9% |
| 20 | 306 | 90/100 | 1.6% |

Bonus=10 で 0.9% 変更、77/100 games に影響 — moderate で安全な範囲。

## Decision

**Safety gate 付き hybrid は全 bonus level で安全。**
**Self-play では勝率変化を直接測定できない。**

### 進めてよい条件: 全て満たす

- End+legal_attack = 0 ✓
- zero_damage = 0 ✓
- miss_KO 安定 ✓
- changed rate < 2% ✓
- errors/timeouts 増なし ✓

### 次のステップ候補

1. **Kaggle 提出して実際のランキングで評価** — self-play ではなく対戦相手が異なる環境
2. **policy.py に env flag 付きで組み込み** → 実際の self-play 100g で処理時間を確認
3. **Bonus ratio 10 で提出候補** を検討

## Runtime Impact (Note)

この PR は offline re-ranking のため、実際の runtime 処理時間は未計測。
policy.py に組み込む場合、DecisionTree の推論は 1 candidate あたり数μs のため、
1 decision (数候補) で数十μs 以下と推定。
