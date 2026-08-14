# CI and hook integration

Every `veriloop` report ends with a machine-readable JSON block
(`verdict`, `findings[]`). That block is the integration surface: any CI job that can
run Codex or Claude Code headlessly can gate on it.

## GitHub Actions — fail the check on a Fail verdict

### Codex runner

Install and invoke the Codex version with:

```yaml
      - name: Install Codex + plugin
        run: |
          npm install -g @openai/codex
          codex plugin marketplace add dev-geon/veriloop
          codex plugin add veriloop@veriloop

      - name: Run review
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          codex exec --approve-for-me --ephemeral \
            --output-last-message review.json \
            'Use $veriloop to review this branch against origin/${{ github.base_ref }}. Output only the machine-readable JSON block.'
```

Use the shared “Gate on verdict” and “Comment findings” steps below after this runner.

### Claude Code runner

```yaml
name: Veriloop review
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
          claude plugin marketplace add dev-geon/veriloop
          claude plugin install veriloop@veriloop

      - name: Run review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Use the veriloop skill to review this branch against origin/${{ github.base_ref }}. Output only the machine-readable JSON block." \
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
            "prompt": "If code files were modified this session and no veriloop review ran on those changes, run the veriloop skill now. If its verdict is fail, do not stop — apply the review findings first."
          }
        ]
      }
    ]
  }
}
```

This makes the review a harness-enforced gate rather than a habit the model must
remember. It is Claude Code-specific: OpenAI's conversion path does not support prompt
or agent hook handlers in Codex. See the Claude Code hooks documentation for the exact
hook schema in your version.
