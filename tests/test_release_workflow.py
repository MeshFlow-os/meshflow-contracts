import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/release.yml"
BUILD_PATH = ROOT / ".github/workflows/release-build.yml"
DRY_RUN_PATH = ROOT / ".github/workflows/release-dry-run.yml"
CI_PATH = ROOT / ".github/workflows/ci.yml"
RELEASING_PATH = ROOT / "RELEASING.md"
TAG_IDENTITY_PATH = ROOT / ".github/scripts/release-tag-identity.sh"

BUILDER_COMMANDS = (
    ("Sync locked dependencies", "uv sync --locked --all-groups"),
    ("Run quality checks", "uv run --frozen pytest"),
    ("Run quality checks", "uv run --frozen ruff check ."),
    ("Run quality checks", "uv run --frozen mypy meshflow_contracts tests"),
    (
        "Build release artifacts once",
        "uv build --clear --no-create-gitignore --build-constraints "
        "build-constraints.txt --require-hashes",
    ),
    ("Verify and smoke-test release artifacts", "uv run --frozen python release_artifacts.py dist"),
    ("Verify and smoke-test release artifacts", "uv venv --clear --python 3.14.3 .smoke-wheel"),
    (
        "Verify and smoke-test release artifacts",
        'uv pip install --python .smoke-wheel/bin/python "dist/$WHEEL"',
    ),
    ("Verify and smoke-test release artifacts", "mkdir smoke-cwd"),
    ("Verify and smoke-test release artifacts", 'repo="$PWD"'),
    (
        "Verify and smoke-test release artifacts",
        '(cd smoke-cwd && EXPECTED_VERSION="$VERSION" "$repo/.smoke-wheel/bin/python" -c '
        "'import os, sys; from pathlib import Path; import meshflow_contracts; assert "
        'meshflow_contracts.__version__ == os.environ["EXPECTED_VERSION"]; assert '
        "Path(meshflow_contracts.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())')",
    ),
    ("Verify and smoke-test release artifacts", "uv venv --clear --python 3.14.3 .smoke-sdist"),
    (
        "Verify and smoke-test release artifacts",
        "uv pip install --python .smoke-sdist/bin/python --build-constraints "
        'build-constraints.txt "dist/$SDIST"',
    ),
    (
        "Verify and smoke-test release artifacts",
        '(cd smoke-cwd && EXPECTED_VERSION="$VERSION" "$repo/.smoke-sdist/bin/python" -c '
        "'import os, sys; from pathlib import Path; import meshflow_contracts; assert "
        'meshflow_contracts.__version__ == os.environ["EXPECTED_VERSION"]; assert '
        "Path(meshflow_contracts.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())')",
    ),
    ("Verify and smoke-test release artifacts", "mkdir release"),
    ("Verify and smoke-test release artifacts", 'cp "dist/$WHEEL" "dist/$SDIST" release/'),
    (
        "Verify and smoke-test release artifacts",
        '(cd release && sha256sum "$WHEEL" "$SDIST" > SHA256SUMS)',
    ),
)


class WorkflowLoader(yaml.SafeLoader):
    pass


WorkflowLoader.yaml_implicit_resolvers = {
    key: [rule for rule in rules if rule[0] != "tag:yaml.org,2002:bool"]
    for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def workflow() -> dict[str, Any]:
    return load_workflow(WORKFLOW_PATH)


def load_workflow(path: Path) -> dict[str, Any]:
    parsed = yaml.load(path.read_text(), Loader=WorkflowLoader)
    assert isinstance(parsed, dict)
    return parsed


def package_version_script() -> str:
    run = cast(
        str,
        next(
            step["run"]
            for step in load_workflow(BUILD_PATH)["jobs"]["build"]["steps"]
            if step["name"] == "Validate package version sources"
        ),
    )
    script = run.split("<<'PY'\n", 1)[1]
    return textwrap.dedent("\n".join(line for line in script.splitlines() if line.strip() != "PY"))


def execute_package_version_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str, source_version: str | None = None
) -> tuple[str, str]:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "meshflow-contracts"\nversion = {json.dumps(version)}\n'
    )
    (tmp_path / "uv.lock").write_text(
        f'[[package]]\nname = "meshflow-contracts"\nversion = {json.dumps(version)}\n'
    )
    github_env = tmp_path / "github-env"
    github_output = tmp_path / "github-output"
    package = ModuleType("meshflow_contracts")
    setattr(package, "__version__", source_version or version)
    artifacts = ModuleType("release_artifacts")
    setattr(artifacts, "VERSION", version)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_ENV", str(github_env))
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setitem(sys.modules, "meshflow_contracts", package)
    monkeypatch.setitem(sys.modules, "release_artifacts", artifacts)
    exec(compile(package_version_script(), "package-version.py", "exec", optimize=1), {})
    return github_env.read_text(), github_output.read_text()


