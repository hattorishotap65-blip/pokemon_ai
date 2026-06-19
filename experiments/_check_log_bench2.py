import json, glob, os

ATTACKERS = {"265", "269", "271"}
NON_ATTACKERS = {"268", "270"}
count = 0

for f in sorted(glob.glob("logs/game_g07*.jsonl"))[:50]:
    with open(f) as fh:
        for line in fh:
            rec = json.loads(line)
            ss = rec.get("state_summary", {})
            act = str(ss.get("active_card_id", "") or "")
            dl = rec.get("deck_log", {})
            bb = dl.get("bellibolt", {})
            cands = rec.get("top_candidates", [])
            has_retreat = any(c.get("is_retreat") for c in cands)
            has_attack = any(c.get("is_attack") for c in cands)

            # Active is non-attacker AND bench has attacker AND no attack option
            if act in NON_ATTACKERS and bb.get("bellibolt_in_play") and not bb.get("bellibolt_is_active"):
                if not has_attack and has_retreat:
                    sel = next((c for c in cands if c.get("selected")), None)
                    sel_class = sel.get("option_class", "") if sel else ""
                    count += 1
                    if count <= 10:
                        gid = os.path.basename(f).replace("game_","").replace(".jsonl","")
                        print(f"{gid} t={rec.get('turn')} active={act} en={ss.get('active_energy')} "
                              f"bench={ss.get('bench_count')} retreat_avail={has_retreat} "
                              f"sel={sel_class}")

print(f"\nTotal: {count} turns with non-attacker active + attacker on bench + no attack + retreat available")
