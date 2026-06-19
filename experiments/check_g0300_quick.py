import json, os, glob
from collections import Counter

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files = sorted(glob.glob(os.path.join(log_dir, 'game_g03*.jsonl')))
print(f'g0300 logs: {len(files)}')

KW='271'; VT='265'; BL='269'
ATK_REQ = {VT:2, BL:4, KW:3}
can_atk=Counter(); did_atk=Counter(); other_atk=Counter()
kw_ab_offered=0; kw_ab_selected=0; kw_ab_attack_avail_selected=0

for f in files:
    with open(f) as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if 'game_id' not in rec:
                continue
            ss   = rec.get('state_summary', {})
            act  = str(ss.get('active_card_id', '') or '')
            en   = ss.get('active_energy', 0)
            cands = rec.get('top_candidates', [])
            sel   = next((c for c in cands if c.get('selected')), None)
            if not sel:
                continue
            has_atk = any(c.get('is_attack') for c in cands)
            for cid, req in ATK_REQ.items():
                if act == cid and has_atk and en >= req:
                    can_atk[cid] += 1
                    if sel.get('is_attack'):
                        did_atk[cid] += 1
                    elif not sel.get('is_end') and not sel.get('is_retreat'):
                        other_atk[cid] += 1
            kw_ab = next((c for c in cands
                          if c.get('is_ability') and str(c.get('resolved_card_id','') or '') == KW), None)
            if kw_ab:
                kw_ab_offered += 1
                if sel.get('is_ability') and str(sel.get('resolved_card_id','') or '') == KW:
                    kw_ab_selected += 1
                    if has_atk and act == KW and en >= 3:
                        kw_ab_attack_avail_selected += 1

print('\n--- Attack execution (g0300) vs (g0200) ---')
prev = {VT:(230,199,31), BL:(220,220,0), KW:(72,56,16)}
for cid in [VT, BL, KW]:
    c = can_atk[cid]; d = did_atk[cid]; o = other_atk[cid]
    pc, pd, po = prev[cid]
    rate = d/c*100 if c else 0
    prate = pd/pc*100 if pc else 0
    print(f'  {cid}: can={c} attacked={d}({rate:.1f}%) other={o}  |  prev: can={pc} attacked={pd}({prate:.1f}%) other={po}')
print(f'\n--- Kilowattrel ability ---')
rate_ab = kw_ab_selected/kw_ab_offered*100 if kw_ab_offered else 0
print(f'  Offered={kw_ab_offered} Selected={kw_ab_selected} ({rate_ab:.1f}%)')
print(f'  Selected despite attack available: {kw_ab_attack_avail_selected}  [should be 0]')