def steps(job: str) -> list[dict[str, Any]]:
    source = load_workflow(BUILD_PATH) if job == "build" else workflow()
    return cast(list[dict[str, Any]], source["jobs"][job]["steps"])


def step_index(job_steps: list[dict[str, Any]], name: str) -> int:
    return next(index for index, step in enumerate(job_steps) if step["name"] == name)


def assert_closed_job(
    job: dict[str, Any], keys: set[str], step_keys: list[set[str]]
) -> None:
    assert set(job) == keys
    assert "if" not in job and "continue-on-error" not in job
    assert [set(step) for step in job.get("steps", [])] == step_keys
    assert all("if" not in step and "continue-on-error" not in step for step in job.get("steps", []))


def assert_release_structure(config: dict[str, Any]) -> None:
    jobs = config["jobs"]
    assert_closed_job(
        jobs["gate"],
        {"runs-on", "timeout-minutes", "permissions", "steps"},
        [{"name", "uses", "with"}, {"name", "env", "run"}],
    )
    assert jobs["build"] == {
        "needs": "gate",
        "permissions": {"contents": "read"},
        "uses": "./.github/workflows/release-build.yml",
    }
    assert_closed_job(
        jobs["publish"],
        {"needs", "runs-on", "timeout-minutes", "environment", "permissions", "steps"},
        [
            {"name", "uses", "with"},
            {"name", "uses", "with"},
            {"name", "run"},
            {"name", "uses", "with"},
        ],
    )
    publish_steps = jobs["publish"]["steps"]
    assert [step["name"] for step in publish_steps] == [
        "Check out verifier at exact release commit",
        "Download exact build artifact",
        "Reverify downloaded artifacts",
        "Publish once with PyPI Trusted Publishing",
    ]
    assert [step.get("uses") for step in publish_steps if "uses" in step] == [
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b",
    ]
    text = str(publish_steps).lower()
    assert not any(route in text for route in ("uv publish", "twine upload", "pip install", "password", "__token__"))


