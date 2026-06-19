"""
Comprehensive behavior analysis for all Pokemon in Iono's Lightning deck.
Checks g0200-g0249 logs.

Checks:
  1. Attack execution: each attacker attacks when energy requirement met
  2. END/RETREAT while attack available (should be 0 for any Pokemon)
  3. Energy attachment targets (should prioritize Iono's Pokemon)
  4. Bellibolt ability usage (should fire when Lightning in hand)
  5. Evolution timing (Tadbulb->Bellibolt, Wattrel->Kilowattrel)
  6. Setup actions (Poffin, Ultra Ball, bench placement)
  7. turn_rule_score -1000 cases (should be 0)
"""
import json, os, glob, sys
from collections import Counter, defaultdict

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files = sorted(glob.glob(os.path.join(log_dir, 'game_g02*.jsonl')))
print(f"Analyzing {len(files)} game logs (g0200-g0249)\n")

# ---- Card IDs ----
VOLTORB      = '265'
TADBULB      = '268'
BELLIBOLT    = '269'
WATTREL      = '270'
KILOWATTREL  = '271'
IONO_LINE    = {VOLTORB, TADBULB, BELLIBOLT, WATTREL, KILOWATTREL}
ATK_REQ      = {VOLTORB: 2, BELLIBOLT: 4, KILOWATTREL: 3}
LIGHTNING    = '4'

# ---- Counters ----
total_turns = 0
atk_can_atk   = Counter()   # Pokemon can attack (energy ready + attack in options)
atk_did_atk   = Counter()   # Pokemon actually attacked
end_w_atk     = Counter()   # END chosen while attack available
retreat_w_atk = Counter()   # RETREAT chosen while attack available

# Energy attachment
energy_attach_targets   = Counter()  # target cid -> count
energy_attach_non_iono  = 0

# Bellibolt ability
belli_ability_w_lightning  = 0
belli_ability_wo_lightning = 0
belli_no_ability_w_lightning = 0  # Lightning in hand but ability NOT used, turn ended

# Evolution
evolve_bellibolt  = 0
evolve_kilowattrel = 0

# Retreat/End violations (turn_rule -1000)
tr_neg1000_count = 0

# setup action reason buckets
setup_reasons = Counter()

# ---- Per-file analysis ----
suspicious_cases = []

for f in files:
    gid = os.path.basename(f).replace('game_', '').replace('.jsonl', '')
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if 'game_id' not in rec:
                continue
            total_turns += 1

            ss     = rec.get('state_summary', {})
            act_cid = str(ss.get('active_card_id', '') or '')
            act_en  = ss.get('active_energy', 0)

            cands   = rec.get('top_candidates', [])
            sel     = next((c for c in cands if c.get('selected')), None)
            if sel is None:
                continue

            has_attack = any(c.get('is_attack') for c in cands)
            is_atk_sel  = sel.get('is_attack', False)
            is_end_sel  = sel.get('is_end', False)
            is_ret_sel  = sel.get('is_retreat', False)
            opt_type    = sel.get('option_type')
            tr_score    = sel.get('turn_rule_score', 0.0)
            rule_reason = sel.get('rule_reason', '')
            reason      = sel.get('reason', '')
            sel_cid     = str(sel.get('resolved_card_id') or '')

            # Check turn_rule -1000 violations
            if tr_score <= -1000.0:
                tr_neg1000_count += 1
                suspicious_cases.append({
                    'game': gid, 'turn': rec.get('turn'),
                    'type': 'TURN_RULE_-1000_SELECTED',
                    'active': act_cid, 'energy': act_en,
                    'is_end': is_end_sel, 'is_retreat': is_ret_sel,
                    'tr_reason': sel.get('turn_rule_reason', ''),
                    'reason': reason,
                })

            # Attack readiness and execution per Pokemon
            for cid, req in ATK_REQ.items():
                if act_cid == cid and has_attack:
                    if act_en >= req:
                        atk_can_atk[cid] += 1
                        if is_atk_sel:
                            atk_did_atk[cid] += 1
                        elif is_end_sel:
                            end_w_atk[cid] += 1
                            suspicious_cases.append({
                                'game': gid, 'turn': rec.get('turn'),
                                'type': f'END_while_{cid}_can_attack',
                                'active': cid, 'energy': act_en,
                                'reason': reason, 'rule_reason': rule_reason,
                                'tr_score': tr_score,
                            })
                        elif is_ret_sel:
                            retreat_w_atk[cid] += 1
                            suspicious_cases.append({
                                'game': gid, 'turn': rec.get('turn'),
                                'type': f'RETREAT_while_{cid}_can_attack',
                                'active': cid, 'energy': act_en,
                                'reason': reason, 'rule_reason': rule_reason,
                                'tr_score': tr_score,
                            })

            # Energy attachment (opt_type=8)
            if opt_type == 8:
                t_cid = sel_cid
                # Try to get target from rule_reason
                if not t_cid:
                    t_cid = 'unknown'
                energy_attach_targets[t_cid] += 1

            # Evolution
            if opt_type == 9:
                if sel_cid == BELLIBOLT:
                    evolve_bellibolt += 1
                elif sel_cid == KILOWATTREL:
                    evolve_kilowattrel += 1

            # Collect setup reasons
            if reason and reason.startswith('ionos:'):
                setup_reasons[reason] += 1

# ---- Print results ----

