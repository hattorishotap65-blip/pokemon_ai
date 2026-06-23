# Action Feature Enrichment 001

## Purpose

#142 で linear ranker が ~72% で天井に達した。特徴量を追加して改善を試みる。

## No Behavior Change

policy.py / submission.tar.gz は一切変更していない。ML は shadow mode のみ。

## Added Features (9 new)

| Feature | Type | Description |
|---------|------|-------------|
| active_can_attack_now | bool | エネルギー足りて攻撃可能か |
| active_energy_shortage | int | 攻撃に不足するエネルギー数 |
| best_attack_can_ko | bool | 候補に KO 可能な攻撃があるか |
| damage_to_ko_gap | int | 相手 HP (KO までの距離の簡易指標) |
| prize_pressure | int | 相手との prize 差 (不利方向) |
| is_behind_prizes | bool | prize で負けているか |
| is_ahead_prizes | bool | prize で勝っているか |
| deck_low | bool | デッキ残り 10 枚以下 |
| hand_low | bool | 手札 2 枚以下 |

Total features: B=30 (baseline), C=39 (enriched)

## Results (100g eval, 20,134 decisions)

| Metric | B: No-Rule (30 feat) | C: Enriched (39 feat) |
|--------|---------------------|----------------------|
| **Top1 agreement** | **77.8%** | 71.7% |
| **Top3 agreement** | **91.1%** | 87.8% |
| ML End top1 | 376 | 376 |
| ML End+legal_attack | **0** | **0** |
| ML miss KO | 197 | 212 |
| ML zero_damage | **0** | **0** |

## Comparison Across PRs

| PR | Mode | Top1 | Top3 | miss_KO | unsafe |
|----|------|------|------|---------|--------|
| #139 | No-rule (30 feat) | 71.5% | 87.8% | 223 | 0 |
| #142 | No-rule OW labeled | 72.0% | 88.4% | 202 | 0 |
| **#143 B** | **No-rule (30 feat)** | **77.8%** | **91.1%** | **197** | **0** |
| #143 C | Enriched (39 feat) | 71.7% | 87.8% | 212 | 0 |

## Findings

### Feature enrichment hurts linear model performance

Adding 9 features **decreased** Top1 from 77.8% to 71.7% and **increased**
miss_KO from 197 to 212. The enriched features introduce noise that the
linear model cannot properly weight.

### Baseline no-rule is at its best (~78%)

The 30-feature no-rule model at 77.8% is the highest agreement seen
(with different data batches). The linear model's ceiling is reached.

### Safety maintained

End+legal_attack=0, zero_damage=0 across all variants.

## Decision

**Feature enrichment with linear model is counterproductive.**

The linear ranker cannot benefit from richer features — it needs either:
1. Feature selection (remove noisy features)
2. Non-linear model (decision tree / random forest)
3. Feature engineering (interaction terms, polynomial)

## Next Steps

1. **Non-linear model**: try decision tree or ensemble on existing 30 features
2. **Feature selection**: identify which of the 9 new features are noise
3. **Or accept ~78% as linear ceiling** and focus on rule-based improvements
4. Runtime default unchanged, ML not enabled
