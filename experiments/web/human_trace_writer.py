"""Write human play trace entries to JSONL files.

Each entry records one human decision point:
- What options were available (with AI scores)
- What the AI recommended
- What the human chose
"""
import json
import os
import time

_TRACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "human_traces")


def _ensure_dir():
    os.makedirs(_TRACE_DIR, exist_ok=True)


def trace_path(session_id=""):
    _ensure_dir()
    if not session_id:
        session_id = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(_TRACE_DIR, "human_trace_%s.jsonl" % session_id)


def build_trace_entry(
    deck_name,
    turn,
    context,
    options,
    ai_pick,
    human_pick,
    params_path="",
):
    """Build a single trace entry dict.

    Args:
        deck_name: name of the deck being piloted
        turn: current game turn number
        context: SelectContext name string
        options: list of {i, label, score, type, cardId, attackId}
        ai_pick: list of AI-recommended option indices
        human_pick: list of human-selected option indices
        params_path: path to params.json used by the agent
    """
    return {
        "ts": time.time(),
        "deck": deck_name,
        "turn": turn,
        "context": context,
        "options": options,
        "ai_pick": ai_pick,
        "human_pick": human_pick,
        "ai_top": ai_pick[0] if ai_pick else None,
        "human_top": human_pick[0] if human_pick else None,
        "agree": _picks_agree(ai_pick, human_pick),
        "params_path": params_path,
    }


def _picks_agree(ai_pick, human_pick):
    if not ai_pick or not human_pick:
        return False
    return set(ai_pick) == set(human_pick)


def write_trace_entry(path, entry):
    """Append one trace entry to a JSONL file. Never raises."""
    try:
        _ensure_dir()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_traces(path):
    """Load all trace entries from a JSONL file."""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
