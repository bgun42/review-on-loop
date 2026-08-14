---
name: agent-work-review
description: >
  Use this skill to review recent code changes — a diff, uncommitted work, or a
  just-finished feature — before they are committed, merged, or deployed. Trigger
  regardless of who wrote the code: an AI coding agent or subagent (Claude, Cursor,
  Copilot, an automated task), or the user themselves saying the implementation is done
  and asking for it to be checked. Trigger regardless of wording or language: review,
  check, verify, inspect, look over, give the diff a final pass, 검토, 리뷰, 확인,
  훑어보기. The review covers regression risk, performance, cloud cost (metered
  services like Cosmos DB, DynamoDB, LLM APIs), readability, and this repo's own
  conventions — trigger even when the user asks about only one of these for recent
  changes (e.g. only regressions, only convention violations, only cost). The review
  is grounded in the change's written specification (requirements/design doc, ticket
  with acceptance detail, API contract); when none exists, the skill routes to the
  bundled draft-spec skill to get one written and confirmed first instead of
  reviewing. Do NOT use
  for reviewing documents or design proposals, applying findings from a previous
  review, writing review checklists or process docs, or discussing review culture —
  only for actually reviewing concrete code changes.
---

# Agent Work Review

Review a diff the way a careful senior engineer reviews a teammate's PR — except the
teammate is an AI agent, which changes what you should be suspicious of. Agents write
plausible-looking code fast, but they tend to make a specific family of mistakes:

- They change a function without checking every caller.
- They write queries that work but scan far more data than needed — which on metered
  cloud services (Cosmos DB RUs, DynamoDB RCUs, per-call APIs) is a *billing* bug, not
  just a performance one.
- They invent their own style instead of matching the repository's existing patterns.
- They over-engineer: extra abstraction layers, dead configuration, speculative options.

Your job is to catch these before the change lands. Work through the five passes below
in order. Report only what you have verified against the actual code — a review full of
speculative findings trains the reader to ignore it.

## Step 0 — Specification gate

A diff can only be judged against its intended behavior, and intent lives in a written
specification — a requirements/design document, an ADR, a ticket with concrete
acceptance detail, an API contract. Establish it before touching the code:

- Identify the spec this change implements: the document the user, branch, PR, or
  ticket references, the goal contract of a running `/work`, or a doc the user
  points you to when asked.
- Read it and carry it through every pass: the regression pass checks the change
  against what the spec promises, and the verdict answers "does this do what the spec
  says" — not merely "does this look clean".
- **If no specification exists, do not run the review.** A review without a spec can
  only judge taste, not correctness. Say that plainly and switch to the bundled
  `draft-spec` skill: it analyzes the codebase (house rules, conventions, workflow)
  and the change itself, then drafts the spec for the user to correct and confirm.
  Run the review only once the confirmed spec exists.

## Step 1 — Scope the diff

Determine exactly what changed. Resolve the target in this order (stop at the first that
applies):

1. The user pointed at something specific (a PR number, commit range, branch, or paths)
   — review that.
2. There are uncommitted changes (`git status`, `git diff HEAD`) — review the working
   tree against HEAD.
3. Otherwise review the current branch against its merge base with the default branch
   (`git merge-base HEAD <default-branch>`).

Collect the full diff and the list of changed files. Read every changed file *in full*,
not just the hunks — the bug is often in how the changed lines interact with the
unchanged ones around them. If not in a git repository, ask the user what to compare.

## Step 2 — Learn the repository's rules before judging

The baseline for "correct style" is this repository, not your general taste. Before the
review passes, spend a few minutes establishing what this codebase considers normal:

- Read `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` if present — these are explicit
  house rules and violations of them outrank your own preferences.
- Check linter/formatter configs (`.editorconfig`, `eslint`/`ruff`/`.editorconfig`/
  analyzer settings) for enforced rules.
- Open 2–3 files that are *siblings* of the changed files (same directory or same layer)
  and note the established patterns: naming, error handling, layering, DI style, how
  queries are built, how tests are structured.

This matters because a public review skill knows nothing about any particular codebase —
the conventions pass (Step 3E) is only as good as the baseline you build here. It also
prevents the most annoying reviewer failure: flagging code for violating a rule the
repository doesn't actually have.

If `.agent-review/baseline.md` exists in the repo, start from it (a cached baseline
from a previous review) and spot-check it against current code before trusting it —
see `references/conventions.md` for the cache rules. If `.agent-review/runs/` exists,
read the latest run's report too — the previous cycle's findings are context for what
to re-check.

## Step 3 — The five review passes

