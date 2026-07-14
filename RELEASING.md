# Release `meshflow-contracts`

This runbook records the recovery boundary for the first public release. It does not authorize tagging, publishing, creating a GitHub Release, or adopting the package in a consumer.

## Failed release history

`v0.2.0`, `v0.2.1`, and `v0.2.2` remain immutable failed, unpublished tags. Never move,
delete, reuse, rerun, retag, publish, or create a GitHub Release for any of them.
The verifier correctly rejected the build because uv added `dist/.gitignore` beside the wheel and sdist; recovery fixes the build invocation rather than weakening the exact artifact allowlist.

The recovery candidate is `0.2.3`. Its release build uses:

```bash
uv build --clear --no-create-gitignore --build-constraints build-constraints.txt --require-hashes
```

Do not run that command as an operator release substitute. The real build-to-verifier-to-smoke regression and release candidate must run in isolated, non-publishing CI.

## Recovery Gate

After the complete automation is merged, run a fresh successful `Release dry run`
for `v0.2.3` from the exact merged `main` SHA. Record its push run ID and verify the run used
`.github/workflows/release-dry-run.yml`, has `event=push`, `head_branch=main`,
the exact candidate `head_sha`, `status=completed`, and `conclusion=success`.

Only after that evidence exists may separately authorized operators create an annotated tag whose message contains exactly one `dry-run-run-id: <id>` line and whose target is that SHA. Verify the run's `updated_at` is not later than the annotated tag's `tagger.date`. This ordering is auditable evidence, not cryptographic proof of local tag creation time.

Tag creation and push, PyPI publication, and any GitHub Release remain outside this work unit and require later explicit irreversible authorization. The `pypi` environment must retain required-reviewer approval. Never substitute a local operator build.

If dry-run fails, diagnose it and merge a corrective PR so a new main SHA gets a
new run. Never rerun or reuse a failed release candidate. For partial PyPI
publication or a post-PyPI failure, inspect remote state before acting and
never overwrite, retag, manually upload, or blindly rerun. Attestations are generated
only by the publish action and must be verified with the public wheel, sdist,
and hashes afterward.

CI actionlint is commit-pinned and time-bounded, with ShellCheck enabled for multiline release shell. Its pinned actionlint binary and any missing ShellCheck package are still transitive downloads, but the job is read-only and has no environment, OIDC, secret, or publish authority.

## Consumer Adoption

Consumers must not adopt `0.2.3` until the public wheel, sdist, hashes, and
provenance are verified. Core adopts `0.2.3` before Gateway. Each consumer must
pin the exact verified version, regenerate its lockfile, use frozen installs,
and prove schema equivalence before deleting duplicated contracts or enabling
runtime behavior.
