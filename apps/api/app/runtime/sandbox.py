"""Workspace-bounded sandboxed file runtime (v1.2).

The first real runtime layer, kept deliberately narrow: file operations only,
confined beneath ``{workspaces_root}/{workspace_id}``. No shell, no command
runner, no build/test execution, no dev server, no orchestration, and no
enforcement gateway — those belong to later Runtime versions.

Path safety is deterministic and checked before any disk access: absolute
paths, ``..`` traversal, null bytes, secret-named files, and anything that
*resolves* outside the workspace root (which also catches symlink escapes,
since resolution follows symlinks) are rejected. A rejected operation never
touches disk; it emits a ``sandbox.file.blocked`` event carrying only the
attempted logical path and the matched rule — never host paths or content.

Successful mutations emit ``sandbox.*`` events through the same collector
pipeline as every other workspace action, so the activity feed, timeline,
and replay reconstruct file history unchanged. Event payloads carry logical
workspace paths, sizes, and content hashes — never file content and never
host filesystem paths.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy.orm import Session

from .. import models as core_models
from .models import Workspace
from .service import _emit

# Reads are capped so the API never streams huge blobs into the UI; writes
# are capped at the schema layer (FileWriteIn.content).
MAX_READ_BYTES = 256 * 1024

# Files whose *name* marks them as likely secrets. Reading, writing, or
# deleting these through the sandbox is blocked outright — the sandbox is for
# project files, and secret material must never transit events or responses.
_SECRET_EXACT = {".env", ".agentlab-secrets.json", ".netrc", ".pgpass"}
_SECRET_PREFIXES = (".env.", "id_rsa", "id_ed25519", "id_ecdsa")
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class SandboxBlocked(Exception):
    """A path-safety rule rejected the operation (already logged as an event)."""

    def __init__(self, reason: str, rule: str, logical_path: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule = rule
        self.logical_path = logical_path
        self.events: list[core_models.Event] = []


class PathViolation(Exception):
    """Pure path-safety rejection — no event attached. Callers that audit
    differently (e.g. the v1.3 command runner emits sandbox.command.blocked
    instead of sandbox.file.blocked) catch this and emit their own event."""

    def __init__(self, reason: str, rule: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule = rule


class SandboxError(Exception):
    """A non-security operational error (missing file, not utf-8, …)."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def is_secret_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in _SECRET_EXACT
        or lowered.startswith(_SECRET_PREFIXES)
        or lowered.endswith(_SECRET_SUFFIXES)
    )


def sandbox_root(workspaces_root: str, workspace_id: str) -> Path:
    return Path(workspaces_root) / workspace_id


def _blocked(
    session: Session,
    workspace: Workspace,
    *,
    operation: str,
    logical_path: str,
    reason: str,
    rule: str,
) -> SandboxBlocked:
    """Emit the audit event and build the exception; the operation never ran."""
    exc = SandboxBlocked(reason, rule, logical_path)
    exc.events = _emit(
        session,
        workspace,
        "sandbox.file.blocked",
        {
            "operation": operation,
            "attempted_path": logical_path[:200],
            "reason": reason,
            "rule": rule,
        },
    )
    return exc


def check_path(root: Path, logical: str, *, allow_root: bool = False) -> Path:
    """Pure deterministic path safety: map a logical workspace path to a real
    path or raise PathViolation. No events, no disk writes — every rule runs
    before any disk access."""
    logical = (logical or "").strip()

    if logical in ("", "."):
        if allow_root:
            return root
        raise PathViolation("a file path is required", "empty_path")
    if "\x00" in logical:
        raise PathViolation("null bytes are not allowed in paths", "null_byte")
    # Reject absolute paths in both POSIX and Windows spellings, plus ~.
    if (
        logical.startswith(("/", "\\", "~"))
        or Path(logical).is_absolute()
        or (len(logical) >= 2 and logical[1] == ":")
    ):
        raise PathViolation(
            "absolute paths are not allowed; use a workspace-relative path",
            "absolute_path",
        )
    if any(part == ".." for part in PurePosixPath(logical).parts):
        raise PathViolation("path traversal ('..') is not allowed", "traversal")
    if any(is_secret_name(part) for part in PurePosixPath(logical).parts):
        raise PathViolation(
            "secret-like files are blocked in the sandbox", "secret_file"
        )

    # Resolution follows symlinks, so a link pointing outside the root lands
    # here as an outside-root rejection — the symlink-escape guard.
    resolved = (root / logical).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PathViolation(
            "path resolves outside the workspace sandbox", "outside_root"
        )
    return resolved


def resolve_path(
    session: Session,
    workspace: Workspace,
    root: Path,
    logical: str,
    *,
    operation: str,
    allow_root: bool = False,
) -> Path:
    """check_path, with rejections audited as sandbox.file.blocked events."""
    try:
        return check_path(root, logical, allow_root=allow_root)
    except PathViolation as violation:
        logical_path = "<null-byte>" if violation.rule == "null_byte" else (logical or "").strip()
        raise _blocked(
            session,
            workspace,
            operation=operation,
            logical_path=logical_path,
            reason=violation.reason,
            rule=violation.rule,
        )


def _logical(root: Path, real: Path) -> str:
    """The only path representation that ever leaves the server."""
    return real.resolve().relative_to(root.resolve()).as_posix()


