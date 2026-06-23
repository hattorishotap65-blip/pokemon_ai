"""Build submission.tar.gz"""
import tarfile, os, sys

files = [
    ('main.py',                    'main.py'),
    ('deck.csv',                   'deck.csv'),
    ('agent/__init__.py',          'agent/__init__.py'),
    ('agent/advantage.py',         'agent/advantage.py'),
    ('agent/card_knowledge.py',    'agent/card_knowledge.py'),
    ('agent/concept_weights.py',   'agent/concept_weights.py'),
    ('agent/ionos_rules.py',        'agent/ionos_rules.py'),
    ('agent/evaluator.py',         'agent/evaluator.py'),
    ('agent/fallback.py',          'agent/fallback.py'),
    ('agent/logger.py',            'agent/logger.py'),
    ('agent/opponent_model.py',    'agent/opponent_model.py'),
    ('agent/planner.py',           'agent/planner.py'),
    ('agent/policy.py',            'agent/policy.py'),
    ('agent/rollout.py',           'agent/rollout.py'),
    ('agent/turn_plan.py',         'agent/turn_plan.py'),
    ('agent/win_condition.py',     'agent/win_condition.py'),
    ('agent/effect_engine.py',     'agent/effect_engine.py'),
    ('agent/turn_rule_engine.py',  'agent/turn_rule_engine.py'),
    ('agent/card_metadata.py',    'agent/card_metadata.py'),
    ('agent/damage_predictor.py', 'agent/damage_predictor.py'),
    ('agent/params.py',           'agent/params.py'),
    ('data/card_knowledge.csv',    'data/card_knowledge.csv'),
    ('data/deck_profile.json',     'data/deck_profile.json'),
    ('data/card_effects_iono_lightning_recommended_en_ja.json',
     'data/card_effects_iono_lightning_recommended_en_ja.json'),
    ('data/weights.json',             'data/weights.json'),
    ('configs/params/default_params.json', 'configs/params/default_params.json'),
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
