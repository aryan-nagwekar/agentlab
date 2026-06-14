# AgentLab Human Approval

The Human Approval System (v1.6, `app/runtime/approvals.py`) resolves the
enforcement gateway's `require_human_approval` decisions. A risky action halts,
becomes a pending approval request, and waits for a human.

## Approval request lifecycle

When enforcement returns `require_human_approval`, AgentLab creates a pending
**`ApprovalRequest`** (deduplicated per unresolved action), carrying:

- a plain-English summary and a technical summary,
- the matched policy rules and a risk level,
- a recommended decision and the allowed options,
- and — for integrated file/command surfaces — the **exact stored payload**
  (file content, command argv) needed to resume the action verbatim.

The stored payload is **never editable through the API** and **never appears in
events**. The action's `approval_id` is threaded into the 403 detail and the
proposal metadata. Statuses: `pending → approved / denied / cancelled /
rerouted / quarantine_requested` (`expired` is reserved; there is no auto-expiry).

## Resolutions

| Resolution | Behavior |
|---|---|
| **approve** / **approve_once** | Re-runs the *exact stored action* through the existing safe executors (v1.2 file service / v1.3 command runner). Their own safety **re-runs** — a command that no longer passes is refused even after approval. |
| **deny** | Marks the action blocked; it never executes. |
| **approve_readonly** | Executes only a genuinely read-only path (e.g. `file.read`), otherwise records a skip with a reason. |
| **reroute** | Records reroute intent + events; no autonomous reassignment. |
| **quarantine** | Applies **real quarantine** to the linked agent (v1.7) and emits the quarantine events. |
| **cancel** | Cancels the pending request without executing. |

Every transition emits `approval.*` events (`requested`, `approved`, `denied`,
`cancelled`, `override_used`, `execution_resumed`/`failed`/`skipped`,
`reroute_requested`, `quarantine_requested`) into the workspace activity run, so
Replay reconstructs the full request → decision → resume trail. Double-resolution
returns `409`.

## Resume behavior

Approval resumes the **exact** stored action — not a user-edited one — between
`action.started` and `action.completed`, with the underlying v1.2/v1.3 safety
re-running. If a safe executor cannot resume (e.g. read-only approval for a
non-read action), the approval is marked approved but **not executed**, with a
clear reason.

## Approval-held action safety

While an action is approval-required, it is **not executed and not on disk**.
The Bottle Shop demo's payment-file write is the canonical example: it stays
pending until you approve it, and only then is the exact write applied. Deny it
and the file never appears. Tests assert the disk is untouched before approval
and that approve writes the exact stored content.

## Routes

`GET /api/runtime/workspaces/{id}/approvals[?status=]` ·
`GET …/approvals/pending-count` · `GET …/approvals/{id}` ·
`POST …/approvals/{id}/{approve,deny,approve-readonly,reroute,quarantine,cancel}`
(writes gated by the existing `X-API-Key`). UI: the **Approvals** panel.

## Limitations

Resume is **action-level**, not a full workflow resume. `reroute` records intent
only (no auto-reassignment). There is no approval auto-expiry. See
[RUNTIME_V1_ACCEPTANCE_MATRIX.md](RUNTIME_V1_ACCEPTANCE_MATRIX.md) (#9, #11).