def _require_initialized(root: Path) -> None:
    if not root.is_dir():
        raise SandboxError("sandbox not initialized for this workspace", status_code=409)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# ------------------------------------------------------------------ lifecycle


def init_sandbox(
    session: Session, workspace: Workspace, workspaces_root: str
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    if root.is_dir():
        return status(workspace, workspaces_root), []
    root.mkdir(parents=True)
    stored = _emit(session, workspace, "sandbox.initialized", {})
    return status(workspace, workspaces_root), stored


def status(workspace: Workspace, workspaces_root: str) -> dict[str, Any]:
    root = sandbox_root(workspaces_root, workspace.id)
    if not root.is_dir():
        return {
            "workspace_id": workspace.id,
            "initialized": False,
            "file_count": 0,
            "directory_count": 0,
            "total_bytes": 0,
        }
    files = directories = total = 0
    for entry in root.rglob("*"):
        if entry.is_symlink() or entry.is_file():
            files += 1
            try:
                total += entry.lstat().st_size
            except OSError:
                pass
        elif entry.is_dir():
            directories += 1
    return {
        "workspace_id": workspace.id,
        "initialized": True,
        "file_count": files,
        "directory_count": directories,
        "total_bytes": total,
    }


# ----------------------------------------------------------------- read paths


def _entry(root: Path, real: Path) -> dict[str, Any]:
    stat = real.lstat()
    return {
        "name": real.name,
        "path": _logical(root, real),
        "type": "directory" if real.is_dir() and not real.is_symlink() else "file",
        "size_bytes": 0 if real.is_dir() and not real.is_symlink() else stat.st_size,
        "modified_at": stat.st_mtime,
    }


def list_dir(
    session: Session, workspace: Workspace, workspaces_root: str, logical: str
) -> list[dict[str, Any]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)
    real = resolve_path(
        session, workspace, root, logical, operation="list", allow_root=True
    )
    if not real.is_dir():
        raise SandboxError("not a directory", status_code=404)
    entries = sorted(
        (_entry(root, child) for child in real.iterdir()),
        key=lambda e: (e["type"] != "directory", e["name"].lower()),
    )
    return entries


def tree(
    session: Session, workspace: Workspace, workspaces_root: str
) -> list[dict[str, Any]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)

    def walk(directory: Path) -> list[dict[str, Any]]:
        nodes = []
        for child in sorted(
            directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        ):
            node = _entry(root, child)
            if node["type"] == "directory":
                node["children"] = walk(child)
            nodes.append(node)
        return nodes

    return walk(root)


def read_file(
    session: Session, workspace: Workspace, workspaces_root: str, logical: str
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)
    real = resolve_path(session, workspace, root, logical, operation="read")
    if not real.is_file():
        raise SandboxError("file not found", status_code=404)
    if real.lstat().st_size > MAX_READ_BYTES:
        raise SandboxError(
            f"file exceeds the {MAX_READ_BYTES // 1024} KB read limit"
        )
    data = real.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise SandboxError("binary files cannot be read as text")
    path = _logical(root, real)
    stored = _emit(
        session,
        workspace,
        "sandbox.file.read",
        {"path": path, "size_bytes": len(data)},
    )
    return (
        {"path": path, "content": content, "size_bytes": len(data), "sha256": _sha256(data)},
        stored,
    )


# ------------------------------------------------------------------ mutations


def write_file(
    session: Session, workspace: Workspace, workspaces_root: str, logical: str, content: str
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)
    real = resolve_path(session, workspace, root, logical, operation="write")
    if real.is_dir():
        raise SandboxError("path is a directory")
    existed = real.exists()
    real.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    real.write_bytes(data)
    path = _logical(root, real)
    stored = _emit(
        session,
        workspace,
        "sandbox.file.updated" if existed else "sandbox.file.created",
        {"path": path, "size_bytes": len(data), "sha256": _sha256(data)},
    )
    return (
        {"path": path, "size_bytes": len(data), "sha256": _sha256(data), "created": not existed},
        stored,
    )


def make_dir(
    session: Session, workspace: Workspace, workspaces_root: str, logical: str
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)
    real = resolve_path(session, workspace, root, logical, operation="mkdir")
    if real.exists():
        if real.is_dir():
            return {"path": _logical(root, real), "created": False}, []
        raise SandboxError("a file with that name already exists")
    real.mkdir(parents=True)
    path = _logical(root, real)
    stored = _emit(session, workspace, "sandbox.directory.created", {"path": path})
    return {"path": path, "created": True}, stored


def delete_path(
    session: Session, workspace: Workspace, workspaces_root: str, logical: str
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)
    real = resolve_path(session, workspace, root, logical, operation="delete")
    path = _logical(root, real)
    if real.is_symlink() or real.is_file():
        real.unlink()
        kind = "file"
    elif real.is_dir():
        try:
            real.rmdir()
        except OSError:
            raise SandboxError("directory is not empty")
        kind = "directory"
    else:
        raise SandboxError("file not found", status_code=404)
    stored = _emit(
        session, workspace, "sandbox.file.deleted", {"path": path, "kind": kind}
    )
    return {"path": path, "kind": kind}, stored
