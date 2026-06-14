"""Safe, read-only static preview of workspace sandbox files (v2.1).

Serves only files that already live inside a workspace's sandbox, so a user
can visually preview a generated static site (e.g. the Bottle Shop demo) from
inside AgentLab. It is *not* a hosting/deployment surface:

- read-only (GET); never writes, runs commands, installs, or deploys;
- every path goes through the v1.2 ``check_path`` (traversal / absolute /
  outside-root / secret-named files are rejected before any disk access);
- only a fixed allowlist of static web extensions is served;
- a size cap bounds responses; file *content* is returned, never host paths.

The frontend renders this in a sandboxed `<iframe>` (scripts isolated in an
opaque origin), so previewed markup/scripts cannot reach the parent app.
"""
from __future__ import annotations

from pathlib import Path

from .models import Workspace
from .sandbox import PathViolation, SandboxError, check_path, sandbox_root

# Generous cap for static assets (images included); the demo is far smaller.
MAX_PREVIEW_BYTES = 2 * 1024 * 1024

# Only these static web types are ever served by the preview.
_MEDIA_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def is_previewable(workspace: Workspace, workspaces_root: str) -> bool:
    """True when the sandbox exists and has an index.html to render."""
    root = sandbox_root(workspaces_root, workspace.id)
    return (root / "index.html").is_file()


def serve(
    workspace: Workspace, workspaces_root: str, path: str
) -> tuple[bytes, str]:
    """Resolve and read one allowed static file from the sandbox.

    Returns (content_bytes, media_type). Raises SandboxError (404/415/413) or
    PathViolation (caller maps to 400) — and never reads outside the sandbox.
    """
    root = sandbox_root(workspaces_root, workspace.id)
    logical = (path or "index.html").strip() or "index.html"

    # Path safety first (raises PathViolation on traversal/absolute/secret/escape).
    real: Path = check_path(root, logical)

    suffix = real.suffix.lower()
    if suffix not in _MEDIA_TYPES:
        raise SandboxError(
            f"preview does not serve '{suffix or logical}' files", status_code=415
        )
    if not real.is_file():
        raise SandboxError("file not found in the workspace sandbox", status_code=404)
    if real.lstat().st_size > MAX_PREVIEW_BYTES:
        raise SandboxError(
            f"file exceeds the {MAX_PREVIEW_BYTES // (1024 * 1024)} MB preview limit",
            status_code=413,
        )
    return real.read_bytes(), _MEDIA_TYPES[suffix]
