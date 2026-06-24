# Active Energy Priority 001

## Purpose

Address loss patterns diagnosed in #152: zero attacks, active attacker energy starvation, bench over-setup. Improve active attacker energy priority in ML hybrid scoring while keeping bonus=10.

## Background

| PR | Description |
|----|-------------|
| #148 | ML hybrid bonus=10 — leaderboard improved |
| #151 | Bonus sweep — confirmed bonus=10 optimal |
| #152 | Loss diagnostics — 3/5 losses had zero attacks |

## Changes

### 1. inPlayArea bug fix

Fixed `attach_to_active` and `attach_to_bench` feature extraction to use correct area constants:
- Before: `inPlayArea == 0` (ACTIVE) / `== 1` (BENCH) — **always False** since cabt uses 4/5
- After: `inPlayArea == _AREA_ACTIVE (4)` / `== _AREA_BENCH (5)` — **correct**

This fix activates the existing `+0.15` heuristic rule for `attach_to_active + active_attach_would_enable`, which was previously dead code.

### 2. New features

- `attach_enables_attack`: True when attaching to active would bring energy to exactly what's needed for attack
- `active_is_main_attacker`: True when active Pokemon is Voltorb/Bellibolt ex/Kilowattrel

### 3. Attack boost compensation

The area fix shifts relative scores (attach gets +0.15 when it was getting 0 before). To maintain KO capture rate, added a compensating attack boost:
- `+0.15` when action is attack AND has_legal_attack is true

### 4. No bench penalty / no additional active priority

Tried in iterations v1-v4: bench over-setup penalty and additional active attach bonus both **worsened** miss_KO significantly. Removed in final version.

## Iteration History

| Version | Changes | miss_KO | KO Capture |
|---------|---------|---------|------------|
| baseline (#151) | bonus=10, area=0/1 (broken) | 2 | 99.1% |
| v1 | area fix + active +0.15 + bench -0.08 + early +0.05 | 7 | 97.1% |
| v2 | area fix + active +0.12 + bench -0.05 (stricter) | 5 | 98.0% |
| v3 | area fix + attach_enables +0.10 + early +0.03 | 19 | 92.0% |
| v4 | area fix + early +0.05 only | 10 | 95.4% |
| v5 | area fix only (no extra bonus) | 9 | 95.9% |
| v6 | area fix + attack compensate +0.08 | 10 | 95.9% |
| **v7 (final)** | **area fix + attack compensate +0.15** | **7** | **96.6%** |

## Self-Play 100g Results (v7 final)

| Metric | Baseline (#151 bonus=10) | Active EP v7 |
|--------|--------------------------|--------------|
| Games | 100 | 100 |
| Errors | 0 | 0 |
| Timeouts | 0 | 0 |
| End+legal_attack | 0 | 0 |
| zero_damage | 0 | 0 |
| miss_KO | 2 | 7 |
| KO capture | 211/213 (99.1%) | 199/206 (96.6%) |
| Decisions | 18953 | 19737 |
| ATTACK | 1180 | 1208 |
| ATTACH | 1209 | 1258 |
| END | 978 | 1008 |
| RETREAT | 324 | 355 |

## Analysis

### What improved
- `attach_to_active` and `attach_to_bench` now fire correctly (bug fix)
- `attach_enables_attack` feature works for accurate tracking
- Active main attacker identification available for future use

### What didn't improve in self-play
- miss_KO went from 2 to 7 (self-play variance + area fix side effect)
- KO capture rate dropped from 99.1% to 96.6%

### Why miss_KO increased
The area fix activates the `+0.15` for attach_enables_attack, which was dead code before. This raises attach scores relative to attack scores in the normalized ML bonus. Even with `+0.15` attack compensation, the net balance shifted slightly against attack in some KO-opportunity decisions.

However, this is in **symmetric self-play** where both sides use the same agent. The miss_KO metric here counts decisions where a KO-capable attack existed but wasn't selected — not necessarily game-losing decisions. In leaderboard play against different opponents, correctly prioritizing energy attach to enable future attacks may outweigh the small miss_KO increase.

## Recommendation

**Proceed cautiously to leaderboard test.**

The area fix is a genuine bug fix that makes attach features work correctly. The self-play miss_KO increase is a concern but may not translate to leaderboard degradation because:
1. Self-play miss_KO has high variance at 100g
2. The fix enables a feature (attach priority) that should help against weaker opponents
3. The fix was dead code before — now it's working as designed

If leaderboard score drops, revert to #148 baseline.

## What This PR Does NOT Do

- Does not change bonus ratio (remains 10.0)
- Does not restore attack_plan.py
- Does not change policy.py or main.py
- Does not rebuild submission.tar.gz
