# experiments/eval_infra

Generic evaluation/measurement infrastructure for comparing a candidate
`raging_bolt`-style artifact (`main.py` + `deck.csv` + optional `params.json`)
against a baseline artifact over a fixed local sandbox opponent league
(Lucario, Dragapult, Mega Starmie; `mirror` = smoke/auxiliary self-play
only).

## Scope boundary (must read before using)

This package does **not**:

- create or activate an App Profile (`profiles/outcome/*`),
- execute screening or confirmation evaluation as defined by
  `docs/agent-workflow/outcome-improvement-cycle.md`,
- produce Gatekeeper PASS Evidence, or import/call
  `tools/outcome_gatekeeper.py` at runtime (only `experiments/test_eval_infra.py`
  does, as a test-only, read-only drift guard),
- decide any production threshold, baseline commit, or dataset version.

It is measurement infrastructure only, out of scope for any prior-session
"golden"/adjudication/deck-enumeration mechanism a past task may have used;
none of that is created, referenced, or adopted here, and this package does
not create `experiments/golden_canonical_hash.py`.

`summarize`'s output is a **Measurement Report**, not a Gatekeeper Evidence
Bundle: every cell it emits is shaped exactly like a Gatekeeper Evidence
cell (`metric_id`, `segment_id`, `observations`, `baseline_stats`,
`candidate_stats`, `delta_stats`), but the report omits `profile_id`,
`profile_version`, `profile_sha256`, `cycle_id`, and `evidence_round` --
those only exist once a real, active App Profile and Cycle are bound.
Assembling a Measurement Report plus an active Profile's binding fields
into a Gatekeeper-ready Evidence Bundle is a distinct, later, out-of-scope
step this package does not perform.

## Design principle: `manifest` freezes EVERYTHING; `run`/`summarize` only verify

An external, independent audit round found that an earlier version of this
design let `run` accept its own `--opponent`/`--games-per-segment` and let
`opponent_pins.json` be read again at `run` time -- meaning two runs against
the *same* `comparison_manifest_sha256` could execute *different* opponents
or game counts. That is now structurally impossible:

- `manifest` is the **only** subcommand that reads `opponent_pins.json`, and
  the only one that selects opponents (`--opponent`, repeatable) or sets
  `--games-per-segment`. It resolves every selected opponent **right then**
  -- for a pinned-clone opponent (Dragapult/Mega Starmie) this means an
  actual `git clone` + commit verification + individual per-file SHA-256,
  not merely recording a commit reference that might not even resolve.
  Manifest creation **aborts** (no file written) if any requested opponent
  cannot be fully resolved right now.
- `run` and `summarize` have **no** `--opponent`, `--games-per-segment`,
  `--games-per-worker`, or `--wall-timeout-seconds` flags at all. Every one
  of those values is read exclusively from `--manifest`.
- `run` additionally **re-verifies** every opponent/artifact binding against
  disk at execution time (re-hashing local files, or re-cloning and
  re-hashing pinned ones) and fails closed on any drift from what the
  manifest recorded -- so even a manifest that was valid when written cannot
  silently execute against opponent/artifact content that changed since.
- Both `run` and `summarize` recompute `protocol_identity`'s hash,
  `dataset_identity`'s hash, each artifact's bundle hash (from its own
  `files` list, not trusted as a separately-stored value), and the
  top-level `comparison_manifest_sha256` from the manifest file's own
  stored fields, and reject the manifest if any no longer matches -- a
  hand-edited manifest JSON file (e.g. a `games_per_segment` or
  `selected_opponents` entry changed by hand after `manifest` wrote the
  file, or an artifact `files` entry repointed at different content or a
  different path while its bundle hash was left untouched) is detected and
  rejected, never silently trusted. `step_limit`/`games_per_worker` are
  additionally checked against the actual hardcoded engine constants (`2000`
  step limit in `experiments/head_to_head.py`; exactly `1` game per
  subprocess) -- a manifest that is internally hash-consistent but claims a
  different value than what `run` will actually execute is rejected, not
  merely a manifest whose hash doesn't match its own content.
  `dataset_identity.league_complete` is likewise never trusted as a stored
  boolean at `summarize` time -- it is recomputed from `selected_opponents`
  itself, so a hand-built (but internally hash-consistent) manifest cannot
  claim league completeness it doesn't actually have.

