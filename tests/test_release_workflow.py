from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/release.yml"


class WorkflowLoader(yaml.SafeLoader):
    pass


WorkflowLoader.yaml_implicit_resolvers = {
    key: [rule for rule in rules if rule[0] != "tag:yaml.org,2002:bool"]
    for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def workflow() -> dict[str, Any]:
    parsed = yaml.load(WORKFLOW_PATH.read_text(), Loader=WorkflowLoader)
    assert isinstance(parsed, dict)
    return parsed


def steps(job: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workflow()["jobs"][job]["steps"])


def step_index(job_steps: list[dict[str, Any]], name: str) -> int:
    return next(index for index, step in enumerate(job_steps) if step["name"] == name)


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