Run all five passes over the diff. Each pass has a reference file with detailed
checklists and known failure patterns — load it when the diff touches that territory
(e.g., read `references/cost.md` whenever the diff touches a database, an external API,
or telemetry). Skip a reference only when the pass is clearly irrelevant (e.g., no I/O
anywhere in the diff → skip cost).

### 3A. Regression — did this break something that used to work?

The highest-severity pass. For every changed or deleted public symbol (function, method,
endpoint, exported type, config key, DB field), find its callers and consumers with
search tools and confirm each still works. Details and checklist:
`references/regression.md`.

### 3B. Performance — does this do more work than it needs to?

Look for I/O inside loops, N+1 query patterns, sync-over-async, unbounded reads,
missing pagination, and accidental algorithmic blowups. Details:
`references/performance.md`.

### 3C. Cost — does this spend money per call, per row, or per byte?

Performance bugs waste time; cost bugs waste money silently, and they scale with
traffic. Anything metered is in scope: request-unit databases (Cosmos DB, DynamoDB),
per-call APIs (LLMs, maps, SMS), egress, log/telemetry volume, storage operations.
Details and a Cosmos DB deep-dive: `references/cost.md`.

### 3D. Readability — will the next human understand this?

Naming, function size, nesting depth, dead code, comment quality, and the
agent-specific smells (narration comments, defensive try/catch wrapping, speculative
generality). Details: `references/readability.md`.

### 3E. Conventions — does this look like it belongs in this repository?

Compare the diff against the baseline from Step 2: layering, naming, error handling,
DI, test placement. A convention violation is judged against *this repo's* rules, never
against generic best practice. Details: `references/conventions.md`. When the repo has
no precedent on a point and the diff is C#, fall back to the Microsoft baseline in
`references/csharp-conventions.md`.

## Step 4 — Verify before reporting

Before a finding goes in the report, re-check it against the code:

- For a regression claim: show the caller that breaks. If you cannot name a concrete
  caller, input, or scenario that fails, downgrade it or drop it.
- For a performance/cost claim: identify the loop, the query, or the call site and state
  what makes it expensive (e.g., "query filters on `status` but the container's
  partition key is `tenantId`, so this fans out to every partition").
- For a convention claim: name the sibling file or house rule it contradicts.

If tests exist and can be run cheaply, run the ones covering the changed files and
include the result. Mark each finding **Confirmed** (you traced the failure) or **Needs
verification** (plausible, but you could not fully trace it) — never present the second
kind as the first.

## Step 5 — Report

Write the report in the language the user is conversing in. Use this structure:

```
## Review: <short description of the change>

**Verdict**: Pass | Pass with warnings | Fail

<one-paragraph summary: what the change does and the overall assessment>

### Findings

#### [Failed] <title>             ← must be fixed before this lands: broken behavior,
                                    silent data corruption, unbounded cost growth,
                                    serious performance defect, written-rule violation
<file>:<line> — evidence, why it fails, suggested fix. (Confirmed / Needs verification)

#### [Warning] <title>            ← should be considered, does not block: readability,
                                    convention drift, missed cheap optimization
...

### Passed checks
<one line per pass that found nothing, e.g. "Cost: no metered calls in this diff — Pass">
```

Rules for the report:

- Two severities only. **Failed** = the change must not land as-is. **Warning** =
  worth fixing, but a human may reasonably accept it. Order Failed findings worst
  first (broken behavior and data corruption above cost, cost above rule violations).
- Verdict follows from the findings: any Failed → **Fail**; only Warnings →
  **Pass with warnings**; nothing → **Pass**.
- The "Passed checks" section is not filler — it tells the reader which risks were
  actually ruled out, which is half the value of a review.
- Do not pad. Three verified findings beat ten speculative ones. An empty findings list
  with a confident "checked and clean" section is a perfectly good review.
- Suggest fixes but do not apply them unless the user asks. The deliverable of this
  skill is the review.

### Machine-readable result block

End every report with this fenced JSON block. It is the contract that lets automation —
the `/work` command, the `apply-review-findings` skill, CI scripts — consume the
review without parsing prose. Keep the prose report as the source of truth for humans;
this block only mirrors it.

```json
{
  "verdict": "pass | pass_with_warnings | fail",
  "findings": [
    {
      "severity": "failed | warning",
      "title": "same title as the prose finding",
      "file": "relative/path",
      "line": 0,
      "confidence": "confirmed | needs_verification",
      "fix_hint": "one-line suggested fix"
    }
  ]
}
```

Rules: `verdict` and `findings` must match the prose exactly (same count, same
severities, same titles — a mismatch breaks the loop that consumes it). A passing
review has `"findings": []` or warning-only entries.
