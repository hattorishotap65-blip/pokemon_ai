"""Shared deck registry for web sandbox and evaluation tools.

Provides a single source of truth for deck name -> (display_name, agent_dir)
and resolution of actual paths.

'my_deck' is a special entry pointing to the project root deck.csv / main.py.
"""
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))

# path value: relative to root (for agents/) or starts with "/" for absolute-style
# Special: "@@PROJECT_ROOT" resolves to the project root directory
DECKS = {
    'my_deck':        ('自分のデッキ (project root)', '@@PROJECT_ROOT'),
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


def resolve_deck_dir(name, root=None):
    """Return absolute path to a deck agent dir, or None if not found."""
    if name not in DECKS:
        return None
    if root is None:
        root = _SCRIPT_DIR
    path_spec = DECKS[name][1]
    if path_spec == '@@PROJECT_ROOT':
        d = _PROJECT_ROOT
    else:
        d = os.path.join(root, path_spec)
    if os.path.isdir(d) and os.path.exists(os.path.join(d, 'deck.csv')):
        return d
    return None


def available_decks(root=None):
    """Return list of deck names whose agent dirs exist."""
    return [k for k in DECKS if resolve_deck_dir(k, root) is not None]


def deck_csv_path(name, root=None):
    """Return path to deck.csv for a given deck name, or None."""
    d = resolve_deck_dir(name, root)
    if d is None:
        return None
    return os.path.join(d, 'deck.csv')


def agent_main_path(name, root=None):
    """Return path to main.py for a given deck name, or None."""
    d = resolve_deck_dir(name, root)
    if d is None:
        return None
    return os.path.join(d, 'main.py')
