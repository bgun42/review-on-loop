---
description: Drive a develop → review → fix loop that stops when the user's stated goal is met and the review verdict is Pass
argument-hint: <goal and acceptance criteria, e.g. "fleet fuel-total endpoint works per house rules; existing data and callers unbroken; tests pass">
---

# Review Loop

Run an iterative develop → review → fix cycle on this repository, terminating on an
explicit, user-defined goal. You are the loop controller: you never review and never
fix in your own context — you delegate those to the skills and judge the results.

## Step 0 — Goal contract (do not skip)

The loop's arguments are: $ARGUMENTS

A loop without an explicit goal cannot terminate meaningfully — "make it better" loops
forever. Before the first iteration, establish the **goal contract**:

1. **Goal** — what finished looks like, in one or two sentences.
2. **Acceptance criteria** — how goal attainment is *verified*. Make each criterion
   **executable**: pair it with the exact check you will run — a test command
   (`dotnet test`, `pytest -k ...`), a grep assertion ("old symbol: zero hits"), a
   build, an HTTP call. Write the pairs down at the start:

   ```
   AC1: existing callers unbroken   → check: grep -r "GetFuelTotalAsync" src/ → 0 hits
   AC2: stored field name preserved → check: grep "fuelConsumedTons" in model+queries
   AC3: tests pass                  → check: dotnet test --filter Reports
   ```

   A criterion you cannot pair with a runnable check is a taste judgment, not a
   criterion — either sharpen it with the user or move it out of the goal contract.
   Success is then mechanical: run every check, all must hold. No model judgment in
   the termination decision.
3. **Scope bounds** — what must NOT change (public API, storage format, other modules).

If the arguments above already contain these, restate them and proceed. If they are
missing or too vague to verify, **ask the user and wait** — do not start the loop on a
guessed goal.

## Findings ledger

Maintain a ledger across iterations at `.agent-review/ledger.json` in the target repo
(create the directory; suggest gitignoring it). One entry per finding ever seen:

```json
{
  "findings": [
    {
      "id": "src-controllers-fleetcontroller-stale-caller",
      "severity": "failed",
      "title": "<exact title from the review>",
      "file": "src/Controllers/FleetController.cs",
      "first_seen": 1, "last_seen": 1,
      "status": "pass | open | recurred | accepted"
    }
  ]
}
```

The `id` is a stable slug from file + title. After every review, reconcile: new
findings get entries; a previously-`pass` finding that reappears becomes `recurred` —
which is the exact, non-fuzzy trigger for the no-progress stop condition below.
The ledger is also what the dashboard and CI read, and where `accepted` warnings are
recorded so they are not re-litigated in future runs.

## Model routing (orchestration)

Loop roles reward different model strengths, and the harness's per-subagent model
override (Agent-tool `model` parameter, or agent-definition frontmatter) lets you
exploit that:

- **Reviewer and final gate → the strongest model available.** Judging is the
  quality ceiling of the whole loop: the loop converges on the *judge's* standards,
  not the author's. Never route the reviewer to a weaker model than the fixer.
- **Develop and fix steps → the session's default (or a mid-tier) model.** Authoring
  mistakes are cheap here precisely because the reviewer catches them — that safety
  net is the point of the loop.
- **Controller (you) → the session model**; your job is bookkeeping, not judgment.

If the environment has no per-agent model override, run everything on the session
model — the loop still works, it just spends more where it didn't need to.

## The loop (max 3 iterations)

### 1. Develop

If the working tree already contains the change to evaluate, skip this step. Otherwise
implement toward the goal, respecting the scope bounds and this repository's
conventions (its CLAUDE.md, linter configs, and sibling code — the same baseline the
review will judge against).

### 2. Review — fresh context, always

Run the `agent-work-review` skill in a **fresh subagent** (Task/Agent tool), never
inline in your own context. Why: you (or your develop step) wrote this code; a reviewer
sharing the author's context inherits the author's blind spots, and the loop's value
collapses. Give the subagent only the repo path and the review request; take back the
report and its machine-readable JSON block (`verdict`, `findings`).

### 3. Check stop conditions — in this order

1. **Success candidate** — BOTH of:
   - every acceptance-criterion check from the goal contract passes (run the checks
     now, each iteration — don't assume last iteration's result still holds), AND
   - review verdict is `pass` or `pass_with_warnings`.
   → Run the **final gate** (below). If the gate holds, **stop** and report success.
2. **Iteration cap** — this was iteration 3 and success was not reached.
   → **Stop.** Escalate to the user with the current state.
3. **No progress** — the ledger shows a `recurred` finding (fixed once, back again),
   or the Failed count did not decrease versus the previous iteration.
   → **Stop.** Escalate: the loop is oscillating and human judgment is needed.
   Continuing would burn cost re-litigating the same code.

### Final gate — pay for confidence only at the end

Success is declared once per loop, so that one declaration deserves independent
confirmation: spawn **one additional fresh reviewer** with a narrowed brief — the
lens with the highest remaining risk for this change (usually regression &
data-contracts, or cost for query-heavy diffs) — on the strongest available model.
The gate holds if it raises no new Failed finding. If it does, the ledger gets the
finding and the loop continues (this consumes an iteration). For high-risk changes or
when the user asked for thoroughness, widen the gate to a 2–3 lens panel; per
iteration reviews stay cheap — only the exit is expensive.

Warning-only findings never keep the loop running — if the only reason you would
iterate again is warnings, that is success condition territory, not another cycle.

### 4. Fix

Run the `apply-review-findings` skill on the review report: every Failed finding,
Warnings only when trivially safe, minimal diffs, each fix verified against the
finding's evidence and reported as **Pass**. Then return to step 2.

## Final report

Whatever the exit path, tell the user:

- **Exit reason**: goal met (gate held) / iteration cap / no progress.
- **Goal verification**: each acceptance criterion with the check that was run, its
  result (**Pass** / Fail), and evidence.
- **Loop history**: per iteration — verdict, Failed/Warning counts, and each resolved
  finding listed as **Pass**.
- **Warning debt**: for each remaining warning, ask the user to disposition it —
  **accept** (recorded as `accepted` in the ledger; future runs won't re-litigate it),
  **file an issue** (create one if an issue tracker is reachable), or **clean up now**
  (run one warnings-only `apply-review-findings` pass — only on this explicit request,
  never automatically). Unmanaged warning debt is how loops quietly rot a codebase.
- On escalation: the specific decision the user needs to make.

Write the report in the language the user is conversing in.

Then offer to render the loop history as a one-glance dashboard using the
`loop-dashboard` skill bundled in this plugin: findings per iteration by severity
(Failed/Warning trend), the verdict progression toward Pass, and each resolved finding
listed as Pass with what caused the retry. If the user's environment has a richer
visualization skill they prefer, use that instead — the data is the same. The text
report above remains the source of truth; the dashboard is a view.
