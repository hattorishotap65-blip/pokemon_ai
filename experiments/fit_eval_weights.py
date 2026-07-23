"""
PRML ch.3-inspired weight fitting: ridge regression (closed-form, MAP
estimate under a Gaussian prior on weights = Bayesian linear regression)
mapping board features -> game outcome, fit from data collected by
collect_eval_training_data.py.

Ridge closed form: w = (X^T X + lambda*I)^-1 X^T y
Features are standardized before fitting (for numerical stability / a
consistent regularization scale across features with very different
magnitudes, e.g. se_hand_card in [0,8] vs se_can_ko in {0,1}), then
coefficients are rescaled back to raw-feature units so they can be dropped
straight into params.json (score = sum(raw_feature_i * weight_i), matching
_eval_search_state's convention).

Usage (inside WSL, no external deps beyond numpy):
  python3 experiments/fit_eval_weights.py \
      --input /tmp/ch3_data/mirror.jsonl /tmp/ch3_data/lucario.jsonl \
      --output experiments/agents/raging_bolt/params_fitted.json \
      --lam 5.0
"""
from __future__ import annotations
import argparse
import json
import sys

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy required (pip install numpy)"); sys.exit(1)

FEATURE_ORDER = [
    "se_prize_taken", "se_prize_given", "se_closing", "se_opp_closing",
    "se_field_energy", "se_bolt_ready", "se_can_ko", "se_bench_bolt_ready",
    "se_active_dies_prize", "se_active_dies_energy", "se_no_backup",
    "se_disabled", "se_dot", "se_opp_damage", "se_my_damage",
    "se_bench_damage", "se_bench_ko_risk", "se_hand_card",
    "se_refuel_resource", "se_ogerpon", "se_board_pokemon", "se_opp_energy",
]

# Current hand-tuned weights (_eval_search_state._EVAL_FEATURE_WEIGHTS),
# duplicated here so the report can show fitted-vs-hand-tuned side by side.
HAND_TUNED = {
    "se_prize_taken": 900, "se_prize_given": -800, "se_closing": 300,
    "se_opp_closing": -400, "se_field_energy": 60, "se_bolt_ready": 350,
    "se_can_ko": 400, "se_bench_bolt_ready": 250,
    "se_active_dies_prize": -350, "se_active_dies_energy": -40,
    "se_no_backup": -200, "se_disabled": -150, "se_dot": -60,
    "se_opp_damage": 2.0, "se_my_damage": -1.0, "se_bench_damage": -0.6,
    "se_bench_ko_risk": -120, "se_hand_card": 40, "se_refuel_resource": 50,
    "se_ogerpon": 120, "se_board_pokemon": 30, "se_opp_energy": -25,
}


def load_rows(paths):
    X, y = [], []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                X.append([row["x"].get(k, 0.0) for k in FEATURE_ORDER])
                y.append(row["y"])
    return np.array(X, dtype=float), np.array(y, dtype=float)


def ridge_fit(X, y, lam):
    """Standardize -> ridge closed form -> rescale to raw-feature units."""
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma < 1e-9] = 1.0  # constant features (e.g. never observed) -> no-op
    Xs = (X - mu) / sigma

    n, d = Xs.shape
    A = Xs.T @ Xs + lam * np.eye(d)
    b = Xs.T @ (y - y.mean())
    w_std = np.linalg.solve(A, b)

    # rescale: score = sum(w_std_i * (x_i - mu_i)/sigma_i) = sum((w_std_i/sigma_i) * x_i) + const
    w_raw = w_std / sigma
    return w_raw


def scale_to_hand_tuned_magnitude(w_raw, keys):
    """Ridge weights come out in arbitrary overall scale (since y in [0,1]
    while hand-tuned weights are in the hundreds). Rescale the whole vector
    by a single constant so its norm matches the hand-tuned vector's norm --
    preserves the *relative* importance the regression learned while making
    the result usable as drop-in params.json values at a comparable scale."""
    hand_vec = np.array([HAND_TUNED[k] for k in keys])
    hand_norm = np.linalg.norm(hand_vec)
    fit_norm = np.linalg.norm(w_raw)
    if fit_norm < 1e-9:
        return w_raw
    return w_raw * (hand_norm / fit_norm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--lam", type=float, default=5.0, help="L2 regularization strength")
    args = ap.parse_args()

    X, y = load_rows(args.input)
    print(f"Loaded {len(y)} rows ({int(y.sum())} from wins, {int(len(y)-y.sum())} from losses)")
    if len(y) < 50:
        print("WARNING: very few rows -- fit will be noisy.")

    w_raw = ridge_fit(X, y, args.lam)
    w_scaled = scale_to_hand_tuned_magnitude(w_raw, FEATURE_ORDER)

    fitted = {k: round(float(v), 2) for k, v in zip(FEATURE_ORDER, w_scaled)}

    print("\n%-24s %12s %12s" % ("feature", "hand-tuned", "fitted"))
    for k in FEATURE_ORDER:
        print("%-24s %12.1f %12.2f" % (k, HAND_TUNED[k], fitted[k]))

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(fitted, f, indent=1)
    print(f"\nFitted weights written to {args.output}")
    print("Merge these se_* keys into a candidate params.json and benchmark "
          "via the standard mirror(100g) + Lucario(100g) protocol before committing.")


if __name__ == "__main__":
    main()
