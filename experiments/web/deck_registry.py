"""Shared deck registry for web sandbox and evaluation tools.

Provides a single source of truth for deck name -> (display_name, agent_dir)
and resolution of actual paths.

'my_deck' is a special entry pointing to the project root deck.csv / main.py.
"""
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))

# Each entry: (display_name, deck_spec)
# deck_spec types:
#   "agents/<name>"           - agents/ subdir with deck.csv + main.py
#   "@@PROJECT_ROOT"          - project root deck.csv + main.py
#   {"deck": <path>, "agent": <path>}  - explicit paths relative to project root
DECKS = {
    'my_deck':        ('自分のデッキ (Lucario)', '@@PROJECT_ROOT'),
    'raging_bolt':    ('タケルライコex + オーガポンex', {
        'deck': 'experiments/decks/raging_bolt_ogerpon.csv',
        'agent': 'main.py',
    }),
    'dragapult':      ('Dragapult ex ドラパルト', 'agents/dragapult'),
    'megastarmie':    ('Mega Starmie ex + Cinderace', 'agents/megastarmie'),
    'megastarmie_v2': ('Mega Starmie v2', 'agents/megastarmie_v2'),
    'alakazam':       ('Alakazam フーディン', 'agents/alakazam'),
    'trevenant':      ("Hop's Trevenant オーロット", 'agents/trevenant'),
    'lucario_v3':     ('Mega Lucario ex ルカリオ', 'agents/lucario_v3'),
    'chandelure':     ('Chandelure シャンデラ', 'agents/chandelure'),
    'froslass':       ('Mega Froslass ex ユキメノコ', 'agents/froslass'),
    'mewtwo':         ("Team Rocket's Mewtwo ex ミュウツー", 'agents/mewtwo'),
}


def _resolve_spec(name, root=None):
    """Return (deck_csv_path, agent_main_path) or (None, None)."""
    if name not in DECKS:
        return None, None
    if root is None:
        root = _SCRIPT_DIR
    spec = DECKS[name][1]

    if spec == '@@PROJECT_ROOT':
        dc = os.path.join(_PROJECT_ROOT, 'deck.csv')
        ag = os.path.join(_PROJECT_ROOT, 'main.py')
        if os.path.exists(dc):
            return dc, ag if os.path.exists(ag) else None
        return None, None

    if isinstance(spec, dict):
        dc = os.path.join(_PROJECT_ROOT, spec['deck'])
        ag = os.path.join(_PROJECT_ROOT, spec['agent'])
        if os.path.exists(dc):
            return dc, ag if os.path.exists(ag) else None
        return None, None

    # agents/<name> style
    d = os.path.join(root, spec)
    dc = os.path.join(d, 'deck.csv')
    ag = os.path.join(d, 'main.py')
    if os.path.isdir(d) and os.path.exists(dc):
        return dc, ag if os.path.exists(ag) else None
    return None, None


def resolve_deck_dir(name, root=None):
    """Return absolute path to a deck agent dir, or None if not found.

    For dict-spec entries (split deck/agent), returns the agent's directory.
    """
    if name not in DECKS:
        return None
    spec = DECKS[name][1]
    if isinstance(spec, dict):
        ag = os.path.join(_PROJECT_ROOT, spec['agent'])
        dc = os.path.join(_PROJECT_ROOT, spec['deck'])
        if os.path.exists(dc):
            return os.path.dirname(ag)
        return None
    dc, _ = _resolve_spec(name, root)
    if dc is None:
        return None
    return os.path.dirname(dc)


def available_decks(root=None):
    """Return list of deck names whose deck files exist."""
    return [k for k in DECKS if _resolve_spec(k, root)[0] is not None]


def deck_csv_path(name, root=None):
    """Return path to deck.csv for a given deck name, or None."""
    dc, _ = _resolve_spec(name, root)
    return dc


def agent_main_path(name, root=None):
    """Return path to main.py for a given deck name, or None."""
    _, ag = _resolve_spec(name, root)
    return ag
