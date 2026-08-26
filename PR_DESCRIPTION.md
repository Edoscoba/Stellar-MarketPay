## Summary

This PR adds the formal verification subsystem for the Soroban escrow contract and fixes the CI issues needed to run it reliably.

The change introduces:

- a new `contracts/marketpay-spec` crate containing:
  - formal invariants for value conservation, exact settlement, authorisation, no dust, and single settlement
  - the escrow transition relation, including multisig and arbitration paths
  - an executable reference model
  - bounded model checking and Kani proof harnesses
- new contract-side verification suites in `contracts/marketpay-contract/tests/`:
  - differential tests against the specification model
  - committed regression tests for counterexamples/findings
  - invariant-guided fuzzing
- published audit-facing documentation:
  - `docs/SPECIFICATION.md`
  - `docs/VERIFICATION.md`
- CI wiring for the verification workflow in `.github/workflows/verification.yml`

It also fixes two immediate CI blockers:

1. `Party::Panel` was added to the specification but not handled in the shared contract test harness, which broke all integration-style contract verification tests at compile time.
2. The Kani workflow attempted to parse `kani-list.json` without ever creating the file. The workflow now writes the harness list to disk before reading it.

## Type of change

- [x] Bug fix
- [ ] New feature
- [x] Documentation
- [x] Refactor or maintenance
- [x] Smart contract change

## Related issue

Closes #<!-- add issue number -->

## Scope and impact

- [ ] Frontend
- [ ] Backend or API
- [x] Soroban contract
- [ ] Database or migration
- [ ] Documentation only

Compatibility impact: none intended at the external API level. This change adds specification, verification, CI, and regression coverage around existing escrow behavior, plus fixes implementation/spec mismatches surfaced by that work.

## Testing

- [ ] Tested locally on Testnet, or not applicable
- [x] No TypeScript / Rust errors, or not applicable
- [x] Docs updated if needed, or not applicable

Local validation completed on Wednesday, August 26, 2026:

- `contracts/marketpay-spec`
  - `cargo clippy --all-targets -- -D warnings`
  - `cargo check --no-default-features`
  - `cargo test --release -- --nocapture`
- `contracts/marketpay-contract`
  - `cargo test --features std`
  - `cargo clippy --all-targets --features std -- -D warnings`
  - `cargo check --target wasm32-unknown-unknown`
  - `cargo audit --ignore RUSTSEC-2020-0071`
- `frontend`
  - `npm test`
  - `npm run test:a11y`
  - `npm run type-check`
  - `npm run lint`
  - `npm run build`
- `backend`
  - `npm run lint`
  - `npm run build`
  - Node 24 plugin sandbox/service tests pass

Known local limitation:

- the full backend integration suite depends on CI-style Postgres/Redis service availability and valid local test DB auth; on this host those tests fail with `password authentication failed for user "test"`, so they should be judged from CI rather than this workstation.

## Validation

- [x] Unit or integration tests run, or not applicable with an explanation
- [x] Frontend accessibility checked, or not applicable
- [x] Backend/API behavior checked, or not applicable
- [x] Soroban contract tests and clippy run, or not applicable
- [x] Documentation and examples checked

## Compatibility and operations

- [x] No breaking changes
- [ ] Breaking changes are documented below
- [x] Database or storage migrations are backward compatible, or the migration plan is documented below
- [x] Deployment, configuration, or rollback notes are included below when needed

Deployment/configuration notes:

- verification is split by cost:
  - bounded model checking, differential tests, regressions, and pull-request-budget fuzzing run in CI
  - Kani and deeper fuzzing run on schedule, manual dispatch, and explicitly labelled PRs
- changing a fund-moving contract entrypoint now requires corresponding specification updates
- counterexamples are meant to be committed back as regression tests

Rollback:

- revert this PR to remove the specification crate, verification workflow, and regression suites
- no storage migration rollback is required

## Screenshots

Not applicable.

## Additional context

- The branch fixes the immediate compile break around `Party::Panel` in `contracts/marketpay-contract/tests/harness.rs`.
- The branch fixes the verification workflow harness discovery bug in `.github/workflows/verification.yml`.
- If reviewers want a sequence-of-PR landing strategy, this branch can be split conceptually into:
  1. specification + docs
  2. differential/regression/fuzz suites
  3. CI wiring
