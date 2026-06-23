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
| Eval candidates | 87,337 |
| Eval decisions | 2,291 |
| **Top1 agreement** | **67.7%** |
| **Top3 agreement** | **81.5%** |
| ML End top1 | 233 |
| ML End + legal_attack | **0** |
| ML miss KO | 10 |
| ML zero_damage top1 | **0** |

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
| ML miss KO | 10 (0.44% of decisions) |

ML は End+legal_attack や zero_damage attack を top1 に選んでいない。
miss KO は 10/2,291 で低い。

## Interpretation

### Top1 agreement 67.7% は「まだ不十分」

rule policy は多肢選択（平均 38 候補/decision）で、ML がまだ rule の判断を
十分再現できていない。candidate_rank への依存が大きく、独自の判断力は弱い。

### Top3 agreement 81.5% は「方向性は合っている」

ML の top3 に rule の選択が含まれる率は高く、粗い合意はある。

### Unsafe decisions は非常に少ない

End+legal_attack=0, zero_damage=0, miss_KO=10 は安全寄り。

## Decision

**ML を行動選択にはまだ使わない**

理由:
1. Top1 agreement 67.7% は hybrid mode に入れるには低い
2. candidate_rank 依存が大きく、ML 独自の判断が弱い
3. feature 改善 or ラベル改善で agreement を上げてから再検討

## Next Steps

1. **Feature 改善**: predicted_damage, opp_bench_hp, hand_composition を追加
2. **Decision-level grouping**: pairwise ranking loss で学習（現在は pointwise）
3. **Outcome-weighted training**: win/loss reward を学習に反映
4. **90%+ agreement** に達したら hybrid 10% scoring を検討
5. Runtime default はまだ変更しない
