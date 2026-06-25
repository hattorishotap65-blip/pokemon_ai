"""
Learning log schema definition and validation.

Each log entry represents one decision point where a human player
chose an action from a set of legal actions.
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional


def validate_entry(entry: dict) -> List[str]:
    """Return a list of validation errors (empty = valid)."""
    errors = []
    if not isinstance(entry, dict):
        return ["entry is not a dict"]

    for field in ("match_id", "turn", "legal_actions", "chosen_action_id"):
        if field not in entry:
            errors.append("missing required field: %s" % field)

    actions = entry.get("legal_actions")
    if not isinstance(actions, list):
        errors.append("legal_actions is not a list")
        return errors
    if isinstance(actions, list):
        ids = set()
        for i, a in enumerate(actions):
            if not isinstance(a, dict):
                errors.append("legal_actions[%d] is not a dict" % i)
                continue
            aid = a.get("id")
            if not aid:
                errors.append("legal_actions[%d] missing id" % i)
            elif aid in ids:
                errors.append("duplicate action id: %s" % aid)
            else:
                ids.add(aid)

        chosen = entry.get("chosen_action_id")
        if chosen and ids and chosen not in ids:
            errors.append("chosen_action_id '%s' not in legal_actions" % chosen)

    return errors


def load_logs(path: str) -> List[dict]:
    """Load JSONL log file, skipping invalid entries."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            errs = validate_entry(entry)
            if errs:
                continue
            entries.append(entry)
    return entries
