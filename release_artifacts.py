import email.parser
import email.policy
import hashlib
import posixpath
import stat
import sys
import tarfile
import unicodedata
import zipfile
from collections.abc import Mapping
from pathlib import Path
from pathlib import PurePosixPath
from typing import IO, Never

NAME = "meshflow-contracts"
VERSION = "0.2.0"
PACKAGE = "meshflow_contracts"
MODULE_FILES = {f"{PACKAGE}/{name}" for name in ("__init__.py", "auth.py", "errors.py", "manifest.py", "observability.py", "py.typed")}  # fmt: skip
LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_MEMBER_COUNT = 16
MAX_MEMBER_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 1024 * 1024
MAX_ZIP_RATIO = 100


def fail(message: str) -> Never:
    raise ValueError(message)


def bounded_read(stream: IO[bytes], limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        fail("content exceeds resource limit")
    return data


def safe_paths(names: list[str]) -> list[str]:
    for name in names:
        if (
            not name
            or "\\" in name
            or any(unicodedata.category(character) == "Cc" for character in name)
            or PurePosixPath(name).is_absolute()
            or posixpath.normpath(name) != name
            or ".." in PurePosixPath(name).parts
        ):
            fail(f"unsafe archive path: {name!r}")
    if len(names) != len(set(names)):
        fail("duplicate normalized archive path")
    return names


def verify_metadata(raw: bytes, version: str) -> None:
    parsed = email.parser.BytesParser(policy=email.policy.default).parsebytes(raw)
    if parsed.defects or any(getattr(value, "defects", ()) for value in parsed.values()):
        fail("invalid metadata syntax")
    expected = {"Name": [NAME], "Version": [version], "License-Expression": ["Apache-2.0"], "Requires-Python": [">=3.14"], "Requires-Dist": ["pydantic>=2.13.4,<3"]}  # fmt: skip
    for field, values in expected.items():
        if parsed.get_all(field, []) != values:
            fail(f"invalid {field}: {parsed.get_all(field, [])!r}")


def verify(
    directory: Path,
    version: str = VERSION,
    expected_hashes: Mapping[str, str] | None = None,
    license_path: Path = Path("LICENSE"),
) -> None:
    wheel_name = f"{PACKAGE}-{version}-py3-none-any.whl"
    sdist_name = f"{PACKAGE}-{version}.tar.gz"
    artifact_names = {wheel_name, sdist_name}
    artifacts = list(directory.iterdir())
    if len(artifacts) != 2 or {path.name for path in artifacts} != artifact_names:
        fail("dist must contain exactly the expected wheel and sdist")
    if any(not path.is_file() or path.is_symlink() for path in artifacts):
        fail("dist entries must be regular files")
    if any(path.stat().st_size > MAX_ARCHIVE_BYTES for path in artifacts):
        fail("artifact exceeds compressed size limit")
    if expected_hashes is not None:
        if set(expected_hashes) != artifact_names:
            fail("artifact hash allowlist must be exact")
        for path in artifacts:
            with path.open("rb") as artifact:
                if (
                    hashlib.sha256(bounded_read(artifact, MAX_ARCHIVE_BYTES)).hexdigest()
                    != expected_hashes[path.name]
                ):
                    fail(f"artifact hash differs: {path.name}")
    with license_path.open("rb") as license_file:
        license_bytes = bounded_read(license_file, MAX_MEMBER_BYTES)
    if hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256:
        fail("repository LICENSE differs from the canonical Apache-2.0 text")
    dist_info = f"{PACKAGE}-{version}.dist-info"
    wheel_files = MODULE_FILES | {
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/RECORD",
        f"{dist_info}/licenses/LICENSE",
    }
    with zipfile.ZipFile(directory / wheel_name) as archive:
        entries = archive.infolist()
        total = 0
        for entry in entries:
            total += entry.file_size
            if (
                len(entries) > MAX_MEMBER_COUNT
                or entry.file_size > MAX_MEMBER_BYTES
                or total > MAX_TOTAL_BYTES
                or entry.file_size > max(entry.compress_size, 1) * MAX_ZIP_RATIO
            ):
                fail("zip member exceeds resource limit")
        names = safe_paths([entry.filename for entry in entries])
        if set(names) != wheel_files:
            fail("wheel content differs from the exact allowlist")
        if any(not stat.S_ISREG(entry.external_attr >> 16) for entry in entries):
            fail("wheel members must be regular files")
        with archive.open(f"{dist_info}/METADATA") as metadata_file:
            verify_metadata(bounded_read(metadata_file, MAX_MEMBER_BYTES), version)
        with archive.open(f"{dist_info}/licenses/LICENSE") as wheel_license:
            archived_license = bounded_read(wheel_license, MAX_MEMBER_BYTES)
        if archived_license != license_bytes:
            fail("wheel LICENSE differs from the repository LICENSE")
    root = f"{PACKAGE}-{version}"
    sdist_files = {f"{root}/{name}" for name in ("LICENSE", "README.md", "pyproject.toml", "PKG-INFO")}  # fmt: skip
    sdist_files |= {f"{root}/{name}" for name in MODULE_FILES}
    sdist_directories = {root, f"{root}/{PACKAGE}"}
    with tarfile.open(directory / sdist_name, "r:gz") as archive:
        members: list[tarfile.TarInfo] = []
        total = 0
        for member in archive:
            members.append(member)
            total += member.size
            if len(members) > MAX_MEMBER_COUNT or not 0 <= member.size <= MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:  # fmt: skip
                fail("tar member exceeds resource limit")
            if member.sparse or any(key.startswith("GNU.sparse") for key in member.pax_headers):
                fail("sparse tar members are forbidden")
            if (
                (
                    member.name in sdist_files
                    and member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE)
                )
                or (member.name in sdist_directories and member.type != tarfile.DIRTYPE)
                or member.name not in sdist_files | sdist_directories
            ):
                fail("sdist member types differ from the exact contract")
        names = safe_paths([member.name for member in members])
        if set(names) != sdist_files | sdist_directories:
            fail("sdist content differs from the exact allowlist")
        tar_metadata = archive.extractfile(next(m for m in members if m.name == f"{root}/PKG-INFO"))
        tar_license = archive.extractfile(next(m for m in members if m.name == f"{root}/LICENSE"))
        if tar_metadata is None or tar_license is None:
            fail("sdist metadata or LICENSE is unreadable")
        verify_metadata(bounded_read(tar_metadata, MAX_MEMBER_BYTES), version)
        if bounded_read(tar_license, MAX_MEMBER_BYTES) != license_bytes:
            fail("sdist LICENSE differs from the repository LICENSE")


if __name__ == "__main__":
    verify(Path(sys.argv[1] if len(sys.argv) == 2 else "dist"))
