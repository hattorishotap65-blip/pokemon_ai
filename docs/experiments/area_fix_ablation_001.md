# Area Fix Ablation 001

## Purpose

Isolate the effect of the inPlayArea bug fix (#153) by comparing three configurations:
- A: Baseline (broken inPlayArea 0/1, no compensation)
- B: Area fix only (correct inPlayArea 4/5, no compensation)
- C: Area fix + attack compensation (#153 behavior)

## Background

| PR | Description |
|----|-------------|
| #151 | Bonus sweep — confirmed bonus=10 optimal. miss_KO=2, KO=99.1% |
| #152 | Loss diagnostics — 3/5 losses had zero attacks |
| #153 | Area fix + attack compensation. miss_KO=7, KO=96.6% |

#153 was merged as experiment but not promoted to submission candidate due to miss_KO increase. This ablation determines whether the regression comes from the area fix itself or the attack compensation.

## Configurations

| Config | inPlayArea | Attack Compensation | Env Flag |
|--------|-----------|--------------------|----|
| A baseline | 0/1 (broken) | No | `POKEMON_AI_AREA_FIX_MODE=baseline` |
| B fix_only | 4/5 (correct) | No | `POKEMON_AI_AREA_FIX_MODE=area_fix_only` |
| C fix_comp | 4/5 (correct) | +0.15 attack bonus | `POKEMON_AI_AREA_FIX_MODE=area_fix_attack_comp` |

All configs use: `POKEMON_AI_ML_HYBRID=1`, `POKEMON_AI_ML_BONUS_RATIO=10.0`

## Commands

```bash
# A: baseline
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=10.0 POKEMON_AI_AREA_FIX_MODE=baseline \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 271000 --run-games --use-wsl \
    --output artifacts/area_fix_ablation_baseline_100g.jsonl

# B: area fix only
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=10.0 POKEMON_AI_AREA_FIX_MODE=area_fix_only \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 272000 --run-games --use-wsl \
    --output artifacts/area_fix_ablation_fix_only_100g.jsonl

# C: area fix + attack compensation
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=10.0 POKEMON_AI_AREA_FIX_MODE=area_fix_attack_comp \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 273000 --run-games --use-wsl \
    --output artifacts/area_fix_ablation_attack_comp_100g.jsonl

# Aggregate
python experiments/compare_area_fix_ablation.py \
  --inputs \
    A_baseline=artifacts/area_fix_ablation_baseline_100g.jsonl \
    B_fix_only=artifacts/area_fix_ablation_fix_only_100g.jsonl \
    C_fix_comp=artifacts/area_fix_ablation_attack_comp_100g.jsonl \
  --summary artifacts/area_fix_ablation_summary.json
```

## Self-Play 100g Results

| Config | Games | Errors | Timeouts | End+legal_attack | zero_damage |
|--------|-------|--------|----------|------------------|-------------|
| A baseline | 100 | 0 | 0 | 0 | 0 |
| B fix_only | 100 | 0 | 0 | 0 | 0 |
| C fix_comp | 100 | 0 | 0 | 0 | 0 |

## KO Capture Rate

| Config | KO Candidates | KO Selected | Capture Rate | miss_KO |
|--------|---------------|-------------|--------------|---------|
| A baseline | 228 | 222 | 97.4% | 6 |
| B fix_only | 243 | 232 | 95.5% | 11 |
| C fix_comp | 226 | 217 | 96.0% | 9 |

Reference: #151 baseline had miss_KO=2, KO capture=99.1% (different game range).

## Action Type Distribution

| Config | ATTACK | ATTACH | END | RETREAT | Decisions |
|--------|--------|--------|-----|---------|-----------|
| A baseline | 1216 | 1239 | 970 | 312 | 19218 |
| B fix_only | 1276 | 1266 | 977 | 350 | 19822 |
| C fix_comp | 1227 | 1231 | 1004 | 298 | 18743 |

## Analysis

### 1. Baseline variance is high

A baseline scored miss_KO=6 in this run vs miss_KO=2 in #151. This confirms that **100g self-play has significant miss_KO variance** — the #151 result of 2 was on the low end, not a stable baseline.

### 2. Area fix increases miss_KO

B (fix_only) has the highest miss_KO (11) and lowest KO capture (95.5%). This is consistent with #153 findings: fixing the area constants activates the +0.15 attach-enables-attack heuristic, which shifts relative scores and reduces attack priority at KO opportunities.

### 3. Attack compensation partially recovers

C (fix_comp) at miss_KO=9 is between A (6) and B (11). The +0.15 attack compensation helps but does not fully restore baseline KO behavior.

### 4. All configs are safe

All three pass safety baseline: errors=0, timeouts=0, End+legal_attack=0, zero_damage=0.

### 5. Action distribution is stable

No extreme skew across configs. B has slightly more ATTACKs (1276 vs 1216/1227) but also more miss_KOs — the extra attacks may be non-KO attacks.

## 300g Re-Comparison

Per PR comment feedback, re-ran A/B/C at 300g to reduce variance.

### 300g KO Capture Rate

| Config | Games | KO Candidates | KO Selected | Capture Rate | miss_KO |
|--------|-------|---------------|-------------|--------------|---------|
| A baseline | 300 | 622 | 600 | 96.5% | 22 |
| **B fix_only** | **300** | **653** | **632** | **96.8%** | **21** |
| C fix_comp | 300 | 666 | 636 | 95.5% | 30 |

### 300g Safety Metrics

| Config | Errors | Timeouts | End+legal_attack | zero_damage |
|--------|--------|----------|------------------|-------------|
| A | 0 | 0 | 0 | 0 |
| B | 0 | 0 | 0 | 0 |
| C | 0 | 0 | 0 | 0 |

### 300g Action Type Distribution

| Config | ATTACK | ATTACH | END | RETREAT | Decisions |
|--------|--------|--------|-----|---------|-----------|
| A | 3714 | 3824 | 3205 | 1084 | 61595 |
| B | 3583 | 3690 | 2851 | 1002 | 57551 |
| C | 3744 | 3765 | 3159 | 1049 | 60562 |

### 300g Analysis

1. **B (area fix only) matches baseline**: miss_KO=21 vs A's 22, KO capture 96.8% vs 96.5%. Within noise — effectively equivalent.
2. **C (attack compensation) is worst**: miss_KO=30, KO capture 95.5%. The +0.15 attack bonus backfires at 300g scale.
3. **100g results were misleading**: At 100g, A looked best (miss_KO=6) and B worst (11). At 300g, they converge. This confirms 100g variance was too high for reliable comparison.
4. **All configs pass safety**: errors=0, timeouts=0, End+legal_attack=0, zero_damage=0.

## Conclusion

**300g confirms: B (area fix only) is equivalent to A (baseline).** The area fix does NOT worsen miss_KO — the 100g difference was variance.

**C (attack compensation) is harmful** — it worsens miss_KO by ~36% vs baseline. The +0.15 attack bonus should be removed.

## Recommendation

**B (area fix only) is safe to adopt.** It correctly fixes attach features without harming KO capture.

Action items:
1. ~~Remove attack compensation (+0.15 attack bonus) from `_heuristic_ml_score`~~ — kept behind env flag, disabled by default
2. Keep the inPlayArea 4/5 fix (B mode) as the new default
3. B can be considered for submission candidate since it matches baseline safety
4. ~~Set `POKEMON_AI_AREA_FIX_MODE` default to `area_fix_only`~~ — done

## Final Implementation

- **Default mode**: `area_fix_only` (correct inPlayArea 4/5, no attack compensation)
- Attack compensation (+0.15) is retained behind `POKEMON_AI_AREA_FIX_MODE=area_fix_attack_comp` for experiment purposes only — it does NOT run by default
- `baseline` mode (broken 0/1) is available for regression comparison only
