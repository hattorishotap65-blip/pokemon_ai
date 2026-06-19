import json
with open("logs/game_g0700.jsonl") as f:
    for i, line in enumerate(f):
        if i > 3:
            break
        rec = json.loads(line)
        ss = rec.get("state_summary", {})
        print(f"turn={rec.get('turn')} ss_keys={sorted(ss.keys())}")
        dl = rec.get("deck_log", {})
        if dl:
            print(f"  deck_log_keys={sorted(dl.keys())}")
            bb = dl.get("bellibolt", {})
            vt = dl.get("voltorb", {})
            if bb: print(f"  bellibolt={bb}")
            if vt: print(f"  voltorb={vt}")
        # Check if bench info is in state_summary
        print(f"  bench_count={ss.get('bench_count')}")
        print(f"  active_card_id={ss.get('active_card_id')}")
        print(f"  active_energy={ss.get('active_energy')}")
        print()
