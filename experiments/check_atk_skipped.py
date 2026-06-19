"""
Drill-down: What action was taken instead of attacking with Voltorb/Kilowattrel?
"""
import json, os, glob
from collections import Counter

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files   = sorted(glob.glob(os.path.join(log_dir, 'game_g02*.jsonl')))

ATK_REQ  = {'265': 2, '271': 3}
NAMES    = {'265': 'Voltorb', '271': 'Kilowattrel'}

# For each attacker: what action was chosen instead of attack?
skip_reasons  = {cid: Counter() for cid in ATK_REQ}
skip_opt_type = {cid: Counter() for cid in ATK_REQ}
skip_cases    = {cid: [] for cid in ATK_REQ}

# Also track: was Bellibolt ability used instead?
bellibolt_ability_instead = {'265': 0, '271': 0}

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

            ss      = rec.get('state_summary', {})
            act_cid = str(ss.get('active_card_id', '') or '')
            act_en  = ss.get('active_energy', 0)
            turn    = rec.get('turn', 0)

            if act_cid not in ATK_REQ:
                continue
            req = ATK_REQ[act_cid]
            if act_en < req:
                continue

            cands    = rec.get('top_candidates', [])
            has_atk  = any(c.get('is_attack') for c in cands)
            if not has_atk:
                continue

            sel = next((c for c in cands if c.get('selected')), None)
            if sel is None or sel.get('is_attack'):
                continue  # attacked normally, skip

            # Did NOT attack — record what was chosen instead
            reason   = sel.get('reason', 'unknown')
            opt_type = sel.get('option_type')
            tr_score = sel.get('turn_rule_score', 0.0)
            rule_r   = sel.get('rule_reason', '')
            is_ab    = sel.get('is_ability', False)
            ab_cid   = str(sel.get('resolved_card_id') or '')

            skip_reasons[act_cid][reason] += 1
            skip_opt_type[act_cid][opt_type] += 1

            if is_ab:
                bellibolt_ability_instead[act_cid] += 1

            if len(skip_cases[act_cid]) < 10:
                skip_cases[act_cid].append({
                    'game': gid, 'turn': turn,
                    'energy': act_en,
                    'opt_type': opt_type,
                    'reason': reason,
                    'rule_reason': rule_r,
                    'tr_score': tr_score,
                    'is_ability': is_ab, 'ability_cid': ab_cid,
                    # Show top attack candidate score for comparison
                    'atk_score': next(
                        (c.get('final_score') for c in cands if c.get('is_attack')), None
                    ),
                    'sel_score': sel.get('final_score'),
                })

for cid in ['265', '271']:
    name = NAMES[cid]
    print(f"\n{'='*60}")
    print(f"{name} ({cid}) — skipped attack despite energy >= {ATK_REQ[cid]}")
    print(f"{'='*60}")
    print(f"  Total skips: {sum(skip_opt_type[cid].values())}")
    print(f"  Of which, Bellibolt ability used instead: {bellibolt_ability_instead[cid]}")
    print(f"\n  OptionType distribution:")
    OPT_NAMES = {7:'PLAY', 8:'ATTACH', 9:'EVOLVE', 10:'ABILITY', 12:'RETREAT', 13:'ATTACK', 14:'END', 0:'NUMBER', 1:'YES', 2:'NO', 3:'CARD'}
    for ot, cnt in skip_opt_type[cid].most_common():
        print(f"    type={ot} ({OPT_NAMES.get(ot,'?'):8s})  {cnt}")

    print(f"\n  Top reasons (ionos_rules / policy):")
    for r, cnt in skip_reasons[cid].most_common(10):
        print(f"    {cnt:4d}  {r}")

    print(f"\n  Sample cases (up to 10):")
    for s in skip_cases[cid]:
        print(f"    {s['game']} t={s['turn']} en={s['energy']} "
              f"opt={s['opt_type']}({OPT_NAMES.get(s['opt_type'],'?')}) "
              f"sel_score={s['sel_score']} atk_score={s['atk_score']} "
              f"ability={s['is_ability']}({s['ability_cid']}) "
              f"reason={s['reason'][:50]}")
