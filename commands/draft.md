---
description: Draft the missing work specification — analyze the codebase and the goal, then deliver a user-confirmed spec ready for /work
argument-hint: <goal, and optionally paths/notes/tickets to use as material, e.g. "fix the parallel-iteration defects in fleet export; material: the last review report">
---

# Draft

Run the `draft-spec` skill on the arguments below and deliver a **user-confirmed
specification** — the document `/work` requires before it will start.

Arguments: $ARGUMENTS

- Treat the arguments, and any files they point to, as *material*: a goal statement,
  notes, a review report, a ticket. Material informs the spec; it becomes the spec
  only through the skill's dialogue and the user's confirmation.
- Follow the `draft-spec` skill workflow exactly: analyze the codebase first (house
  rules, conventions, workflow, the code the goal touches), then the goal against
  that reality, interview only for load-bearing decisions, draft, and get the user's
  confirmation.
- If the arguments are empty, ask what the user wants to build or change — that
  answer is the material.
- Finish by stating the confirmed spec's path and offering to continue with
  `/work <goal citing the spec>`.
