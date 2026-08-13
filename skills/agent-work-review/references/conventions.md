# Convention Review

Goal: verify the diff looks like it was written by the team that owns the repository.
The standard is *this repository's* established practice — discovered, not assumed.
Generic best practice is explicitly not the standard here: a repo that consistently
uses a pattern you consider outdated has made its choice, and a diff that follows it is
correct, while a diff that unilaterally "improves" on it is the violation.

## Why this pass matters for agent code

An agent carries habits from its training data: it will introduce its favorite error-
handling style, its favorite folder layout, its favorite test framework idioms — each
reasonable in isolation, each a divergence. A codebase where every agent session adds
its own dialect becomes unmaintainable even if every individual change "works". The
review's job is to keep one dialect.

## Building the baseline (done in Step 2 of the skill — verify it covered these)

Sources, in order of authority:

1. **Explicit house rules** — `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, docs/ style
   guides, PR templates. These are contracts; a violation here is automatically at
   least **Major**, because the team wrote the rule down precisely so it would be
   enforced.
2. **Enforced tooling** — linter/formatter/analyzer configs. If a rule is configured,
   run the tool on the changed files rather than eyeballing (it's faster and exact).
3. **The neighbors** — the 2–3 sibling files of each changed file. This is the binding
   precedent for everything unwritten: layering, naming, error handling, DI, test
   structure. When the repo is inconsistent, the nearest neighbors and the newest code
   win — do not flag a diff for matching the file it sits in.
4. **Language default baseline** — only for points where sources 1–3 are silent. For
   C#, use `csharp-conventions.md` (the Microsoft/.NET-runtime baseline). For other
   languages, fall back to the language's dominant community standard (PEP 8 for
   Python, etc.) and say so in the finding.

## What to compare

- **Placement & layering.** Does new code sit where this repo puts that kind of code
  (controller/service/repository split, feature folders, test file location and
  naming)? Does it respect layer direction — e.g., if no other controller talks to the
  database directly, a new one that does is a finding even if it works.
- **Naming schemes.** Casing, prefixes/suffixes (`IThing`, `ThingService`, `useThing`,
  `thing.spec.ts` vs `thing.test.ts`), pluralization, domain vocabulary. Match the
  diff's names against the sibling files' names.
- **Error handling.** Whatever the repo does — exceptions vs Result types, error
  hierarchies, logging-and-rethrow patterns, error response shapes — the diff must do
  the same. Mixed error dialects are among the most expensive conventions to unwind
  later, because callers encode the dialect.
- **Established mechanisms reinvented.** Before accepting a new helper/util/wrapper,
  search the repo for an existing one that does the job (HTTP client factories, date
  handling, config access, pagination helpers, base classes, test fixtures). An agent
  that didn't find the existing mechanism will write a second one; two mechanisms for
  one job is a standing source of bugs. Point the diff at the existing mechanism.
- **Dependency discipline.** A new package/library dependency the repo didn't have is a
  decision, not a detail — flag it so a human confirms it (license, maintenance,
  overlap with an existing dependency).
- **Framework idioms.** DI registration style, async conventions, ORM usage patterns,
  test arrange/act/assert shape, fixture/mocking library — match what's there.

## How to report a convention finding

Always cite the precedent: the rule file and line, or the sibling file that does it the
established way. "`CLAUDE.md` says services never open their own connections" or "the
other 14 repositories in this folder inherit `RepositoryBase`; this one doesn't" is a
finding. "I would structure this differently" is not. If you cannot cite a precedent,
it belongs in readability (or nowhere).

## Severity guidance

- Violation of a written house rule, or a second mechanism duplicating an established
  one → **Major**.
- Divergence from consistent sibling precedent (naming, placement, error dialect) →
  **Minor**.
- Divergence where the repo itself is already inconsistent → **Nit**, or silence.
