"""
Analyze g0200+ logs for Bellibolt attack behavior.
Checks:
  - How often Bellibolt (269) attacks when it has >= 4 energy
  - How often END is chosen when Bellibolt active + attack available
  - How often RETREAT is chosen when Bellibolt active + attack available
  - turn_rule_score on selected actions (should be +150 for attacks, -1000 for bad end/retreat)
"""
import json, os, glob, sys

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files = sorted(glob.glob(os.path.join(log_dir, 'game_g02*.jsonl')))
print(f"Log files: {len(files)} (g0200-g0249 range)")

bellibolt_attack = 0
bellibolt_end_with_atk = 0
bellibolt_retreat_with_atk = 0
bellibolt_turns_with_attack_avail = 0
total_turns = 0

# Detail log for suspicious cases
suspicious = []

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

            ss = rec.get('state_summary', {})
            active_cid    = str(ss.get('active_card_id', '') or '')
            active_energy = ss.get('active_energy', 0)

            cands = rec.get('top_candidates', [])
            has_attack = any(c.get('is_attack') for c in cands)
            sel = next((c for c in cands if c.get('selected')), None)
            if sel is None:
                continue

            if active_cid == '269' and has_attack:
                bellibolt_turns_with_attack_avail += 1

            if active_cid == '269' and sel.get('is_attack'):
                bellibolt_attack += 1

            if active_cid == '269' and active_energy >= 4 and has_attack:
                if sel.get('is_end'):
                    bellibolt_end_with_atk += 1
                    suspicious.append({
                        'game': gid,
                        'type': 'END_while_bellibolt_can_attack',
                        'energy': active_energy,
                        'turn_rule_score': sel.get('turn_rule_score'),
                        'rule_reason': sel.get('rule_reason'),
                        'reason': sel.get('reason'),
                        'final_score': sel.get('final_score'),
                    })
                elif sel.get('is_retreat'):
                    bellibolt_retreat_with_atk += 1
                    suspicious.append({
                        'game': gid,
                        'type': 'RETREAT_while_bellibolt_can_attack',
                        'energy': active_energy,
                        'turn_rule_score': sel.get('turn_rule_score'),
                        'rule_reason': sel.get('rule_reason'),
                        'reason': sel.get('reason'),
                        'final_score': sel.get('final_score'),
                    })

print(f"\nTotal turns analyzed : {total_turns}")
print(f"Bellibolt active + attack available : {bellibolt_turns_with_attack_avail}")
print(f"Bellibolt attacked  : {bellibolt_attack}")
print(f"END while Bellibolt (>=4 energy) + attack avail : {bellibolt_end_with_atk}")
print(f"RETREAT while Bellibolt (>=4 energy) + attack avail : {bellibolt_retreat_with_atk}")

if suspicious:
    print(f"\n--- Suspicious cases ({len(suspicious)}) ---")
    for s in suspicious[:10]:
        print(f"  {s['game']}  {s['type']}  energy={s['energy']}")
        print(f"    reason={s['reason']}  final_score={s['final_score']}")
        print(f"    turn_rule_score={s['turn_rule_score']}  rule_reason={s['rule_reason']}")
else:
    print("\nNo suspicious cases found.")

# Also show turn_rule score distribution for selected actions
print("\n--- turn_rule_score on selected actions (all) ---")
from collections import Counter
tr_scores = Counter()
for f2 in files:
    with open(f2) as fh2:
        for line2 in fh2:
            try:
                rec2 = json.loads(line2)
            except Exception:
                continue
            if 'game_id' not in rec2:
                continue
            sel2 = next((c for c in rec2.get('top_candidates', []) if c.get('selected')), None)
            if sel2:
                ts = sel2.get('turn_rule_score', 0.0)
                tr_scores[ts] += 1

for score, cnt in sorted(tr_scores.items(), key=lambda x: -x[1]):
    label = {150.0: "attack", -1000.0: "bad end/retreat", 0.0: "no rule", 10.0: "attach(no atk)", 15.0: "ability(no atk)", 5.0: "ability(w/atk)"}.get(score, str(score))
    print(f"  turn_rule_score={score:8.1f}  ({label:25s})  count={cnt}")
