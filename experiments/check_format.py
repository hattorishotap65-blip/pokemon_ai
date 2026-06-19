import json, glob
files = sorted(glob.glob('/mnt/c/Users/shclo/projects/pokemon_card_ai/logs/game_g01*.jsonl'))
for fpath in files[:5]:
    for line in open(fpath):
        e = json.loads(line.strip())
        r = e.get('reason', '')
        if 'bellibolt_ex_attack' in r or 'avoid_retreat' in r:
            print(json.dumps({k: v for k, v in e.items() if k not in ('obs', 'options', 'deck_log')}, indent=2))
            break
