"""Statistics primitives for the eval-infra harness.

No third-party dependency (no numpy/scipy) -- matches the existing repo
convention (tools/outcome_gatekeeper.py is stdlib-only) and this repo's
absence of any numpy/scipy requirement.

Two estimation regimes, chosen for reasons tied to confirmed repository
evidence and this harness's actual per-game record granularity, not
preference (see raging_bolt_eval.py's "Metric-to-statistical-method mapping"
module-level comment / README.md for which metric uses which):

- Wilson score interval for 0/1 GAME-level rate metrics (win/error/timeout/
  illegal_action). In this harness's schema, each of these four metrics
  contributes exactly one independent binary observation per game (a game
  terminates the instant an illegal action/error/timeout occurs, so there is
  no meaningful within-game repetition for these four at this granularity).
  No seed/RNG control exists anywhere in cg.api/cg.game's Python surface, so
  baseline and candidate runs are independent, unpaired samples -- Wilson is
  a standard, well-behaved interval for binomial proportions, including near
  p=0 or p=1 (illegal_action_rate is expected to be at or near 0 for long
  stretches). Newcombe's method (see newcombe_delta) is used for the *delta*
  of two independent Wilson intervals.
- A whole-GAME cluster bootstrap specifically for DECISION-level metrics
  (decision_time_p50_ms/p95_decision_time), where a single game genuinely
  contributes multiple, correlated observations (one per decision). Decisions
  within one game are not independent of each other (they share the game's
  state and, per this repo's own measured findings, the engine's internal,
  Python-uncontrollable RNG) -- resampling at the decision level would
  understate interval width (pseudo-replication). The bootstrap therefore
  always resamples whole games, never individual decisions.

format_decimal-shaped output ({"estimate","lower","upper"} as canonical
Decimal strings, lower<=estimate<=upper) throughout, so results are directly
usable as a Gatekeeper-shaped stats triple without importing the Gatekeeper.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

from experiments.eval_infra.canon import canonicalize, format_decimal


@dataclass(frozen=True)
class IntervalStats:
    estimate: str
    lower: str
    upper: str

    def as_dict(self) -> dict:
        return {"estimate": self.estimate, "lower": self.lower, "upper": self.upper}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def wilson_interval(successes: int, n: int, confidence: str = "0.95") -> IntervalStats:
    """Wilson score interval for a single proportion successes/n."""
    if n <= 0:
        raise ValueError("wilson_interval requires n >= 1")
    if not (0 <= successes <= n):
        raise ValueError("successes must be within [0, n]")

    conf = Decimal(confidence)
    if not (Decimal("0") < conf < Decimal("1")):
        raise ValueError("confidence must be strictly between 0 and 1")
    # Two-sided z for the given confidence level via the inverse error function
    # (stdlib math.erfinv is unavailable pre-3.11 in some builds, so we use a
    # small dependency-free rational approximation good to ~1e-9 for the
    # confidence levels this harness uses, e.g. 0.90/0.95/0.99).
    z = _norm_ppf(1.0 - (1.0 - float(conf)) / 2.0)

    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    half = (z * math.sqrt((p_hat * (1 - p_hat) / n) + (z2 / (4 * n * n)))) / denom

    lower = _clamp01(center - half)
    upper = _clamp01(center + half)
    estimate = _clamp01(p_hat)
    # Guard the documented invariant lower <= estimate <= upper against any
    # floating-point edge case at the p=0/p=1 boundary.
    lower = min(lower, estimate)
    upper = max(upper, estimate)
    return IntervalStats(
        estimate=format_decimal(estimate),
        lower=format_decimal(lower),
        upper=format_decimal(upper),
    )


def newcombe_delta(
    baseline_successes: int, baseline_n: int,
    candidate_successes: int, candidate_n: int,
    confidence: str = "0.95",
) -> IntervalStats:
    """Newcombe-Wilson hybrid score interval (Newcombe 1998, "Method 10")
    for the difference of two INDEPENDENT proportions: candidate - baseline
    (no seed control exists anywhere in cg.api/cg.game -> runs are unpaired,
    see EV-02). Combines each side's OWN Wilson interval as:

        lower = (p2 - p1) - sqrt((p2 - l2)^2 + (u1 - p1)^2)
        upper = (p2 - p1) + sqrt((u2 - p2)^2 + (p1 - l1)^2)

    where arm 1 = baseline (p1, [l1, u1]) and arm 2 = candidate (p2, [l2, u2]).
    This is the standard Newcombe-Wilson formula -- NOT naive interval
    subtraction (delta_lo = c_lo - b_hi / delta_hi = c_hi - b_lo), which is a
    valid but needlessly wider (over-conservative) bound and was flagged as
    a labeling/correctness defect by an earlier heterogeneous-model audit
    pass (Codex Final Auditor) before this implementation.
    """
    b = wilson_interval(baseline_successes, baseline_n, confidence)
    c = wilson_interval(candidate_successes, candidate_n, confidence)
    p1 = baseline_successes / baseline_n
    p2 = candidate_successes / candidate_n
    l1, u1 = float(b.lower), float(b.upper)
    l2, u2 = float(c.lower), float(c.upper)

    delta_est = p2 - p1
    lower = delta_est - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    upper = delta_est + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    lower = min(lower, delta_est)
    upper = max(upper, delta_est)
    return IntervalStats(
        estimate=format_decimal(delta_est),
        lower=format_decimal(lower),
        upper=format_decimal(upper),
    )


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile (0 <= pct <= 100) over a pooled,
    sorted sample. Equivalent to numpy's default ("linear") method,
    reimplemented without numpy."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not (0 <= pct <= 100):
        raise ValueError("pct must be within [0, 100]")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (pct / 100.0) * (len(xs) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return xs[int(lo)]
    frac = rank - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def percentile_interval(values: Sequence[float], pct: float, confidence: str = "0.95") -> IntervalStats:
    """Per-arm point estimate for a continuous metric (e.g. p95 decision
    time), with the interval bound to the exact same value as the estimate
    unless combined with a bootstrap; per-arm intervals here report the
    observed value with zero-width bounds, since within-arm uncertainty for
    a single arm's percentile is reported through the delta's bootstrap
    interval (see game_cluster_bootstrap_delta), not re-derived twice."""
    est = percentile(values, pct)
    return IntervalStats(
        estimate=format_decimal(est),
        lower=format_decimal(est),
        upper=format_decimal(est),
    )


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation,
    stdlib-only, no scipy). Accurate to ~1.15e-9 relative error."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must be within (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _resample_index_stream(seed_material: dict, n_indices: int, pool_size: int):
    """Deterministic resample-index generator: SHA-256-counter-block PRNG
    keyed on seed_material (must include comparison-manifest hash, metric,
    segment, artifact role, replicate number). Not a cryptographic use --
    only determinism and a uniform distribution over [0, pool_size) are
    required. Explicitly harness-side "analysis_resampling"; does NOT claim
    or imply control of the underlying game engine's RNG (see EV-02: no
    seed/RNG control exists anywhere in cg.api/cg.game's Python surface)."""
    if pool_size <= 0:
        raise ValueError("pool_size must be >= 1")
    base = canonicalize(seed_material)
    counter = 0
    produced = 0
    while produced < n_indices:
        block = hashlib.sha256(base + counter.to_bytes(8, "big")).digest()
        # 4 bytes per draw -> plenty of independent draws per SHA-256 block
        for offset in range(0, len(block) - 3, 4):
            if produced >= n_indices:
                break
            value = int.from_bytes(block[offset:offset + 4], "big")
            yield value % pool_size
            produced += 1
        counter += 1


