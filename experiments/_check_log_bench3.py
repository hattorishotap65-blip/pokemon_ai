import json, glob, os

ATTACKERS = {"265", "269", "271"}
ATK_REQ = {"265": 2, "269": 4, "271": 3}
count = 0
cases = []

for f in sorted(glob.glob("logs/game_g07*.jsonl"))[:50]:
    with open(f) as fh:
        for line in fh:
            rec = json.loads(line)
            ss = rec.get("state_summary", {})
            act = str(ss.get("active_card_id", "") or "")
            act_en = ss.get("active_energy", 0) or 0
            dl = rec.get("deck_log", {})
            cands = rec.get("top_candidates", [])
            has_retreat = any(c.get("is_retreat") for c in cands)
            has_attack = any(c.get("is_attack") for c in cands)
            sel = next((c for c in cands if c.get("selected")), None)
            sel_class = sel.get("option_class", "") if sel else ""

            # Active can't attack (not enough energy or not an attacker)
            active_can_attack = False
            if act in ATK_REQ and act_en >= ATK_REQ[act]:
                active_can_attack = True

            if not active_can_attack and has_retreat and not has_attack:
                count += 1
                if len(cases) < 10:
                    gid = os.path.basename(f).replace("game_","").replace(".jsonl","")
                    cases.append(f"{gid} t={rec.get('turn')} active={act} en={act_en} "
                                 f"bench={ss.get('bench_count')} sel={sel_class}")

for c in cases:
    print(c)
print(f"\nTotal: {count} turns where active can't attack + retreat available + no attack option")

# Also: how often is active a non-attacker at all?
non_atk_count = 0
for f in sorted(glob.glob("logs/game_g07*.jsonl"))[:50]:
    with open(f) as fh:
        for line in fh:
            rec = json.loads(line)
            ss = rec.get("state_summary", {})
            act = str(ss.get("active_card_id", "") or "")
            if act and act not in ATTACKERS and act not in ("", "None"):
                non_atk_count += 1
print(f"Non-attacker active turns: {non_atk_count}")
