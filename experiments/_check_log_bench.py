import json

with open("logs/game_g0700.jsonl") as f:
    for i, line in enumerate(f):
        rec = json.loads(line)
        ss = rec.get("state_summary", {})
        act = ss.get("active_card_id", "")
        dl = rec.get("deck_log", {})
        bb = dl.get("bellibolt", {})
        cands = rec.get("top_candidates", [])
        has_retreat = any(c.get("is_retreat") for c in cands)
        has_attack = any(c.get("is_attack") for c in cands)
        sel = next((c for c in cands if c.get("selected")), None)

        # Show turns where active is NOT an attacker (268=Tadbulb, 270=Wattrel)
        # and bellibolt or voltorb is on bench
        if act in ("268", "270") and bb.get("bellibolt_in_play") and not bb.get("bellibolt_is_active"):
            print(f"turn={rec.get('turn')} active={act} energy={ss.get('active_energy')} "
                  f"bench_count={ss.get('bench_count')} has_retreat={has_retreat} has_attack={has_attack} "
                  f"bellibolt_on_bench=True "
                  f"sel_class={sel.get('option_class','') if sel else ''} "
                  f"sel_reason={sel.get('reason','')[:50] if sel else ''}")
            if i > 200:
                break
