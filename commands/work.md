---
description: Drive a develop → review → fix loop that stops when the user's stated goal is met and the review verdict is Pass
argument-hint: <goal, acceptance criteria, and the spec it implements, e.g. "per docs/fleet-fuel-spec.md: endpoint works per house rules; existing data and callers unbroken; tests pass">
---

# Work

Run an iterative develop → review → fix cycle on this repository, terminating on an
explicit, user-defined goal. You are the loop controller: you never review and never
fix in your own context — you delegate those to the skills and judge the results.

## Authority model

The confirmed specification owns required behavior; the goal contract and the plan
serve it, and existing code is a HOW reference — never the authority for WHAT. On any
conflict — spec ↔ code, spec ↔ reviewer taste, spec ↔ the loop's own convenience — the
spec wins, and a conflict only the user can resolve is escalated, never self-resolved.
Never lean downstream: the developer and fixer verify their own work as if the review
and the final gate did not exist. A gate finding is an upstream failure that escaped,
not the gate doing its job.

## Step 0 — Goal contract (do not skip)

The loop's arguments are: $ARGUMENTS

A loop without an explicit goal cannot terminate meaningfully — "make it better" loops
forever. Before the first iteration, establish the **goal contract**:

0. **Specification** — the written spec this work implements: a requirements or
   design document in the repo, an ADR, a ticket with concrete acceptance detail, an
   API contract. The goal contract must cite it, and the developer, reviewer, and
   gate subagents all receive its path as ground truth. Development that references
   no specification has no stable definition of "done" — the loop would converge on
   the reviewer's taste instead of documented intent. **If no such document exists,
   do not start the loop.** Run the bundled `draft-spec` skill instead: it analyzes
   the target codebase first (house rules, conventions, workflow, the code the goal
   touches), interprets the user's goal against that reality, and drafts the spec —
   with executable acceptance criteria — for the user to correct. Writing the spec
   becomes the current task; the loop starts only after the user confirms it.
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

   A check passes only on captured evidence — the command's exit code or observed
   output, shown in the report. **An unevaluable check is a fail, not a pass**: if
   the assertion itself could not run (the build died before the tests, the grep
   scanned an empty file set, the server never answered), diagnose and re-run —
   never infer success from side effects.

   When the spec declares a runnable service and the repository has a cheap way to
   run it locally, include a **runtime-smoke** criterion — start it, make one health
   request, expect a success response, stop it. A green build proves the code
   compiles; only a smoke proves it boots.
3. **Scope bounds** — what must NOT change (public API, storage format, other modules).

If the arguments above already contain these, restate them and proceed. If they are
missing or too vague to verify, **ask the user and wait** — do not start the loop on a
guessed goal, and never on work that has no specification behind it.

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

## Model configuration (user-owned)

Read `.agent-review/config.json` (written by `/init`; roles: `developer`,
`fixer`, `reviewer`, `gate`). When spawning each subagent, pass that role's model via
the harness's model override where supported; `inherit`, a missing key, or a missing
file all mean the session model. **The user's configuration is authoritative — never
silently override it.**

One sanity check at loop start, once: if the `reviewer` or `gate` is configured on a
weaker tier than `developer`/`fixer` (known tier order haiku < sonnet < opus <
top-tier; skip when either side is `inherit`/unknown), warn the user — the loop
converges on the judge's standards, so a weak judge caps what the loop can guarantee —
then proceed exactly as configured.

If no config exists, run everything on the session model and mention that
`/init` enables per-role model routing (e.g., a stronger model on the
reviewer/gate while develop/fix stay on a cheaper tier).

## Strict blind mode (default)

Treat a missing `blind_mode` as `strict`. Before development, verify that the Task/Agent
tool can create a unique subagent for every reviewer and gate without inheriting the
controller, developer, fixer, or prior-review conversation.

If clean contexts are unavailable, stop before changing code and ask whether the user
authorizes reduced independence for **this run only**. Never reuse an earlier approval
or save relaxed mode in config. If approved, keep the review verdict vocabulary
unchanged, label affected reviews and gates `independence: reduced` in the controller
record, and record the reason and approval in `run.json`. If declined
or unanswered, exit with `blind_context_unavailable`. Never call inline review blind
or independent.

