---
name: {{DESIGN_SKILL_NAME}}
description: Run the project's read-only multi-agent design debate and produce an evidence-grounded integrated design for explicit user approval. Invoke manually for architecture, multi-file design, high-risk changes, performance improvements, refactors, or test-strategy work.
argument-hint: "[design task]"
disable-model-invocation: true
user-invocable: true
---

# {{DESIGN_SKILL_NAME}}

This Skill orchestrates the project's read-only multi-agent design workflow (`docs/agent-workflow/README.md` / `review-protocol.md` / `docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md`) to produce one evidence-grounded integrated design for the user to explicitly approve. The parent Claude Code session runs every phase below in order; it is the sole orchestrator. Claude project subagents (`.claude/agents/`) and the `codex-reviewer` MCP server (`.mcp.json`) are invoked from here — subagents never invoke each other, and Codex is never invoked from inside a subagent.

**Design task**: $ARGUMENTS

If `$ARGUMENTS` is empty, do not start any phase. Ask the user to provide the design task, then stop.

## Absolute boundaries

This Skill is design-only and read-only, for its entire execution:

- No file creation, edit, or deletion
- No code implementation
- No test implementation
- No commit, push, PR creation, or merge
- No deploy or write to any external service
- No implementation before explicit user approval — even if the user's initial input requests implementation directly, this Skill stops at the Phase 7 approval gate and presents the integrated design instead

`READY_FOR_APPROVAL` (Phase 6/7) means the integrated design is ready to present to the user — it is **not** implementation authorization. Every repository change in the integrated design requires the user's explicit approval before any implementation begins.

## Quality-first token policy

This Skill inherits `docs/agent-workflow/quality-first-token-policy.md` in full. No hard token cap is set. Reasoning effort is never fixed low to save tokens, and no role is merged with another to save tokens.

**May reduce**: duplicate context, full re-quoted code, full re-quoted proposal text, decision-irrelevant success logs, repeated restatement of the same claim, unnecessary agent invocations, unnecessary new Codex threads.

**Must never reduce**: required evidence; the Confirmed / Inference / Unknown distinction; material risks; open issues; benefits/drawbacks; rejection reasons; test plans; rollback plans; items requiring user approval; the complete context a design judgment actually depends on. When reducing something risks ambiguity or dropped context, keep the fuller version.

Practical rules used throughout the phases below:

- Success logs may be summarized to their conclusion; failure logs keep whatever is needed to find the root cause (error text, failing command, relevant diff/trace).
- Refer to proposals and evidence by ID (`Proposal ID`, `Evidence ID`) and by diff against a prior version — never re-paste a full proposal or full evidence text that already has an ID.
- A single Independent Architect Codex conversation continues via its `threadId` and `codex-reply`; do not open a new thread to continue the same discussion.
- Never write a `threadId` or an Agent ID (subagent run identifier) into any file, commit, or PR body — both are transient run identifiers, referenced only within the current session's working memory.
- Invoke Alternative Architect only when its trigger condition (see Phase 3) is actually met.

## Phase 0 — Preflight and safety gate

Before any subagent or MCP call, the parent session confirms and records (for the Execution Trace, not for a document):

- Current working directory and that it is the intended repository/worktree
- The design task's purpose (from `$ARGUMENTS`)
- That this is a design-only, read-only task: no file changes, no commit/push/PR
- That the `codex-reviewer` MCP server is available (e.g. via `/mcp` in this session)
- That the required project subagents (`requirements-auditor`, `simplifier`, `claude-architect`, `design-judge`) are available

If the `codex-reviewer` MCP server or any required subagent is not available, **do not simulate or fake the missing role.** Stop and report `Status: BLOCKED`, naming exactly what is unavailable.

## Phase 1 — Requirements audit and normalized task packet

Invoke the `requirements-auditor` subagent explicitly via the Agent tool. Pass it:

- `$ARGUMENTS`
- The current working directory
- That this is design-only, read-only work
- That implementation, commit, push, and PR are not authorized at this stage
- `docs/agent-workflow/review-protocol.md`'s task input format, for it to audit against

If `requirements-auditor` returns **BLOCKED**:

- Do not invoke any further subagent
- Do not invoke Codex MCP
- Return its Blockers and Clarifying questions, and stop

