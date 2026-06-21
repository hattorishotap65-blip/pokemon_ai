# voltorb_damage_scaling Externalization

## Purpose

Externalize the hardcoded Voltorb damage scaling multiplier (0.8) from
ionos_rules.py to data/weights.json, enabling auto_tune_runner.py
to search for optimal values.

## Change

| Item | Before | After |
|------|--------|-------|
| ionos_rules.py:801 | `score += damage * 0.8` | `score += damage * _voltorb_damage_scaling` |
| data/weights.json | (not present) | `voltorb_damage_scaling: 0.8` |
| Fallback | N/A | 0.8 |

## Behavior Change

**None.** The agent uses the same value (0.8) before and after this change.

## Auto-Tune Grid

```
voltorb_damage_scaling: [0.4, 0.6, 0.8, 1.0, 1.2]
```

Added to: auto_tune.py, auto_tune_runner.py, weight_search.py

## Next Step

Run 30g search via auto_tune_runner.py:
```bash
python tools/auto_tune_runner.py --parameter voltorb_damage_scaling \
    --stage 30g --games 30 --start-game 15000 --use-wsl --output reports --run
```