def assert_actionlint_structure(job: dict[str, Any]) -> None:
    assert_closed_job(
        job,
        {"name", "runs-on", "timeout-minutes", "permissions", "steps"},
        [{"name", "uses", "with"}, {"name", "uses", "with"}],
    )
    assert (job["name"], job["runs-on"], job["timeout-minutes"], job["permissions"]) == ("actionlint", "ubuntu-latest", 5, {"contents": "read"})
    assert [step["name"] for step in job["steps"]] == [
        "Check out repository",
        "Lint GitHub Actions workflows",
    ]
    assert job["steps"][0] == {"name": "Check out repository", "uses": "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "with": {"persist-credentials": "false"}}
    assert job["steps"][1] == {
        "name": "Lint GitHub Actions workflows",
        "uses": "raven-actions/actionlint@3d39aea434753780c3b3d4a1a31c854b4dbf49d7",
        "with": {"version": "1.7.12", "files": ".github/workflows/*.yml", "shellcheck": "true", "pyflakes": "false"},
    }


def assert_gate_evidence_contract(run: str) -> None:
    for repeated in ("gh api --fail-with-body", "Accept: application/vnd.github+json", "X-GitHub-Api-Version: 2022-11-28"):
        assert run.count(repeated) == 3, "missing release evidence contract"
    required = (
        'release-tag-identity.sh "$tag_ref" "$EVENT_AFTER" "$EXPECTED_SHA"',
        'encoded_tag="$(jq -rn',
        "/git/ref/tags/${encoded_tag}",
        "/actions/runs/${dry_run_id}",
        "jq -e --arg ref",
        '.ref == $ref and .object.type == "tag"',
        '.tag == $tag and .sha == $tag_sha',
        '.object.type == "commit" and .object.sha == $sha',
        'jq -e --arg repo "$REPOSITORY" --arg sha "$peeled_commit_sha"',
        '.name == "Release dry run"',
        '.path == ".github/workflows/release-dry-run.yml"',
        '.event == "push"',
        '.head_branch == "main"',
        ".head_repository.full_name == $repo",
        ".head_sha == $sha",
        '.status == "completed"',
        '.conclusion == "success"',
        "completed_at=\"$(jq -er '.updated_at'",
        "tagged_at=\"$(jq -er '.tagger.date'",
        'test "$(date -d "$completed_at" +%s)" -le "$(date -d "$tagged_at" +%s)"',
    )
    assert all(item in run for item in required), "missing release evidence contract"


def assert_builder_command_contract(build_steps: list[dict[str, Any]]) -> None:
    positions: list[tuple[int, int]] = []
    for step_name, command in BUILDER_COMMANDS:
        index = step_index(build_steps, step_name)
        run_lines = build_steps[index]["run"].splitlines()
        assert command in run_lines, f"{step_name!r} is missing exact command: {command}"
        positions.append((index, run_lines.index(command)))

    assert positions == sorted(positions), "reusable builder command order drifted"
    upload = step_index(build_steps, "Upload verified release artifacts")
    assert positions[-1][0] < upload, "artifact upload must follow every required command"


def test_trigger_concurrency_permissions_and_jobs_are_exact() -> None:
    config = workflow()
    jobs = config["jobs"]
    assert config["on"] == {"push": {"tags": ["v*"]}}
    assert config["permissions"] == {"contents": "read"}
    assert config["concurrency"] == {
        "group": "${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": "false",
    }
    assert set(jobs) == {"gate", "build", "publish"}
    assert jobs["gate"]["permissions"] == {"actions": "read", "contents": "read"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["build"]["needs"] == "gate"
    assert jobs["build"]["uses"] == "./.github/workflows/release-build.yml"
    assert jobs["publish"]["needs"] == ["gate", "build"]
    assert jobs["publish"]["environment"] == "pypi"
    assert jobs["publish"]["permissions"] == {"contents": "read", "id-token": "write"}
    assert_release_structure(config)


def test_actions_and_security_relevant_inputs_are_exact() -> None:
    build_steps, publish_steps = steps("build"), steps("publish")
    assert [step.get("uses") for step in build_steps if "uses" in step] == [
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ]
    assert [step.get("uses") for step in publish_steps if "uses" in step] == [
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b",
    ]
    assert build_steps[0]["with"] == {
        "ref": "${{ github.sha }}",
        "fetch-depth": 0,
        "persist-credentials": "false",
    }
    assert build_steps[1]["with"] == {
        "version": "0.11.28",
        "python-version": "3.14.3",
        "enable-cache": "true",
        "cache-dependency-glob": "build-constraints.txt\npyproject.toml\nuv.lock\n",
    }
    assert build_steps[-1]["with"] == {
        "name": "release-${{ github.run_id }}-${{ github.sha }}",
        "path": "release/${{ steps.package-version.outputs.wheel }}\nrelease/${{ steps.package-version.outputs.sdist }}\nrelease/SHA256SUMS\n",
        "if-no-files-found": "error",
        "retention-days": 2,
    }
    assert publish_steps[0]["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert publish_steps[1]["with"] == {
        "name": "release-${{ github.run_id }}-${{ github.sha }}",
        "path": "release",
    }
    assert publish_steps[-1]["with"] == {
        "packages-dir": "dist",
        "attestations": "true",
        "verify-metadata": "true",
        "skip-existing": "false",
    }


def test_build_quality_precedes_one_build_and_artifact_verification() -> None:
    build_steps = steps("build")
    quality, build, verify, upload = (
        step_index(build_steps, name)
        for name in (
            "Run quality checks",
            "Build release artifacts once",
            "Verify and smoke-test release artifacts",
            "Upload verified release artifacts",
        )
    )
    quality_run = build_steps[quality]["run"]
    assert quality < build < verify < upload
    assert [quality_run.index(command) for command in (
        "uv run --frozen pytest",
        "uv run --frozen ruff check .",
        "uv run --frozen mypy meshflow_contracts tests",
    )] == sorted(quality_run.index(command) for command in (
        "uv run --frozen pytest",
        "uv run --frozen ruff check .",
        "uv run --frozen mypy meshflow_contracts tests",
    ))
    assert build_steps[build]["run"].count(
        "uv build --clear --no-create-gitignore --build-constraints build-constraints.txt --require-hashes"
    ) == 1
    assert "uv run --frozen python release_artifacts.py dist" in build_steps[verify]["run"]
    assert all(text in build_steps[verify]["run"] for text in ("smoke-cwd", "meshflow_contracts.__file__"))


def test_publish_reverifies_same_run_artifacts_without_rebuilding() -> None:
    publish_steps = steps("publish")
    download, verify, publish = (
        step_index(publish_steps, name)
        for name in (
            "Download exact build artifact",
            "Reverify downloaded artifacts",
            "Publish once with PyPI Trusted Publishing",
        )
    )
    assert download < verify < publish
    assert "sha256sum --check SHA256SUMS" in publish_steps[verify]["run"]
    assert "python release_artifacts.py dist" in publish_steps[verify]["run"]
    assert "meshflow_contracts-0.2.2-py3-none-any.whl" in publish_steps[verify]["run"]
    assert "meshflow_contracts-0.2.2.tar.gz" in publish_steps[verify]["run"]
    assert "uv build" not in WORKFLOW_PATH.read_text()
    assert publish_steps[publish]["with"].keys().isdisjoint(
        {"user", "password", "token", "repository-url"}
    )


def test_shell_steps_fail_closed_and_remote_tag_gate_is_exact() -> None:
    for job in ("gate", "publish"):
        for step in steps(job):
            if "\n" in step.get("run", ""):
                assert step["run"].startswith("set -euo pipefail\n")
    gate = steps("gate")[step_index(steps("gate"), "Validate tag and recorded dry-run evidence")]
    assert gate["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "TAG_NAME": "${{ github.ref_name }}",
        "EXPECTED_SHA": "${{ github.sha }}",
        "EVENT_AFTER": "${{ github.event.after }}",
        "REPOSITORY": "${{ github.repository }}",
    }
    for required in (
        'object.type == "tag"',
        "/git/tags/",
        ".tag == $tag",
        'object.type == "commit"',
        '--arg tag_sha "$tag_object_sha"',
        '--arg sha "$peeled_commit_sha"',
    ):
        assert required in gate["run"]


def test_no_unsafe_events_secrets_or_github_release_logic() -> None:
    config = workflow()
    text = WORKFLOW_PATH.read_text()
    assert not ({"workflow_dispatch", "schedule", "release", "pull_request", "workflow_run", "repository_dispatch"} & config["on"].keys())
    assert "secrets." not in text
    assert "softprops/action-gh-release" not in text
    assert "gh release" not in text
    assert "skip-existing: true" not in text


def test_reusable_builder_has_exact_topology_actions_and_artifact_contract() -> None:
    builder = load_workflow(BUILD_PATH)
    job = builder["jobs"]["build"]
    build_steps = cast(list[dict[str, Any]], job["steps"])

    assert builder["on"] == {"workflow_call": {}}
    assert set(builder["jobs"]) == {"build"}
    assert builder["permissions"] == job["permissions"] == {"contents": "read"}
    assert [step.get("uses") for step in build_steps if "uses" in step] == [
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ]
    checkout, setup, upload = (build_steps[index]["with"] for index in (0, 1, -1))
    version_step = build_steps[step_index(build_steps, "Validate package version sources")]
    assert checkout == {"ref": "${{ github.sha }}", "fetch-depth": 0, "persist-credentials": "false"}
    assert setup["version"] == "0.11.28"
    assert setup["python-version"] == "3.14.3"
    assert setup["enable-cache"] == "true"
    assert setup["cache-dependency-glob"] == "build-constraints.txt\npyproject.toml\nuv.lock\n"
    assert version_step["id"] == "package-version"
    assert 'output.write(f"wheel={wheel}\\n")' in version_step["run"]
    assert 'output.write(f"sdist={sdist}\\n")' in version_step["run"]
    assert upload["name"] == "release-${{ github.run_id }}-${{ github.sha }}"
    assert upload["path"] == (
        "release/${{ steps.package-version.outputs.wheel }}\n"
        "release/${{ steps.package-version.outputs.sdist }}\n"
        "release/SHA256SUMS\n"
    )
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == 2


@pytest.mark.parametrize("version", ("1.2.3", "0.0.0"))
def test_package_version_script_validates_then_writes_exact_environment_and_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    env, output = execute_package_version_script(tmp_path, monkeypatch, version)

    assert env == (
        f"VERSION={version}\n"
        f"WHEEL=meshflow_contracts-{version}-py3-none-any.whl\n"
        f"SDIST=meshflow_contracts-{version}.tar.gz\n"
    )
    assert output == (
        f"wheel=meshflow_contracts-{version}-py3-none-any.whl\n"
        f"sdist=meshflow_contracts-{version}.tar.gz\n"
    )


@pytest.mark.parametrize(
    "version",
    ("1.2", "01.2.3", "1.2.3\noutput=injected", "1.2.3\x00", "1.2.3/unsafe", "v1.2.3"),
)
def test_package_version_script_rejects_unsafe_versions_without_writing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    with pytest.raises(ValueError, match="invalid package version"):
        execute_package_version_script(tmp_path, monkeypatch, version)

    assert not (tmp_path / "github-env").exists() and not (tmp_path / "github-output").exists()


def test_package_version_script_rejects_source_mismatch_without_writing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="package version sources disagree"):
        execute_package_version_script(tmp_path, monkeypatch, "1.2.3", "1.2.4")
    assert not (tmp_path / "github-env").exists() and not (tmp_path / "github-output").exists()


def test_package_version_step_precedes_every_version_derived_consumer() -> None:
    build_steps = cast(list[dict[str, Any]], load_workflow(BUILD_PATH)["jobs"]["build"]["steps"])
    version_step = step_index(build_steps, "Validate package version sources")

    consumers = [
        index
        for index, step in enumerate(build_steps)
        if any(
            value in str(step)
            for value in ("$VERSION", "$WHEEL", "$SDIST", "steps.package-version.outputs.")
        )
    ]

    assert consumers
    assert all(version_step < consumer for consumer in consumers)


def test_builder_derives_version_and_orders_quality_build_verify_upload() -> None:
    build_steps = cast(list[dict[str, Any]], load_workflow(BUILD_PATH)["jobs"]["build"]["steps"])
    text = BUILD_PATH.read_text()

    assert_builder_command_contract(build_steps)
    assert text.count(
        "uv build --clear --no-create-gitignore --build-constraints build-constraints.txt --require-hashes"
    ) == 1
    for required in (
        'env.write(f"WHEEL={wheel}\\n")',
        'env.write(f"SDIST={sdist}\\n")',
        "uv run --frozen python release_artifacts.py dist",
        "smoke-cwd",
        "SHA256SUMS",
    ):
        assert required in text
    for step in build_steps:
        if "\n" in step.get("run", ""):
            assert step["run"].startswith("set -euo pipefail\n")


@pytest.mark.parametrize(("step_name", "command"), BUILDER_COMMANDS)
def test_builder_contract_rejects_each_missing_command(step_name: str, command: str) -> None:
    build_steps = cast(list[dict[str, Any]], load_workflow(BUILD_PATH)["jobs"]["build"]["steps"])
    index = step_index(build_steps, step_name)
    build_steps[index]["run"] = build_steps[index]["run"].replace(command, "", 1)

    with pytest.raises(AssertionError, match="is missing exact command"):
        assert_builder_command_contract(build_steps)


@pytest.mark.parametrize(
    ("step_name", "first", "second"),
    (
        ("Run quality checks", BUILDER_COMMANDS[1][1], BUILDER_COMMANDS[2][1]),
        ("Verify and smoke-test release artifacts", BUILDER_COMMANDS[5][1], BUILDER_COMMANDS[6][1]),
    ),
)
def test_builder_contract_rejects_command_order_drift(
    step_name: str, first: str, second: str
) -> None:
    build_steps = cast(list[dict[str, Any]], load_workflow(BUILD_PATH)["jobs"]["build"]["steps"])
    index = step_index(build_steps, step_name)
    run_lines = build_steps[index]["run"].splitlines()
    first_index, second_index = run_lines.index(first), run_lines.index(second)
    run_lines[first_index], run_lines[second_index] = second, first
    build_steps[index]["run"] = "\n".join(run_lines)

    with pytest.raises(AssertionError, match="command order drifted"):
        assert_builder_command_contract(build_steps)


def test_dry_run_only_delegates_from_pull_requests_and_main_pushes() -> None:
    dry_run = load_workflow(DRY_RUN_PATH)
    reusable = "./.github/workflows/release-build.yml"

    assert dry_run["on"] == {"pull_request": {}, "push": {"branches": ["main"]}}
    assert dry_run["permissions"] == {"contents": "read"}
    assert dry_run["jobs"] == {
        "build": {"permissions": {"contents": "read"}, "uses": reusable}
    }
    text = BUILD_PATH.read_text() + DRY_RUN_PATH.read_text()
    for forbidden in (
        "id-token: write", "environment:", "pypa/gh-action-pypi-publish",
        "secrets.", "workflow_dispatch", "uv publish", "twine upload",
    ):
        assert forbidden not in text
    assert all(command not in DRY_RUN_PATH.read_text() for command in ("uv build", "release_artifacts.py"))


def test_release_gate_requires_unique_exact_dry_run_evidence_before_build() -> None:
    gate = steps("gate")[step_index(steps("gate"), "Validate tag and recorded dry-run evidence")]
    run = gate["run"]

    for required in (
        'read -r tag_object_sha peeled_commit_sha',
        'test "$TAG_NAME" = "v$version"',
        "test \"$(grep -c '^dry-run-run-id: [0-9][0-9]*$' <<<\"$tag_body\")\" = 1",
        "dry_run_id=\"$(sed -n 's/^dry-run-run-id: \\([0-9][0-9]*\\)$/\\1/p'",
        "/actions/runs/${dry_run_id}",
        '.event == "push"',
        '.head_branch == "main"',
        ".head_sha == $sha",
        '.status == "completed"',
        '.conclusion == "success"',
        '.path == ".github/workflows/release-dry-run.yml"',
        "completed_at=\"$(jq -er '.updated_at'",
        "tagged_at=\"$(jq -er '.tagger.date'",
        'test "$(date -d "$completed_at" +%s)" -le "$(date -d "$tagged_at" +%s)"',
    ):
        assert required in run
    helper = TAG_IDENTITY_PATH.read_text()
    assert 'test "$(git cat-file -t "$tag_ref")" = tag' in helper
    assert 'test "$tag_object_sha" = "$2"' in helper
    assert 'test "$peeled_commit_sha" = "$3"' in helper
    assert_gate_evidence_contract(run)


def test_tag_identity_distinguishes_annotated_object_from_peeled_commit(tmp_path: Path) -> None:
    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=check, capture_output=True, text=True
        )

    git("init", "--quiet")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.invalid")
    (tmp_path / "file").write_text("release\n")
    git("add", "file")
    git("commit", "--quiet", "-m", "release")
    commit_sha = git("rev-parse", "HEAD").stdout.strip()
    git("tag", "-a", "v0.2.2", "-m", "dry-run-run-id: 123")
    tag_sha = git("rev-parse", "refs/tags/v0.2.2").stdout.strip()

    assert tag_sha != commit_sha
    assert subprocess.run(
        ["bash", str(TAG_IDENTITY_PATH), "refs/tags/v0.2.2", tag_sha, commit_sha],
        cwd=tmp_path,
        check=False,
    ).returncode == 0
    assert subprocess.run(
        ["bash", str(TAG_IDENTITY_PATH), "refs/tags/v0.2.2", commit_sha, tag_sha],
        cwd=tmp_path,
        check=False,
    ).returncode != 0

    git("tag", "v0.2.2-lightweight", commit_sha)
    assert subprocess.run(
        [
            "bash",
            str(TAG_IDENTITY_PATH),
            "refs/tags/v0.2.2-lightweight",
            commit_sha,
            commit_sha,
        ],
        cwd=tmp_path,
        check=False,
    ).returncode != 0


