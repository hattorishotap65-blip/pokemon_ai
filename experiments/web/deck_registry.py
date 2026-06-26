"""Shared deck registry for web sandbox and evaluation tools.

Provides a single source of truth for deck name -> (display_name, agent_dir)
and resolution of actual paths.
"""
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DECKS = {
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
    d = os.path.join(root, DECKS[name][1])
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
