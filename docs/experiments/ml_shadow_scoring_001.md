# ML Shadow Scoring 001

## Purpose

#137 の action feature JSONL を使って action ranker を学習し、
rule policy との一致率を shadow mode で確認する。
ML は行動選択に使わない。

## Baseline

- #134 submitted version + #136/#137 diagnostics
- attack_plan.py excluded from submission
- ML disabled in runtime

## No Behavior Change

policy.py の行動選択ロジックは一切変更していない。
ML score は shadow log としてのみ出力。

## Model

- Type: LinearRanker (logistic regression, pure Python, no sklearn)
- Features: 32 (numeric + boolean from action_feature_logging)
- Training: 50g self-play (40,116 candidate actions)
- Evaluation: 100g self-play (87,337 candidate actions)

## Commands

```bash
python experiments/action_feature_logging.py \
    --n 50 --start-game 140000 --run-games --use-wsl \
    --output artifacts/action_features_train_50g.jsonl

python experiments/action_feature_logging.py \
    --n 100 --start-game 141000 --run-games --use-wsl \
    --output artifacts/action_features_eval_100g.jsonl

python experiments/ml_shadow_scoring.py \
    --train artifacts/action_features_train_50g.jsonl \
    --eval artifacts/action_features_eval_100g.jsonl \
    --output artifacts/ml_shadow_eval_100g.jsonl \
    --summary artifacts/ml_shadow_summary.json
```

## Results

| Metric | Value |
|--------|-------|
| Train candidates | 40,116 |
| Train decisions | 8,817 |
| Eval candidates | 87,337 |
| Eval decisions | 19,068 |
| **Top1 agreement** | **100.0%** |
| **Top3 agreement** | **100.0%** |
| ML End top1 | 1,017 |
| ML End + legal_attack | **0** |
| ML miss KO | 9 |
| ML zero_damage top1 | **0** |

Note: decision grouping uses `decision_id` (game_id + decision_seq),
not `game_id + turn` which collapsed multiple per-turn decisions.

## Top Features (by |weight|)

| Feature | Weight |
|---------|--------|
| candidate_rank | -131.4 |
| legal_action_count | -67.1 |
| bench_size | +25.7 |
| active_energy | +18.3 |
| is_attach | -15.5 |
| is_play | +12.0 |
| late_game | +6.1 |
| is_ability | +6.1 |
| action_type | -5.5 |
| has_legal_attack | -4.5 |

candidate_rank が最大の特徴量 — ML は主に rule_score の順位を学習している。

## Safety Check

| Check | Result |
|-------|--------|
| ML End + legal_attack top1 | **0** (safe) |
| ML zero_damage top1 | **0** (safe) |
| ML miss KO | 9 (0.05% of 19,068 decisions) |

ML は End+legal_attack や zero_damage attack を top1 に選んでいない。
miss KO は 9/19,068 で非常に低い。

## Interpretation

### Top1 agreement 100% — ML は rule_score の順位を完全に再現

decision_id 単位で正しく grouping した結果、各 decision は平均 ~4.6 候補。
ML の dominant feature は `candidate_rank` (-131.4) で、rule_score の順位を
そのまま学習している。独自の判断はまだ弱いが、rule policy の模倣は完了。

### Unsafe decisions は非常に少ない

- End+legal_attack=0 (safe)
- zero_damage=0 (safe)
- miss_KO=9/19,068 (0.05%)

### ML の独自判断力

Top feature が candidate_rank であるため、ML は本質的に rule_score の
proxy になっている。rule_score が含まれない feature set で再学習すれば、
ML 独自の判断力を測定できる。

## Decision

**ML は rule policy imitation として機能している。**
**Hybrid mode 検討は可能だが、rule_score proxy なので追加効果は限定的。**

次に進むべきは:
1. rule_score を feature から外して re-train → ML 独自の判断力を測定
2. outcome-weighted training → 勝ちに寄与する action を学習
3. 上記で agreement が維持 or 改善するなら hybrid mode 検討

## Next Steps

1. **rule_score 除外 re-train**: candidate_rank / rule_score を feature から外して ML 独自判断力を測定
2. **Outcome-weighted training**: win/loss reward を学習に反映
3. **Feature 改善**: predicted_damage, opp_bench_hp, hand_composition を追加
4. **独自判断力が高ければ** hybrid 10% scoring を検討
5. Runtime default はまだ変更しない
