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
2. **Acceptance criteria** — how goal attainment is *verified*: which tests pass, which
   behavior is observable, which constraint holds. Each criterion must be checkable by
   you (run a command, read code, run the app) — not a matter of taste.
3. **Scope bounds** — what must NOT change (public API, storage format, other modules).

If the arguments above already contain these, restate them and proceed. If they are
missing or too vague to verify, **ask the user and wait** — do not start the loop on a
guessed goal.

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

1. **Success** — BOTH of:
   - every acceptance criterion from the goal contract verifies (run the checks now,
     each iteration — don't assume last iteration's result still holds), AND
   - review verdict is `pass` or `pass_with_warnings`.
   → **Stop.** Report success (see Final report).
2. **Iteration cap** — this was iteration 3 and success was not reached.
   → **Stop.** Escalate to the user with the current state.
3. **No progress** — the findings count did not decrease versus the previous iteration,
   or the same finding title appears for the second time after being "fixed".
   → **Stop.** Escalate: the loop is oscillating and human judgment is needed.
   Continuing would burn cost re-litigating the same code.

Warning-only findings never keep the loop running — if the only reason you would
iterate again is warnings, that is success condition territory, not another cycle.

### 4. Fix

Run the `apply-review-findings` skill on the review report: every Failed finding,
Warnings only when trivially safe, minimal diffs, each fix verified against the
finding's evidence and reported as **Pass**. Then return to step 2.

## Final report

Whatever the exit path, tell the user:

- **Exit reason**: goal met / iteration cap / no progress.
- **Goal verification**: each acceptance criterion with its check result (**Pass** /
  Fail) and evidence.
- **Loop history**: per iteration — verdict, Failed/Warning counts, and each resolved
  finding listed as **Pass**.
- **Remaining items**: open warnings, skipped findings with reasons, anything out of
  scope that was noticed but deliberately untouched.
- On escalation: the specific decision the user needs to make.

Write the report in the language the user is conversing in.

Then offer to render the loop history as a one-glance dashboard using the
`loop-dashboard` skill bundled in this plugin: findings per iteration by severity
(Failed/Warning trend), the verdict progression toward Pass, and each resolved finding
listed as Pass with what caused the retry. If the user's environment has a richer
visualization skill they prefer, use that instead — the data is the same. The text
report above remains the source of truth; the dashboard is a view.
