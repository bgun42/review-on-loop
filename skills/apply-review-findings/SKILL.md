---
name: apply-review-findings
description: >
  Apply the findings of a code review to the working tree: fix every Failed finding,
  Warnings only when safe or requested, and verify each fix resolves the finding's
  evidence — resolved findings are reported as Pass.
  Use this skill whenever a review report exists (from the agent-work-review skill or
  any structured review) and the user asks to act on it — "apply the review findings",
  "fix what the review found", "리뷰 지적사항 반영해줘", "리뷰에서 나온 문제 고쳐줘" —
  and as the fix step inside the /work command.
---

# Apply Review Findings

Turn a review report into the smallest set of edits that makes the next review pass.
You are the repair crew, not a second reviewer and not a refactoring engine: fix what
the review found, verify each fix against the finding's own evidence, and change
nothing else.

## Step 1 — Load the findings

Locate the review report (the user points at it, or it is the output of a review that
just ran in this conversation). Prefer the machine-readable JSON block at the end of an
`agent-work-review` report; fall back to parsing the prose findings. For each finding
capture: severity, title, file/line, the evidence (the caller that breaks, the query
that fans out), and the suggested fix.

If there is no review report at all, say so and stop — running a review first is the
`agent-work-review` skill's job, not this one's.

## Step 2 — Decide what to fix

- **Failed**: always fix, in the report's order (worst first).
- **Warning**: fix only when the user asked for it, or when the fix is a strict
  deletion (dead code, narration comments) that cannot change behavior. Everything
  else stays untouched. This is a convergence rule, not laziness: a loop that chases
  warnings produces new diffs for the next review to comment on and never terminates.
  Remaining warnings stay in the report for a human to accept or batch later.
- **Warnings-only cleanup mode**: when explicitly invoked for it (e.g., the
  /work loop's warning-debt disposition), fix ONLY warnings — skip any warning the
  ledger marks `accepted`, and still take the minimal-diff path.
- If the repo has `.agent-review/ledger.json`, skip findings marked `accepted` and
  keep finding titles identical to the ledger's so statuses reconcile.
- **Needs-verification findings**: verify first (trace the caller, find the partition
  key). If the finding turns out to be false, record it as `skipped — not reproducible`
  with your evidence instead of "fixing" a non-problem.
- **Risk-focus findings**: when the spec or the review names a Risk focus area, a fix
  touching it gets the strongest verification available — run the covering tests, not
  only the finding's own evidence.

## Step 3 — Fix, one finding at a time

For each finding, in severity order:

1. Read the full file (not just the cited line) and the finding's evidence.
2. Make the **minimal** edit that resolves the evidence. Prefer the review's
   `fix_hint`/suggested fix; deviate only when the hint is wrong for the code you see,
   and say so.
3. Follow the repository's conventions — the review's convention findings tell you the
   local dialect (Result vs exceptions, repository layering, naming). A fix written in
   the wrong dialect just becomes next round's finding.
4. Do not refactor beyond the finding. Every extra changed line is new review surface;
   scope creep is the main reason review-fix loops fail to converge. If you notice an
   unrelated problem, note it in your output — don't touch it.

## Step 4 — Verify each fix against its own evidence

A fix is done when the finding's failure scenario no longer exists, checked concretely:

- Stale caller → the caller now resolves (grep the old name: zero hits outside history).
- Serialized-field break → the wire/storage name is restored or migrated end to end.
- Cross-partition/unbounded query → the query now pins the partition key / has bounds;
  quote the new query text.
- Convention violation → the code now matches the cited precedent.

Run the build and the tests covering the changed files if the repo supports it
cheaply, and report the actual result — "compiles, 14/14 tests pass" or "no build
infrastructure available, verified by grep".

## Step 5 — Report

Output a status table that reuses the review's exact finding titles (the next review
pass and the loop controller correlate by title). A finding whose fix is applied and
verified is reported as **Pass**:

```
| # | Severity | Finding (title from review) | Status | Evidence of resolution |
|---|----------|------------------------------|--------|------------------------|
| 1 | Failed   | ...                          | Pass   | ...                    |
| 2 | Warning  | ...                          | skipped — <reason> | ...        |
```

Then list files changed, and anything you deliberately did not touch (nits, unrelated
observations). Write in the language the user is conversing in.
