import base64
import hashlib
import io
import stat
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

import release_artifacts

ROOT = Path(__file__).parents[1]
REGULAR_MODE = stat.S_IFREG | 0o644
DIRECTORY_MODE = stat.S_IFDIR | 0o755
VERSION = "0.2.2"


def metadata(**changes: str) -> bytes:
    fields = {"Metadata-Version": "2.4", "Name": "meshflow-contracts", "Version": VERSION, "License-Expression": "Apache-2.0", "Requires-Python": ">=3.14", "Requires-Dist": "pydantic>=2.13.4,<3"} | changes  # fmt: skip
    return ("\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n\n").encode()


def add_zip_file(archive: zipfile.ZipFile, name: str, content: bytes, mode: int, system: int = 3) -> None:
    entry = zipfile.ZipInfo(name)
    entry.create_system = system
    entry.external_attr = mode << 16
    archive.writestr(entry, content)


def record_row(name: str, content: bytes) -> bytes:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(content)}\n".encode()


def synthetic_dist(
    directory: Path,
    *,
    wheel_extra: tuple[str, int] | None = None,
    wheel_mode: tuple[str, int] | None = None,
    wheel_system: str | None = None,
    sdist_extra: tuple[str, bytes] | None = None,
    sdist_type: tuple[str, bytes] | None = None,
    sdist_sparse: bool = False,
    meta: bytes | None = None,
    license_bytes: bytes | None = None,
) -> None:
    directory.mkdir()
    license_bytes = license_bytes or (ROOT / "LICENSE").read_bytes()
    info = f"meshflow_contracts-{VERSION}.dist-info"
    wheel_files = [(name, b"x") for name in release_artifacts.MODULE_FILES]
    wheel_files += [
        (f"{info}/METADATA", meta or metadata()),
        (
            f"{info}/WHEEL",
            b"Wheel-Version: 1.0\nGenerator: uv 0.11.28\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        ),  # fmt: skip
        (f"{info}/licenses/LICENSE", license_bytes),
    ]
    record_name = f"{info}/RECORD"
    wheel_files.append((record_name, b"".join(record_row(*item) for item in wheel_files) + f"{record_name},,\n".encode()))  # fmt: skip
    if wheel_extra:
        wheel_files.append((wheel_extra[0], b"forbidden"))
    wheel = directory / f"meshflow_contracts-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in ("meshflow_contracts/", f"{info}/", f"{info}/licenses/"):
            mode = wheel_mode[1] if wheel_mode and name == wheel_mode[0] else DIRECTORY_MODE
            add_zip_file(archive, name, b"", mode, 0 if name == wheel_system else 3)
        for name, content in wheel_files:
            mode = wheel_mode[1] if wheel_mode and name == wheel_mode[0] else REGULAR_MODE
            add_zip_file(archive, name, content, mode, 0 if name == wheel_system else 3)

    root = f"meshflow_contracts-{VERSION}"
    source = [(name, b"x") for name in release_artifacts.MODULE_FILES]
    source += [
        ("LICENSE", license_bytes),
        ("README.md", b"readme"),
        (
            "pyproject.toml",
            f'[build-system]\nrequires=["uv_build>=0.11.28,<0.12"]\nbuild-backend="uv_build"\n[project]\nname="meshflow-contracts"\nversion="{VERSION}"\n'.encode(),
        ),  # fmt: skip
        ("PKG-INFO", meta or metadata()),
    ]
    sdist = directory / f"meshflow_contracts-{VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for name in (root, f"{root}/meshflow_contracts"):
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            if sdist_type and name == sdist_type[0]:
                member.type = sdist_type[1]
            archive.addfile(member)
        for name, content in source:
            full_name = f"{root}/{name}"
            member = tarfile.TarInfo(full_name)
            if sdist_sparse and name == "meshflow_contracts/auth.py":
                member.pax_headers = {"GNU.sparse.realsize": str(len(content))}
            if sdist_type and full_name == sdist_type[0]:
                member.type = sdist_type[1]
                archive.addfile(member)
                continue
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        if sdist_extra:
            member = tarfile.TarInfo(sdist_extra[0])
            member.type = sdist_extra[1]
            archive.addfile(member)


def verify(directory: Path) -> None:
    release_artifacts.verify(directory, version=VERSION, license_path=ROOT / "LICENSE")


def reject(tmp_path: Path, match: str | None = None, **kwargs: Any) -> None:
    dist = tmp_path / f"dist-{len(list(tmp_path.iterdir()))}"
    synthetic_dist(dist, **kwargs)
    with pytest.raises(ValueError, match=match):
        verify(dist)


def test_valid_archives_and_supplied_hashes_are_accepted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    synthetic_dist(dist)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dist.iterdir()}
    release_artifacts.verify(dist, expected_hashes=hashes, license_path=ROOT / "LICENSE")


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize("path", ["../x", "/x", "tests\\x.py", "bad\x01name", "a//b", "a/../b", "meshflow_contracts//", "meshflow_contracts///", ".env", "tests/x.py"])  # fmt: skip
def test_rejects_unsafe_unexpected_and_sensitive_paths(
    tmp_path: Path, kind: str, path: str
) -> None:
    if kind == "wheel":
        reject(tmp_path, wheel_extra=(path, REGULAR_MODE))
    else:
        reject(tmp_path, sdist_extra=(path, tarfile.REGTYPE))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_rejects_duplicate_members(tmp_path: Path, kind: str) -> None:
    dist = tmp_path / "dist"
    duplicate = "meshflow_contracts/auth.py"
    if kind == "wheel":
        synthetic_dist(dist, wheel_extra=(f"{duplicate}/", DIRECTORY_MODE))
    else:
        synthetic_dist(dist, sdist_extra=(f"meshflow_contracts-{VERSION}/{duplicate}", tarfile.REGTYPE))
    with pytest.raises(ValueError, match="duplicate normalized"):
        verify(dist)


