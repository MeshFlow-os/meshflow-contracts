import json
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
    return cast(list[dict[str, Any]], workflow()["jobs"][job]["steps"])


def step_index(job_steps: list[dict[str, Any]], name: str) -> int:
    return next(index for index, step in enumerate(job_steps) if step["name"] == name)


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
    assert set(jobs) == {"build", "publish"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert "environment" not in jobs["build"]
    assert jobs["publish"]["needs"] == "build"
    assert jobs["publish"]["environment"] == "pypi"
    assert jobs["publish"]["permissions"] == {"contents": "read", "id-token": "write"}


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
        "name": "release-${{ github.run_id }}",
        "path": "release/meshflow_contracts-0.2.1-py3-none-any.whl\nrelease/meshflow_contracts-0.2.1.tar.gz\nrelease/SHA256SUMS\n",
        "if-no-files-found": "error",
        "retention-days": 2,
    }
    assert publish_steps[0]["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert publish_steps[1]["with"] == {
        "name": "release-${{ github.run_id }}",
        "path": "release",
        "github-token": "${{ github.token }}",
        "repository": "${{ github.repository }}",
        "run-id": "${{ github.run_id }}",
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


def test_publish_reverifies_downloaded_artifacts_before_remote_gate_and_publish() -> None:
    publish_steps = steps("publish")
    download, verify, gate, publish = (
        step_index(publish_steps, name)
        for name in (
            "Download exact build artifact",
            "Reverify downloaded artifacts",
            "Revalidate remote annotated tag",
            "Publish once with PyPI Trusted Publishing",
        )
    )
    assert download < verify < gate < publish
    assert "sha256sum --check SHA256SUMS" in publish_steps[verify]["run"]
    assert "python release_artifacts.py dist" in publish_steps[verify]["run"]
    assert publish_steps[publish]["with"].keys().isdisjoint(
        {"user", "password", "token", "repository-url"}
    )


def test_shell_steps_fail_closed_and_remote_tag_gate_is_exact() -> None:
    config = workflow()
    for job in config["jobs"]:
        for step in steps(job):
            if "\n" in step.get("run", ""):
                assert step["run"].startswith("set -euo pipefail\n")
    gate = steps("publish")[step_index(steps("publish"), "Revalidate remote annotated tag")]
    assert gate["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "TAG_NAME": "${{ github.ref_name }}",
        "EXPECTED_SHA": "${{ github.sha }}",
        "EVENT_AFTER": "${{ github.event.after }}",
        "REPOSITORY": "${{ github.repository }}",
    }
    for required in (
        'object.type == "tag"', "/git/tags/", ".tag == $tag", 'object.type == "commit"',
        'test "$EXPECTED_SHA" = "$EVENT_AFTER"', 'test "$peeled_sha" = "$EXPECTED_SHA"',
        'test "$peeled_sha" = "$EVENT_AFTER"',
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
