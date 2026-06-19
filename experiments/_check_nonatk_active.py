import json, glob
from collections import Counter

ATTACKERS = {"265", "269", "271"}
turn_dist = Counter()
count = 0

for f in sorted(glob.glob("logs/game_g07*.jsonl"))[:50]:
    with open(f) as fh:
        for line in fh:
            rec = json.loads(line)
            ss = rec.get("state_summary", {})
            act = str(ss.get("active_card_id", "") or "")
            gt = ss.get("turn", 0)
            cands = rec.get("top_candidates", [])
            has_retreat = any(c.get("is_retreat") for c in cands)
            has_attack = any(c.get("is_attack") for c in cands)

            if act and act not in ATTACKERS and act != "" and gt >= 1:
                turn_dist[gt] += 1
                count += 1

print(f"Non-attacker active (game_turn >= 1): {count}")
print(f"By game_turn: {dict(sorted(turn_dist.items())[:20])}")
