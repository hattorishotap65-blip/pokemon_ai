"""Analyze Voltorb attack behavior in g0400+ logs."""
import json, os, glob
from collections import Counter

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
files   = sorted(glob.glob(os.path.join(log_dir, 'game_g04*.jsonl')))
print(f"Analyzing {len(files)} game logs (g0400)\n")

VT='265'; BL='269'; KW='271'
ATK_REQ = {VT:2, BL:4, KW:3}

can_atk = Counter(); did_atk = Counter(); other_atk = Counter()
vt_end_w_atk = 0; vt_ret_w_atk = 0; vt_ab_w_atk = 0
vt_score_dist = Counter()
vt_skip_reasons = Counter()
belli_ab_over_voltorb_atk = 0

for f in files:
    gid = os.path.basename(f).replace('game_','').replace('.jsonl','')
    with open(f) as fh:
        for line in fh:
            try: rec = json.loads(line)
            except: continue
            if 'game_id' not in rec: continue
            ss = rec.get('state_summary',{})
            act = str(ss.get('active_card_id','') or '')
            en  = ss.get('active_energy',0)
            cands = rec.get('top_candidates',[])
            sel = next((c for c in cands if c.get('selected')),None)
            if not sel: continue
            has_atk = any(c.get('is_attack') for c in cands)
            for cid,req in ATK_REQ.items():
                if act==cid and has_atk and en>=req:
                    can_atk[cid]+=1
                    if sel.get('is_attack'): did_atk[cid]+=1
                    elif not sel.get('is_end') and not sel.get('is_retreat'):
                        other_atk[cid]+=1
            if act==VT and has_atk and en>=2:
                vs = sel.get('voltorb_attack_score',0.0)
                if vs > 0: vt_score_dist['atk_score>0']+=1
                if sel.get('is_end'): vt_end_w_atk+=1
                if sel.get('is_retreat'): vt_ret_w_atk+=1
                if sel.get('is_ability'):
                    vt_ab_w_atk+=1
                    ab_cid = str(sel.get('resolved_card_id','') or '')
                    if ab_cid == BL: belli_ab_over_voltorb_atk+=1
                if not sel.get('is_attack'):
                    reason = sel.get('reason','')[:60]
                    vt_skip_reasons[reason]+=1

print("="*60)
print("ATTACK EXECUTION (energy ready + attack in options)")
print("="*60)
names = {VT:'Voltorb(265)', BL:'Bellibolt(269)', KW:'Kilowattrel(271)'}
for cid in [VT,BL,KW]:
    c=can_atk[cid]; d=did_atk[cid]; o=other_atk[cid]
    rate = f"{d/c*100:.1f}%" if c else "N/A"
    print(f"  {names[cid]:20s}  can={c:4d}  attacked={d:4d}({rate})  other={o}")

print(f"\n{'='*60}")
print("VOLTORB: INVALID ACTIONS WHEN ATTACK AVAILABLE")
print(f"{'='*60}")
print(f"  END chosen      : {vt_end_w_atk}  [should be 0]")
print(f"  RETREAT chosen   : {vt_ret_w_atk}  [should be 0]")
print(f"  ABILITY chosen   : {vt_ab_w_atk}")
print(f"    of which Bellibolt: {belli_ab_over_voltorb_atk}")

if vt_skip_reasons:
    print(f"\n{'='*60}")
    print("VOLTORB SKIPPED ATTACK: WHY?")
    print(f"{'='*60}")
    for reason, cnt in vt_skip_reasons.most_common(10):
        print(f"  {cnt:4d}  {reason}")

# Energy attachment analysis
energy_tgt = Counter()
for f in files:
    with open(f) as fh:
        for line in fh:
            try: rec=json.loads(line)
            except: continue
            if 'game_id' not in rec: continue
            dk=rec.get('deck_log',{})
            ea=dk.get('energy_attach')
            if not ea: continue
            t=str(ea.get('target_card_id','') or '')
            energy_tgt[t]+=1

print(f"\n{'='*60}")
print("ENERGY ATTACHMENT TARGETS")
print(f"{'='*60}")
total_e = sum(energy_tgt.values())
lbl = {VT:'Voltorb',BL:'Bellibolt','268':'Tadbulb','270':'Wattrel',KW:'Kilowattrel'}
for cid,cnt in energy_tgt.most_common():
    name = lbl.get(cid, f'cid={cid}')
    print(f"  {name:14s} ({cid})  {cnt:5d}  {cnt/total_e*100:.1f}%")