If it returns **READY**, take its Normalized task packet as the single source of truth for the rest of this run, and additionally create:

- **Task ID** — an identifier for this design run
- **Evidence Registry** — a running list of Evidence IDs (`E-001`, `E-002`, ...) with what each cites (file path / function / line range / command output), added to as later phases produce evidence
- Evidence IDs referenced in later phases must exist in this Registry

The parent session does not fill in information the Normalized task packet left as `Unknown` — an unresolved `Unknown` here can still be carried forward and addressed later (e.g. in Phase 6's Blockers), but it is never invented.

## Phase 2 — Independent architecture proposals

From the same Normalized task packet, produce exactly two independent initial proposals, **each completed before either is shown to the other producer**:

**Proposal 1 (Main Architect)** — invoke the `claude-architect` subagent via the Agent tool with the Normalized task packet and Evidence Registry. Its own definition (`.claude/agents/claude-architect.md`) already requires it to work without seeing any other architect's proposal.

**Proposal 2 (Independent Architect)** — use the `codex-reviewer` MCP server's `codex` tool, opening a **new** thread, with:

- `cwd` set to the current worktree root
- `sandbox`: read-only
- `approval-policy`: never
- No model override
- No fixed reasoning effort
- No file changes, no commit/push/PR
- Logical role framed as: Independent Architect, working from the same Normalized task packet and Evidence Registry, without seeing Proposal 1

Assign a Proposal ID to each (e.g. `P-1`, `P-2`). Record the Independent Architect's `threadId` only for this run's internal continuation (Phase 4) — never write it to a file, commit, or PR.

## Phase 3 — Simplification and Red Team review

Run only after both Phase 2 proposals are complete.

**Simplifier** — invoke the `simplifier` subagent via the Agent tool. Present the two proposals anonymized as 案A / 案B (drop any wording that names Claude, Codex, or a specific model). Ask it to flag: over-engineering, unnecessary scope, duplication, unneeded dependencies, over-abstraction.

It must not remove: correctness, safety, required evidence, testability, rollback-ability, performance work the task actually requires, material risks, or Unknowns. `.claude/agents/simplifier.md`'s own rollback-safety rules already forbid it from suggesting `git checkout`/`reset`/`stash`/`clean`.

**Red Team Reviewer** — use the `codex-reviewer` MCP server's `codex` tool in a **new**, read-only thread (not the Independent Architect's thread). Ask it to check both proposals (anonymized 案A / 案B) for: destructive changes, security issues, data loss, compatibility breaks, performance regressions, failure modes, missing tests, non-reversible changes, insufficient evidence, scope creep, wrong assumptions, operational problems.

### Alternative Architect (optional)

Do not invoke by default. Invoke only when one of these is actually true:

- Both initial proposals (P-1, P-2) have material flaws
- A serious, unresolved conflict remains between them
- A genuinely different third design is needed
- Red Team rates both proposals as effectively REJECT
- The user explicitly asked for a third proposal

When invoked: `codex-reviewer`'s `codex` tool, a new read-only thread, `approval-policy: never`, no model override, no fixed reasoning effort, and no mention of authorship or model identity in the prompt.

