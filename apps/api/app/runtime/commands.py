"""Safe command runner for workspace sandboxes (v1.3).

A narrow, deterministic command layer — NOT the future enforcement gateway.
Requests are structured (program + argv, never a shell string), evaluated by
an allowlist-first safety policy before any process is spawned, and executed
with ``shell=False``, cwd locked inside the workspace sandbox, a scrubbed
environment, a hard timeout, and capped/redacted output capture.

Block-by-default: shell metacharacters, program paths, known-dangerous
programs, package installs, unknown programs, disallowed argument shapes,
and any path argument that fails the v1.2 path-safety checker are all
rejected *before execution* with a ``sandbox.command.blocked`` audit event.

Out of scope here (later Runtime versions): interactive shells, persistent
sessions, long-running processes, dev servers, package installation,
orchestration, policy engine, approvals, validators, quarantine.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from .. import models as core_models
from .models import Workspace
from .sandbox import (
    PathViolation,
    SandboxBlocked,
    SandboxError,
    _require_initialized,
    check_path,
    sandbox_root,
)
from .service import _emit

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
# API responses carry up to this much of each stream; event payloads carry a
# shorter summary so the activity run stays light.
MAX_OUTPUT_CHARS = 10_000
EVENT_OUTPUT_CHARS = 2_000

# Characters that signal shell composition. Execution is shell=False, so none
# of these would *expand* — they are blocked outright so a request can never
# even look like chaining, redirection, or substitution.
_METACHARACTERS = re.compile(r"[;&|<>`$\n\r]")

# Obvious secret shapes scrubbed from captured output before it is stored or
# returned. Conservative: API keys/tokens, not generic entropy. The leading
# boundary stops false positives inside ordinary ids (e.g. "task-abc123"
# must not match the sk- pattern).
_SECRET_PATTERNS = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}"
    r"|gho_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}|xox[bap]-[A-Za-z0-9-]{10,})"
)

# Named-and-known dangerous programs get an explicit rule (clearer audit
# trail than unknown_command). Everything not allowlisted is blocked anyway.
DANGEROUS_PROGRAMS = frozenset(
    {
        "rm", "rmdir", "mv", "cp", "dd", "mkfs", "chmod", "chown", "chgrp",
        "sudo", "su", "doas", "kill", "killall", "pkill", "reboot", "shutdown",
        "ssh", "scp", "sftp", "rsync", "curl", "wget", "nc", "netcat", "ncat",
        "telnet", "ftp", "bash", "sh", "zsh", "fish", "dash", "ksh", "csh",
        "perl", "ruby", "php", "pip", "pip3", "yarn", "pnpm", "npx", "uv",
        "git", "docker", "podman", "kubectl", "helm", "terraform", "vercel",
        "netlify", "flyctl", "heroku", "aws", "gcloud", "az", "psql", "mysql",
        "sqlite3", "mongo", "redis-cli", "env", "printenv", "export",
    }
)

_PACKAGE_INSTALL_SUBCOMMANDS = frozenset(
    {"install", "i", "add", "ci", "uninstall", "remove", "rm", "update",
     "upgrade", "publish", "exec", "x", "link", "audit"}
)


class CommandBlock(Exception):
    """Internal: a safety rule rejected the command (reason + rule)."""

    def __init__(self, reason: str, rule: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule = rule


def _redact(text: str) -> str:
    return _SECRET_PATTERNS.sub("[redacted]", text)


def _cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) > limit:
        return text[:limit], True
    return text, False


# ----------------------------------------------------------------- allowlist


def _no_args(args: list[str], root: Path) -> None:
    if args:
        raise CommandBlock("this command takes no arguments", "disallowed_args")


def _version_only(args: list[str], root: Path) -> None:
    if args != ["--version"]:
        raise CommandBlock(
            "only '--version' is allowed for this command", "disallowed_args"
        )


_LS_FLAGS = frozenset({"-l", "-a", "-la", "-al", "-1", "-lh", "-lah", "-alh"})


def _ls_args(args: list[str], root: Path) -> None:
    paths = 0
    for arg in args:
        if arg in _LS_FLAGS:
            continue
        if arg.startswith("-"):
            raise CommandBlock(f"ls flag {arg!r} is not allowed", "disallowed_args")
        check_path(root, arg, allow_root=True)  # PathViolation propagates
        paths += 1
        if paths > 1:
            raise CommandBlock("ls accepts at most one path", "disallowed_args")


def _cat_args(args: list[str], root: Path) -> None:
    if len(args) != 1 or args[0].startswith("-"):
        raise CommandBlock(
            "cat accepts exactly one workspace-relative file path", "disallowed_args"
        )
    check_path(root, args[0])  # secret-name + escape checks included


def _npm_args(args: list[str], root: Path) -> None:
    if args and args[0] in _PACKAGE_INSTALL_SUBCOMMANDS:
        raise CommandBlock(
            "package installation and npm lifecycle commands are blocked in v1.3",
            "package_install",
        )
    if args == ["--version"]:
        return
    if args in (["test"], ["run", "build"]):
        if not (root / "package.json").is_file():
            raise CommandBlock(
                "package.json not found in the workspace sandbox", "missing_manifest"
            )
        return
    raise CommandBlock(
        "only 'npm --version', 'npm test', and 'npm run build' are allowed",
        "disallowed_args",
    )


def _python_args(args: list[str], root: Path) -> None:
    if args == ["--version"]:
        return
    if args == ["-m", "pytest"]:
        has_pytest_setup = any(
            (root / name).exists()
            for name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tests")
        )
        if not has_pytest_setup:
            raise CommandBlock(
                "no pytest configuration or tests/ directory in the workspace sandbox",
                "missing_manifest",
            )
        return
    if args[:1] == ["-c"]:
        raise CommandBlock("inline code execution ('-c') is blocked", "inline_code")
    raise CommandBlock(
        "only '--version' and '-m pytest' are allowed for python", "disallowed_args"
    )


def _node_args(args: list[str], root: Path) -> None:
    if args == ["--version"]:
        return
    if args[:1] in (["-e"], ["--eval"], ["-p"], ["--print"]):
        raise CommandBlock("inline code execution ('-e') is blocked", "inline_code")
    raise CommandBlock("only '--version' is allowed for node", "disallowed_args")


@dataclass(frozen=True)
class CommandSpec:
    description: str
    examples: list[str]
    validate: Callable[[list[str], Path], None]


ALLOWED_COMMANDS: dict[str, CommandSpec] = {
    "pwd": CommandSpec("Print the working directory", ["pwd"], _no_args),
    "ls": CommandSpec(
        "List workspace files (flags: -l -a -la -1; one optional path)",
        ["ls", "ls -la", "ls src"],
        _ls_args,
    ),
    "cat": CommandSpec(
        "Print one workspace file (path-safety checked)",
        ["cat README.md"],
        _cat_args,
    ),
    "node": CommandSpec("Node.js version check", ["node --version"], _node_args),
    "npm": CommandSpec(
        "npm version / test / build (requires package.json for test/build)",
        ["npm --version", "npm test", "npm run build"],
        _npm_args,
    ),
    "python": CommandSpec(
        "Python version check / pytest (requires pytest config or tests/)",
        ["python --version", "python -m pytest"],
        _python_args,
    ),
    "python3": CommandSpec(
        "Python 3 version check / pytest (requires pytest config or tests/)",
        ["python3 --version", "python3 -m pytest"],
        _python_args,
    ),
}


def allowed_commands() -> list[dict[str, Any]]:
    return [
        {"command": name, "description": spec.description, "examples": spec.examples}
        for name, spec in sorted(ALLOWED_COMMANDS.items())
    ]


# ------------------------------------------------------------------ safety


def evaluate(command: str, args: list[str], root: Path) -> None:
    """Deterministic allow/block decision. Raises CommandBlock to block;
    returning means the command is allowlisted with valid arguments."""
    tokens = [command, *args]
    for token in tokens:
        if "\x00" in token:
            raise CommandBlock("null bytes are not allowed", "shell_metacharacter")
        if _METACHARACTERS.search(token):
            raise CommandBlock(
                "shell metacharacters (;&|<>`$) are not allowed — commands run "
                "without a shell and cannot be chained",
                "shell_metacharacter",
            )
    if "/" in command or "\\" in command or command.startswith((".", "~")):
        raise CommandBlock(
            "program paths are not allowed; use a bare allowlisted command name",
            "program_path",
        )
    lowered = command.lower()
    if lowered in DANGEROUS_PROGRAMS:
        raise CommandBlock(
            f"'{command}' is a blocked command class in the sandbox", "dangerous_command"
        )
    spec = ALLOWED_COMMANDS.get(lowered)
    if spec is None:
        raise CommandBlock(
            f"'{command}' is not on the sandbox command allowlist", "unknown_command"
        )
    spec.validate(args, root)


def _scrubbed_env() -> dict[str, str]:
    """Minimal environment: enough to locate interpreters, nothing else.
    Host env vars (and any secrets in them) never reach sandbox commands."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "NO_COLOR": "1",
        "CI": "1",
    }


