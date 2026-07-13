import os
import shutil
import subprocess
from pathlib import Path

import pytest

import release_artifacts

ROOT = Path(__file__).parents[1]
VERSION = "0.2.1"


def run(*command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def smoke_import(venv: Path, cwd: Path, version: str) -> None:
    result = run(
        str(venv_python(venv)),
        "-c",
        "import meshflow_contracts; print(meshflow_contracts.__version__); print(meshflow_contracts.__file__)",
        cwd=cwd,
    )
    imported_version, imported_file = result.stdout.strip().splitlines()
    assert imported_version == version
    assert Path(imported_file).resolve().is_relative_to(venv.resolve())


@pytest.mark.integration
def test_pinned_uv_build_verifier_and_distribution_smoke(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    assert run(uv, "--version", cwd=ROOT).stdout.startswith("uv 0.11.28 ")

    source = tmp_path / "source"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "dist"
        ),
    )
    run(
        uv,
        "build",
        "--clear",
        "--no-create-gitignore",
        "--build-constraints",
        "build-constraints.txt",
        "--require-hashes",
        cwd=source,
    )

    dist = source / "dist"
    wheel = dist / f"meshflow_contracts-{VERSION}-py3-none-any.whl"
    sdist = dist / f"meshflow_contracts-{VERSION}.tar.gz"
    release_artifacts.verify(dist, license_path=source / "LICENSE")

    (smoke_cwd := tmp_path / "unrelated-cwd").mkdir()
    for name, artifact in (("wheel", wheel), ("sdist", sdist)):
        venv = tmp_path / f"smoke-{name}"
        run(uv, "venv", "--clear", "--python", "3.14.3", str(venv), cwd=source)
        install = [uv, "pip", "install", "--python", str(venv_python(venv))]
        if name == "sdist":
            install.extend(("--build-constraints", "build-constraints.txt"))
        run(*install, str(artifact), cwd=source)
        smoke_import(venv, smoke_cwd, VERSION)
