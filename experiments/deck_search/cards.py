"""
Card pool definitions for deck search.

Loads the full card catalog from artifacts/all_cards.json (dumped from
cg.api.all_card_data). Provides typed accessors and classification helpers.

Not tied to any specific deck archetype — designed to support
exploration across the full card pool.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
_CARDS_PATH = os.path.join(_REPO, "artifacts", "all_cards.json")
_ATTACKS_PATH = os.path.join(_REPO, "artifacts", "all_attacks.json")


@dataclass
class CardInfo:
    id: int
    name: str
    is_basic: bool = False
    is_stage1: bool = False
    is_stage2: bool = False
    is_ex: bool = False
    is_mega_ex: bool = False
    is_ace_spec: bool = False
    hp: int = 0
    retreat_cost: int = 0

    @property
    def is_pokemon(self) -> bool:
        return self.is_basic or self.is_stage1 or self.is_stage2

    @property
    def is_energy(self) -> bool:
        return 1 <= self.id <= 20

    @property
    def is_trainer(self) -> bool:
        return self.id >= 1000

    @property
    def category(self) -> str:
        if self.is_pokemon:
            return "pokemon"
        if self.is_energy:
            return "energy"
        if self.is_trainer:
            return "trainer"
        return "unknown"

    @property
    def max_copies(self) -> int:
        if self.is_energy and self.id <= 11:
            return 60
        if self.is_ace_spec:
            return 1
        return 4


def _load_cards() -> Dict[int, CardInfo]:
    if not os.path.exists(_CARDS_PATH):
        raise FileNotFoundError(
            f"{_CARDS_PATH} not found. Run dump_cards via WSL first."
        )
    with open(_CARDS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    cards = {}
    for r in raw:
        cid = r["id"]
        cards[cid] = CardInfo(
            id=cid, name=r.get("name", ""),
            is_basic=r.get("basic", False),
            is_stage1=r.get("stage1", False),
            is_stage2=r.get("stage2", False),
            is_ex=r.get("ex", False),
            is_mega_ex=r.get("megaEx", False),
            is_ace_spec=r.get("aceSpec", False),
            hp=r.get("hp", 0),
            retreat_cost=r.get("retreatCost", 0),
        )
    return cards


_CARD_DB: Optional[Dict[int, CardInfo]] = None


def card_db() -> Dict[int, CardInfo]:
    global _CARD_DB
    if _CARD_DB is None:
        _CARD_DB = _load_cards()
    return _CARD_DB


def get_card(card_id: int) -> Optional[CardInfo]:
    return card_db().get(card_id)


def all_pokemon() -> List[CardInfo]:
    return [c for c in card_db().values() if c.is_pokemon]


def all_basic_pokemon() -> List[CardInfo]:
    return [c for c in card_db().values() if c.is_basic]


def all_trainers() -> List[CardInfo]:
    return [c for c in card_db().values() if c.is_trainer]


def all_energies() -> List[CardInfo]:
    return [c for c in card_db().values() if c.is_energy]


def all_ace_specs() -> List[CardInfo]:
    return [c for c in card_db().values() if c.is_ace_spec]


BASIC_ENERGY_IDS = list(range(1, 12))