### What is actually hashed into `comparison_manifest_sha256`

`protocol_identity` (procedural specification):
`id`, `step_limit`, `games_per_worker` (always `1`, see below),
`wall_timeout_seconds`, `games_per_segment`, `side_allocation_schedule`
(the exact, deterministic per-game seat-0/seat-1 sequence, precomputed at
manifest time), `worker_model`, `decision_time_measurement`,
`game_rng_control`, `engine_binding` (`reference/extracted/cg/libcg.so`'s own
SHA-256, or an explicit `UNAVAILABLE` if the file isn't present),
`evaluator_binding` (SHA-256 of every one of this package's own `.py` source
files, individually and as a canonical bundle -- so a code change to the
harness itself changes the manifest hash), `runtime_environment`
(`platform.python_version()`/`system()`/`release()`/`machine()`, plus
`os_distribution`: `WSL_DISTRO_NAME` and `/etc/os-release` identity when
running under WSL/Linux, or an explicit `NOT_APPLICABLE` on Windows --
`platform_release` alone cannot distinguish two different WSL distributions
sharing the same reported kernel release and Python version).

`dataset_identity` (what will be measured):
`id`, `version`, `selected_opponents` (the full, resolved binding for each
`--opponent` -- for `mirror`: just `{"source_kind": "self_play"}`; for
Lucario (`local_only`): individual per-file SHA-256 of the local agent/deck
files; for Dragapult/Mega Starmie (`pinned_clone`): `repo_url`, exact
`commit_sha`, and individual per-file SHA-256 of the cloned agent/deck
files), `league_complete` (`true` only if all of `{lucario, dragapult,
megastarmie}` were selected).

`candidate_artifact`/`baseline_artifact`: `artifact_id` plus a `files` list
of **individual** `{logical_name, path, sha256}` entries (agent, deck,
optional params) -- not a hash of raw concatenated bytes, which cannot tell
you *which* file changed or where one file's bytes end and the next one's
begin. The artifact's own `sha256` is a canonical hash *over that per-file
list, including each entry's `path`* -- not just `{logical_name, sha256}` --
so a file entry cannot be repointed at a byte-identical copy of the same
content living at a different path without changing the bundle hash (path
matters because code can resolve neighboring files relative to its own
location, so identical bytes at a different location can still behave
differently at run time).

## CLI

```
python -m experiments.eval_infra.raging_bolt_eval manifest \
    --candidate-agent PATH --candidate-deck PATH --candidate-artifact-id ID \
    --baseline-agent PATH --baseline-deck PATH --baseline-artifact-id ID \
    [--candidate-params PATH] [--baseline-params PATH] \
    --protocol-id ID --dataset-id ID --dataset-version V --stage {screening,confirmation} \
    --opponent OPPONENT [--opponent OPPONENT ...] --games-per-segment N \
    [--wall-timeout-seconds S] --out PATH
    # --opponent is repeatable; each must be lucario/dragapult/megastarmie/mirror and is
    # RESOLVED (and, for a pinned-clone opponent, actually cloned+verified) RIGHT NOW --
    # manifest creation aborts (no file written) if any of them cannot be resolved.
    # Duplicate/empty --opponent selections are rejected. Requires --games-per-segment >= 1
    # and a finite, strictly positive --wall-timeout-seconds. Refuses to overwrite an
    # existing file at PATH.

python -m experiments.eval_infra.raging_bolt_eval run \
    --manifest PATH --jsonl-out DIR [--allow-partial]
    # NO --opponent/--games-per-segment/--games-per-worker/--wall-timeout-seconds flags --
    # every one of those comes exclusively from --manifest (see "Design principle" above).
    # Re-verifies the manifest's own hash chain, then re-hashes candidate/baseline artifact
    # files on disk (abort on drift), then re-verifies (or re-clones+re-hashes) every
    # selected opponent binding (abort on drift or on a network failure for a pinned-clone
    # opponent). If an artifact binds a --*-params file, sets POKEMON_AI_PARAMS_PATH to that
    # exact absolute path for the head_to_head.py subprocess (and explicitly clears any
    # inherited value otherwise). All --agent-*/--deck-* paths passed to that subprocess are
    # normalized to repo-root-absolute first (never left relative/cwd-dependent). Refuses to
    # write into an already-existing per-(opponent,arm) jsonl file -- use a fresh
    # --jsonl-out directory per run. games_per_worker is always exactly 1 (one subprocess per
    # game; batching is unimplemented for seat alternation and is no longer even
    # configurable -- see the former F3 caveat, now enforced rather than merely documented).
    # After each subprocess call, verifies the jsonl file gained exactly 1 new record; a
    # zero-exit subprocess that wrote the wrong count is an error, not a silent success. On a
    # wall-clock timeout, if the subprocess had already flushed its one real record just
    # before hanging, that REAL record is used as-is (no spurious synthesized record on top of
    # it); only if nothing was flushed is a synthesized wall_clock timeout record appended.
    # Every appended record is ENRICHED by the orchestrator (never by head_to_head.py itself,
    # which has no notion of any of this -- generic/application separation) with a globally
    # unique game_id, a batch_id, and comparison_manifest_sha256/dataset_id/protocol_id/
    # opponent_id/arm/artifact_id -- head_to_head.py's own "game_index" field resets to 0 on
    # every single-game subprocess invocation and would otherwise collide across every game
    # in one output file.

python -m experiments.eval_infra.raging_bolt_eval summarize \
    --manifest PATH --jsonl-in FILE [--jsonl-in FILE ...] \
    --stage {screening,confirmation} --rng-seed N [--allow-partial-report] --out PATH
    # --stage must match --manifest's own stage; --manifest's own hash chain is re-verified.
    # --confidence-level is used by every stats computation; --bootstrap-replicates/--rng-seed
    # are used specifically by the two latency/bootstrap cells (game-level rate cells use
    # Wilson/Newcombe, no bootstrap) -- all three are recorded in the output report's
    # "measurement_settings" so the report is self-documenting/reproducible.
    # --jsonl-in filenames must carry the FULL 64-hex comparison_manifest_sha256 as their
    # prefix (not a truncated one) and a known opponent_id/arm; each record's own
    # comparison_manifest_sha256/opponent_id/arm/label_a/label_b are cross-checked against
    # the filename and against the manifest, and rejected on any mismatch. game_id values
    # are checked for GLOBAL uniqueness across every --jsonl-in file combined -- a duplicate
    # is rejected. Malformed JSON, and any decision duration_ms that is non-numeric,
    # non-finite, or negative, are explicitly rejected (never silently coerced/ignored).
    # illegal_action_rate's denominator excludes legality=="unknown" records.
    #
    # The output report's "report_kind" is "primary" ONLY when league completeness --
    # RECOMPUTED from dataset_identity.selected_opponents itself, never trusted from the
    # stored dataset_identity.league_complete boolean -- confirms all 3 required opponents
    # were selected AT MANIFEST TIME, AND every selected league opponent (excluding mirror) has both baseline
    # and candidate input present among --jsonl-in. Otherwise "report_kind" is
    # "partial_diagnostic", the run either fails closed (default) or requires
    # --allow-partial-report to proceed, and the league-wide external_league_win_rate/
    # "overall" cell is NEVER computed for a partial_diagnostic report (a partial opponent
    # set can never masquerade as a full-league result). Per-opponent cells for whatever WAS
    # supplied are still computed either way.
```

`opponent_pins.json` in this directory is a **static, tracked scaffold that
starts as `{}`**. It is never auto-populated by any script, and is read
**only by `manifest`** (never by `run` -- see "Design principle" above) --
entries are added only by explicit manual edit before running
`clone_opponent.py`-backed opponents, in this shape:

```json
{"dragapult": {"commit_sha": "<40-hex>", "repo_url": "<https:// URL or local path>",
                "file_paths": ["<repo-relative agent .py>", "<repo-relative deck .csv>"]}}
```

A pin missing any of `commit_sha`/`repo_url`/`file_paths`, or with
`file_paths` not containing exactly 2 entries (agent, then deck), causes
`manifest` creation to abort for that opponent -- never partially trusted or
silently retried with a floating/unpinned clone. `repo_url` is checked
against a scheme allowlist (`https://`, or a bare local filesystem path with
no scheme at all) and any value containing `::` (git's `ext::`/`fd::`
remote-helper transport syntax, which can execute arbitrary commands) is
rejected before git is ever invoked.

`protocol_manifest.json` in this directory is a **static schema/example
template only** (see its own `_comment`/`status` fields) -- real per-run
manifests are always written by the `manifest` subcommand to a
caller-specified `--out` path, never to this tracked file.

## Metric-to-statistical-method mapping

- `external_league_win_rate`, `error_rate`, `timeout_rate`,
  `illegal_action_rate`: each GAME contributes exactly one independent 0/1
  observation (a game terminates the instant an illegal action/error/timeout
  occurs, so there is no meaningful within-game repetition for these four
  metrics given this package's per-game record granularity). Per-arm
  intervals use the Wilson score method; the delta (candidate - baseline)
  uses the Newcombe-Wilson hybrid interval (`stats.newcombe_delta`) built
  from each arm's own Wilson bounds -- the standard method for the
  difference of two independent proportions, not naive interval subtraction.
- `decision_time_p50_ms`, `p95_decision_time`: MULTIPLE, correlated
  observations per game (every decision in a game shares that game's engine
  state and non-deterministic search behavior). Per-arm AND delta intervals
  all use a whole-GAME cluster bootstrap (`stats.game_cluster_bootstrap_interval`
  for each arm's own baseline_stats/candidate_stats, `stats.game_cluster_bootstrap_delta`
  for the delta; 10,000 replicates by default, deterministic given
  `--rng-seed`) that resamples whole games (never individual decisions) to
  avoid understating the interval from within-game correlation
  (pseudo-replication). An earlier version reported a degenerate,
  zero-width "interval" (`estimate==lower==upper`) for each arm's own
  stats -- an external audit correctly flagged that a zero-width interval
  presented as a confidence interval is not actually quantifying
  uncertainty; both arms now get a real bootstrap CI.
- `observation_count`: an exact count (this arm's own recorded decisions,
  summed across the segment's games), reported as a degenerate interval
  (`estimate == lower == upper`) with no fabricated uncertainty -- this one
  metric is legitimately exact, unlike the latency percentiles above.
- Every `head_to_head.py --jsonl-out` decision entry is tagged
  `"actor": "a"` or `"b"`; `run` always invokes `head_to_head.py` with the
  arm under measurement as `--agent-a` and the opponent as `--agent-b`, so
  `summarize`'s decision-time/observation-count computations filter to
  `actor == "a"` only -- the arm's own decisions, never the opponent's.
- If every game in a segment contributed zero own-decisions (e.g. timing
  wasn't captured, or every game ended in `engine_null_start`), the
  latency/observation_count cells are simply **omitted** (UNAVAILABLE) --
  never a fabricated zero, and never an uncaught exception.

## Seat labeling: `seat-0`/`seat-1`, never "first-player"/"second-player"

`head_to_head.py`'s `--first-player` flag controls player-index/deck-slot
assignment only; it does not read or condition on the compiled cabt engine's
own coin-flip-determined first-mover (`Observation.current.firstPlayer`).
Calling the resulting segments "first-player"/"second-player" (as an earlier
version of this design did, and as `profiles/outcome/pokemon-ai.example.json`
itself does) would overclaim engine-confirmed first-mover status this
harness does not actually have -- an external audit correctly flagged this.
`summarize` therefore emits `seat-0`/`seat-1` segment IDs, which are
**deliberately not aligned** with the example Profile's IDs (see F1 below);
this is the one place this package intentionally diverges from the
otherwise-1:1 metric/segment ID alignment with that Profile.

## Required caveats (from a same-model Design Challenger pass and several
independent, different-model Codex Final Auditor rounds; all apply as
documented risk acceptances or known limitations, not defects to silently
work around -- items later found to be actual bugs, not acceptable caveats,
were fixed in the implementation instead of documented here; see git
history for the full findings of each round)

- **F1** -- True first-mover parity is unverified pending an L1 Linux run
  that inspects `obc.current.firstPlayer` across paired runs (see "Seat
  labeling" above for how this is handled: `seat-0`/`seat-1`, not
  "first-player"/"second-player").
- **F2** -- A malformed agent return value raises `ValueError` from
  `cg/game.py`'s `battle_select()` (checked before the engine call), not
  `IndexError`. This harness's per-game record classifies that case's
  `error_actor` as `"engine"` rather than the acting agent, and its
  `legality` as `"unknown"` rather than `"illegal"` -- a known,
  intentional three-bucket-model consequence (legal / illegal / unknown; an
  unconfirmed case is never silently counted as either legal or illegal).
  `illegal_action_rate`'s numerator only counts engine-confirmed illegal
  actions (a real `IndexError` from `battle_select`), and a malformed-return
  case is excluded from that rate's denominator entirely rather than
  miscounted -- an undercount risk if malformed returns are common,
  disclosed here rather than silently smoothed over.
- **F4** -- `clone_opponent.py`'s hardening threat model is a
  **manually-edited, local, non-network-facing** `opponent_pins.json` --
  it rejects `..`/backslash/drive-letter path components, repo URLs
  starting with `-`, and enforces a URL-scheme allowlist (`https://` or a
  bare local path only, rejecting `ext::`/`fd::`/`http://`/`git://`/
  `ssh://` etc., and rejecting SCP-style SSH remote syntax
  `user@host:path`/`host:path`). The single-letter Windows-drive-letter
  exception (`C:...`) only applies when `platform.system() == "Windows"`,
  so a single-character SCP-style host (e.g. `a:b`) is correctly rejected
  when running on Linux/WSL, where real cabt games actually execute. This
  closes the earlier documented gap; it is no longer a caveat, just a
  description of the current hardening.
- **F8** -- The `--jsonl-out`/`--record-decision-timing` code-path split
  inside `experiments/head_to_head.py`'s game loop (added additively; the
  default no-flags path is untouched) has had its default-off-path safety
  verified by code review and by the Windows-runnable test suite's
  structural/formula-level checks only. It has not yet been exercised by an
  actual cabt game (that requires WSL/Linux; see L1-L3 in
  `experiments/test_eval_infra.py`'s module docstring), so its behavior
  under real engine execution is not yet empirically confirmed.
- **F9** -- No test anywhere in this repository's current CI
  (`.github/workflows/tests.yml`) exercises the real compiled `cg` engine.
  Deferring this package's real-game tests (L1-L3) to a manual/Linux-only
  run continues that existing repository-wide convention; it is not a new
  gap introduced by this package.

(F3, F5, F6, F7 from earlier rounds are no longer listed as standalone
caveats: F3's "games-per-worker>1 + seat alternation" concern is now moot --
`games_per_worker` is hardcoded to `1`, not a configurable value anywhere.
F5's wording issue and F6's template-vs-runtime-manifest distinction are
covered by the sections above. F7 -- `mirror` opponent handling -- was a
required implementation item, not a caveat; see "Opponent availability"
below.)

## Opponent availability, as of this package's current implementation

- **Lucario**: `UNAVAILABLE`. `experiments/agents/top_lucario_1084_main.py`
  and `experiments/decks/top_lucario_1084.csv` are a gitignored,
  manually-retained, local-only pair of files with no clone/download path,
  and both are currently absent from this worktree. No substitute or
  inferred deck is ever accepted. `manifest --opponent lucario` will abort
  (no file written) until these files exist.
- **Dragapult, Mega Starmie**: `UNAVAILABLE` until `opponent_pins.json` is
  given a real, complete entry (`commit_sha` + `repo_url` + `file_paths`)
  for each, at which point `manifest --opponent dragapult`/`megastarmie`
  will actually clone, verify, and hash-bind it right then -- requires
  network access, not exercised by this Windows implementation session (see
  L3). `run` re-verifies (re-clones and re-hashes) the same binding again at
  execution time.
- **Mirror**: `AVAILABLE`, always. Requires no pin or clone -- each arm
  (baseline/candidate) plays against itself. Reported only in the
  Measurement Report's `diagnostics` block (`mirror_games`), and is
  excluded from every league win-rate/error-rate/latency/etc. cell (mirror
  games never enter `league_baseline`/`league_candidate`).

## Tests

See `experiments/test_eval_infra.py`'s module docstring for the full
T1-T23 (Windows-runnable now) / L1-L3 (Linux-only, explicitly deferred and
not claimed passing) breakdown.
