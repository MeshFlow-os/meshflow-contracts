# Release `meshflow-contracts`

This runbook is for the first public `meshflow-contracts` release. Version
`0.2.0` is prepared in source but is not published until every R0.9 check below
passes. Publishing uses PyPI Trusted Publishing (OIDC); do not create or use an
API token.

## Preconditions

Before tagging, verify all of the following:

- R0.6, R0.7a, R0.7b, and R0.8 are merged to `main`, and required CI is green.
- `pyproject.toml`, `meshflow_contracts.__version__`, and `uv.lock` all identify
  `0.2.0`; `CHANGELOG.md` describes that version.
- The public repository is `MeshFlow-os/meshflow-contracts`; package metadata
  names MeshFlow contributors and uses Apache-2.0.
- GitHub environment `pypi` exists with required manual approval.
- Remote tag protection covers `v*`.
- The PyPI Pending Publisher has this exact tuple:

  | Field | Value |
  |---|---|
  | PyPI project | `meshflow-contracts` |
  | GitHub owner | `MeshFlow-os` |
  | GitHub repository | `meshflow-contracts` |
  | Workflow | `release.yml` |
  | Environment | `pypi` |

The Pending Publisher was configured out of band but is not publicly
verifiable. The environment, tag protection, PyPI project, tag, and release do
not exist yet; R0.9 must verify or create each applicable gate before publishing.

## Tag And Publish

1. Start from an up-to-date, clean `main` after all release-readiness PRs merge.
2. Record the verified release commit SHA. Confirm CI and version sources at
   that exact commit.
3. Create annotated tag `v0.2.0` at that SHA and inspect its peeled commit before
   pushing it:

   ```bash
   git tag -a v0.2.0 <verified-main-sha> -m "meshflow-contracts 0.2.0"
   git rev-parse v0.2.0^{commit}
   git push origin refs/tags/v0.2.0
   ```

4. Treat the pushed tag as immutable. Never move, delete, or reuse a release tag.
5. In `release.yml`, the `build` job validates the annotated tag and versions,
   runs quality checks, builds once, verifies and smoke-tests the wheel and
   sdist, records `SHA256SUMS`, and uploads one short-lived workflow artifact.
6. Before approving the `publish` job in environment `pypi`, verify the run is
   for tag `v0.2.0`, its commit is the recorded SHA, and the build job succeeded.
7. The approved `publish` job downloads and reverifies the exact build artifact,
   revalidates the remote annotated tag, then publishes once through OIDC with
   PyPI attestations enabled and `skip-existing: false`.

Do not rerun a publish job merely to make it green. First determine whether PyPI
accepted either file.

## Verify The First Release

Complete these gates in order. Do not begin consumer adoption early:

1. Publish through the approved PyPI OIDC workflow described above.
2. Verify PyPI against the workflow-produced `SHA256SUMS` and retained workflow
   artifact evidence. The project page must show `0.2.0`, Apache-2.0, the
   expected Python requirement, project links, and these exact filenames:
   `meshflow_contracts-0.2.0-py3-none-any.whl` and
   `meshflow_contracts-0.2.0.tar.gz`. Download both files without installing
   them, confirm their SHA-256 values, and verify provenance/attestations for
   both files against the expected repository, workflow, tag, and commit. A
   clean environment must also install exactly `meshflow-contracts==0.2.0` from
   public PyPI and import it with `__version__ == "0.2.0"`.
3. Create a non-draft, non-prerelease GitHub Release for immutable tag `v0.2.0`
   at the verified commit. Attach the exact retained workflow wheel, sdist, and
   `SHA256SUMS`; do not rebuild them.
4. Re-download every GitHub Release asset. Confirm the wheel and sdist are byte
   for byte identical to the PyPI files and that all hashes match the retained
   workflow `SHA256SUMS`.
5. Only after all comparisons pass, mark the release verified and begin Core
   adoption.

## Failure Handling

| Failure point | Required response |
|---|---|
| Before any PyPI upload | Fix infrastructure and rerun only when the commit and tag are unchanged. If release content must change, use a new version and tag. |
| Partial publish | Stop and investigate PyPI state. Do not overwrite, delete, or blindly rerun. Decide the fix from the files PyPI accepted. |
| Bad published release | Yank the whole `0.2.0` release when appropriate and publish corrected version `0.2.1`. Normal unconstrained and range resolution avoids a yanked release, but an exact pin such as `==0.2.0` may still resolve and install it. Never overwrite or reuse release files, filenames, versions, or tags. |
| GitHub Release failure after PyPI succeeds | Create or repair the GitHub Release from the already verified same artifacts. Do not republish to PyPI. |

PyPI files are immutable. Recovery is always investigation or a versioned fix,
never replacement in place.

## Consumer Adoption

Adopt only after all first-release checks pass:

1. Core adds exact dependency `meshflow-contracts==0.2.0`, regenerates and
   commits its lockfile, and proves CI installs from that lock.
2. Core Docker builds use strict frozen synchronization so a build cannot update
   dependency resolution.
3. Core runs equivalence tests between imported contracts and duplicated local
   schemas before deleting any duplicate.
4. Gateway repeats the same exact-pin, lockfile, frozen-sync, and equivalence
   gates only after Core adoption is green.
5. Delete duplicated schemas only after equivalence and service regression tests
   pass. Upgrading the package alone must not enable runtime capability.

If an adopted release must be rolled back, pin the previous verified public
version and regenerate the lockfile. No such fallback exists for the first
public release until another version has actually been published.
