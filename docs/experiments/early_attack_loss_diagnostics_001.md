# Early Attack Loss Diagnostics 001

## Purpose

Diagnose loss patterns observed in Kaggle leaderboard matches. Based on manual review of 5 unique loss logs, recurring patterns of "zero attacks", "active attacker energy starvation", and "bench over-setup" were identified.

## Background

| PR | Description |
|----|-------------|
| #134 | Baseline clean submission candidate |
| #148 | ML hybrid bonus=10 — improved leaderboard |
| #149 | Recorded #148 result |
| #150 | Bonus sweep infrastructure |
| #151 | Bonus sweep results — confirmed bonus=10 is optimal in 8-15 range |

## Observations from 5 Loss Logs

### Summary

- Analyzed 5 unique loss logs from Kaggle leaderboard
- 3/5 losses had zero attacks
- Multiple games showed bench energy accumulation while active could not attack
- Several games completed evolution (Bellibolt ex / Kilowattrel) but never attacked
- Conclusion: next improvement should target early attack / active energy priority, not bonus ratio

### Per Match Table

_To be filled when Kaggle match logs are processed with the diagnostics script._

| Episode | Opponent | Result | Our Attacks | Opp Attacks | Active Attach | Bench Attach | 1st Active | Key Pattern |
|---------|----------|--------|-------------|-------------|---------------|--------------|------------|-------------|
| — | — | loss | — | — | — | — | — | — |

### Common Patterns

| Pattern | Description | Frequency |
|---------|-------------|-----------|
| `attack_zero_loss` | Lost with zero attacks executed | 3/5 |
| `active_energy_lag` | No energy attached to active while bench received 2+ | observed |
| `bench_over_setup` | 3+ bench attaches with <=1 active attach and <=2 attacks | observed |
| `completed_attacker_no_attack` | Completed Bellibolt ex or Kilowattrel but never attacked | observed |
| `early_attack_missing` | First attack at turn 5+ with <=2 total attacks | observed |
| `low_damage_output` | Attacked but only 1-2 times total | observed |

## Diagnostics Script

```bash
# From Kaggle match logs
python experiments/analyze_loss_patterns.py \
    --inputs artifacts/loss_logs/*.json \
    --summary artifacts/early_attack_loss_summary.json

# From self-play game range
python experiments/analyze_loss_patterns.py \
    --from-range 261000 261005 \
    --summary artifacts/early_attack_loss_summary.json

# Losses only
python experiments/analyze_loss_patterns.py \
    --inputs artifacts/loss_logs/*.json \
    --losses-only \
    --summary artifacts/early_attack_loss_summary.json
```

## Collected Metrics

Per game:
- `our_attack_count` / `opponent_attack_count`
- `first_attack_turn` / `turns_until_first_attack`
- `active_attach_count` / `bench_attach_count` / `bench_attach_ratio`
- `bellibolt_ex_completed` / `kilowattrel_completed`
- `completed_attacker_no_attack` (boolean)

Pattern flags:
- `early_attack_missing`
- `attack_zero_loss`
- `bench_over_setup`
- `active_energy_lag`
- `completed_attacker_no_attack`
- `low_damage_output`
- `opponent_outpaced_us`

## Recommendation

Next implementation candidates (keeping bonus=10 unchanged):

1. **Active attacker energy priority bonus** — prefer attaching to active if it enables attack within 1 turn
2. **Bench over-setup penalty** — penalize excessive bench energy when active cannot attack
3. **Early attack urgency** — increase urgency to deal damage before opponent pulls ahead
4. **Completed attacker utilization** — avoid setup actions if a ready attacker exists but hasn't attacked
5. **Keep bonus=10 unchanged** — bonus ratio is not the cause of these losses

## What This PR Does NOT Do

- Does not change runtime policy (policy.py, ml_hybrid.py, ionos_rules.py)
- Does not change ML hybrid score or bonus ratio
- Does not rebuild submission.tar.gz
- Does not submit to leaderboard
- Does not restore attack_plan.py
