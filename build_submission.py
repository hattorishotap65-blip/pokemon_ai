"""Build submission.tar.gz

Submission agent: raging_bolt (Raging Bolt ex + Teal Mask Ogerpon ex),
adopted 2026-07 from experiments/agents/raging_bolt/main.py. Self-contained
single-file agent + params.json + deck.csv; no agent/ package needed.
"""
import tarfile, os, sys

files = [
    ('main.py',      'main.py'),
    ('deck.csv',     'deck.csv'),
    ('params.json',  'params.json'),
]

with tarfile.open('submission.tar.gz', 'w:gz') as tar:
    for local, arc in files:
        if os.path.exists(local):
            tar.add(local, arcname=arc)
            sys.stdout.write('  + ' + arc + '\n')
        else:
            sys.stdout.write('  MISSING: ' + local + '\n')
    tar.add('reference/extracted/cg', arcname='cg')
    sys.stdout.write('  + cg/\n')

sz = os.path.getsize('submission.tar.gz') // 1024
sys.stdout.write('Done -- ' + str(sz) + ' KB\n')
