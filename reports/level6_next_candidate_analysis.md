# Next Candidate Analysis

## Current State

- Tests: 141/141 pass
- retreat_to_better_attacker_bonus=1400 adopted
- anomalies_total: ~4.97/g (200g validated)
- Safety: all 0

## Remaining Anomaly Structure (post retreat_bonus=1400)

| Category | /game | Status |
|----------|-------|--------|
| bellibolt_attack_probably_correct | 2.25 | no_fix_needed |
| kw_f0007_range_game_flow | 1.10 | structural constraint |
| bb_f0007_range_no_retreat | 0.57 | no retreat available |
| bb_240_259 | 0.54 | F0009/F0010 rejected |
| wt_game_flow | 0.38 | structural constraint |

## Proposed Next Candidate

**`attack_suppress_penalty` micro-tuning**

| Value | Description |
|-------|-------------|
| -20.0 | Weaker suppression: attack earlier, skip pre-attack actions |
| **-30.0** | **Current baseline** |
| -40.0 | Stronger suppression: complete pre-attack actions first |

### Why This Candidate

1. Already externalized in `data/weights.json` — no code change needed
2. Does not conflict with `retreat_to_better_attacker_bonus=1400`
3. Small adjustment (-30 to -20 or -40)
4. Level 6 Run 002 tested this at 30g (pre-retreat_bonus=1400) but needs revalidation with current config
5. Affects attack priority balance — could improve or reveal new patterns

### Level 6 Run 002 Results (pre-retreat_bonus=1400)

| attack_suppress_penalty | 30g /game | vs baseline |
|------------------------|-----------|-------------|
| -20.0 | 5.10 | +5% |
| -30.0 | 4.87 | baseline |
| -40.0 | 5.30 | +9% |

These results are from before retreat_bonus=1400 adoption. The interaction between retreat_bonus=1400 and attack_suppress_penalty has not been tested.

### Expected Improvement

- -20 might enable faster attacks in edge cases where pre-attack setup is unnecessary
- -40 might improve attack quality by ensuring Boss/Switch/Energy are completed first
- Neither is expected to be large; this is fine-tuning

### Expected Risks

- -20: may skip needed pre-attack actions → lower quality attacks
- -40: may delay attacks → attack_available_but_no_attack could increase
- Both detectable via safety metrics

### A/B Evaluation Plan

```bash
python experiments/weight_search.py \
  --grid-file <attack_suppress_grid.json> \
  --games 30 --use-wsl --start-game 8600
```

If 30g shows promise, follow up with 50g then 200g (same process as retreat_bonus=1400).

### Files to Change

| File | Change |
|------|--------|
| data/weights.json | Temporarily adjust attack_suppress_penalty |

No agent logic changes.

## Alternative Candidates Considered

| Candidate | Reason Not Selected |
|-----------|-------------------|
| Bellibolt evolve priority (220.0) | Large impact, risk of breaking setup flow |
| Voltorb attack bonus externalization | score_voltorb_attack has multiple hardcoded values, complex |
| Kilowattrel ability threshold | F0004 confirmed as no_fix_needed |
| New weight parameter | Premature — should exhaust existing params first |
