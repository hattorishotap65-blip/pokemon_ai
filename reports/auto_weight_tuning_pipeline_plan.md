# Automated Weight Tuning Pipeline Design

## Current Stable Version

| Tag | v1.0-stable |
|-----|-------------|
| Tests | 141/141 |
| submission.tar.gz | updated |
| Safety | all 0 |

## Current Stable Baseline

| Parameter | Value | Adopted In |
|-----------|-------|------------|
| retreat_to_better_attacker_bonus | 1400.0 | PR #30 |
| attack_suppress_penalty | -40.0 | PR #39 |
| advantage_weight | 0.4 | default |
| energy_to_plan_bonus | 5.0 | default |
| energy_to_plan_bonus_no_need | 2.0 | default |

## Excluded From Current Search

| Parameter | Value | Reason |
|-----------|-------|--------|
| retreat_to_better_attacker_bonus | 1400.0 | Fully validated, stable |
| attack_suppress_penalty | -40.0 | Fully validated, stable |

---

## Tunable Existing Weights (weights.json)

These are already externalized and can be tuned without code changes.

| Parameter | Current | Explored? | Range to try |
|-----------|---------|-----------|--------------|
| advantage_weight | 0.4 | 30g only (Run 002) | 0.2 - 0.6 step 0.1 |
| energy_to_plan_bonus | 5.0 | 30g only (Run 002) | 3.0 - 8.0 step 1.0 |
| energy_to_plan_bonus_no_need | 2.0 | never | 1.0 - 4.0 step 1.0 |

Note: Run 002 results (pre-retreat_bonus=1400) are stale. All 3 need re-evaluation with current stable config.

## Hardcoded Candidates for Externalization

Priority is based on impact scope and ease of extraction.

### Tier 1: High impact, easy to extract

| File | Value | Context | Description |
|------|-------|---------|-------------|
| ionos_rules.py:813 | 1000.0 | voltorb_ko_attack_bonus | Voltorb KO attack bonus |
| ionos_rules.py:798 | 0.8 | voltorb_damage_scaling | Damage-to-score multiplier |
| ionos_rules.py:956 | 220.0 | evolve_first_bellibolt | First Bellibolt evolve priority |
| ionos_rules.py:361 | 400.0 | energy_ko_line_bonus | KO line reached energy bonus |
| ionos_rules.py:298 | 300.0 | energy_attack_enablement | Attack enablement bonus |

### Tier 2: Medium impact

| File | Value | Context | Description |
|------|-------|---------|-------------|
| policy.py:439-450 | 20/30/5/3/6 | attack_ko_bonus | KO/almost-KO attack bonuses |
| policy.py:395 | 15.0 | deck_out_penalty | Draw-related deck-out penalty |
| policy.py:498 | 8.0 | urgent_bench_bonus | Urgent role bench bonus |
| planner.py:40-44 | 0.7/0.8 | future_threat_weight | Lookahead weights |
| planner.py:247-248 | 0.25/0.50 | ko_risk_threshold | HP ratio thresholds |

### Tier 3: Low priority (many related values, complex)

| File | Values | Context | Description |
|------|--------|---------|-------------|
| ionos_rules.py:316-348 | 45-140 range | energy_card_priority | Card-specific energy priorities (12+ values) |
| ionos_rules.py:418-500 | 35-175 range | poffin_bench_priority | Poffin/bench fill priorities (15+ values) |
| ionos_rules.py:516-531 | 130-170 range | play_basic_priority | Basic Pokemon play priorities |

---

## Existing Tools (Reusable)

| Tool | Purpose | Status |
|------|---------|--------|
| experiments/weight_search.py | Grid search with WSL support | Working, needs grid-file update |
| tools/analyze_battle_logs.py | Anomaly detection from logs | Working |
| tools/classify_anomalies.py | Category-level classification | Working |
| tools/evaluate_candidate.py | Accept/hold/reject decision | Working, safety=after==0 |
| tools/prepare_pr_candidate.py | PR candidate report | Working |
| tools/generate_pr_metadata.py | PR title/body/branch generation | Working |
| scripts/run_all_tests.sh | CI test runner | Working |

## New Tools Needed

| Tool | Purpose | Priority |
|------|---------|----------|
| tools/auto_tune.py | Orchestrator: staged search pipeline | Required |
| tools/promotion_gate.py | 30g→50g / 50g→200g promotion logic | Required |
| tools/search_history.py | Track explored candidates, prevent re-exploration | Recommended |
| reports/search_history.json | Persistent log of all search results | Recommended |

---

## Recommended Search Method

### Staged Grid Search (recommended)

1. **Why grid search**: Our parameter space is small (3-5 variables, 4-6 values each). Grid search is deterministic, reproducible, and easy to audit.
2. **Why not random search**: With <50 grid points, random doesn't help. Grid covers the space completely.
3. **Why staged**: 30g results are unreliable (proven twice in Level 6). Staged promotion filters noise cheaply.

### Single-variable priority order

Explore one variable at a time, holding others at stable baseline. This avoids interaction effects and keeps each search interpretable.

