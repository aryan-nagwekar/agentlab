# AgentLab Sandbox Safety

The sandbox is where AI-built project files live and where commands run. Its
safety is **deterministic and checked before any disk access or process spawn**.
Source: `app/runtime/sandbox.py` (v1.2), `app/runtime/commands.py` (v1.3),
`app/runtime/preview.py` (v2.1).

## Workspace root

Each workspace gets a real directory under
`{AGENTLAB_WORKSPACES_ROOT}/{workspace_id}/` (default `.agentlab-workspaces/`,
gitignored). All file and command operations are confined beneath it.

## Path safety (`check_path`)

Before touching disk, every logical path is checked by `check_path`, which
rejects — in order — and raises `PathViolation`:

| Rule | Rejects |
|---|---|
| `empty_path` | empty path where a file is required |
| `null_byte` | NUL bytes in the path |
| `absolute_path` | absolute paths (POSIX `/…`, Windows `C:\…`, `~`) |
| `traversal` | any `..` segment |
| `secret_file` | secret-named files: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `.agentlab-secrets.json`, `.netrc` |
| `outside_root` | anything that **resolves** outside the workspace root — resolution follows symlinks, so this is also the **symlink-escape guard** |

A rejected operation never touches disk. The file APIs emit a
`sandbox.file.blocked` audit event with the attempted logical path (≤200 chars)
and the matched rule — never host paths or content.

## Safe file operations

`init`, `status`, `list`, `tree`, `read` (UTF-8, 256 KB cap), `write`/`create`
(1 MB cap, parents auto-created), `mkdir`, `delete` (files + empty directories).
Only logical, workspace-relative paths ever leave the server; event payloads
carry path, size, and a sha256 prefix — never file content or host paths.

## Safe command allowlist

The command runner uses **structured requests** (program + argv, never a shell
string) executed with `shell=False`. Evaluation is allowlist-first and runs
before any process spawns:

- **Allowed:** `pwd`, `ls` (safe flags + one path-checked path), `cat` (one
  path-checked file), `node/npm/python/python3 --version`, `npm test` /
  `npm run build` (require `package.json`), `python -m pytest` (requires pytest
  config or a `tests/` dir).
- **Blocked (by rule):** shell metacharacters (`; && | < > $ ` `` ` `` `),
  program paths (`/bin/ls`, `./x`), known-dangerous programs
  (`rm`/`sudo`/`curl`/`bash`/`git`/`docker`/`pip`/…), package installs, inline
  code (`-c`/`-e`), disallowed argument shapes, missing manifests, and any path
  argument failing `check_path`. Unknown programs are blocked by default.

Execution is contained: cwd locked inside the sandbox, environment rebuilt from
scratch (PATH/HOME/LANG only — host env vars/secrets never reach the child),
timeout clamped to 1–120 s, stdout/stderr capped (10 KB response / 2 KB event
summary) and **secret-redacted**. The command display string and argv are
redacted too — a secret pasted as an argument is scrubbed like one printed to
stdout. Marker-file tests prove blocked commands never spawn a process.

## Website preview safety (v2.1)

The preview serves only files **already inside** the sandbox, read-only:

- every path goes through the same `check_path` (traversal/absolute/outside-
  root/symlink/secret rejected before disk access);
- only an allowlist of static web extensions is served (else `415`);
- a 2 MB cap bounds responses;
- the route family is **GET-only** (`POST`/`DELETE` → `405`);
- it returns file content + a content-type, **never a host path**;
- the frontend embeds it in a `sandbox="allow-scripts"` iframe (no
  `allow-same-origin`), so previewed scripts run isolated in an opaque origin
  and cannot reach the parent app.

It is a **preview surface, not a host**: no dev server, build, install, or deploy.

## Local-dev limitation vs production isolation

The sandbox is **application-level**, not OS-level. Path/command safety is
enforced in the API process; there is **no** chroot, container, jail, CPU/memory
limit, or network namespace. An allowlisted interpreter (e.g. `python -m pytest`
over workspace test files) executes whatever those files contain. The
deterministic allowlist + path safety is the boundary; **container/OS isolation
is required for production** and is out of scope for Runtime v1's local-first
mode. See [RUNTIME_V1_ACCEPTANCE_MATRIX.md](RUNTIME_V1_ACCEPTANCE_MATRIX.md).