Whether invoked or not, record the decision and its reason in the Execution Trace (Phase 7's `Alternative Architect: invoked/not invoked — reason`).

### Evidence limitations

If a reviewer or architect role (subagent or Codex, in any phase) cannot re-verify a repository primary source it needs — for example a tool/sandbox failure prevents it from reading the files it would normally check — that fact and its scope of impact must be recorded as an explicit **Evidence limitation**, in that role's own output. A finding produced under an Evidence limitation is never treated as ordinary, fully-verified evidence; it is labeled with what could and could not be checked (e.g. "evaluated for internal consistency only; could not re-read repository files this run").

`design-judge` (Phase 6) independently re-verifies, via Read/Glob/Grep, any fact material to its judgment before relying on it — it does not take an unverifiable claim from an earlier phase at face value. If a materially important fact cannot be re-verified this way, and the gap would materially affect correctness, safety, or the accept/reject decision, `design-judge` returns **BLOCKED** instead of proceeding on an unverified basis.

An Evidence limitation is never hidden, downplayed, or written up as if the affected review succeeded without qualification.

## Phase 4 — Evidence-based rebuttal rounds

Maximum **2 rounds**.

**Round 1** — run when Simplifier or Red Team raised a substantive point.

- *Codex side*: continue the Phase 2 Independent Architect's existing `threadId` via `codex-reply` (never open a new thread for this). Ask for: response to each point raised, which revisions are accepted, which are rejected (with reason), updated risks, new Unknowns, and a Proposal delta (not a full re-statement).
- *Claude side*: do not assume the `claude-architect` subagent instance can be "resumed" — subagent invocations do not carry conversational state across calls. The parent session itself constructs the Claude-side response, grounded in the original Proposal ID and the Evidence Registry: response to each point, accepted revisions, rejected revisions with reason, new evidence (with Evidence IDs), updated risks, new Unknowns, and a Proposal delta.

**Round 2** — only if one of these holds:

- New evidence has appeared
- A material rebuttal remains unresolved
- A material conflict on safety or correctness remains
- There isn't enough resolved evidence to hand to Design Judge yet

Do not run Round 2 to repeat a claim already made in Round 1.

## Phase 5 — Anonymization

Before anything is handed to `design-judge`, strip:

- Claude, Codex, Anthropic, OpenAI, Sonnet, Opus, Haiku (or any other model/vendor name)
- MCP tool names, subagent names
- `threadId`, Agent ID
- Any wording that would let the reader infer which system produced which proposal

Relabel proposals as 案A / 案B, and 案C only if an Alternative Architect proposal exists.

Keep everything substantive: Proposal ID, Evidence ID, the design content itself, benefits, drawbacks, risks, test plan, rollback plan, Unknowns, Simplifier's points, Red Team's points, and the rebuttal deltas from Phase 4.

## Phase 6 — Anonymous judging and integrated design

Invoke the `design-judge` subagent via the Agent tool with the anonymized package from Phase 5, including any Evidence limitations recorded in Phase 3 or Phase 4. Per "Evidence limitations" above, `design-judge` re-verifies materially important facts itself via Read/Glob/Grep rather than trusting an unverified claim, and returns BLOCKED if a material gap can't be closed this way — its **Evidence sufficiency** output reflects this.

Scoring (100 points, per `.claude/agents/design-judge.md` and `review-protocol.md`):

| Criterion | Points |
|---|---:|
| 正確性 (correctness) | 30 |
| 根拠の強さ (strength of evidence) | 20 |
| 安全性・変更範囲遵守 (safety and scope adherence) | 20 |
| 単純さ・保守性 (simplicity/maintainability) | 15 |
| テスト可能性・ロールバック性 (testability/rollback-ability) | 15 |

Judged by evidence and these criteria — never by a plain vote count.

Required output (unchanged from `design-judge`'s own format):

- Evidence sufficiency
- Anonymous score table
- Blockers
- Accepted elements
- Rejected elements and reasons
- Integrated design (target files, change order, test plan, rollback plan, risks, Unknown, user approval items)
- Verdict: READY_FOR_APPROVAL / BLOCKED

## Phase 7 — User approval gate

**If BLOCKED**: present Blockers, missing evidence, Clarifying questions, and what confirmation is needed next, then stop. Do not proceed to implementation planning.

**If READY_FOR_APPROVAL**: present to the user, in full:

- Task ID
- Design purpose
- Anonymous score table
- Accepted elements
- Rejected elements and reasons
- Integrated design
- Target files
- Change order
- Test plan
- Rollback plan
- Risks
- Unknown
- User approval items
- Execution Trace

Then explicitly ask the user whether to proceed to implementation, and stop. **Never implement before that approval is given**, regardless of how the original request was phrased.

## Execution Trace

The final output includes an Execution Trace containing only what actually happened in this run — no role is marked `invoked` unless it actually ran. `threadId` and Agent ID values are never written into it. Example shape:

```
- requirements-auditor: invoked / READY
- claude-architect: invoked / proposal received
- Independent Architect (codex): invoked / proposal received
- simplifier: invoked
- Red Team Reviewer (codex): invoked
- codex-reply: same thread reused / yes
- rebuttal rounds: 1
- Alternative Architect: not invoked / trigger absent
- design-judge: invoked / READY_FOR_APPROVAL
- repository files changed: no
- implementation performed: no
```
