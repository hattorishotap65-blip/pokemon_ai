import json
from collections import Counter

with open("reports/latest_anomaly_report.json") as f:
    data = json.load(f)

anomalies = data["anomalies"]
print(f"Total: {len(anomalies)}")

# Breakdown by confidence
conf = Counter(a["confidence"] for a in anomalies)
print(f"By confidence: {dict(conf)}")

# Breakdown by active role
active_ids = Counter(str(a.get("active_id", "")) for a in anomalies)
print(f"By active_id: {dict(active_ids.most_common(10))}")

# Show samples by confidence
for c in ["high", "medium", "low"]:
    samples = [a for a in anomalies if a["confidence"] == c][:3]
    if samples:
        print(f"\n--- confidence={c} samples ---")
        for a in samples:
            print(f"  {a['id']} game={a['game_id']} turn={a['turn']} "
                  f"active={a['active_id']} energy={a['active_energy_count']} "
                  f"actual={a['actual_action'][:40]}")
