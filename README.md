# agent-work-review

[한국어 README](./README.ko.md)

A Claude Code skill that reviews code changes produced by AI agents **before they are
committed or merged**. AI agents write plausible code fast — and make a predictable
family of mistakes. This skill runs a five-pass review targeted at exactly those:

| Pass | What it catches |
|---|---|
| **Regression** | Changed/renamed symbols with un-updated callers, broken serialization contracts, silently modified test assertions |
| **Performance** | N+1 queries, I/O in loops, sync-over-async, unbounded reads, missing pagination |
| **Cost** | Spend that scales with traffic/data on metered services — Cosmos DB / DynamoDB request units, per-call APIs (LLMs, SMS, maps), egress, log ingestion. Includes a Cosmos DB RU deep-dive (cross-partition fan-out, query-vs-point-read, write amplification) |
| **Readability** | Narration comments, defensive wrapping, speculative generality, dead code — the smells specific to agent-written code |
| **Conventions** | Divergence from *your repository's* established patterns — discovered from your `CLAUDE.md`, linter configs, and sibling files, never from generic "best practice" |

Findings are verified against the actual code before being reported (each is marked
**Confirmed** or **Needs verification**) and classified CI-style: **Failed** (must be
fixed before landing) or **Warning** (advisory, does not block), rolled up into a
verdict of **Pass · Pass with warnings · Fail**. Checks that found nothing are listed
explicitly as passed, and once a finding is fixed it is reported as **Pass**.

## Install

```
/plugin marketplace add <owner>/agent-work-review
/plugin install agent-work-review@agent-work-review
```

No configuration needed. The skill learns each repository's conventions at review time.

## Use

The skill triggers automatically on requests like:

- "review what the agent just did"
- "check this diff before I commit"
- "is this branch safe to merge?"
- "에이전트가 작업한 결과물 리뷰해줘"

It reviews, in order of precedence: the target you name (PR / commit range / paths) →
uncommitted working-tree changes → the current branch against its merge base with the
default branch. Reports are written in whatever language you're conversing in.

## Loop engineering: `/review-loop`

The plugin also ships a goal-driven develop → review → fix loop:

```
/review-loop fleet fuel-total endpoint works per house rules; existing data and callers unbroken
```

- The loop **refuses to start without an explicit goal** — you state the goal and
  verifiable acceptance criteria up front (it asks if they're missing).
- Each iteration: develop (skipped if the diff already exists) → fresh-context review
  (`agent-work-review`) → stop-condition check → fix (`apply-review-findings`).
- **It stops when your goal's acceptance criteria verify AND the review verdict is
  Pass.** Safety stops: max 3 iterations, and escalation to you if findings stop
  decreasing (oscillation). Warnings never keep the loop running.
- The pieces interoperate through a machine-readable JSON block (`verdict`,
  `findings[]`) that every review report ends with — you can consume it from CI too.

The `apply-review-findings` skill also works standalone: "apply the review findings" /
"리뷰 지적사항 반영해줘".

When the loop finishes it offers a **one-glance dashboard** of the run — retry causes
per iteration, Failed/Warning trend chart, resolved-as-Pass items, goal verification —
via the bundled `loop-dashboard` skill (self-contained HTML, inline SVG charts, zero
CDN dependencies, so it ships with the plugin and works offline).

> Tip: to *enforce* review on every session without invoking the loop, wire a Claude
> Code [Stop hook](https://docs.anthropic.com/en/docs/claude-code/hooks) in your own
> settings that runs a review and blocks completion on Failed findings. That is a
> per-user harness setting, so this plugin documents it rather than shipping it.

## Structure

```
commands/
└── review-loop.md            # goal-driven develop→review→fix loop controller
skills/
├── agent-work-review/
│   ├── SKILL.md              # the five-pass review workflow (+ machine-readable result block)
│   └── references/
│       ├── regression.md         # consumer tracing, serialization boundaries
│       ├── performance.md        # N+1, unbounded reads, sync-over-async
│       ├── cost.md               # metered-service model + Cosmos DB deep-dive
│       ├── readability.md        # agent-specific code smells
│       ├── conventions.md        # discovering and enforcing repo precedent
│       └── csharp-conventions.md # Microsoft C# baseline (fallback when the repo has no precedent)
├── apply-review-findings/
│   └── SKILL.md              # fixes Failed findings from a review report, reports them as Pass
└── loop-dashboard/
    └── SKILL.md              # renders loop history as a self-contained HTML dashboard
```

## License

MIT
