# Contract evaluation fixture

The fixture target must:

- normalize a valid ISO date without changing its value;
- calculate the same fleet total as the reference sum;
- issue one logical batch for a non-empty fleet and none for an empty fleet;
- use only the Python standard library.

Acceptance checks and late-bound probes must execute assertions against
`evals.fixtures.sample_project`. A held snapshot is the SHA-256 digest of the target
files listed by the contract case.