MEMBER_CASES = [
    ({"wheel_system": "meshflow_contracts/auth.py"}, "regular"),
    ({"wheel_system": "meshflow_contracts/"}, "directory"),
    ({"wheel_mode": ("meshflow_contracts/auth.py", stat.S_IFLNK | 0o777)}, "regular"),
    ({"wheel_mode": ("meshflow_contracts/", REGULAR_MODE)}, "directory"),
    ({"wheel_mode": ("meshflow_contracts/auth.py", DIRECTORY_MODE)}, "regular"),
    *[
        (
            {"sdist_type": (f"meshflow_contracts-{VERSION}/meshflow_contracts/auth.py", kind)},
            "member types|sparse",
        )
        for kind in (
            tarfile.SYMTYPE,
            tarfile.LNKTYPE,
            tarfile.CHRTYPE,
            tarfile.BLKTYPE,
            tarfile.FIFOTYPE,
            tarfile.CONTTYPE,
            tarfile.GNUTYPE_SPARSE,
        )
    ],  # fmt: skip
    ({"sdist_sparse": True}, "sparse"),
    ({"sdist_type": (f"meshflow_contracts-{VERSION}", tarfile.REGTYPE)}, "member types"),
]


@pytest.mark.parametrize(("kwargs", "match"), MEMBER_CASES)
def test_rejects_non_regular_sparse_and_wrong_directory_members(
    tmp_path: Path, kwargs: dict[str, Any], match: str
) -> None:
    reject(tmp_path, match, **kwargs)


@pytest.mark.parametrize(
    "field", ["Name", "Version", "License-Expression", "Requires-Python", "Requires-Dist"]
)
def test_rejects_metadata_mismatch(tmp_path: Path, field: str) -> None:
    reject(tmp_path, f"invalid {field}", meta=metadata(**{field: "wrong"}))


def test_rejects_duplicate_metadata(tmp_path: Path) -> None:
    duplicate = metadata().replace(
        b"Name: meshflow-contracts\n",
        b"Name: meshflow-contracts\nName: meshflow-contracts\n",
    )
    reject(tmp_path, "invalid Name", meta=duplicate)


def test_rejects_metadata_parser_defects(tmp_path: Path) -> None:
    reject(tmp_path, "metadata syntax", meta=b"broken header\n" + metadata())


@pytest.mark.parametrize(("limit", "value"), [("MAX_ARCHIVE_BYTES", 0), ("MAX_MEMBER_COUNT", 10), ("MAX_MEMBER_BYTES", 0), ("MAX_TOTAL_BYTES", 0), ("MAX_ZIP_RATIO", 0)])  # fmt: skip
def test_rejects_resource_ceiling_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str, value: int
) -> None:
    dist = tmp_path / "dist"
    synthetic_dist(dist)
    monkeypatch.setattr(release_artifacts, limit, value)
    with pytest.raises(ValueError, match="limit"):
        verify(dist)


@pytest.mark.parametrize("extra_name", [".gitignore", "unexpected"])
def test_rejects_nul_path_and_inexact_distribution_set(
    tmp_path: Path, extra_name: str
) -> None:
    with pytest.raises(ValueError, match="unsafe archive path"):
        release_artifacts.safe_paths(["bad\0name"])
    dist = tmp_path / "dist"
    synthetic_dist(dist)
    (dist / extra_name).write_bytes(b"x")
    with pytest.raises(ValueError, match="exactly the expected"):
        verify(dist)


def test_rejects_changed_license_and_artifact_hash(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    synthetic_dist(dist, license_bytes=b"wrong")
    with pytest.raises(ValueError, match="LICENSE differs"):
        verify(dist)
    hashes = {path.name: "0" * 64 for path in dist.iterdir()}
    with pytest.raises(ValueError, match="artifact hash differs"):
        release_artifacts.verify(dist, expected_hashes=hashes, license_path=ROOT / "LICENSE")


@pytest.mark.parametrize("extra", [False, True])
def test_rejects_missing_or_extra_hash_keys(tmp_path: Path, extra: bool) -> None:
    dist = tmp_path / "dist"
    synthetic_dist(dist)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dist.iterdir()}
    if extra:
        hashes["extra"] = "0" * 64
    else:
        hashes.pop(next(iter(hashes)))
    with pytest.raises(ValueError, match="allowlist must be exact"):
        release_artifacts.verify(dist, expected_hashes=hashes, license_path=ROOT / "LICENSE")
