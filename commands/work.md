---
description: Run Veriloop's strict-blind develop → review → fix workflow
argument-hint: <confirmed spec path, goal, executable acceptance checks, and scope bounds>
---

# Work

Invoke the bundled `run-review-loop` skill with `$ARGUMENTS`.

Treat `skills/run-review-loop/SKILL.md` as the single source of truth. Follow its goal
contract, strict blind-mode preflight, role boundaries, batching rule, three-iteration
limit, schemas, archive contract, and stop conditions without restating or weakening
them here.

If the arguments do not identify a confirmed specification, let `run-review-loop`
route to `draft-spec` and pause as defined by that skill.
