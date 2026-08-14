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

## 3. Maintain the findings ledger

Create .agent-review/ledger.json with {"findings": []} when absent.

Use a stable slug derived from file and finding title. Track severity, title, file,
first_seen, last_seen, and status (open, pass, recurred, or accepted). A finding that
returns after reaching pass becomes recurred.

## 4. Iterate at most three times

### Develop

If the target diff already exists, skip development. Otherwise delegate the
implementation to a worker with the repository path, confirmed specification, goal
contract, scope bounds, and required verification. The worker must inspect and obey
the applicable AGENTS.md, CLAUDE.md, contributor guidance, and repository checks.

Use the host's internal subagent or delegation mechanism when available. Do not
create a user-owned task or external thread merely to simulate an internal worker.

### Review in fresh context

Run the bundled agent-work-review skill in a fresh reviewer context. Give it only the
repository path, review target, confirmed specification, and prior accepted warnings.
Require the prose report and its final machine-readable JSON block.

If the host cannot provide a fresh context, disclose the reduced independence before
reviewing inline. Never claim an independent review occurred when it did not.

Reconcile every returned finding with the ledger.

### Check stop conditions in order

1. Success candidate: every acceptance check passes and the verdict is pass or
   pass_with_warnings. Run the final gate below.
2. Iteration cap: iteration three ended without a successful gate. Stop and escalate
   with evidence.
3. No progress: any finding is recurred, or the failed count did not decrease from
   the previous iteration. Stop and ask for the specific human decision needed.

### Final gate

Delegate one additional fresh reviewer using the configured gate model. Focus the
brief on the specification's Risk focus; if absent, choose the highest-evidence
remaining risk and state the choice. The gate holds when it produces no new failed
finding. Add any new failed finding to the ledger and continue within the same
three-iteration limit.

Warnings never keep the loop running by themselves.

### Fix

When failed findings remain, delegate the bundled apply-review-findings skill with
the review report, confirmed specification, risk focus, and ledger. Require minimal
edits and verification against each finding's evidence. Then review again in a fresh
context.

## 5. Archive and report

On every exit, create the next numbered .agent-review/runs/NNN/ directory. Store each
iteration's prose review plus JSON block and a run.json containing the goal, spec
path, per-iteration verdict/counts, acceptance results, and exit reason. Do not copy
the specification into the archive.

Report:

- exit reason: goal met, iteration cap, or no progress;
- every acceptance criterion, exact check, Pass/Fail, and captured evidence;
- each iteration's verdict and failed/warning counts;
- every resolved finding as Pass;
- every remaining warning and its required disposition: accept, file an issue, or
  clean up now.

Record accepted warnings in the ledger. Do not create issues or apply warning-only
cleanup without the user's authorization. Offer the bundled loop-dashboard skill
after the text report; the text report remains the source of truth.
