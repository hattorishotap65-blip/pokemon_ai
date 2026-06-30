"""Tests for the live (in-game) disagreement review path.

server.py itself can't be imported in this environment (cg/sim.py loads a
Linux .so via ctypes), so these tests exercise classify_decision() /
build_live_review() / format_live_review() directly -- the same functions
server.py's _live_review_for() calls -- plus a small simulation of the
do_POST wiring contract (live_review attached only when a trace entry was
actually recorded, i.e. only after the human's pick).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import build_trace_entry
from experiments.web.disagreement_review_builder import (
    build_live_review, format_live_review, classify_decision,
    _RISK_PRIORITY_CATEGORIES,
)

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0


def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond:
        _f += 1


def _select_response(traced_entry):
    """Mirrors do_POST's /select wiring: live_review is only attached to the
    response when a trace entry exists, i.e. after recording the human's
    pick. Never let a classifier failure replace the real state payload."""
    payload = {"state": "ok"}
    if traced_entry is not None:
        payload["live_review"] = build_live_review(traced_entry)
    return payload


# === plain agreement, no risk: nothing to review ===
print("=== plain agreement ===")
e_agree = build_trace_entry("rb", 1, "MAIN",
    [{"i": 0, "label": "Attack", "score": 500, "type": 13}],
    ai_pick=[0], human_pick=[0])
check("plain agreement: build_live_review returns None", build_live_review(e_agree) is None)

# === disagreement in a priority risk category: shown ===
print("\n=== disagreement, priority category ===")
e_dis = build_trace_entry("rb", 7, "MAIN",
    [{"i": 0, "label": "Bellowing Thunder", "score": 3200, "type": 13, "cardId": 63},
     {"i": 1, "label": "Crispin", "score": 2500, "type": 7, "cardId": 1198}],
    ai_pick=[0], human_pick=[1],
    my_active={"id": 63, "hp": 20, "maxHp": 240, "energy": 1},
    opp_active={"id": 100, "hp": 320, "maxHp": 320, "energy": 2},
    my_prizes=4, opp_prizes=6)
e_dis.update({"turn_goal": "take_ko_now", "agent_goals": ["take_ko_now"],
              "agent_risks": ["no_next_attacker"], "risk_flags": ["no_next_attacker"]})
live = build_live_review(e_dis)
check("priority disagreement: not None", live is not None)
check("priority disagreement: show True", live is not None and live["show"] is True)
check("priority disagreement: category in priority set",
      live is not None and live["category"] in _RISK_PRIORITY_CATEGORIES)
check("priority disagreement: ai_action set", live is not None and live["ai_action"] == "Bellowing Thunder")
check("priority disagreement: human_action set", live is not None and live["human_action"] == "Crispin")
check("priority disagreement: score_gap", live is not None and live["score_gap"] == 700)
check("priority disagreement: message non-empty", live is not None and bool(live["message"]))

# === disagreement outside priority categories: not shown ===
print("\n=== disagreement, non-priority category ===")
e_dis_low = build_trace_entry("rb", 2, "MAIN",
    [{"i": 0, "label": "Ultra Ball", "score": 600, "type": 7},
     {"i": 1, "label": "Pokegear", "score": 550, "type": 7}],
    ai_pick=[0], human_pick=[1])
live_low = build_live_review(e_dis_low)
check("non-priority disagreement: either None or show False",
      live_low is None or live_low["show"] is False)

# === agreement_bad (agree, but flagged risk): still shown ===
print("\n=== agreement_bad ===")
e_bad = build_trace_entry("rb", 4, "MAIN",
    [{"i": 0, "label": "Attack", "score": 1500, "type": 13}],
    ai_pick=[0], human_pick=[0],
    my_prizes=3, opp_prizes=3)
e_bad.update({"risk_flags": ["no_next_attacker"], "agent_risks": []})
live_bad = build_live_review(e_bad)
check("agreement_bad: not None", live_bad is not None)
check("agreement_bad: show True", live_bad is not None and live_bad["show"] is True)
check("agreement_bad: category is agreement_bad_risk",
      live_bad is not None and live_bad["category"] == "agreement_bad_risk")

# === classifier never raises, even on malformed input ===
print("\n=== classifier exception safety ===")
check("None entry: no crash", build_live_review(None) is None)
empty_result = build_live_review({})
check("empty dict: no crash", empty_result is None or isinstance(empty_result, dict))
check("garbage options: no crash",
      build_live_review({"options": "not-a-list", "ai_pick": [0], "human_pick": [1],
                          "agree": False}) is None)


def _boom(*a, **kw):
    raise RuntimeError("classifier blew up")


_real_classify_decision = sys.modules["experiments.web.disagreement_review_builder"].classify_decision
sys.modules["experiments.web.disagreement_review_builder"].classify_decision = _boom
try:
    check("classify_decision raising: build_live_review still returns None (no raise)",
          build_live_review(e_dis) is None)
finally:
    sys.modules["experiments.web.disagreement_review_builder"].classify_decision = _real_classify_decision

# === /select wiring contract: live_review only appears once an entry exists ===
print("\n=== /select wiring contract ===")
resp_no_pick = _select_response(None)
check("no pick yet: no live_review key in response", "live_review" not in resp_no_pick)

resp_after_pick = _select_response(e_dis)
check("after pick: live_review key present", "live_review" in resp_after_pick)
check("after pick: state payload untouched", resp_after_pick["state"] == "ok")

print("\n%d/%d passed" % (_t - _f, _t))
if _f:
    sys.exit(1)
