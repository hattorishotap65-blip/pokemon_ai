"""Corrected log analysis: Poffin / bench diversity / Lillie / Voltorb."""
import json
import glob
import os
from collections import Counter

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
files   = sorted(glob.glob(os.path.join(LOG_DIR, "game_g00*.jsonl")))

NAMES = {"265": "Voltorb", "268": "Tadbulb", "270": "Wattrel",
         "271": "Kilowattrel", "269": "Bellibolt"}

poffin_play_reasons  = Counter()  # ctx=0 play action
poffin_bench_reasons = Counter()  # ctx=5 bench fetch after poffin
lillie_reasons       = Counter()
ctx2_cids            = Counter()
ctx5_cids            = Counter()
voltorb_dmgs         = []

# ctx5 pair diversity tracking
ctx5_pairs    = []
_prev_turn    = -999
_prev_fpath   = ""
_prev_ctx5    = []

for fpath in files:
    for e in (json.loads(ln) for ln in open(fpath, encoding="utf-8") if ln.strip()):
        if e.get("event") == "game_end":
            continue

        sel_ctx  = e.get("select_context")
        sel_type = e.get("select_type")
        cid      = str(e.get("resolved_card_id") or "")
        reason   = str(e.get("reason") or "")
        gturn    = e.get("game_turn", 0)

        # --- Poffin: play (select_context=0) vs bench-fetch (select_context=5) ---
        if cid == "1086":
            if sel_ctx == 0:
                poffin_play_reasons[reason] += 1
            else:
                poffin_play_reasons[f"ctx{sel_ctx}|{reason}"] += 1

        # --- ctx=2 SetupBench ---
        if sel_ctx == 2 and cid in ("265", "268", "270"):
            ctx2_cids[cid] += 1

        # --- ctx=5 ToBench ---
        if sel_ctx == 5 and cid in ("265", "268", "270"):
            ctx5_cids[cid] += 1
            key = (fpath, gturn)
            if key == (_prev_fpath, _prev_turn):
                _prev_ctx5.append(cid)
            else:
                if len(_prev_ctx5) >= 2:
                    ctx5_pairs.append(tuple(sorted(_prev_ctx5[:2])))
                _prev_fpath, _prev_turn, _prev_ctx5 = fpath, gturn, [cid]
        # --- Lillie ---
        if cid == "1227":
            lillie_reasons[reason] += 1

        # --- Voltorb damage ---
        dl  = e.get("deck_log") or {}
        dmg = (dl.get("voltorb") or {}).get("estimated_voltorb_damage")
        if dmg is not None:
            voltorb_dmgs.append(int(dmg))

    # flush last ctx5 group per file
    if len(_prev_ctx5) >= 2:
        ctx5_pairs.append(tuple(sorted(_prev_ctx5[:2])))
        _prev_ctx5 = []


def bar(n, total):
    w = int(n / max(total, 1) * 40)
    return "#" * w

def sep(t):
    print(f"\n{'='*58}\n  {t}\n{'='*58}")


sep("1. Poffin PLAY reasons  (resolved_card_id=1086, ctx=0)")
for r, c in poffin_play_reasons.most_common(12):
    print(f"  {c:4d}  {r}")
if not poffin_play_reasons:
    print("  (none)")

sep("2. ctx=2 SetupBench -- Iono's basics placed")
for cid, cnt in sorted(ctx2_cids.items(), key=lambda x: -x[1]):
    print(f"  {NAMES.get(cid,'?'):<12} ({cid}): {cnt:4d}")
if not ctx2_cids:
    print("  (none)")

sep("3. ctx=5 ToBench -- Iono's basics frequency")
for cid, cnt in sorted(ctx5_cids.items(), key=lambda x: -x[1]):
    print(f"  {NAMES.get(cid,'?'):<12} ({cid}): {cnt:4d}")

sep("3b. ctx=5 ToBench pair diversity")
pair_ctr  = Counter(ctx5_pairs)
same_cnt  = sum(v for p, v in pair_ctr.items() if p[0] == p[1])
mixed_cnt = sum(v for p, v in pair_ctr.items() if p[0] != p[1])
total_p   = same_cnt + mixed_cnt
for pair, cnt in pair_ctr.most_common(12):
    tag = "SAME" if pair[0] == pair[1] else "mix "
    n0, n1 = NAMES.get(pair[0], pair[0]), NAMES.get(pair[1], pair[1])
    print(f"  {cnt:4d}  [{tag}]  {n0} + {n1}")
if total_p:
    print(f"\n  same-name pairs : {same_cnt:3d} ({same_cnt/total_p*100:.0f}%)")
    print(f"  diverse pairs   : {mixed_cnt:3d} ({mixed_cnt/total_p*100:.0f}%)")

sep("4. Lillie reasons  (resolved_card_id=1227)")
for r, c in lillie_reasons.most_common(8):
    print(f"  {c:4d}  {r}")
if not lillie_reasons:
    print("  (none)")

sep("5. Voltorb estimated_damage distribution")
if voltorb_dmgs:
    dmg_ctr = Counter(voltorb_dmgs)
    total_v = len(voltorb_dmgs)
    for dmg in sorted(dmg_ctr):
        b = bar(dmg_ctr[dmg], total_v)
        print(f"  {dmg:4d}: {b:<42} ({dmg_ctr[dmg]})")
    avg = sum(voltorb_dmgs) / total_v
    print(f"\n  avg={avg:.1f}  n={total_v}")
else:
    print("  (no data found)")
