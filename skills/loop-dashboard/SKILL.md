---
name: loop-dashboard
description: >
  Render a run-review-loop run (or any sequence of review iterations) as a single-file,
  self-contained HTML dashboard: what caused each retry, what was fixed and now passes,
  Failed/Warning trend charts, and goal-verification results — readable at a glance.
  Use whenever the user wants to visualize review-loop history, see loop results as a
  dashboard, "루프 결과 대시보드로 보여줘", "리뷰 이력 시각화해줘", or after run-review-loop
  finishes and the user accepts the dashboard offer. Data comes from the
  conversation's loop history or, when that is gone, from the archived run under
  `.agent-review/runs/NNN/`.
---

# Loop Dashboard

Turn the history of a review loop into one HTML file a human can absorb in ten
seconds: did it converge, what blocked each iteration, and what is now Pass.

## Input

Gather from the conversation or from saved loop artifacts (review reports, fix
reports, and `.agent-review/ledger.json` when present — the ledger is the most
reliable source for finding statuses across iterations, including `accepted`
warnings): the goal contract (goal, acceptance criteria, scope bounds), and per
iteration — verdict, findings (severity, title, file, confidence), and fix statuses
(Pass / skipped). Use real data only; if something is unknown, omit the element rather
than inventing numbers.

## Output

ONE `.html` file (descriptive kebab-case name, saved where the user works or asks).
Fully self-contained: **inline CSS, inline JS, inline SVG charts — zero external
requests** (no CDN scripts, fonts, or images). This is what makes the file portable:
it opens offline, attaches to email, and renders under strict content-security
policies where CDN-based pages go blank.

## Layout (top to bottom)

1. **Header** — dashboard title, the goal in one sentence, and a large final-verdict
   badge (Pass / Pass with warnings / Fail) plus the exit reason (goal met /
   iteration cap / no progress).
2. **KPI row** — 4 stat cards: iterations run, Failed findings resolved (now Pass),
   warnings remaining, acceptance criteria passed (n/m). Big number (≥2rem bold),
   small label.
3. **Trend chart** — findings per iteration as a grouped/stacked bar chart (inline
   SVG): Failed and Warning counts per iteration, chronological left → right so the
   downward trend reads as improvement. Label each bar with its count; add the
   verdict under each iteration's axis label.
4. **Iteration cards** — one card per iteration, in order. Each card answers "why did
   we retry?": the verdict, then each finding as a row — severity chip (Failed /
   Warning), title, `file:line` — and its outcome chip (**Pass** once fixed, or
   "open"). The next iteration's card should visibly show those rows gone.
5. **Goal verification table** — each acceptance criterion with a Pass/Fail chip and
   its one-line evidence.

## Design rules

- **Semantic colors only where they mean something**: Failed = red family, Warning =
  amber, Pass = green, neutral text otherwise. Never decorate numbers with color that
  has no meaning.
- **Theme**: define color tokens as CSS custom properties on `:root` (light values),
  override under `@media (prefers-color-scheme: dark)`. Every color in the page goes
  through a token — no hardcoded hexes in content markup. Verify mentally that all
  text is readable on both themes.
- **Charts as inline SVG**: compute bar heights from the data yourself; include axis
  labels and value labels in `<text>` elements so nothing depends on JS executing.
  Wrap each chart in a container with `role="img"` and a descriptive `aria-label`.
- **Typography**: system font stack (`-apple-system, "Segoe UI", "Noto Sans KR",
  sans-serif` — covers Korean without webfont downloads); clear size hierarchy
  (h1 > h2 > body ≥ 16px); big stat numbers.
- **Responsive**: CSS grid with `repeat(auto-fit, minmax(280px, 1fr))` for cards; the
  page must not scroll horizontally at 375px width — wide charts scroll inside their
  own `overflow-x: auto` container.
- **Visual restraint**: no decorative animations, gradients-for-gradients'-sake, or
  emoji icons. The data is the design. One accent color plus the three semantic
  colors is enough.
- Write all user-facing text in the language the user is conversing in.

## After writing the file

Tell the user the absolute path as a clickable Markdown file link and, when the
environment can, open or send the file so they see it immediately.
