# Release `meshflow-contracts`

This runbook records the recovery boundary for the first public release. It does not authorize tagging, publishing, creating a GitHub Release, or adopting the package in a consumer.

## Failed `v0.2.0` History

`v0.2.0` remains an immutable failed, unpublished tag. Never move, delete, reuse, retag, publish, or create a GitHub Release for it.
The verifier correctly rejected the build because uv added `dist/.gitignore` beside the wheel and sdist; recovery fixes the build invocation rather than weakening the exact artifact allowlist.

The recovery candidate is `0.2.1`. Its release build uses:

```bash
uv build --clear --no-create-gitignore --build-constraints build-constraints.txt --require-hashes
```

Do not run that command as an operator release substitute. The real build-to-verifier-to-smoke regression and release candidate must run in isolated, non-publishing CI.

## Recovery Gate

After the complete automation is merged, record the successful `Release dry run` push run ID and exact merged `main` SHA. Before any tag operation, verify the run used `.github/workflows/release-dry-run.yml`, has `event=push`, `head_branch=main`, the exact candidate `head_sha`, `status=completed`, and `conclusion=success`.

Only after that evidence exists may separately authorized operators create an annotated tag whose message contains exactly one `dry-run-run-id: <id>` line and whose target is that SHA. Verify the run's `updated_at` is not later than the annotated tag's `tagger.date`. This ordering is auditable evidence, not cryptographic proof of local tag creation time.

Tag creation and push, PyPI publication, and any GitHub Release remain outside this work unit and require later explicit irreversible authorization. The `pypi` environment must retain required-reviewer approval. Never substitute a local operator build.

If dry-run fails, diagnose it and merge a corrective PR so a new main SHA gets a new run. A pre-publish failure may be retried only after diagnosis when source, tag, and artifacts are unchanged; source correction requires a later patch. For partial PyPI publication or a post-PyPI failure, inspect remote state before acting and never overwrite, retag, manually upload, or blindly rerun.

CI actionlint is commit-pinned and time-bounded, with ShellCheck enabled for multiline release shell. Its pinned actionlint binary and any missing ShellCheck package are still transitive downloads, but the job is read-only and has no environment, OIDC, secret, or publish authority.

## Consumer Adoption

Consumers must not adopt `0.2.1` until the public wheel, sdist, hashes, and
provenance are verified. Core adopts `0.2.1` before Gateway. Each consumer must
pin the exact verified version, regenerate its lockfile, use frozen installs,
and prove schema equivalence before deleting duplicated contracts or enabling
runtime behavior.
