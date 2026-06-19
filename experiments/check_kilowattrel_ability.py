"""
Analyze Kilowattrel ability behavior in g0300+ logs.
Verifies that score_kilowattrel_ability() is correctly suppressing ability usage
when Kilowattrel can attack.
"""
import json, os, glob
from collections import Counter

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files   = sorted(glob.glob(os.path.join(log_dir, 'game_g03*.jsonl')))
print(f"Analyzing {len(files)} game logs (g0300-g0349)\n")

KILOWATTREL = '271'
ATK_REQ     = 3

kw_ability_selected   = 0
kw_ability_avoided    = 0  # offered but not selected
kw_atk_selected       = 0

kw_score_dist = Counter()  # kilowattrel_ability_score buckets
kw_reason_dist = Counter()

# Cases where ability was offered
cases_offered = []
cases_used_despite_attack = []

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

            cands = rec.get('top_candidates', [])
            ss    = rec.get('state_summary', {})
            act_cid    = str(ss.get('active_card_id', '') or '')
            act_energy = ss.get('active_energy', 0)

            # Find Kilowattrel ability option in candidates
            kw_ab_cand = next((c for c in cands
                               if c.get('is_ability')
                               and str(c.get('resolved_card_id', '') or '') == KILOWATTREL), None)
            if kw_ab_cand is None:
                continue  # no Kilowattrel ability offered this turn

            sel = next((c for c in cands if c.get('selected')), None)
            if sel is None:
                continue

            has_attack = any(c.get('is_attack') for c in cands)
            kw_score   = kw_ab_cand.get('kilowattrel_ability_score', 0.0)
            kw_reason  = kw_ab_cand.get('kilowattrel_ability_reason', '')
            ab_selected = (sel.get('is_ability')
                           and str(sel.get('resolved_card_id', '') or '') == KILOWATTREL)

            # Score bucket
            if kw_score <= -250:
                bucket = 'score<=-250 (hard_avoid)'
            elif kw_score <= -120:
                bucket = 'score<=-120 (large_hand)'
            elif kw_score < 0:
                bucket = 'score<0 (misc)'
            elif kw_score == 0:
                bucket = 'score==0'
            else:
                bucket = 'score>0 (encouraged)'
            kw_score_dist[bucket] += 1
            kw_reason_dist[kw_reason[:60]] += 1

            if ab_selected:
                kw_ability_selected += 1
                # Was attack available when ability was used?
                if has_attack and act_cid == KILOWATTREL and act_energy >= ATK_REQ:
                    cases_used_despite_attack.append({
                        'game': gid, 'turn': rec.get('turn'),
                        'energy': act_energy, 'has_attack': has_attack,
                        'kw_score': kw_score, 'kw_reason': kw_reason,
                        'sel_reason': sel.get('reason'),
                    })
            else:
                kw_ability_avoided += 1

            if sel.get('is_attack') and act_cid == KILOWATTREL:
                kw_atk_selected += 1

            if len(cases_offered) < 5:
                cases_offered.append({
                    'game': gid, 'turn': rec.get('turn'),
                    'energy': act_energy, 'hand': ss.get('hand_count', 0),
                    'has_attack': has_attack, 'ab_selected': ab_selected,
                    'kw_score': kw_score, 'kw_reason': kw_reason[:60],
                    'sel_type': sel.get('option_type'),
                    'sel_reason': sel.get('reason', '')[:50],
                })

print("=== Kilowattrel Ability Usage ===")
total_kw_ab = kw_ability_selected + kw_ability_avoided
print(f"  Turns ability offered  : {total_kw_ab}")
print(f"  Ability selected       : {kw_ability_selected}")
print(f"  Ability avoided        : {kw_ability_avoided}")
rate = kw_ability_selected / total_kw_ab * 100 if total_kw_ab else 0
print(f"  Usage rate             : {rate:.1f}%")
print(f"  Kilowattrel attacks    : {kw_atk_selected}")

print(f"\n=== kilowattrel_ability_score distribution ===")
for bucket, cnt in sorted(kw_score_dist.items(), key=lambda x: -x[1]):
    print(f"  {cnt:4d}  {bucket}")

print(f"\n=== kilowattrel_ability_reason distribution (top 10) ===")
for reason, cnt in kw_reason_dist.most_common(10):
    print(f"  {cnt:4d}  {reason}")

print(f"\n=== Cases used despite attack available (should be 0) ===")
if cases_used_despite_attack:
    for c in cases_used_despite_attack[:5]:
        print(f"  PROBLEM: {c}")
else:
    print("  [CLEAN] None found.")

print(f"\n=== Sample offered cases ===")
for c in cases_offered:
    print(f"  {c['game']} t={c['turn']} en={c['energy']} hand={c['hand']} "
          f"has_atk={c['has_attack']} ab_sel={c['ab_selected']} "
          f"kw_score={c['kw_score']} sel_type={c['sel_type']} sel={c['sel_reason']}")
    print(f"    kw_reason: {c['kw_reason']}")
