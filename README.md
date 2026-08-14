<p align="center">
  <a href="./README.md"><img src="https://img.shields.io/badge/English-30363D?style=for-the-badge" alt="Read in English" /></a>
  <a href="./README.ko.md"><img src="https://img.shields.io/badge/한국어-30363D?style=for-the-badge" alt="한국어로 읽기" /></a>
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/▶_INSTALL-OPEN-111111?style=for-the-badge&labelColor=5B5B5B" alt="Install Veriloop" /></a>
  &nbsp;&nbsp;
  <a href="#recommended-workflow"><img src="https://img.shields.io/badge/▶_WORKFLOW-EXPLORE-8B5CF6?style=for-the-badge&labelColor=5B5B5B" alt="Explore the Veriloop workflow" /></a>
</p>

<p align="center">
  <kbd>skills 6</kbd>
  <kbd>review passes 5</kbd>
  <kbd>platforms Codex + Claude</kbd>
  <kbd>blind mode strict</kbd>
</p>

<p align="center">
  <a href="https://github.com/dev-geon/veriloop/stargazers"><img src="https://img.shields.io/github/stars/dev-geon/veriloop?style=flat" alt="GitHub stars" /></a>
  <a href="https://github.com/dev-geon/veriloop/releases/latest"><img src="https://img.shields.io/github/v/release/dev-geon/veriloop?style=flat" alt="Latest release" /></a>
  <a href="https://github.com/dev-geon/veriloop/blob/main/LICENSE"><img src="https://img.shields.io/github/license/dev-geon/veriloop?style=flat" alt="MIT license" /></a>
</p>

# Veriloop
A **spec-grounded code review and repair loop** for Codex and Claude Code.

It checks agent-written changes from five perspectives, then repeats for up to three iterations until no failed finding remains and the goal's acceptance checks pass as executable commands.

## Skill architecture

```mermaid
flowchart TD
    Init["Initialize (optional)<br/>initialize-review-loop · /init"] --> State["Strict blind mode + model routing<br/>.agent-review/config.json"]
    Draft["Confirm specification<br/>draft-spec · /draft"] --> Spec["Confirmed specification<br/>Executable acceptance checks"]
    State --> Run["Run the loop<br/>run-review-loop · /work"]
    Spec --> Run
    Run --> Develop["1. Develop"]
    Develop --> Review["2. New blind reviewer<br/>veriloop"]
    Review --> Decision{"Acceptance checks pass<br/>and no Failed?"}
    Decision -- "No" --> Fix["3. Apply findings<br/>apply-review-findings"]
    Fix --> Review
    Decision -- "Yes" --> Gate["4. New blind gate<br/>late-bound holdout probes"]
    Gate -- "New Failed" --> Fix
    Gate -- "Pass" --> Archive["5. Archive the run<br/>loop-dashboard"]
```

`veriloop` also works on its own. If there is no confirmed specification, it routes to `draft-spec` first instead of approving spec-less work by guesswork.

## Recommended workflow

| Step | Codex | Claude Code | Output |
|---|---|---|---|
| 0. Configure role models *(optional)* | `$initialize-review-loop` | `/init` | Strict blind mode, model routing, and findings ledger |
| 1. Confirm the work specification | `$draft-spec` | `/draft` | A repository-grounded spec with executable acceptance checks |
| 2. Develop, review, and repair | `$run-review-loop <goal>` | `/work <goal>` | Verified changes and a final verdict |
| 3. Inspect the completed run | `$loop-dashboard` or a natural-language request | Natural-language request | An offline HTML dashboard |

### 0. Initialize the loop *(optional)*

Choose the model used for each role: developer, fixer, reviewer, and final gate.

```text
# Codex
$initialize-review-loop

# Claude Code
/init
```

The selection and `"blind_mode": "strict"` are stored in `.agent-review/config.json`. If a configured model is unavailable, the loop stops instead of silently substituting another one.

### 1. Draft and confirm the specification

`draft-spec` first inspects the repository's `AGENTS.md` / `CLAUDE.md`, relevant code, tests, and established patterns. It then writes a work specification in which every acceptance criterion is paired with a command that can actually verify it, such as a test or a grep assertion.

```text
# Codex
$draft-spec add a per-vehicle fuel total API

# Claude Code
/draft add a per-vehicle fuel total API
```

Before you confirm the draft, an independent guess-hunt review looks for decisions that were assumed rather than grounded in the repository or your intent. The implementation loop does not start until you confirm the specification.

### 2. Run the loop with an explicit goal

The goal should cite the confirmed specification and state the verifiable outcome.

```text
# Codex
$run-review-loop implement the fuel-total API per docs/fleet-fuel-spec.md while preserving existing data and callers

# Claude Code
/work implement the fuel-total API per docs/fleet-fuel-spec.md while preserving existing data and callers
```

Each iteration follows the same sequence:

1. Implement the specification, unless the target diff already exists.
2. Create a unique blind reviewer and run `veriloop` across five focused passes.
3. Run the acceptance checks and inspect the review for `Failed` findings.
4. Repair verified failures, then review again.
5. Freeze the candidate, then create a different blind gate that generates new holdout probes after implementation.

### Strict blind mode *(default)*

Developers receive the specification and basic acceptance checks, but not review
reports, the review checklist, gate plans, holdout probes, or reviewer reasoning.
Every iteration reviewer and final gate is a new subagent. Each receives only the
repository, frozen target, confirmed specification, scope bounds, and risk focus;
the controller keeps the ledger and all prior history.

The final gate creates late-bound probes after the candidate is frozen: boundary and
invalid inputs, state ordering, failure injection, property/metamorphic or
differential behavior, and test-strength checks. It cannot modify the target
worktree. If the host cannot provide a clean subagent context, the loop stops and
asks whether you authorize reduced independence for that run only. Relaxed mode is
never persisted or inferred from an earlier approval.

### 3. Stop and inspect the result

The loop succeeds only when all of these conditions hold:

- Every executable acceptance check in the specification passes.
- The review verdict is `Pass` or `Pass with warnings`.
- The frozen snapshot is unchanged, every late-bound gate probe passes, and the gate finds no new `Failed` item.

The loop is capped at three iterations. If failures stop decreasing or recur, it escalates the decision to you. Warnings do not keep the loop running; each remaining warning is explicitly accepted, filed as follow-up work, or fixed now.

Completed runs are archived under `.agent-review/runs/`. `loop-dashboard` turns them into a self-contained HTML report showing retry causes, Failed/Warning trends, resolved findings, and goal verification—without an external CDN.

## Use only the piece you need

### Review the current change

Ask naturally or invoke `$veriloop` directly:

- “Review what the agent just changed.”
- “Check this diff before I commit.”
- “Is this branch safe to merge?”

Scope is resolved in this order: **a PR, commit range, or path you name → uncommitted changes → the current branch against the default branch's merge base**. Review mode does not modify code.

### Apply an existing review report

```text
$apply-review-findings
```

The skill re-verifies each `Failed` item against the actual code, repairs it, and reports resolved findings as `Pass`.

### Open a dashboard for previous runs

```text
$loop-dashboard
```

## The five review passes

| Pass | What it checks |
|---|---|
| **Regression** | Unupdated callers of changed symbols, broken serialization contracts, silently weakened tests |
| **Performance** | N+1 queries, I/O in loops, sync-over-async, unbounded reads, missing pagination |
| **Cost** | Traffic- or data-scaled API, LLM, SMS, map, egress, logging, and Cosmos DB RU costs |
| **Readability** | Narration comments, excessive defensive wrapping, speculative generality, dead code |
| **Conventions** | The current repository's rules, linters, and neighboring patterns—not generic best practice |

Every finding is rechecked against the code and marked `Confirmed` or `Needs verification`. Results are classified as `Failed` or `Warning` and roll up to `Pass`, `Pass with warnings`, or `Fail`. Checks that found nothing—and findings that have been fixed—are reported explicitly as `Pass`.

## Install

### Codex

```bash
codex plugin marketplace add dev-geon/veriloop
codex plugin add veriloop@veriloop
```

Start a new Codex task after installation so the bundled skills are discovered.

### Claude Code

```text
/plugin marketplace add dev-geon/veriloop
/plugin install veriloop@veriloop
```

No configuration is required. The plugin discovers the repository's conventions at review time.

## Run state and CI

| Path | Purpose |
|---|---|
| `.agent-review/config.json` | Per-role model routing |
| `.agent-review/ledger.json` | Finding state across iterations: open, Pass, recurred, accepted |
| `.agent-review/runs/` | Archived runs used by the dashboard |

Every review report ends with a machine-readable JSON block containing `verdict` and `findings[]`. See [docs/ci.md](docs/ci.md) for a GitHub Actions gate and a Claude Code Stop-hook recipe built on that contract.

> **Claude Code only:** To enforce a review on sessions that do not invoke the loop, add a Stop hook in your own Claude Code settings. Hooks are user-owned harness configuration, so the plugin documents this setup instead of installing it.

## Repository structure

<details>
<summary>Show plugin files</summary>

```text
.agents/plugins/marketplace.json  # Codex Git marketplace entry
.codex-plugin/plugin.json         # Codex plugin manifest
.claude-plugin/plugin.json        # Claude Code plugin manifest
commands/
├── init.md                       # Claude Code initialization command
├── draft.md                      # Claude Code specification command
└── work.md                       # Claude Code loop command
skills/
├── initialize-review-loop/       # Role-model routing and ledger setup
├── draft-spec/                   # Repository analysis → draft → confirmation
├── run-review-loop/              # Develop → review → repair → final gate
├── veriloop/                     # Independent five-pass blind review
├── apply-review-findings/        # Repair verified findings
└── loop-dashboard/               # Render run history as offline HTML
```

</details>

## License

MIT
