---
name: initialize-review-loop
description: Initialize Veriloop in the current repository by creating optional per-role model configuration, strict blind review defaults, and the findings ledger. Use when the user asks to set up, configure, initialize, or choose developer, fixer, reviewer, or gate models for the review loop. Do not use merely to run a review or start a loop.
---

# Initialize Review Loop

Set up the optional .agent-review/ state used by run-review-loop. Every bundled
skill works without this initialization and inherits the current session model.

## Resolve role models

Configure these roles:

| Role | Responsibility |
|---|---|
| developer | Implement toward the confirmed specification and goal |
| fixer | Apply verified review findings |
| reviewer | Run the per-iteration five-pass review |
| gate | Independently confirm the success candidate |

Accept inherit or an exact model identifier supported by the current host. Default
every unspecified role to inherit. Do not invent provider-specific aliases, replace
an unavailable model with another model, or assume a model-strength ordering.

If the user supplied role/model pairs, use them. Otherwise ask one concise question
for the desired overrides; keeping every role on inherit is the recommended default.
When the host exposes model availability, validate exact identifiers before writing.
If it does not, preserve the user's identifier and state that availability was not
validated.

## Write state

Create or update .agent-review/config.json with this shape:

    {
      "blind_mode": "strict",
      "models": {
        "developer": "inherit",
        "fixer": "inherit",
        "reviewer": "inherit",
        "gate": "inherit"
      }
    }

Create .agent-review/ledger.json with {"findings": []} only when it is absent.
Never overwrite an existing ledger.

`strict` is the only persistent blind mode. Do not write a relaxed default. If a host
cannot create clean reviewer or gate contexts, `run-review-loop` must stop and request
explicit user approval for a one-run relaxation.

If the host provides a reliable strength comparison and a configured reviewer or gate
is weaker than the developer or fixer, warn once without changing the configuration.
Otherwise skip the comparison instead of guessing.

Suggest ignoring the run archive and ledger when they are personal scratch state.
Explain that teams may instead commit config.json and a convention baseline because
those encode shared decisions. Do not edit ignore files unless the user asks.

Report strict blind mode, the final role table, and the paths written in the user's
language.
