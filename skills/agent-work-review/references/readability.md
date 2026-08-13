# Readability Review

Goal: judge whether the *next human* — who has none of the agent's session context —
can read this code and understand what it does and why. Readability findings are almost
never blockers, but they are where agent-written code most visibly differs from
human-written code, and where unreviewed agent output degrades a codebase fastest.

## Agent-specific smells (check these first)

These patterns are rare in human code and common in agent code:

1. **Narration comments.** Comments that restate the next line ("// increment the
   counter"), describe the editing process ("// updated to use the new method"), or
   justify the change to a reviewer ("// this is safe because..."). Comments should
   carry information the code cannot: constraints, units, invariants, links to the
   *why*. Everything else is noise — flag it for deletion.
2. **Defensive wrapping.** try/catch around code that cannot throw, or that catches,
   logs, and continues with a broken state; null-checks on values the type system or
   the call site already guarantees. Each one implies a failure mode that doesn't
   exist and makes the real failure modes harder to see.
3. **Speculative generality.** An interface with one implementation, a strategy/factory
   for one case, config options nothing sets, parameters no caller passes. Agents add
   these to look thorough. Unused flexibility is not free — every reader must check
   whether it is used.
4. **Dead code left behind.** The old implementation commented out or renamed to
   `xxxOld`, unused imports/usings, variables assigned and never read. The diff should
   contain only what the change needs.
5. **Duplicated blocks.** Agents frequently paste-and-tweak instead of extracting.
   Twice is usually fine; three near-identical blocks that must change together is a
   finding.

## General checklist

- **Naming.** Names say what a thing *is/does*, at the right precision, without
  encoding the type (`dataList`, `tempObj`) and without lying (a `getX` that mutates,
  an `isValid` that also saves). Inconsistent vocabulary for the same concept
  (`vessel`/`ship` mixed within the diff) forces the reader to check whether they
  differ.
- **Function size and shape.** A function should fit in one mental frame: one level of
  abstraction, roughly one screen. Flag functions doing several unrelated jobs, deep
  nesting (>2–3 levels — early returns and guard clauses usually fix it), and long
  parameter lists (>3–4 — often a missing type).
- **Magic values.** Unexplained numbers/strings with domain meaning (`* 0.85`,
  `status == 3`). Ask for a named constant or a comment with the source of the value.
- **Control-flow honesty.** Exceptions used for normal flow, booleans threaded through
  three functions to change one branch, output parameters where a return type works.
- **Comment accuracy.** A comment the diff made false is worse than no comment — check
  comments *near* the changed lines, not only in them.

## How to weigh findings

Readability is the pass where false positives are cheapest to make and most annoying to
receive, so hold a high bar: flag what would genuinely slow down or mislead a competent
reader, not deviations from personal taste. If the surrounding codebase consistently
uses a style you dislike, that's the convention baseline (see `conventions.md`), not a
finding.

## Severity guidance

- Misleading name / false comment / dead code that will confuse maintenance → **Minor**
  (upgrade to **Major** only if it hides a behavioral trap).
- Narration comments, small duplication, style polish → **Nit**.
