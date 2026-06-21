# voltorb_ko_attack_bonus Externalization

## Purpose

Externalize the hardcoded Voltorb KO attack bonus (1000.0) from
ionos_rules.py to data/weights.json, enabling auto_tune_runner.py
to search for optimal values.

## Change

| Item | Before | After |
|------|--------|-------|
| ionos_rules.py:813 | `score += 1000.0` | `score += _voltorb_ko_attack_bonus` |
| data/weights.json | (not present) | `voltorb_ko_attack_bonus: 1000.0` |
| Fallback | N/A | 1000.0 |

## Behavior Change

**None.** The agent uses the same value (1000.0) before and after this change.

## Auto-Tune Grid

```
voltorb_ko_attack_bonus: [500, 750, 1000, 1250, 1500]
```

Added to: auto_tune.py, auto_tune_runner.py, weight_search.py

## Next Step

Run 30g search via auto_tune_runner.py:
```bash
python tools/auto_tune_runner.py --parameter voltorb_ko_attack_bonus \
    --stage 30g --games 30 --start-game 11000 --use-wsl --output reports --run
```