## The loop (max 3 iterations)

### 1. Develop

If the working tree already contains the change to evaluate, skip this step. Otherwise
implement toward the goal, respecting the scope bounds and this repository's
conventions (its CLAUDE.md, linter configs, and sibling code — the same baseline the
review will judge against).
Give the developer the specification and acceptance checks, but not review reports,
the review checklist, gate plans, holdout probes, or reviewer reasoning.

### 2. Review — unique blind context, always

Create a new subagent for this iteration and run the `veriloop` skill. Never reuse a
reviewer from an earlier iteration or gate. Give it only the strict-blind invocation
marker, repo path, frozen review target, confirmed specification, scope bounds, and
risk focus.

Do not send developer/fixer reasoning, prior reports, ledger contents, accepted
warnings, acceptance results, or gate probes. Tell it not to read `.agent-review/`.
If forbidden history contaminates the brief, discard the review and start a clean
reviewer; if that is impossible, return to the strict-mode preflight. Reconcile the
report with the controller-owned ledger only after the blind review returns.

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

### Final gate — blind, late-bound verification

Freeze the success candidate by recording the commit plus a digest of the working-tree
diff. Spawn one additional gate subagent that is new to the run. Give it only the repo
path, frozen target, confirmed specification, scope bounds, risk focus, and snapshot
identifier. Do not reveal review verdicts, acceptance results, findings, ledger,
developer explanations, or previous gate probes.

The gate inspects the frozen implementation first, then creates holdout probes that
were absent from the developer brief:

- Executable code: at least two safe probes from different categories — boundary or
  invalid inputs, state ordering, failure injection, property/metamorphic behavior,
  differential behavior, or test-strength/mutation checks.
- Documentation or non-executable configuration: at least one independent observable
  assertion.
- At least one probe covers in-spec behavior not identical to a named acceptance
  check.

Prefer non-mutating commands. Temporary tests must run in an isolated temporary
workspace and must not edit the target worktree. An unevaluable probe is blocked, not
passed. The gate never fixes code.

The gate holds only when the snapshot is unchanged, every probe passes, and no new
Failed finding exists. Require snapshot, probe category, command/assertion, evidence,
and new findings in its report.

Require this final machine-readable gate block:

```json
{
  "gate": "hold | fail | blocked",
  "snapshot": "commit-and-diff identifier",
  "independence": "strict | reduced",
  "probes": [
    {
      "category": "boundary | state | failure | property | differential | mutation | assertion",
      "check": "command or observable assertion",
      "result": "pass | fail | blocked",
      "evidence": "captured output"
    }
  ],
  "findings": []
}
```

On failure, add the finding to the controller-owned ledger and give the fixer only
the failed invariant plus minimal reproducible evidence. Withhold passed probes and
the rest of the gate reasoning. After fixing and blind review, spawn an entirely new
gate that generates new probes. Continue within the same three-iteration limit.

Warning-only findings never keep the loop running — if the only reason you would
iterate again is warnings, that is success condition territory, not another cycle.

### 4. Fix

Run the `apply-review-findings` skill on the review report: every Failed finding,
Warnings only when trivially safe, minimal diffs, each fix verified against the
finding's evidence and reported as **Pass**. A fix that touches the spec's Risk
focus area gets the strongest verification available — run the covering tests, not
only the finding's own evidence. Then return to step 2.

For a gate failure, pass only the minimal failure packet above, not the full gate
report or any passed holdout probes.

## Archive the run

Review reports and iteration history exist only in the conversation and evaporate
with it. When the loop ends (any exit path), write them down: create
`.agent-review/runs/<NNN>/` (next number) containing each iteration's review report
(prose + JSON block) and a `run.json` containing goal, spec path, per-iteration
verdict and counts, acceptance results, blind mode, any authorized relaxation, gate
snapshot, holdout evidence, and exit reason. Write the archive only after exit; active
reviewers and gates never read it. The `loop-dashboard` skill renders the archive,
while the ledger stays the cross-run index. Specs live in the repo's docs and are already
versioned by git; do not duplicate them here.

## Final report

Whatever the exit path, tell the user:

- **Exit reason**: goal met (gate held) / iteration cap / no progress / blind context
  unavailable.
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