def assert_tag_identity_rejected_before_identity(tmp_path: Path, *args: str) -> None:
    result = subprocess.run(
        ["bash", str(TAG_IDENTITY_PATH), *args],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TRACE": "1"},
    )

    assert result.returncode != 0
    assert "cat-file" not in result.stderr
    assert "rev-parse" not in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("refs/tags/v0.2.2", "a" * 40),
        ("refs/tags/v0.2.2", "a" * 40, "b" * 40, "extra"),
    ],
)
def test_tag_identity_rejects_inexact_argument_count(tmp_path: Path, args: tuple[str, ...]) -> None:
    assert_tag_identity_rejected_before_identity(tmp_path, *args)


@pytest.mark.parametrize(
    "tag_ref",
    [
        "refs/tags/v0.2.2^{tag}",
        "refs/tags/v0..2.2",
        "refs/tags/../v0.2.2",
        "refs/heads/v0.2.2",
        "refs/tags/v0.2.2 release",
        "refs/tags/v0.2.2\nrelease",
    ],
)
def test_tag_identity_rejects_malformed_tag_refs(tmp_path: Path, tag_ref: str) -> None:
    assert_tag_identity_rejected_before_identity(tmp_path, tag_ref, "a" * 40, "b" * 40)


@pytest.mark.parametrize("argument", [1, 2])
@pytest.mark.parametrize("sha", ["A" * 40, "a" * 39, "g" * 40])
def test_tag_identity_rejects_noncanonical_shas(tmp_path: Path, argument: int, sha: str) -> None:
    args = ["refs/tags/v0.2.2", "a" * 40, "b" * 40]
    args[argument] = sha

    assert_tag_identity_rejected_before_identity(tmp_path, *args)


