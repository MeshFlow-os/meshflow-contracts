import hashlib
import tomllib
from pathlib import Path

import meshflow_contracts


PROJECT_ROOT = Path(__file__).parents[1]
PYPROJECT = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())


def test_public_package_metadata_is_release_ready() -> None:
    project = PYPROJECT["project"]

    assert project["version"] == meshflow_contracts.__version__
    assert project["requires-python"] == ">=3.14"
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert project["dependencies"] == ["pydantic>=2.13.4,<3"]
    assert project["authors"] == [{"name": "MeshFlow contributors"}]
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Programming Language :: Python :: 3.14" in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]
    assert project["urls"] == {
        "Repository": "https://github.com/MeshFlow-os/meshflow-contracts",
        "Issues": "https://github.com/MeshFlow-os/meshflow-contracts/issues",
        "Changelog": "https://github.com/MeshFlow-os/meshflow-contracts/blob/main/CHANGELOG.md",
    }


def test_uv_build_uses_supported_backend_and_flat_layout() -> None:
    assert PYPROJECT["build-system"] == {
        "requires": ["uv_build>=0.11.28,<0.12"],
        "build-backend": "uv_build",
    }
    assert PYPROJECT["tool"]["uv"]["required-version"] == "==0.11.28"
    assert PYPROJECT["tool"]["uv"]["build-backend"] == {
        "module-root": "",
        "module-name": "meshflow_contracts",
    }


def test_license_and_typing_markers_are_present() -> None:
    license_bytes = (PROJECT_ROOT / "LICENSE").read_bytes()

    assert hashlib.sha256(license_bytes).hexdigest() == (
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    )
    assert "Copyright 2026 MeshFlow contributors" in (PROJECT_ROOT / "README.md").read_text()
    assert (PROJECT_ROOT / "meshflow_contracts" / "py.typed").is_file()
