"""Opponent identity and availability resolution.

Classifies each opponent in the fixed local sandbox league as AVAILABLE,
PARTIAL, or UNAVAILABLE -- never fabricated, never silently substituted.

- lucario: local_only_manual. Its source (experiments/agents/
  top_lucario_1084_main.py, experiments/decks/top_lucario_1084.csv) is a
  manually-retained, gitignored, local-only pair of files with no clone/
  download path and no known recovery source. Resolved purely by checking
  those exact paths at call time -- if absent (as they currently are in this
  worktree), UNAVAILABLE, with no substitute or inferred deck ever accepted.
- dragapult, megastarmie: pinned_clone. Resolved via an entry in
  opponent_pins.json (never invented or discovered by this module -- only
  added by explicit manual edit, see clone_opponent.py). A present, well-
  formed pin is PARTIAL until clone_opponent.py actually verifies the commit
  is reachable and matches; this module never claims AVAILABLE for a
  network-dependent opponent without that verification step actually running.
- mirror: special-cased, always AVAILABLE. Requires no pin and no clone --
  it is the candidate agent/deck playing against itself. Per the task's
  explicit instruction, mirror is smoke/auxiliary use only and must never
  contribute to the primary league win-rate cells (see schema.py's
  AUXILIARY_SEGMENT_IDS / raging_bolt_eval.py's cell-emission logic).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

LOCAL_ONLY_OPPONENTS = {
    "lucario": {
        "agent_path": os.path.join("experiments", "agents", "top_lucario_1084_main.py"),
        "deck_path": os.path.join("experiments", "decks", "top_lucario_1084.csv"),
    },
}
PINNED_CLONE_OPPONENTS = ("dragapult", "megastarmie")
MIRROR_OPPONENT_ID = "mirror"

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class OpponentResolution:
    opponent_id: str
    availability: str  # AVAILABLE | PARTIAL | UNAVAILABLE
    reason: str
    requires_clone: bool
    commit_sha: str | None = None
    agent_path: str | None = None  # repo-relative, for local_only opponents only
    deck_path: str | None = None   # repo-relative, for local_only opponents only


def load_pins(pins_path: str) -> dict:
    if not os.path.isfile(pins_path):
        return {}
    with open(pins_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"opponent_pins.json at {pins_path} must be a JSON object")
    return data


def resolve_opponent(opponent_id: str, pins: dict, repo_root: str) -> OpponentResolution:
    """Resolve one opponent's availability. Never raises for an unknown or
    unavailable opponent_id -- callers get an UNAVAILABLE resolution with a
    reason string instead, so a league run can report partial coverage
    honestly rather than crashing."""
    if opponent_id == MIRROR_OPPONENT_ID:
        return OpponentResolution(
            opponent_id=opponent_id, availability=AVAILABLE,
            reason="mirror requires no pin/clone; candidate always plays itself",
            requires_clone=False,
        )

    if opponent_id in LOCAL_ONLY_OPPONENTS:
        paths = LOCAL_ONLY_OPPONENTS[opponent_id]
        agent_abs = os.path.join(repo_root, paths["agent_path"])
        deck_abs = os.path.join(repo_root, paths["deck_path"])
        agent_ok, deck_ok = os.path.isfile(agent_abs), os.path.isfile(deck_abs)
        if agent_ok and deck_ok:
            return OpponentResolution(
                opponent_id=opponent_id, availability=AVAILABLE,
                reason="local-only files present", requires_clone=False,
                agent_path=paths["agent_path"], deck_path=paths["deck_path"],
            )
        missing = [p for p, ok in ((paths["agent_path"], agent_ok), (paths["deck_path"], deck_ok)) if not ok]
        return OpponentResolution(
            opponent_id=opponent_id, availability=UNAVAILABLE,
            reason=f"local-only files absent, no known recovery path: {missing}",
            requires_clone=False,
        )

    if opponent_id in PINNED_CLONE_OPPONENTS:
        entry = pins.get(opponent_id)
        if not entry:
            return OpponentResolution(
                opponent_id=opponent_id, availability=UNAVAILABLE,
                reason="no entry in opponent_pins.json; this module never invents a commit SHA",
                requires_clone=True,
            )
        commit_sha = entry.get("commit_sha") if isinstance(entry, dict) else None
        if not commit_sha or not _COMMIT_SHA_RE.fullmatch(commit_sha):
            return OpponentResolution(
                opponent_id=opponent_id, availability=UNAVAILABLE,
                reason="opponent_pins.json entry missing a valid 40-hex commit_sha",
                requires_clone=True,
            )
        return OpponentResolution(
            opponent_id=opponent_id, availability=PARTIAL,
            reason="pinned commit recorded; AVAILABLE only confirmed after clone_opponent.py "
                   "verifies git rev-parse --verify <sha>^{commit} succeeds against a real clone",
            requires_clone=True, commit_sha=commit_sha,
        )

    return OpponentResolution(
        opponent_id=opponent_id, availability=UNAVAILABLE,
        reason=f"unknown opponent_id: {opponent_id!r} (not mirror, not local_only, not pinned_clone)",
        requires_clone=False,
    )
