"""Safe extraction of uploaded ZIP archives. Uploads are untrusted input."""

from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 500
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
_CHUNK = 64 * 1024


class ArchiveError(ValueError):
    """The archive is invalid, unsafe or too large."""


def _safe_target(destination: Path, member_name: str) -> Path:
    """Resolve a member path and reject anything that would land outside ``destination``."""
    normalised = member_name.replace("\\", "/")
    pure = PurePosixPath(normalised)
    if pure.is_absolute() or ".." in pure.parts or (pure.parts and ":" in pure.parts[0]):
        raise ArchiveError(f"unsafe path in archive: {member_name!r}")
    target = (destination / pure).resolve()
    if not target.is_relative_to(destination.resolve()):
        raise ArchiveError(f"unsafe path in archive: {member_name!r}")
    return target


def _validate_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > MAX_FILES:
        raise ArchiveError(f"archive has {len(members)} entries (limit {MAX_FILES})")
    declared = 0
    for info in members:
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ArchiveError(f"symbolic links are not allowed: {info.filename!r}")
        if info.flag_bits & 0x1:
            raise ArchiveError("encrypted archives are not supported")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ArchiveError(f"{info.filename!r} is larger than {MAX_MEMBER_BYTES // 2**20} MB")
        declared += info.file_size
    if declared > MAX_TOTAL_BYTES:
        raise ArchiveError(f"archive expands to more than {MAX_TOTAL_BYTES // 2**20} MB")
    return members


def _write_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> int:
    """Copy one member, counting real bytes so a lying header cannot bypass the limits."""
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with archive.open(info) as source, target.open("wb") as sink:
        while chunk := source.read(_CHUNK):
            written += len(chunk)
            if written > MAX_MEMBER_BYTES:
                raise ArchiveError(f"{info.filename!r} expands beyond the size limit")
            sink.write(chunk)
    return written


def _single_root(destination: Path) -> Path:
    """GitHub-style archives wrap everything in one folder; use it as the repository root."""
    entries = [p for p in destination.iterdir() if p.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return destination


def extract_zip(zip_path: Path, destination: Path) -> Path:
    """Extract ``zip_path`` into ``destination`` and return the repository root."""
    if not zipfile.is_zipfile(zip_path):
        raise ArchiveError("the uploaded file is not a valid ZIP archive")
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in _validate_members(archive):
                target = _safe_target(destination, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += _write_member(archive, info, target)
                if total > MAX_TOTAL_BYTES:
                    raise ArchiveError("archive expands beyond the total size limit")
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise ArchiveError(f"could not read archive: {exc}") from exc
    except ArchiveError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return _single_root(destination)
