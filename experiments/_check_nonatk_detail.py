import json, glob
from collections import Counter

ATTACKERS = {"265", "269", "271"}
count = 0
samples = []

for f in sorted(glob.glob("logs/game_g0[4-7]*.jsonl")):
    with open(f) as fh:
        # Group by game_turn
        turn_groups = {}
        for line in fh:
            rec = json.loads(line)
            ss = rec.get("state_summary", {})
            gt = ss.get("turn", 0)
            turn_groups.setdefault(gt, []).append(rec)

        for gt, recs in sorted(turn_groups.items()):
            if gt < 3:
                continue
            has_attack_in_turn = False
            has_retreat_in_turn = False
            attack_selected = False
            last_rec = recs[-1]

            for rec in recs:
                cands = rec.get("top_candidates", [])
                if any(c.get("is_attack") for c in cands):
                    has_attack_in_turn = True
                if any(c.get("is_retreat") for c in cands):
                    has_retreat_in_turn = True
                sel = next((c for c in cands if c.get("selected")), None)
                if sel and sel.get("option_class") == "attack":
                    attack_selected = True

            ss = last_rec.get("state_summary", {})
            act = str(ss.get("active_card_id", "") or "")
            bench = ss.get("bench_count", 0)

            if (act and act not in ATTACKERS
                    and not has_attack_in_turn and has_retreat_in_turn
                    and bench > 0 and not attack_selected):
                count += 1
                if len(samples) < 10:
                    import os
                    gid = os.path.basename(f).replace("game_","").replace(".jsonl","")
                    samples.append(f"{gid} gt={gt} active={act} bench={bench} "
                                   f"retreat_avail={has_retreat_in_turn}")

for s in samples:
    print(s)
print(f"\nTotal: {count}")
