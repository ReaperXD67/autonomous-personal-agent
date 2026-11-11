"""Verify and seed the reviewed, dependency-free Hermes promotion skill namespace.

This installer runs in the networkless hermes-config service before Hermes starts.
It never loads a skill as code or reads existing agent configuration or memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

PACK_ID = "hermes-promotion"
MARKER = ".managed-manifest.json"
MAX_FILES = 64
MAX_BYTES = 262_144
PATH_PATTERN = re.compile(r"[a-zA-Z0-9._/-]+")


class PackError(ValueError):
    """The reviewed package or owned destination needs operator review."""


def _no_symlink_ancestors(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise PackError("Symlinked package or destination paths are refused")


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not PATH_PATTERN.fullmatch(value):
        raise PackError("Invalid manifest path")
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or path.as_posix() != value
            or any(part in {".", ".."} for part in path.parts)):
        raise PackError("Manifest paths must stay within the owned namespace")
    return value


def _read_manifest(path: Path) -> dict:
    _no_symlink_ancestors(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise PackError("Manifest is missing or oversized")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackError("Manifest cannot be read") from exc
    if (not isinstance(manifest, dict) or manifest.get("pack_id") != PACK_ID
            or manifest.get("schema_version") != 1):
        raise PackError("Unknown managed package")
    files = manifest.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise PackError("Invalid managed file count")
    for name, digest in files.items():
        _relative_path(name)
        if name == MARKER or not isinstance(digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}", digest):
            raise PackError("Invalid managed digest")
    return manifest


def verify_files(root: Path, manifest: dict, *, installed: bool = False) -> None:
    """Verify a complete allowlisted tree, including extras and symlink refusal."""
    _no_symlink_ancestors(root)
    if not root.is_dir():
        raise PackError("Package directory is missing")
    actual = set()
    total = 0
    allowed_directories = {
        parent.as_posix()
        for name in manifest["files"]
        for parent in PurePosixPath(name).parents
        if parent.as_posix() != "."
    }
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PackError("Symlinks are refused in a managed package")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            if relative not in allowed_directories:
                raise PackError("Unmanaged directory in owned namespace; preserve and review")
            continue
        if not path.is_file():
            raise PackError("Non-regular package file")
        if installed and relative == MARKER:
            continue
        actual.add(relative)
        if relative not in manifest["files"]:
            raise PackError("Unmanaged file in owned namespace; preserve and review")
        total += path.stat().st_size
        if total > MAX_BYTES:
            raise PackError("Managed package is oversized")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][relative]:
            raise PackError("Managed file digest mismatch; preserve and review")
    if actual != set(manifest["files"]):
        raise PackError("Managed package is incomplete")


def install(source: Path, manifest_path: Path, skills_root: Path) -> str:
    """Replace only our unchanged managed namespace, using verified staging."""
    manifest = _read_manifest(manifest_path)
    verify_files(source, manifest)
    _no_symlink_ancestors(skills_root)
    skills_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = skills_root / PACK_ID
    lock = skills_root / f".{PACK_ID}.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PackError("Managed install already locked; inspect before retrying") from exc
    stage = None
    backup = None
    try:
        os.close(lock_fd)
        _no_symlink_ancestors(target)
        if target.exists():
            previous = _read_manifest(target / MARKER)
            verify_files(target, previous, installed=True)
            if previous == manifest:
                return "unchanged"
        # Hermes recursively indexes skills/. Arbitrary dot directories are not
        # excluded, so neither staging nor rollback copies may live under it.
        stage = Path(tempfile.mkdtemp(prefix=f".{PACK_ID}.stage-", dir=skills_root.parent))
        for name in manifest["files"]:
            output = stage / name
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            output.write_bytes((source / name).read_bytes())
            output.chmod(0o600)
        marker = stage / MARKER
        marker.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        marker.chmod(0o600)
        verify_files(stage, manifest, installed=True)
        if target.exists():
            backup = Path(tempfile.mkdtemp(
                prefix=f".{PACK_ID}.previous-", dir=skills_root.parent
            ))
            backup.rmdir()
            target.rename(backup)
        try:
            stage.rename(target)
            stage = None
        except OSError:
            if backup is not None:
                backup.rename(target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
        return "installed"
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        # An unrecoverable rename failure retains the previous verified directory.
        # Never delete the backup from a failed commit path.
        lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            manifest = _read_manifest(args.manifest)
            verify_files(args.source, manifest)
            status = "verified"
        else:
            if args.skills_root is None:
                parser.error("--skills-root is required for installation")
            status = install(args.source, args.manifest, args.skills_root)
    except (PackError, OSError) as exc:
        parser.exit(1, f"Managed skills refused: {exc}\n")
    print(json.dumps({"pack_id": PACK_ID, "status": status}))


if __name__ == "__main__":
    main()
