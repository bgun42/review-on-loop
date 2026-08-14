---
description: Initialize Veriloop for this repository — per-role model configuration, ledger scaffolding, and the optional convention-baseline cache
argument-hint: [optional role=model pairs, e.g. "reviewer=opus developer=sonnet"]
---

# Init

Set up `.agent-review/` in the current repository so the review skills and the
`/work` command run with the user's own choices — especially which model each
loop role uses. Nothing here is mandatory: every skill in this plugin works without
initialization, on the session model. Init exists so the user can be deliberate.
Strict blind review remains the default with or without initialization.

Arguments: $ARGUMENTS

## 1. Explain the roles (briefly, once)

| Role | What it does | Where it runs |
|---|---|---|
| `developer` | implements toward the goal (loop step 1) | fresh subagent |
| `fixer` | applies review findings (`apply-review-findings`) | fresh subagent |
| `reviewer` | the per-iteration five-pass review | fresh subagent |
| `gate` | the independent final confirmation before success | fresh subagent |

## 2. Resolve the model for each role

- If the arguments contain `role=model` pairs, use them.
- Otherwise ask the user, one question, listing the choices: `inherit` (= whatever
  model the session runs on — the default), a tier alias the harness accepts (e.g.
  `haiku`, `sonnet`, `opus`), or a full model id. Which models are actually available
  depends on the user's plan and harness — do not present a hardcoded menu as
  exhaustive, and accept whatever the user names.
- Any role the user doesn't care about stays `inherit`.

## 3. Write the config

Create `.agent-review/config.json`:

```json
{
  "blind_mode": "strict",
  "models": {
    "developer": "inherit",
    "fixer": "inherit",
    "reviewer": "opus",
    "gate": "opus"
  }
}
```

`strict` is the only value that may be saved. Never persist relaxed mode. When the
host cannot provide a unique clean reviewer or gate context, `/work` pauses and asks
the user for a one-run relaxation; previous approval never carries forward.

Also scaffold `.agent-review/ledger.json` (`{"findings": []}`) if absent, and suggest
gitignoring `ledger.json` while noting `config.json` and `baseline.md` are worth
committing — they encode team decisions.

## 4. Sanity check — warn, never override

Compare tiers where both sides are known (order: haiku < sonnet < opus < top-tier
ids; `inherit` or an unrecognized id → skip the comparison). If the `reviewer` or
`gate` lands on a **weaker** tier than `developer`/`fixer`, tell the user once, plainly:

> 리뷰어가 개발 모델보다 약합니다. 루프는 심판의 기준으로 수렴하므로, 약한 심판은
> 강한 개발자가 만든 결함을 놓친 채 Pass를 선언할 수 있습니다. 설정은 그대로
> 적용합니다.

Then apply the configuration exactly as given. The user's choice is authoritative —
this is a warning, not a gate. (The commonly useful setup, for reference: strongest
available model on `reviewer`/`gate`, session or mid-tier on `developer`/`fixer`.)

## 5. Confirm

Show strict blind mode, the final per-role table, and where it was written, in the
language the user is conversing in.
