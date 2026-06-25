"""
Deck constraint definitions and validation.

Enforces cabt deck rules and configurable construction constraints.
Designed for use by candidate generators and validators.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from experiments.deck_search.cards import CardInfo, card_db, get_card


@dataclass
class DeckConstraints:
    total_cards: int = 60
    min_pokemon: int = 1
    max_pokemon: int = 30
    min_energy: int = 5
    max_energy: int = 30
    min_trainer: int = 5
    max_trainer: int = 40
    min_basic_pokemon: int = 1
    max_ace_spec: int = 1
    max_copies_non_basic_energy: int = 4
    required_evolution_base_min: int = 2


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)


def validate_deck(card_ids: List[int], constraints: DeckConstraints = None) -> ValidationResult:
    """Validate a deck against constraints. Returns errors if invalid."""
    if constraints is None:
        constraints = DeckConstraints()

    errors = []
    counts = Counter(card_ids)
    db = card_db()

    if len(card_ids) != constraints.total_cards:
        errors.append(f"total={len(card_ids)}, expected={constraints.total_cards}")

    pokemon_count = 0
    energy_count = 0
    trainer_count = 0
    basic_count = 0
    ace_spec_count = 0
    unknown_ids = []

    for cid, cnt in counts.items():
        card = db.get(cid)
        if card is None:
            unknown_ids.append(cid)
            continue

        if card.is_pokemon:
            pokemon_count += cnt
            if card.is_basic:
                basic_count += cnt
        elif card.is_energy:
            energy_count += cnt
        elif card.is_trainer:
            trainer_count += cnt

        if card.is_ace_spec:
            ace_spec_count += cnt

        if cnt > card.max_copies:
            errors.append(f"card {cid} ({card.name}): {cnt} copies, max={card.max_copies}")

    if unknown_ids:
        errors.append(f"unknown card IDs: {unknown_ids}")

    if pokemon_count < constraints.min_pokemon:
        errors.append(f"pokemon={pokemon_count}, min={constraints.min_pokemon}")
    if pokemon_count > constraints.max_pokemon:
        errors.append(f"pokemon={pokemon_count}, max={constraints.max_pokemon}")
    if energy_count < constraints.min_energy:
        errors.append(f"energy={energy_count}, min={constraints.min_energy}")
    if energy_count > constraints.max_energy:
        errors.append(f"energy={energy_count}, max={constraints.max_energy}")
    if trainer_count < constraints.min_trainer:
        errors.append(f"trainer={trainer_count}, min={constraints.min_trainer}")
    if trainer_count > constraints.max_trainer:
        errors.append(f"trainer={trainer_count}, max={constraints.max_trainer}")
    if basic_count < constraints.min_basic_pokemon:
        errors.append(f"basic_pokemon={basic_count}, min={constraints.min_basic_pokemon}")
    if ace_spec_count > constraints.max_ace_spec:
        errors.append(f"ace_spec={ace_spec_count}, max={constraints.max_ace_spec}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def deck_composition(card_ids: List[int]) -> Dict[str, int]:
    """Return category counts for a deck."""
    db = card_db()
    comp = {"pokemon": 0, "energy": 0, "trainer": 0, "basic_pokemon": 0,
            "stage1": 0, "stage2": 0, "ex": 0, "mega_ex": 0, "ace_spec": 0}
    for cid in card_ids:
        card = db.get(cid)
        if card is None:
            continue
        if card.is_pokemon:
            comp["pokemon"] += 1
            if card.is_basic:
                comp["basic_pokemon"] += 1
            if card.is_stage1:
                comp["stage1"] += 1
            if card.is_stage2:
                comp["stage2"] += 1
            if card.is_ex:
                comp["ex"] += 1
            if card.is_mega_ex:
                comp["mega_ex"] += 1
        elif card.is_energy:
            comp["energy"] += 1
        elif card.is_trainer:
            comp["trainer"] += 1
        if card.is_ace_spec:
            comp["ace_spec"] += 1
    return comp