def test_release_permissions_artifact_identity_and_actionlint_are_isolated() -> None:
    release = workflow()
    publish = release["jobs"]["publish"]
    release_text = WORKFLOW_PATH.read_text()

    assert release["jobs"]["build"]["uses"] == "./.github/workflows/release-build.yml"
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert release_text.count("id-token: write") == 1
    assert "release-${{ github.run_id }}-${{ github.sha }}" in release_text
    assert "sha256sum --check SHA256SUMS" in release_text
    assert "attestations: true" in release_text
    assert "secrets." not in release_text

    actionlint = load_workflow(CI_PATH)["jobs"]["actionlint"]
    assert actionlint["timeout-minutes"] == 5
    assert actionlint["permissions"] == {"contents": "read"}
    lint_step = actionlint["steps"][1]
    assert lint_step["uses"] == "raven-actions/actionlint@3d39aea434753780c3b3d4a1a31c854b4dbf49d7"
    assert lint_step["with"] == {
        "version": "1.7.12",
        "files": ".github/workflows/*.yml",
        "shellcheck": "true",
        "pyflakes": "false",
    }
    assert_actionlint_structure(actionlint)


def test_runbook_requires_recorded_main_evidence_and_forbids_operator_shortcuts() -> None:
    runbook = RELEASING_PATH.read_text()
    for required in (
        "exact merged `main` SHA",
        "successful `Release dry run`",
        "`dry-run-run-id: <id>`",
        "`updated_at`",
        "`tagger.date`",
        "later explicit irreversible authorization",
        "Never substitute a local operator build",
        "never overwrite, retag, manually upload, or blindly rerun",
        "`v0.2.0` and `v0.2.1` remain immutable failed, unpublished tags",
    ):
        assert required in runbook


@pytest.mark.parametrize(
    "required",
    (
        "gh api --fail-with-body",
        '.head_repository.full_name == $repo',
        "completed_at=\"$(jq -er '.updated_at'",
    ),
)
def test_release_gate_contract_rejects_representative_removals(required: str) -> None:
    gate = steps("gate")[step_index(steps("gate"), "Validate tag and recorded dry-run evidence")]
    mutated = gate["run"].replace(required, "", 1)

    with pytest.raises(AssertionError, match="missing release evidence contract"):
        assert_gate_evidence_contract(mutated)
