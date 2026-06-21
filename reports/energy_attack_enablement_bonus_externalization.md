# energy_attack_enablement_bonus Externalization

## Purpose

Externalize the hardcoded energy attack enablement bonus (300.0) from
ionos_rules.py to data/weights.json, enabling auto_tune_runner.py
to search for optimal values.

## Change

| Item | Before | After |
|------|--------|-------|
| ionos_rules.py:304 | `score += 300.0` | `score += _energy_attack_enablement_bonus` |
| data/weights.json | (not present) | `energy_attack_enablement_bonus: 300.0` |
| Fallback | N/A | 300.0 |

## Behavior Change

**None.** The agent uses the same value (300.0) before and after this change.

## Auto-Tune Grid

```
energy_attack_enablement_bonus: [150, 200, 300, 400, 500]
```

Added to: auto_tune.py, auto_tune_runner.py, weight_search.py

## Next Step

Run 30g search via auto_tune_runner.py:
```bash
python tools/auto_tune_runner.py --parameter energy_attack_enablement_bonus \
    --stage 30g --games 30 --start-game 16000 --use-wsl --output reports --run
```
