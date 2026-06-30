"""Tests for disagreement_label_analyzer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.disagreement_label_analyzer import analyze, format_report

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


def _item(review_id, category="no_next_attacker", human_action_type="PLAY",
          human_action="Crispin", ai_action="Attack"):
    return {
        "review_id": review_id, "category": category,
        "human_action_type": human_action_type,
        "human_action": human_action, "ai_action": ai_action,
    }


# === empty input ===
print("=== empty input ===")
summary = analyze([], [])
check("empty: no crash", summary["total_records"] == 0)
check("empty: total_labeled 0", summary["total_labeled"] == 0)
check("empty: recommendations list", isinstance(summary["recommendations"], list))
report = format_report(summary)
check("empty: format_report no crash", isinstance(report, str))

# === basic aggregation ===
print("\n=== basic aggregation ===")
items = [_item("r1"), _item("r2"), _item("r3", category="attack_too_early"),
         _item("r4", category="both_bad_case")]
labels = [
    {"review_id": "r1", "label": "human_better", "confidence": "high", "category": "no_next_attacker"},
    {"review_id": "r2", "label": "human_better", "confidence": "medium", "category": "no_next_attacker"},
    {"review_id": "r3", "label": "agent_better", "confidence": "low", "category": "attack_too_early"},
    {"review_id": "r4", "label": "both_bad", "confidence": "", "category": "both_bad_case"},
]
summary2 = analyze(labels, items)
check("label_counts human_better", summary2["label_counts"].get("human_better") == 2)
check("label_counts agent_better", summary2["label_counts"].get("agent_better") == 1)
check("label_counts both_bad", summary2["label_counts"].get("both_bad") == 1)
check("total_labeled", summary2["total_labeled"] == 4)
check("high_confidence_labeled", summary2["high_confidence_labeled"] == 1)
check("category_label_distribution", summary2["category_label_distribution"]["no_next_attacker"]["human_better"] == 2)
check("dominant_human_better has r1,r2", set(summary2["dominant_human_better"]) == {"r1", "r2"})
check("dominant_both_bad has r4", summary2["dominant_both_bad"] == ["r4"])

# === unclear / unlabeled handling ===
print("\n=== unlabeled ===")
labels_unlabeled = [{"review_id": "r5", "label": "", "confidence": ""}]
summary3 = analyze(labels_unlabeled, [])
check("unlabeled counted separately", summary3["label_counts"].get("unlabeled") == 1)
check("unlabeled not in total_labeled", summary3["total_labeled"] == 0)

# === invalid label doesn't crash, emits warning ===
print("\n=== invalid label ===")
warnings = []
labels_bad = [
    {"review_id": "r6", "label": "totally_invalid", "confidence": "high"},
    {"review_id": "r7", "label": "human_better", "confidence": "extreme"},
]
summary4 = analyze(labels_bad, [], warn=warnings.append)
check("invalid label: no crash", summary4["invalid_label_count"] == 1)
check("invalid confidence: no crash, recorded", summary4["invalid_confidence_count"] == 1)
check("invalid confidence: still counted as human_better", summary4["label_counts"].get("human_better") == 1)
check("warnings emitted", len(warnings) == 2)

# === recommendations require >= 2 human_better in known category ===
print("\n=== recommendations ===")
items_many = [_item("a%d" % i, category="no_next_attacker") for i in range(3)]
labels_many = [{"review_id": "a%d" % i, "label": "human_better", "confidence": "high",
                "category": "no_next_attacker"} for i in range(3)]
summary5 = analyze(labels_many, items_many)
check("recommendations: produced for repeated human_better category",
      any(r["category"] == "no_next_attacker" for r in summary5["recommendations"]))

report5 = format_report(summary5)
check("report: has candidate fixes section", "Candidate main.py / params.json Fixes" in report5)
check("report: mentions category", "no_next_attacker" in report5)

print("\n%d/%d passed" % (_t - _f, _t))
if _f:
    sys.exit(1)
