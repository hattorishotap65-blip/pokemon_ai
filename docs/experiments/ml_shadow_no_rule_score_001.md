# ML Shadow Scoring Without Rule Score 001

## Purpose

#138 では ML が rule_score / candidate_rank を学習しているだけだった。
rule_score / candidate_rank を除外して、ML が盤面特徴だけで rule policy を
どの程度再現できるか、危険な判断をしないかを確認する。

## No Behavior Change

policy.py の行動選択ロジックは一切変更していない。
ML score は shadow log としてのみ出力。submission.tar.gz 更新なし。

## Comparison: Full vs No-Rule Features

| Metric | A: Full (32 feat) | B: No-Rule (30 feat) |
|--------|-------------------|---------------------|
| Eval decisions | 20,757 | 20,757 |
| Eval candidates | 95,906 | 95,906 |
| **Top1 agreement** | 100.0% | **71.5%** |
| **Top3 agreement** | 100.0% | **87.8%** |
| ML End top1 | 1,048 | 373 |
| ML End + legal_attack | **0** | **0** |
| ML miss KO | 4 | 223 |
| ML zero_damage top1 | **0** | **0** |

## Excluded Features (B)

- rule_score
- candidate_rank

## No-Rule Top Features (by |weight|)

Trained on 50g (43,927 candidates), evaluated on 100g.

## Safety Check

| Check | Full | No-Rule |
|-------|------|---------|
| ML End + legal_attack | **0** | **0** |
| ML zero_damage top1 | **0** | **0** |
| ML miss KO | 4 (0.02%) | 223 (1.1%) |

No-rule ML は End+legal_attack / zero_damage で安全。
miss KO は 223/20,757 = 1.1% に上昇。rule_score なしでは
KO 候補の識別が若干弱くなるが、致命的ではない。

## Interpretation

### Top1 71.5% — ML に一定の独自判断力がある

rule_score を使わずに 71.5% の一致は、盤面特徴だけでも
rule policy の大半の判断を再現できることを意味する。

### Top3 87.8% — 粗い合意は高い

ML の top3 に rule の選択が含まれる率は高く、
大きく外れた判断は少ない。

### miss KO 1.1% は許容範囲

223/20,757 で、KO 機会の逃しは 1.1%。
rule_score があれば 0.02% だが、独自判断でも 98.9% は KO を逃さない。

### End+legal_attack = 0, zero_damage = 0

安全性は full feature と同等に維持。

## Decision

**ML 独自の判断力は一定水準に達している。**

- Top1 71.5% / Top3 87.8% は feature 改善で向上余地あり
- 安全性 (End+legal_attack=0, zero_damage=0) は確保
- miss_KO 1.1% は outcome-weighted training で改善候補

次に outcome-weighted training に進めるか: **進められる。**

## Next Steps

1. **Outcome-weighted training**: win/loss reward を学習に反映し、
   勝ちに寄与する action を優先するモデルを作る
2. **Feature 改善**: predicted_damage, hand_composition を追加して
   Top1 agreement を 80%+ に引き上げ
3. **miss_KO 改善**: KO 候補の特徴量を強化
4. **90%+ agreement + unsafe=0** に達したら hybrid 10% scoring を検討
