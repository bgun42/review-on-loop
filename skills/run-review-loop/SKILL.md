---
name: run-review-loop
description: Run a bounded, specification-grounded develop-review-fix loop on a repository until executable acceptance checks pass and independent code review has no failed findings. Use when the user asks to implement or repair work in a review loop, iterate until clean, run the Veriloop workflow, or invokes $run-review-loop. Requires an explicit goal, a confirmed written specification, executable acceptance checks, and scope bounds. Do not use for a one-off review or for open-ended make-it-better requests.
---

# Run Review Loop

Control a develop → review → fix cycle with a maximum of three iterations. The
confirmed specification owns required behavior. Existing code is evidence of current
behavior and local conventions, not authority for product intent.

## 1. Establish the goal contract

Before changing code, record:

1. Specification: a confirmed requirements/design document, ADR, detailed ticket, or
   API contract. Pass its path to every worker and reviewer.
2. Goal: one or two sentences describing the finished state.
3. Executable acceptance criteria: pair every criterion with an exact command or
   observable assertion. Capture exit codes and relevant output.
4. Scope bounds: behavior, interfaces, storage formats, and modules that must not
   change.

If the specification is missing, invoke the bundled draft-spec skill and pause the
loop until the user confirms the document. If the goal, checks, or scope bounds are
too vague, ask the smallest blocking question. Never start from a guessed contract.
An unevaluable acceptance check fails; diagnose and rerun it instead of inferring
success.

Add a runtime smoke check when the specification covers a runnable service and the
repository has a safe, inexpensive local start path.

## 2. Load optional role configuration

Read .agent-review/config.json when present. Supported roles are developer, fixer,
reviewer, and gate. inherit, a missing role, or a missing file means the current
session model.

When delegating, apply an exact configured model only if the host supports model
overrides. If the configured model cannot be used, stop and ask rather than silently
substituting another model. The user's configuration is authoritative.

Treat a missing `blind_mode` as `strict`. Strict is the only persistent mode; never
save relaxed mode as a repository default.

## 3. Enforce strict blind mode

Before development, verify that the host can:

1. create a unique internal subagent for every iteration reviewer and final gate;
2. start each with no controller, developer, fixer, or prior-review conversation;
3. send an allowlisted brief without attaching hidden conversation history.

If any guarantee is unavailable, stop before changing code and name the unsupported
capability. Ask whether the user authorizes relaxed review **for this run only**.
Never infer approval from urgency, configuration, or a previous run. If approved, use
the strongest available separation, keep the review verdict vocabulary unchanged,
label each affected review and gate `independence: reduced` in the controller
record, and record the reason and authorization in `run.json`. If not
approved, exit with `blind_context_unavailable`. Never describe relaxed review as
independent or blind.

## 4. Maintain the findings ledger

Create .agent-review/ledger.json with {"findings": []} when absent.

Use a stable slug derived from file and finding title. Track severity, title, file,
first_seen, last_seen, and status (open, pass, recurred, or accepted). A finding that
returns after reaching pass becomes recurred.

The controller owns the ledger. Never send it to a reviewer or gate. Reconcile
accepted warnings after receiving a blind report instead of preloading them into the
reviewer's context.

## 5. Iterate at most three times

### Develop

If the target diff already exists, skip development. Otherwise delegate the
implementation to a worker with the repository path, confirmed specification, goal
contract, scope bounds, and required verification. The worker must inspect and obey
the applicable AGENTS.md, CLAUDE.md, contributor guidance, and repository checks.

Use the host's internal subagent or delegation mechanism when available. Do not
create a user-owned task or external thread merely to simulate an internal worker.
Give the worker the specification and acceptance checks, but do not give it review
reports, the review checklist, gate plans, holdout probes, or reviewer reasoning.

### Review in a unique blind context

Create a new reviewer subagent for this iteration. Never reuse a reviewer from an
earlier iteration or gate. Run the bundled `veriloop` skill with only:

- strict-blind invocation marker;
- repository path;
- frozen review target;
- confirmed specification;
- scope bounds;
- risk focus.

Do not send developer or fixer reasoning, prior reports, ledger contents, accepted
warnings, acceptance results, or gate probes. Tell the reviewer not to read
`.agent-review/`. If forbidden context leaks into the brief, discard that review and
start a clean reviewer; if that cannot be done, return to the strict-mode preflight.

Require the prose report and final machine-readable JSON block. The controller then
reconciles findings and filters previously accepted warnings without exposing history
to the reviewer.

### Check stop conditions in order

1. Success candidate: every acceptance check passes and the verdict is pass or
   pass_with_warnings. Run the final gate below.
2. Iteration cap: iteration three ended without a successful gate. Stop and escalate
   with evidence.
3. No progress: any finding is recurred, or the failed count did not decrease from
   the previous iteration. Stop and ask for the specific human decision needed.

### Final blind gate with late-bound probes

When a success candidate is reached, freeze it by recording the commit plus a digest
of the working-tree diff. Any target change invalidates the gate.

Create one additional gate subagent that is new to the run and uses the configured
gate model. Give it only the same allowlisted inputs as a blind reviewer plus the
frozen snapshot identifier. Do not reveal the iteration verdict, acceptance results,
prior findings, ledger, developer explanations, or previous gate probes.

The gate must inspect the frozen implementation first and then generate holdout probes
that did not exist in the developer brief:

- For executable code, run at least two safe probes from different categories:
  boundary or invalid inputs, state-transition ordering, failure injection,
  property/metamorphic behavior, differential behavior, or test-strength/mutation
  checks.
- For documentation or non-executable configuration, run at least one independent
  observable assertion.
- At least one probe must exercise an in-spec behavior not identical to a named
  acceptance check.

Prefer non-mutating commands. If a temporary test is required, use an isolated
temporary workspace and never edit the target worktree. A probe that cannot execute
is blocked, not passed. The gate must not fix code.

The gate holds only when the snapshot is unchanged, every holdout probe passes, and no
new Failed finding exists. Its report must include the snapshot, probe category,
command or assertion, captured evidence, and any new Failed finding.

Require a final machine-readable gate block:

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

On failure, add the finding to the controller-owned ledger and give the fixer only the
failed invariant and minimal reproducible evidence; withhold passed probes and the
rest of the gate's reasoning. After fixing and blind review, create another entirely
new gate that generates new probes. Continue within the same three-iteration limit.

Warnings never keep the loop running by themselves.

### Fix

When failed findings remain, delegate the bundled apply-review-findings skill with
the review report, confirmed specification, risk focus, and ledger. Require minimal
edits and verification against each finding's evidence. Then review again in a fresh
context.

For a blind-gate failure, pass only the minimal failure packet defined above, not the
full gate report. Never let the fixer read passed holdout probes.

## 6. Archive and report

On every exit, create the next numbered .agent-review/runs/NNN/ directory. Store each
iteration's prose review plus JSON block and a run.json containing the goal, spec
path, per-iteration verdict/counts, acceptance results, blind mode, any authorized
relaxation, gate snapshot, holdout probe evidence, and exit reason. Write archives
only after the run exits so no active reviewer can consume them. Do not copy the
specification into the archive.

Report:

- exit reason: goal met, iteration cap, no progress, or blind context unavailable;
- every acceptance criterion, exact check, Pass/Fail, and captured evidence;
- each iteration's verdict and failed/warning counts;
- every resolved finding as Pass;
- every remaining warning and its required disposition: accept, file an issue, or
  clean up now.

Record accepted warnings in the ledger. Do not create issues or apply warning-only
cleanup without the user's authorization. Offer the bundled loop-dashboard skill
after the text report; the text report remains the source of truth.
