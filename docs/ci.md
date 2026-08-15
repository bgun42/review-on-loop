# CI and hook integration

Veriloop publishes four JSON Schema contracts:

- `schemas/worker-result.schema.json` — developer and fixer completion output;
- `schemas/review-result.schema.json` — standalone review and PR gate output;
- `schemas/gate-result.schema.json` — late-bound final gate output;
- `schemas/run-result.schema.json` — archived `run.json` output.

Use native structured output when the host supports it. Otherwise require raw JSON and
validate it before reading the verdict. Never extract JSON from prose with a regular
expression.

## Worker completion protocol

Developer and fixer results use `worker-result.schema.json` so the controller can
distinguish a completed task from a partial response, failed tool call, timeout,
cancellation, context limit, or invalid result. The host's delegation/tool termination
status is authoritative and is checked before the response body.

Native structured output is preferred. When it is unavailable, the worker returns one
raw JSON object as its entire final response. The controller parses the whole response
with a JSON parser and validates the schema; it never extracts an object from prose with
a regular expression. One format-only retry may repair serialization without rerunning
tools or editing code. A second invalid result exits fail-closed as
`worker_result_invalid`.

`status: completed` advances only when `termination` is `completed`, every required
check passes with a valid exit code, `tool_failures` is empty, and `blocker` is null.
Blocked or failed results are archived but never advance to review or gate. This makes
JSON parse/schema errors an explicit stop condition rather than a false success.

The complete UTF-8 worker envelope is limited to 16 KiB. Evidence excerpts, tool
errors, and blocker messages are limited to 512 characters. Essential longer output
is stored outside the target worktree and referenced as an artifact with a verified
byte count and SHA-256 digest. The controller does not load successful-path artifacts
or pass them to reviewers and gates.

## Zero-cost controller contract regression

Run the dependency-free contract suite before publishing the plugin or changing the
review-loop instructions and schemas:

```bash
python3 evals/run_contract_evals.py
```

It checks three controller traces: a clean diff held by late-bound probes, a seeded
failure repaired before a fresh review identity, and a strict-blind capability failure
that exits before code changes. It also verifies an explicitly authorized reduced-mode
transition. Every fixture assertion runs against a checked-in target and specification,
and the frozen snapshot is the target's SHA-256 digest. Twenty-four deliberate negative
mutations cover result fabrication, stale acceptance checks, agent/context reuse,
leaked fixer context, target invalidation, no-progress bypass, unauthorized relaxation,
gate-failure bypass, holdout duplication, worker-role mismatch, host/body termination
contradictions, and substitution of unrelated fixer checks.

The same run exercises three worker termination exits, accepts seven valid
completed/blocked/failed worker envelopes, rejects twenty-one contradictory or
schema-invalid worker-result mutations, and checks six whole-response JSON fallback
paths including the single format-only retry and fail-closed second failure.

This suite validates controller state, recorded identities, allowlisted fields, schemas,
and executable fixture evidence. Because it does not call a model or control a host's
context delivery, it cannot prove that two recorded identities were truly separate
subagents or judge review quality. Run a live forward test with fresh subagents when
changing blind-context orchestration, reviewer prompts, or gate behavior.

## GitHub Actions — Codex

Set the repository variable `VERILOOP_SPEC_PATH` to the confirmed specification that
the reviewed branch implements. The job fails before model invocation when the path is
missing or untracked.