print("=" * 60)
print("1. ATTACK EXECUTION (attacker active, energy ready, attack in options)")
print("=" * 60)
cid_names = {VOLTORB: "Voltorb(265)", BELLIBOLT: "Bellibolt(269)", KILOWATTREL: "Kilowattrel(271)"}
all_clean = True
for cid in [VOLTORB, BELLIBOLT, KILOWATTREL]:
    can  = atk_can_atk[cid]
    did  = atk_did_atk[cid]
    end  = end_w_atk[cid]
    ret  = retreat_w_atk[cid]
    other = can - did - end - ret
    rate = f"{did/can*100:.1f}%" if can > 0 else "N/A"
    ok   = (end == 0 and ret == 0)
    flag = "" if ok else " <-- PROBLEM"
    if not ok:
        all_clean = False
    print(f"  {cid_names[cid]:20s}  can_atk={can:4d}  attacked={did:4d}({rate})  end={end}  retreat={ret}  other={other}{flag}")

print()
print("=" * 60)
print("2. END/RETREAT WHILE ATTACK AVAILABLE (any Pokemon)")
print("=" * 60)
total_bad = sum(end_w_atk.values()) + sum(retreat_w_atk.values())
print(f"  Total bad END    : {sum(end_w_atk.values())}")
print(f"  Total bad RETREAT: {sum(retreat_w_atk.values())}")
print(f"  turn_rule -1000 selected: {tr_neg1000_count}")
if total_bad == 0 and tr_neg1000_count == 0:
    print("  [CLEAN] No violations found.")

print()
print("=" * 60)
print("3. ENERGY ATTACHMENT TARGETS (type=8, resolved_card_id)")
print("=" * 60)
# Note: for ATTACH type=8, resolved_card_id is the ENERGY card, not the target
# The target info is in rule_reason. Let's parse differently.
# Actually, let's re-analyze using the ionos_log energy_attach section
energy_target_counter = Counter()
energy_mode_counter   = Counter()
energy_bad_target = 0

for f in files:
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if 'game_id' not in rec:
                continue
            dk = rec.get('deck_log', {})
            ea = dk.get('energy_attach')
            if ea is None:
                continue
            t_cid = str(ea.get('target_card_id', '') or '')
            mode  = ea.get('scoring_mode', 'unknown')
            is_iono = ea.get('is_iono_pokemon', False)
            energy_target_counter[t_cid] += 1
            energy_mode_counter[mode] += 1
            if not is_iono:
                energy_bad_target += 1

total_attach = sum(energy_target_counter.values())
cid_label = {VOLTORB: 'Voltorb', TADBULB: 'Tadbulb', BELLIBOLT: 'Bellibolt', WATTREL: 'Wattrel', KILOWATTREL: 'Kilowattrel'}
for cid, cnt in energy_target_counter.most_common():
    name = cid_label.get(cid, f'cid={cid}')
    pct  = cnt / total_attach * 100 if total_attach else 0
    iono_flag = '' if cid in IONO_LINE else ' <-- NON-IONO!'
    print(f"  {name:14s} ({cid})  {cnt:5d}  {pct:5.1f}%{iono_flag}")
print(f"  Non-Iono attachments: {energy_bad_target}")
print(f"  Modes: {dict(energy_mode_counter)}")

print()
print("=" * 60)
print("4. BELLIBOLT ABILITY USAGE (via rule_reason in top_candidates)")
print("=" * 60)
belli_ability_fired    = 0
belli_ability_no_fire_end = 0

for f in files:
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if 'game_id' not in rec:
                continue
            cands = rec.get('top_candidates', [])
            sel   = next((c for c in cands if c.get('selected')), None)
            if sel is None:
                continue

            rule_r = sel.get('rule_reason', '')
            if 'bellibolt_ability' in rule_r:
                belli_ability_fired += 1

# Count ability option in candidates when Bellibolt is somewhere on field
belli_on_field_ability_avail = 0
belli_on_field_ability_used  = 0

for f in files:
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if 'game_id' not in rec:
                continue
            cands = rec.get('top_candidates', [])
            has_belli_ability = any(
                c.get('is_ability') and str(c.get('resolved_card_id', '')) == BELLIBOLT
                for c in cands
            )
            if has_belli_ability:
                belli_on_field_ability_avail += 1
                sel = next((c for c in cands if c.get('selected')), None)
                if sel and sel.get('is_ability') and str(sel.get('resolved_card_id', '')) == BELLIBOLT:
                    belli_on_field_ability_used += 1

print(f"  Turns Bellibolt ability was available : {belli_on_field_ability_avail}")
print(f"  Times ability was selected            : {belli_on_field_ability_used}")
rate_ab = belli_on_field_ability_used / belli_on_field_ability_avail * 100 if belli_on_field_ability_avail else 0
print(f"  Ability usage rate                    : {rate_ab:.1f}%")
print(f"  rule_reason 'bellibolt_ability*' fired: {belli_ability_fired}")
if belli_on_field_ability_avail > 0 and rate_ab < 50:
    print("  [WARN] Ability used less than 50% of available turns")

print()
print("=" * 60)
print("5. EVOLUTION COUNTS")
print("=" * 60)
print(f"  Tadbulb->Bellibolt   (EVOLVE): {evolve_bellibolt}")
print(f"  Wattrel ->Kilowattrel(EVOLVE): {evolve_kilowattrel}")

print()
print("=" * 60)
print("6. TOP IONOS RULE REASONS (action count)")
print("=" * 60)
for reason, cnt in setup_reasons.most_common(20):
    print(f"  {cnt:5d}  {reason}")

print()
print("=" * 60)
print("7. SUSPICIOUS CASES DETAIL")
print("=" * 60)
if suspicious_cases:
    for s in suspicious_cases[:15]:
        print(f"  {s}")
else:
    print("  None found.")

print(f"\nTotal turns analyzed: {total_turns}")
