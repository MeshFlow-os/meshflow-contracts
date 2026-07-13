import hashlib
import tomllib
from pathlib import Path

import meshflow_contracts
import release_artifacts


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


def test_recovery_version_authorities_are_consistently_0_2_1() -> None:
    expected_version = "0.2.1"
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text())
    locked_versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == PYPROJECT["project"]["name"]
    ]
    workflow = (PROJECT_ROOT / ".github/workflows/release-build.yml").read_text()
    readme = (PROJECT_ROOT / "README.md").read_text()
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text()
    releasing = (PROJECT_ROOT / "RELEASING.md").read_text()

    assert PYPROJECT["project"]["version"] == expected_version
    assert meshflow_contracts.__version__ == expected_version
    assert release_artifacts.VERSION == expected_version
    assert locked_versions == [expected_version]
    assert "__version__ != VERSION or VERSION != version" in workflow
    assert 'env.write(f"VERSION={version}\\n")' in workflow
    assert 'output.write(f"wheel={wheel}\\n")' in workflow
    assert 'output.write(f"sdist={sdist}\\n")' in workflow
    assert 'EXPECTED_VERSION="$VERSION"' in workflow
    assert 'meshflow_contracts.__version__ == os.environ["EXPECTED_VERSION"]' in workflow
    assert 'pip install "meshflow-contracts~=0.2.1"' in readme
    assert "## 0.2.1" in changelog
    assert "`v0.2.0` remains an immutable failed, unpublished tag" in releasing
    assert "Core adopts `0.2.1` before Gateway" in releasing


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
    assert any(
        marker.startswith("integration:")
        for marker in PYPROJECT["tool"]["pytest"]["ini_options"]["markers"]
    )


def test_license_and_typing_markers_are_present() -> None:
    license_bytes = (PROJECT_ROOT / "LICENSE").read_bytes()

    assert hashlib.sha256(license_bytes).hexdigest() == (
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    )
    assert "Copyright 2026 MeshFlow contributors" in (PROJECT_ROOT / "README.md").read_text()
    assert (PROJECT_ROOT / "meshflow_contracts" / "py.typed").is_file()