```yaml
name: Veriloop review
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    outputs:
      result: ${{ steps.run_codex.outputs.final-message }}
    env:
      CODEX_HOME: ${{ runner.temp }}/codex-home
      VERILOOP_SPEC_PATH: ${{ vars.VERILOOP_SPEC_PATH }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Install Codex and Veriloop
        run: |
          npm install -g @openai/codex
          codex plugin marketplace add dev-geon/veriloop
          codex plugin add veriloop@veriloop

      - name: Resolve the installed review schema
        id: veriloop
        shell: bash
        run: |
          plugin_root="$(codex plugin list --json | jq -er '.installed[] | select(.pluginId == "veriloop@veriloop") | .source.path')"
          schema="$plugin_root/schemas/review-result.schema.json"
          test -f "$schema"
          echo "review_schema=$schema" >> "$GITHUB_OUTPUT"

      - name: Verify the confirmed specification
        run: |
          test -n "$VERILOOP_SPEC_PATH"
          test -f "$VERILOOP_SPEC_PATH"
          git ls-files --error-unmatch "$VERILOOP_SPEC_PATH"

      - name: Run schema-constrained review
        id: run_codex
        uses: openai/codex-action@v1
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          codex-home: ${{ env.CODEX_HOME }}
          sandbox: workspace-write
          safety-strategy: drop-sudo
          codex-args: >-
            ["--ephemeral", "--output-schema", "${{ steps.veriloop.outputs.review_schema }}"]
          prompt: >-
            Use $veriloop to review this branch against
            origin/${{ github.base_ref }} using the confirmed specification at
            ${{ env.VERILOOP_SPEC_PATH }}. Return only the schema-conforming JSON
            object.

  gate:
    needs: review
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    env:
      REVIEW_JSON: ${{ needs.review.outputs.result }}
    steps:
      - name: Validate verdict semantics
        run: |
          printf '%s\n' "$REVIEW_JSON" | jq -e '
            (.verdict == "pass" and (.findings | length) == 0) or
            (.verdict == "pass_with_warnings" and (.findings | length) > 0 and all(.findings[]; .severity == "warning")) or
            (.verdict == "fail" and any(.findings[]; .severity == "failed"))
          '

      - name: Comment findings on the PR
        if: always() && env.REVIEW_JSON != ''
        env: { GH_TOKEN: "${{ github.token }}" }
        run: gh pr comment ${{ github.event.number }} --body "$REVIEW_JSON"

      - name: Gate on verdict
        run: printf '%s\n' "$REVIEW_JSON" | jq -e '.verdict == "pass" or .verdict == "pass_with_warnings"'
```

`--output-schema` constrains the final response before it reaches the shell. The
separate gate job checks the cross-field verdict rules with `jq -e`; a malformed,
missing, or contradictory result fails instead of being mistaken for a passing review.
The Codex action keeps the API key behind its proxy and runs Codex as the last step in
the review job.

## GitHub Actions — Claude Code

Claude Code does not use Codex's `--output-schema` flag. Ask for the same raw JSON
object, then validate `review.json` against a checked-in copy of
`schemas/review-result.schema.json` with the team's JSON Schema validator before the
shared `jq -e` verdict step.

```yaml
      - name: Run review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          test -n "$VERILOOP_SPEC_PATH"
          test -f "$VERILOOP_SPEC_PATH"
          claude -p "Use the veriloop skill to review this branch against origin/${{ github.base_ref }} using the confirmed specification at $VERILOOP_SPEC_PATH. Return only the JSON object defined by schemas/review-result.schema.json." \
            --output-format text > review.json

      - name: Validate and gate
        run: |
          npx --yes ajv-cli@5 validate --spec=draft2020 \
            -s schemas/review-result.schema.json -d review.json
          jq -e '
            (.verdict == "pass" and (.findings | length) == 0) or
            (.verdict == "pass_with_warnings" and (.findings | length) > 0 and all(.findings[]; .severity == "warning")) or
            (.verdict == "fail" and any(.findings[]; .severity == "failed"))
          ' review.json
          jq -e '.verdict == "pass" or .verdict == "pass_with_warnings"' review.json
```

Use the repository's existing JSON Schema validator instead of `ajv-cli` when one is
already installed. Keeping the schema in the repository pins the CI contract to a
reviewed version instead of silently following a marketplace update.

## Claude Code Stop hook

Hooks execute on the user's machine, so the plugin documents but does not install one.
This optional Stop hook asks for a review when code changed without one:

```jsonc
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "If code files changed and no Veriloop review covered the current diff, run the veriloop skill against its confirmed specification. If the verdict is fail, do not stop."
          }
        ]
      }
    ]
  }
}
```

Treat the hook as convenience, not the CI gate. CI owns the machine-readable verdict.
