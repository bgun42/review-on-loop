---
name: draft-spec
description: >
  Use this skill to produce the written specification for a concrete piece of upcoming
  development work when none exists yet. The /draft command fronts this skill; the
  spec gates in the agent-work-review skill and the /work command route here whenever
  they find no referenced spec; and users can invoke it directly in any language:
  "write a spec for this first",
  "draft the spec before we start", "명세서 작성해줘", "명세부터 만들자", "이 작업
  명세로 정리해줘". It analyzes the target codebase first — house rules, conventions,
  workflow, and the code the goal touches — then interprets the user's goal against
  that reality and drafts a spec with executable acceptance criteria for the user to
  correct and confirm. Do NOT use for full project documentation suites (project
  plans, ERDs, API reference manuals) or for reviewing an existing spec — only for
  producing the missing specification of one concrete piece of work.
---

# Draft Spec

A specification written from a generic template is fiction; a specification written
from the code is a contract. The review skill and the loop in this plugin refuse to
work spec-less, and the fastest honest way to produce the missing spec is to read the
codebase first and interpret the user's goal against what is actually there — not to
hand the user a blank form.

The deliverable is a spec document **the user has confirmed**. Until the user corrects
and accepts the draft, there is no spec — do not let the caller (the review, the loop,
or the user) proceed on an unconfirmed draft.

## Step 1 — Analyze the codebase before interpreting the goal

The spec must describe work that fits *this* repository, so establish the repository's
reality first. Existing code is a reality check and a HOW reference — never the
authority for what the work *should* do; that authority is built in Step 2 with the
user.

- **House rules**: read `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` if present, and
  linter/formatter/analyzer configs — these are written constraints the spec must not
  contradict.
- **Conventions**: open siblings of the code the goal touches (same directory or same
  layer) and note the established patterns — naming, layering, error handling, DI,
  how queries are built, where tests live. This is the same baseline method as the
  review skill's Step 2 (`skills/agent-work-review/references/conventions.md`); if
  `.agent-review/baseline.md` exists, start from it and spot-check.
- **Workflow**: how changes land here — branch and PR conventions from recent history
  (`git log`), CI configuration, the commands that build and test this project. The
  spec's acceptance checks must be commands that actually run in this repo.
- **Target code**: read, in full, the files the goal names or implies. Record current
  behavior, callers and consumers, and the data contracts (stored fields, API shapes)
  that must not break. These become the spec's "current behavior" and "constraints"
  sections — grounded in `file:line`, not in memory.

## Step 2 — Analyze the user's goal against that reality

Everything you were given — the goal statement, notes, tickets, a review report — is
**material, not ground truth**. Its content flows into the spec, but its authority
does not: a decision enters the spec only when it is grounded in the user — they said
it, it follows from the model you have built of their goal and constraints, or they
chose from options you presented. The existence of a document is not evidence it
settled anything.

- Restate the goal in terms of the actual files, symbols, and behaviors found in
  Step 1 — a goal that talks about real code is already half a spec.
- **Enumerate the decision surface** — the load-bearing decisions this work is
  obligated to answer. Walk four lenses over each entity the work touches and each
  colliding pair: **structural** (cardinality, composition, identity), **behavioral**
  (lifecycle, concurrency, failure policy, edge cases), **technical** (persistence,
  interfaces, consistency), **contract** (status/enum sets, uniqueness, output
  shapes). Enumerate exhaustively; you will ask minimally.
- Resolve each enumerated decision by where the knowledge lives — never by silent
  default:
  - the code answers it → look it up (Step 1), don't ask;
  - the user's own words, or your grounded model of their intent, answers it →
    realize it, don't ask;
  - **domain or preference knowledge only the user holds → EXTRACT**: draw it out
    with questions; never invent it;
  - **a technical shape the user hasn't settled → PRESENT**: options with trade-offs
    and a recommendation, and the user decides — never decide silently.

  There is no "pick a reasonable default and move on" for a load-bearing decision —
  that is a stranger's guess, and it is exactly what detonates later as rework.
- Ask in batched rounds: at most ~4 questions at a time, lead with your
  recommendation, and never re-ask what the codebase or the dialogue already
  answered.

## Step 3 — Draft the spec

Draft only after Step 2's load-bearing decisions are closed. A spec written around
open questions either bakes in guesses or ships placeholder sections — both put the
question round after the document, which is backwards. If the user needs to see
structure before answering, show them the decision table from Step 2, not a half-spec.

Use this structure:

```
# <work title>

## Purpose & background      ← why this work exists, in one paragraph
## Scope                     ← in / out, explicitly
## Current behavior          ← what the code does today, file:line grounded
## Target behavior           ← what it must do when this work is done
## Constraints               ← repo conventions and workflow that apply; what must NOT change
## Acceptance criteria       ← each criterion paired with an executable check
## Risks & edge cases
## Risk focus                ← the ONE area where this change fails worst
## References                ← files, tickets, related docs
```

Acceptance criteria follow the same rule as the loop's goal contract: every criterion
is paired with the exact check that verifies it (a test command, a grep assertion, a
build, an HTTP call). A criterion with no runnable check is a taste judgment — sharpen
it or move it out.

**Risk focus** is one short paragraph naming where this change fails worst (which
lens, which file or contract) — `/work` aims its final-gate reviewer there and the
fixer verifies hardest there. Name one area; a risk focus that lists everything aims
nothing.

Save the draft where this repository keeps documents (an existing docs directory, or
propose a sensible path and let the user decide). Check the chosen path is actually
tracked by git — some repos gitignore their docs directories, and a spec teammates
cannot see is not a team contract; if it is ignored, say so and agree on a tracked
location with the user.

## Step 4 — Independent guess-hunt before confirmation

The drafter cannot audit their own guesses — that is self-judgment. Before presenting
the draft, dispatch **one fresh subagent** that did not author the spec (use the
`gate` role's model from `.agent-review/config.json` when present; session model
otherwise). Give it the draft, the enumerated decision surface with each decision's
disposition and grounding, and read access to the code. Its brief is two questions:

1. Is each decision's grounding real — did the user actually say or choose it, or
   was it rubber-stamped as "grounded" without evidence in the dialogue?
2. Walking the four lenses independently over the code the spec touches, is there a
   load-bearing decision the drafter never enumerated at all?

Every finding is relayed to the user as a question (EXTRACT or PRESENT — never
silently patched into the draft). Close the findings, re-check once; a surviving
dispute escalates to the user. This costs one subagent and protects everything
downstream: a wrong spec makes the developer, reviewer, and gate all faithfully
converge on the wrong target.

## Step 5 — Confirm and hand back

Present the draft and ask the user to correct and confirm it. Apply their corrections.
Only a confirmed spec counts.

Then state the confirmed spec's path plainly, so the caller can use it: the
`/work` goal contract cites it as ground truth for the developer, reviewer, and
gate; the review skill judges the diff against it. Write the spec (and converse) in
the language the user is conversing in.