| Priority | Variable | Values | Grid points |
|----------|----------|--------|-------------|
| 1 | advantage_weight | 0.2, 0.3, 0.4, 0.5, 0.6 | 5 |
| 2 | energy_to_plan_bonus | 3.0, 4.0, 5.0, 6.0, 7.0, 8.0 | 6 |
| 3 | energy_to_plan_bonus_no_need | 1.0, 2.0, 3.0, 4.0 | 4 |

Total: 15 grid points at 30g each = ~450 games (~30 min WSL).

### Multi-variable search (later)

After single-variable sweeps, promising pairs can be combined:
- best_advantage_weight x best_energy_to_plan_bonus (small grid)

---

## Pipeline Stages

### Stage 1: Grid Search (30g)

```
Input:  grid.json (parameter x values)
Run:    weight_search.py --grid-file grid.json --games 30
Output: reports/search_results_30g.json
Filter: anomalies_total < baseline AND safety all 0
```

**Promotion criteria to Stage 2:**
- anomalies_total < baseline (any improvement)
- Safety metrics all 0
- No A-category anomalies (real_fix_candidate = 0)

### Stage 2: Validation (50g)

```
Input:  promoted candidates from Stage 1
Run:    50g baseline + 50g candidate
Output: reports/validation_50g.json
Filter: improvement sustained AND safety all 0
```

**Promotion criteria to Stage 3:**
- anomalies_total improvement maintained (delta <= 0 vs baseline)
- Safety metrics all 0
- No new anomaly categories appearing

### Stage 3: Confirmation (200g)

```
Input:  promoted candidates from Stage 2
Run:    200g baseline + 200g candidate
Output: reports/validation_200g.json
Decision: accept / hold / reject
```

---

## Decision Criteria

### Accept

All must be true:
- anomalies_total improvement at 200g (delta < 0)
- Safety metrics all 0 at all stages
- No new anomaly categories
- Consistency: improvement direction same at 30g/50g/200g
- bellibolt_attack_probably_correct not worsened by >10%

### Hold

Any of:
- Improvement at 30g/50g but not confirmed at 200g
- Marginal improvement (<2% at 200g)
- One anomaly category worsened while total improved

### Reject

Any of:
- anomalies_total worse at 200g
- Any safety metric > 0 at any stage
- real_fix_candidate > 0 at any stage

---

## Safety Criteria

All 4 must be 0 at every stage:
- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available
- ability_without_followup_attack

If any > 0 at any stage, the candidate is immediately rejected.

---

## Category-Level Evaluation

Beyond anomalies_total, the following categories are tracked:

| Category | Threshold | Action if exceeded |
|----------|-----------|-------------------|
| bellibolt_attack_probably_correct | +10% vs baseline | hold |
| kw_f0007_range_game_flow | +20% vs baseline | warn |
| bb_f0007_range_no_retreat | +20% vs baseline | warn |
| bb_240_259 | +20% vs baseline | warn |
| wt_game_flow | +50% vs baseline | warn |

---

## Re-exploration Prevention

### search_history.json

```json
{
  "entries": [
    {
      "parameter": "attack_suppress_penalty",
      "value": -20.0,
      "result": "reject",
      "stage": "30g",
      "date": "2026-06-20",
      "anomalies_per_game": 5.17,
      "reason": "Worse than baseline"
    }
  ]
}
```

Rules:
- Rejected candidates: do not re-explore unless stable baseline changes
- Held candidates: may re-explore after 2+ stable baseline changes
- Accepted candidates: become part of stable baseline

---

## Human Checkpoints

| Step | Automated | Human |
|------|-----------|-------|
| Grid search execution | Yes | No |
| 30g→50g promotion decision | Suggested | Approved |
| 50g→200g promotion decision | Suggested | Approved |
| Accept/hold/reject decision | Suggested | Approved |
| weights.json update | No | Yes |
| PR creation | Metadata generated | Created by human or approved |
| PR merge | No | Yes |
| submission.tar.gz update | No | Yes |
| Tag creation | No | Yes |

---

## Report Output Format

Each stage produces:
- `reports/auto_tune_{parameter}_{value}_{stage}.json` — machine-readable
- `reports/auto_tune_{parameter}_{value}_{stage}.md` — human-readable

Final summary:
- `reports/auto_tune_run_{date}_summary.json`
- `reports/auto_tune_run_{date}_summary.md`

---

## Implementation PR Sequence

| PR | Scope | Depends on |
|----|-------|------------|
| **PR A** | `tools/search_history.py` + `reports/search_history.json` | None |
| **PR B** | `tools/promotion_gate.py` (30g→50g / 50g→200g logic) | PR A |
| **PR C** | `tools/auto_tune.py` (single-variable staged pipeline) | PR A, B |
| **PR D** | Update `experiments/weight_search.py` defaults to match current stable | None |
| **PR E** | First real search run: `advantage_weight` sweep | PR C, D |
| **PR F** | Second search run: `energy_to_plan_bonus` sweep | PR E |

## Recommended First Implementation PR

**PR A: `tools/search_history.py` + `reports/search_history.json`**

Reason:
- Smallest scope, no dependencies
- Prevents future duplicate exploration
- Can backfill existing results (retreat_bonus, attack_suppress)
- Useful immediately even without the full pipeline
