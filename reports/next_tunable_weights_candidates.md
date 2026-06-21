# Next Tunable Weight Candidates

## Current Stable Baseline

| Parameter | Value | Status |
|-----------|-------|--------|
| retreat_to_better_attacker_bonus | 1400.0 | adopted, not re-searching |
| attack_suppress_penalty | -40.0 | adopted, not re-searching |
| advantage_weight | 0.4 | confirmed optimal (PR #48) |
| energy_to_plan_bonus | 5.0 | confirmed optimal (PR #49) |
| energy_to_plan_bonus_no_need | 2.0 | confirmed optimal (PR #50/#51) |

## Existing 3-Weight Search Conclusion

All 3 tunable weights confirmed at current values. No further exploration needed for these.

---

## Priority A: High Impact, Externalization Ready

### A1: voltorb_ko_attack_bonus

| Item | Detail |
|------|--------|
| File | ionos_rules.py:813 |
| Current value | 1000.0 |
| Behavior | Massive bonus when Voltorb attack can KO opponent active |
| Expected effect | Tuning could balance between KO aggression and setup completion |
| Risk | High — too low means missing KO opportunities |
| Grid | [500, 750, 1000, 1250, 1500] |
| Requires agent change | Yes (externalize to weights.json) |
| Runner ready | After externalization |

### A2: voltorb_damage_scaling

| Item | Detail |
|------|--------|
| File | ionos_rules.py:798 |
| Current value | 0.8 |
| Behavior | Multiplier converting Voltorb estimated damage to attack score |
| Expected effect | Higher = more aggressive attack selection, lower = more conservative |
| Risk | Medium — affects all Voltorb attack decisions |
| Grid | [0.5, 0.6, 0.8, 1.0, 1.2] |
| Requires agent change | Yes (externalize) |
| Runner ready | After externalization |

### A3: energy_attack_enablement_bonus

| Item | Detail |
|------|--------|
| File | ionos_rules.py:298 |
| Current value | 300.0 |
| Behavior | Bonus when energy attachment enables an immediate attack |
| Expected effect | Higher = prioritize attack-enabling attachments more |
| Risk | Low — already guarded by safety metrics |
| Grid | [150, 200, 300, 400, 500] |
| Requires agent change | Yes (externalize) |
| Runner ready | After externalization |

### A4: evolve_first_bellibolt_bonus

| Item | Detail |
|------|--------|
| File | ionos_rules.py:956 |
| Current value | 220.0 |
| Behavior | Priority bonus for evolving the first Bellibolt ex |
| Expected effect | Higher = evolve earlier, lower = delay for other actions |
| Risk | Medium — too low could delay engine setup |
| Grid | [150, 180, 220, 260, 300] |
| Requires agent change | Yes (externalize) |
| Runner ready | After externalization |

### A5: voltorb_energy_ko_line_bonus

| Item | Detail |
|------|--------|
| File | ionos_rules.py:361 |
| Current value | 400.0 |
| Behavior | Bonus when energy attachment reaches opponent KO threshold |
| Expected effect | Tuning could sharpen KO targeting via energy placement |
| Risk | Medium — interacts with energy distribution strategy |
| Grid | [200, 300, 400, 500, 600] |
| Requires agent change | Yes (externalize) |
| Runner ready | After externalization |

---

## Priority B: Medium Impact

### B1: turn_rule_legal_attack_score

| Item | Detail |
|------|--------|
| File | turn_rule_engine.py:281 |
| Current value | 150.0 |
| Behavior | Baseline bonus for any legal attack action |
| Expected effect | Adjusts general attack priority vs other actions |
| Risk | Low |
| Grid | [100, 125, 150, 175, 200] |

### B2: ko_risk_critical_penalty

| Item | Detail |
|------|--------|
| File | planner.py:247 |
| Current value | 8.0 |
| Behavior | Penalty when active Pokemon HP ratio <= 0.25 |
| Expected effect | Higher = more conservative when near KO |
| Risk | Low |
| Grid | [4.0, 6.0, 8.0, 10.0, 12.0] |

### B3: retreat_losing_energy_penalty

| Item | Detail |
|------|--------|
| File | turn_rule_engine.py:294 |
| Current value | 250.0 |
| Behavior | Penalty for retreating when it costs energy |
| Expected effect | Tuning balances retreat willingness vs energy loss |
| Risk | Medium — interacts with retreat_to_better_attacker_bonus |
| Grid | [150, 200, 250, 300, 350] |

### B4: voltorb_avoid_attach_when_attack_available

| Item | Detail |
|------|--------|
| File | ionos_rules.py:852 |
| Current value | 500.0 |
| Behavior | Penalty for attaching energy when Voltorb can already attack |
| Expected effect | Lower = allow pre-attack energy for future, higher = attack first |
| Risk | Medium |
| Grid | [300, 400, 500, 600, 700] |

### B5: kilowattrel_ability_hand_threshold

| Item | Detail |
|------|--------|
| File | ionos_rules.py:905 |
| Current value | 120.0 (large hand penalty) |
| Behavior | Penalty for using Kilowattrel ability when hand >= 5 |
| Expected effect | Tuning controls ability usage based on hand size |
| Risk | Low |
| Grid | [60, 90, 120, 150, 180] |

### B6: win_condition_weight

| Item | Detail |
|------|--------|
| File | evaluator.py:8 |
| Current value | 0.6 |
| Behavior | Scale factor for plan progress in board evaluation |
| Expected effect | Higher = weight plan progress more, lower = weight board state more |
| Risk | Medium — affects overall strategy balance |
| Grid | [0.3, 0.4, 0.6, 0.8, 1.0] |

---

## Priority C: Low Impact / Complex

### C1: Card-specific energy attachment priorities (12+ values)

- ionos_rules.py:316-348
- Individual voltorb/bellibolt/kilowattrel/tadbulb/wattrel energy bonuses
- Too many interdependent values to tune individually
- Better handled as a group if needed

### C2: Poffin / bench fill priorities (15+ values)

- ionos_rules.py:418-500
- Bench construction strategy values
- Complex interactions between card availability
- Low anomaly impact in current logs

### C3: Planner lookahead weights

- planner.py:40-44 (FUTURE_WEIGHT=0.7, THREAT_WEIGHT=0.8)
- Architectural constants affecting lookahead quality
- High risk of unintended interactions
- Better left for dedicated planner improvements

---

## Recommended First Externalization

### voltorb_ko_attack_bonus (A1)

**Reason:**
1. Single clear value (1000.0) with a single clear purpose
2. Directly impacts Voltorb KO decisions — a major game-winning action
3. Safety metrics will catch regressions immediately
4. Easy to externalize: one line in ionos_rules.py + one key in weights.json
5. auto_tune_runner.py can handle it after adding to _SEARCH_GRID
6. Anomaly category `bellibolt_attack_probably_correct` (2.19/g at 200g) may be influenced

### Second candidate: voltorb_damage_scaling (A2)

**Reason:**
1. Simple multiplier (0.8) affecting all Voltorb attack scores
2. Complementary to A1 — together they control Voltorb attack priority
3. Should be tuned after A1 to avoid interaction effects

---

## Next PR Plan

| PR | Content |
|----|---------|
| Next | Externalize `voltorb_ko_attack_bonus` to weights.json + add to auto_tune grids |
| After | Run 30g search for voltorb_ko_attack_bonus via auto_tune_runner.py |
| Later | Externalize `voltorb_damage_scaling` if A1 shows promise |

## Note

This PR contains no agent behavior changes. All findings are documentation only.
