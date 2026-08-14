# CI and hook integration

Every `agent-work-review` report ends with a machine-readable JSON block
(`verdict`, `findings[]`). That block is the integration surface: anything that can
run Claude Code headless can gate on it.

## GitHub Actions — fail the check on a Fail verdict

```yaml
name: agent-work-review
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - name: Install Claude Code + plugin
        run: |
          npm install -g @anthropic-ai/claude-code
          claude plugin marketplace add <owner>/review-on-loop
          claude plugin install agent-work-review@review-on-loop

      - name: Run review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Use the agent-work-review skill to review this branch against origin/${{ github.base_ref }}. Output only the machine-readable JSON block." \
            --output-format text > review.json

      - name: Gate on verdict
        run: |
          python - <<'EOF'
          import json, re, sys
          text = open('review.json', encoding='utf-8').read()
          m = re.search(r'\{[\s\S]*\}', text)
          if not m: sys.exit("no machine-readable block found")
          r = json.loads(m.group(0))
          print(f"verdict: {r['verdict']}, findings: {len(r['findings'])}")
          sys.exit(1 if r['verdict'] == 'fail' else 0)
          EOF

      - name: Comment findings on the PR
        if: always()
        env: { GH_TOKEN: ${{ github.token }} }
        run: gh pr comment ${{ github.event.number }} --body-file review.json
```

Adapt the checkout ref, model, and comment formatting to taste — the contract is only
the JSON block. If the repo carries `.agent-review/ledger.json`, findings marked
`accepted` there should not fail the gate.

## Claude Code Stop hook — block session completion on Failed findings

Per-user setting (`~/.claude/settings.json` or project `.claude/settings.json`), not
shipped by this plugin — hooks execute on the user's machine and belong to the user:

```jsonc
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "If code files were modified this session and no agent-work-review ran on those changes, run the agent-work-review skill now. If its verdict is fail, do not stop — apply the review findings first."
          }
        ]
      }
    ]
  }
}
```

This makes the review a harness-enforced gate rather than a habit the model must
remember. See the Claude Code hooks documentation for the exact hook schema in your
version.
