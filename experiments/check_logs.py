"""Quick log analysis: Poffin / bench / Lillie / Voltorb damage."""
import json
import glob
import os
from collections import Counter, defaultdict

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
files = sorted(glob.glob(os.path.join(LOG_DIR, "game_g00*.jsonl")))

NAMES = {"265": "Voltorb", "268": "Tadbulb", "270": "Wattrel", "271": "Kilowattrel", "269": "Bellibolt"}

poffin_reasons = Counter()
ctx2_cids      = Counter()
ctx5_cids      = Counter()
lillie_reasons = Counter()
voltorb_dmgs   = []

# ctx5 diversity tracking: list of frozensets of (cid, cid) per multi-select event
ctx5_pairs = []
_ctx5_buf  = defaultdict(list)  # game_id -> list of (game_turn, cid)

for fpath in files:
    with open(fpath, encoding="utf-8") as f:
        entries = [json.loads(ln) for ln in f if ln.strip()]

    prev_ctx5_turn = -99
    prev_ctx5_cids = []

    for e in entries:
        if e.get("event") == "game_end":
            continue

        sel_ctx  = e.get("select_context")
        opt_type = e.get("select_type")
        cid      = str(e.get("resolved_card_id") or "")
        reason   = str(e.get("reason") or "")
        gturn    = e.get("game_turn", 0)

        # 1. Poffin PLAY
        if opt_type == 7 and cid == "1086":
            poffin_reasons[reason] += 1

        # 2. ctx=2 SetupBench
        if sel_ctx == 2 and cid in ("265", "268", "270"):
            ctx2_cids[cid] += 1

        # 3. ctx=5 ToBench — also track consecutive pairs for diversity
        if sel_ctx == 5 and cid in ("265", "268", "270"):
            ctx5_cids[cid] += 1
            if gturn == prev_ctx5_turn:
                prev_ctx5_cids.append(cid)
            else:
                if len(prev_ctx5_cids) >= 2:
                    ctx5_pairs.append(tuple(sorted(prev_ctx5_cids[:2])))
                prev_ctx5_turn = gturn
                prev_ctx5_cids = [cid]
    if len(prev_ctx5_cids) >= 2:
        ctx5_pairs.append(tuple(sorted(prev_ctx5_cids[:2])))

        # 4. Lillie play
        if opt_type == 7 and cid == "1227":
            lillie_reasons[reason] += 1

        # 5. Voltorb damage from deck_log
        dl = e.get("deck_log") or {}
        dmg = (dl.get("voltorb") or {}).get("estimated_voltorb_damage")
        if dmg is not None:
            voltorb_dmgs.append(int(dmg))


def sep(title):
    print(f"\n{'='*56}")
    print(f"  {title}")
    print(f"{'='*56}")


sep("1. Poffin PLAY reasons (top 10)")
for r, c in poffin_reasons.most_common(10):
    print(f"  {c:4d}  {r}")
if not poffin_reasons:
    print("  (none)")

sep("2. ctx=2 SetupBench -- Iono's basics")
for cid, cnt in sorted(ctx2_cids.items(), key=lambda x: -x[1]):
    print(f"  {NAMES.get(cid, cid):<12} ({cid}): {cnt:4d}")
if not ctx2_cids:
    print("  (none)")

sep("3. ctx=5 ToBench -- Iono's basics")
for cid, cnt in sorted(ctx5_cids.items(), key=lambda x: -x[1]):
    print(f"  {NAMES.get(cid, cid):<12} ({cid}): {cnt:4d}")

sep("3b. ctx=5 ToBench -- pair diversity (same-name vs mixed)")
pair_ctr = Counter(ctx5_pairs)
same, mixed = 0, 0
for pair, cnt in pair_ctr.most_common(15):
    tag = "SAME" if pair[0] == pair[1] else "mix "
    n0, n1 = NAMES.get(pair[0], pair[0]), NAMES.get(pair[1], pair[1])
    print(f"  {cnt:4d}  {tag}  {n0} + {n1}")
    if pair[0] == pair[1]:
        same += cnt
    else:
        mixed += cnt
total_pairs = same + mixed
if total_pairs:
    print(f"  --- same-name: {same} ({same/total_pairs*100:.0f}%)  mixed: {mixed} ({mixed/total_pairs*100:.0f}%)")

sep("4. Lillie reasons (top 5)")
for r, c in lillie_reasons.most_common(5):
    print(f"  {c:4d}  {r}")
if not lillie_reasons:
    print("  (none)")

sep("5. Voltorb estimated_damage distribution")
if voltorb_dmgs:
    dmg_cnt = Counter(voltorb_dmgs)
    for dmg in sorted(dmg_cnt):
        bar = "#" * min(dmg_cnt[dmg] // 2, 50)
        print(f"  {dmg:4d}: {bar:<50}  ({dmg_cnt[dmg]})")
    avg = sum(voltorb_dmgs) / len(voltorb_dmgs)
    print(f"  avg={avg:.1f}  n={len(voltorb_dmgs)}")
else:
    print("  (no voltorb damage data in deck_log)")
