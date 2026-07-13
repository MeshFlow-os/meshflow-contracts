# Release `meshflow-contracts`

This runbook records the recovery boundary for the first public release. It does
not authorize tagging, publishing, creating a GitHub Release, or adopting the
package in a consumer.

## Failed `v0.2.0` History

`v0.2.0` remains an immutable failed, unpublished tag. Never move, delete,
reuse, retag, publish, or create a GitHub Release for it. The verifier correctly
rejected the build because uv added `dist/.gitignore` beside the wheel and
sdist; recovery fixes the build invocation rather than weakening the exact
artifact allowlist.

The recovery candidate is `0.2.1`. Its release build uses:

```bash
uv build --clear --no-create-gitignore --build-constraints build-constraints.txt --require-hashes
```

Do not run that command as an operator release substitute. The real
build-to-verifier-to-smoke regression and release candidate must run in isolated,
non-publishing CI.

## Recovery Gate

Keep all release operations blocked until the reusable dry-run and release
workflow isolation lands and passes review. A failure requires diagnosis and a
corrective PR or later patch; do not blindly rerun, overwrite, or mutate tagged
or published history.

After the complete release automation is merged, the exact merged `main` SHA
must pass the non-publishing dry-run before any annotated `v0.2.1` tag can be
authorized. PyPI publication and GitHub Release creation require separate,
explicit irreversible authorization.

## Consumer Adoption

Consumers must not adopt `0.2.1` until the public wheel, sdist, hashes, and
provenance are verified. Core adopts `0.2.1` before Gateway. Each consumer must
pin the exact verified version, regenerate its lockfile, use frozen installs,
and prove schema equivalence before deleting duplicated contracts or enabling
runtime behavior.
