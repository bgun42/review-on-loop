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
**Confirmed** or **Needs verification**), ranked Blocker / Major / Minor / Nit, and
rolled up into a verdict: Approve · Approve with nits · Needs changes · Block.

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

## Structure

```
skills/agent-work-review/
├── SKILL.md                  # the five-pass workflow
└── references/
    ├── regression.md         # consumer tracing, serialization boundaries
    ├── performance.md        # N+1, unbounded reads, sync-over-async
    ├── cost.md               # metered-service model + Cosmos DB deep-dive
    ├── readability.md        # agent-specific code smells
    └── conventions.md        # discovering and enforcing repo precedent
```

## License

MIT
