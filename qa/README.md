# Repeatable Release QA

Prepza now treats QA as a **code-traced release system**, not a collection of unrelated test files.

The source of truth is `qa/release_manifest.json`. Each release-scoped feature declares the layers that must be traceable:

1. frontend entry/consumer
2. backend route
3. backend business logic
4. database model/schema
5. executable runtime/browser tests
6. CI coverage

`scripts/qa_trace.py` verifies those links exist. It does **not** claim source presence proves correctness; runtime correctness still comes from the declared tests.

## Release rule

A feature cannot be called GREEN merely because its source files exist.

GREEN requires traceable source, real runtime tests, passing results, CI evidence where applicable, browser evidence where the feature crosses the real UI, and integration evidence for subsystem boundaries.

Features intentionally not ready are explicitly marked instead of silently omitted.

## Local use

`python scripts/qa_trace.py`

For structural failures to stop the command:

`python scripts/qa_trace.py --strict`

Runtime commands remain separate because the local Docker/PostgreSQL environment is required for integration gates.

## Release loop

change code
→ update/verify trace
→ run focused runtime tests
→ run affected integration/browser tests
→ run release regression
→ record commit + CI result
→ release or stop

This follows the mature engineering principle of layered, repeatable testing and automated release gates. AWS recommends combining unit/integration/acceptance/security/performance testing as appropriate and stopping later release stages when earlier gates fail. Microsoft recommends writing tests at the lowest practical level and reusing the same tests across environments.