# ------------------------------------------------------------------- runner


def run_command(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    *,
    command: str,
    args: list[str],
    timeout_seconds: int,
    working_subdir: str = "",
) -> tuple[dict[str, Any], list[core_models.Event]]:
    root = sandbox_root(workspaces_root, workspace.id)
    _require_initialized(root)

    # Redacted everywhere it appears: a secret pasted as an *argument* must
    # not survive into events any more than one printed to stdout would.
    display = _redact(shlex.join([command, *args]))
    stored: list[core_models.Event] = []

    def emit(event_type: str, payload: dict[str, Any]) -> None:
        stored.extend(
            _emit(session, workspace, event_type, {"command": display[:200], **payload})
        )

    emit("sandbox.command.proposed", {"argv": [_redact(a) for a in [command, *args]][:20]})

    def block(reason: str, rule: str) -> SandboxBlocked:
        emit("sandbox.command.blocked", {"reason": reason, "rule": rule})
        exc = SandboxBlocked(reason, rule, display[:200])
        exc.events = stored
        return exc

    # Working directory must pass the same path safety as file operations.
    try:
        cwd = check_path(root, working_subdir, allow_root=True)
    except PathViolation as violation:
        raise block(f"working directory: {violation.reason}", violation.rule)
    if not cwd.is_dir():
        raise SandboxError("working directory not found", status_code=404)
    logical_cwd = cwd.resolve().relative_to(root.resolve()).as_posix() if cwd != root else "."

    # Deterministic safety decision — nothing executes unless this passes.
    try:
        evaluate(command, args, root)
    except PathViolation as violation:
        raise block(f"command argument: {violation.reason}", violation.rule)
    except CommandBlock as decision:
        raise block(decision.reason, decision.rule)

    emit("sandbox.command.allowed", {"rule": "allowlist", "cwd": logical_cwd})

    executable = shutil.which(command)
    if executable is None:
        emit(
            "sandbox.command.failed",
            {"error": f"'{command}' is not installed on this host", "exit_code": None},
        )
        return (
            {
                "command": display,
                "argv": [command, *args],
                "cwd": logical_cwd,
                "status": "failed",
                "exit_code": None,
                "duration_ms": 0,
                "stdout": "",
                "stderr": f"'{command}' is not installed on this host",
                "stdout_truncated": False,
                "stderr_truncated": False,
            },
            stored,
        )

    timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))
    emit("sandbox.command.started", {"cwd": logical_cwd, "timeout_seconds": timeout})
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 — argv list, shell=False, scrubbed env
            [executable, *args],
            cwd=cwd,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - started) * 1000)
        emit(
            "sandbox.command.timed_out",
            {"timeout_seconds": timeout, "duration_ms": duration_ms},
        )
        return (
            {
                "command": display,
                "argv": [command, *args],
                "cwd": logical_cwd,
                "status": "timed_out",
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout": "",
                "stderr": f"command exceeded the {timeout}s timeout and was terminated",
                "stdout_truncated": False,
                "stderr_truncated": False,
            },
            stored,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout, stdout_truncated = _cap(_redact(completed.stdout or ""), MAX_OUTPUT_CHARS)
    stderr, stderr_truncated = _cap(_redact(completed.stderr or ""), MAX_OUTPUT_CHARS)
    status = "completed" if completed.returncode == 0 else "failed"
    emit(
        f"sandbox.command.{status}",
        {
            "cwd": logical_cwd,
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout_summary": stdout[:EVENT_OUTPUT_CHARS],
            "stderr_summary": stderr[:EVENT_OUTPUT_CHARS],
            "output_truncated": stdout_truncated
            or stderr_truncated
            or len(stdout) > EVENT_OUTPUT_CHARS
            or len(stderr) > EVENT_OUTPUT_CHARS,
        },
    )
    return (
        {
            "command": display,
            "argv": [command, *args],
            "cwd": logical_cwd,
            "status": status,
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        },
        stored,
    )