def game_cluster_bootstrap_delta(
    baseline_games: Sequence[Sequence[float]],
    candidate_games: Sequence[Sequence[float]],
    statistic_fn: Callable[[Sequence[float]], float],
    seed_material: dict,
    replicates: int = 10_000,
    confidence: str = "0.95",
) -> IntervalStats:
    """A generic whole-game-cluster bootstrap delta estimator, USED IN THIS
    HARNESS specifically for decision-level, within-game-correlated metrics
    (decision_time_p50_ms/p95_decision_time) -- game-level 0/1 rate metrics
    (win/error/timeout/illegal_action) use newcombe_delta() instead, since
    each game contributes exactly one independent observation for those and
    Newcombe-Wilson is the standard, narrower method for that case (see this
    module's top docstring and raging_bolt_eval.py's cmd_summarize). Each
    element of baseline_games / candidate_games is one GAME's list of
    values (e.g. a list of per-decision durations for a latency metric).
    Resamples WHOLE GAMES with replacement, independently within each arm,
    pools the resampled games' values, applies statistic_fn (e.g. a
    percentile(95) closure) to each arm, and reports the percentile interval
    of the `replicates` resulting (candidate_stat - baseline_stat) deltas.
    seed_material must uniquely identify this cell (comparison-manifest
    hash + metric_id + segment_id + artifact role) so resample indices are
    reproducible given identical inputs -- required, no default seed.
    """
    if not baseline_games or not candidate_games:
        raise ValueError("game_cluster_bootstrap_delta requires at least one game per arm")
    if replicates < 1:
        raise ValueError("replicates must be >= 1")

    b_indices = list(_resample_index_stream(
        {**seed_material, "arm": "baseline"}, replicates * len(baseline_games), len(baseline_games)
    ))
    c_indices = list(_resample_index_stream(
        {**seed_material, "arm": "candidate"}, replicates * len(candidate_games), len(candidate_games)
    ))

    deltas: list[float] = []
    for r in range(replicates):
        b_sample: list[float] = []
        for idx in b_indices[r * len(baseline_games):(r + 1) * len(baseline_games)]:
            b_sample.extend(baseline_games[idx])
        c_sample: list[float] = []
        for idx in c_indices[r * len(candidate_games):(r + 1) * len(candidate_games)]:
            c_sample.extend(candidate_games[idx])
        if not b_sample or not c_sample:
            continue
        deltas.append(statistic_fn(c_sample) - statistic_fn(b_sample))

    if not deltas:
        raise ValueError("bootstrap produced no valid replicates (empty resampled games)")

    alpha = (1.0 - float(Decimal(confidence))) / 2.0
    point_estimate = statistic_fn(
        [v for g in candidate_games for v in g]
    ) - statistic_fn([v for g in baseline_games for v in g])
    lower = percentile(deltas, alpha * 100)
    upper = percentile(deltas, (1 - alpha) * 100)
    lower = min(lower, point_estimate)
    upper = max(upper, point_estimate)
    return IntervalStats(
        estimate=format_decimal(point_estimate),
        lower=format_decimal(lower),
        upper=format_decimal(upper),
    )


def mean_statistic(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def percentile_statistic(pct: float) -> Callable[[Sequence[float]], float]:
    def _fn(values: Sequence[float]) -> float:
        return percentile(values, pct)
    return _fn


def exact_count_interval(count: int) -> IntervalStats:
    """Degenerate exact interval for an exact count (e.g. observation_count):
    estimate == lower == upper, no fabricated uncertainty on an exact value."""
    text = format_decimal(count)
    return IntervalStats(estimate=text, lower=text, upper=text)
