# AgentLab — BYOK & Secrets Handling

How AgentLab handles model-provider API keys (bring-your-own-key) and other
secrets. The guarantees below are enforced in code and covered by tests.

## Where keys come from

AgentLab never asks you to paste a key into the chat or store it in the browser.
Keys are read **server-side only**, from either:

1. **Environment variables** — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
   `GEMINI_API_KEY` / `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, `OPENROUTER_API_KEY`
   (also accepted under `AGENTLAB_`-prefixed aliases); or
2. **A local secrets file** — `.agentlab-secrets.json`, configured through the
   Settings → Model Gateway UI. It is **gitignored**, written `chmod 0600`, and
   overlays the environment when the provider registry is built. Clearing a key
   falls back to the environment.

The default **mock** provider needs **no key at all** — demos and the entire test
suite run keyless.

## Guarantees (enforced + tested)

- **Keys never reach the frontend.** They are not returned by any API response;
  the provider list shows only a redacted hint (e.g. `sk-…abcd`).
  → `test_no_raw_key_in_provider_list`, `test_configure_refreshes_provider_list_with_redaction`
- **Keys never enter events, replay, errors, logs, validator evidence, or test
  snapshots.** HTTP errors strip auth headers; a test plants a fake key and greps
  responses/events for it.
  → `test_configured_key_never_leaks_into_events_or_errors`, `test_gemini_configured_with_key_is_redacted`
- **Only a redacted hint is ever displayed**, produced by each provider's
  `redact_key()`. → `test_redact_key`
- **The secrets file stays local.** Configured keys are written only to the
  gitignored `.agentlab-secrets.json`, never the database.
  → `test_configure_stores_secret_in_local_file_only`, `test_file_secret_overrides_env_and_clear_falls_back`
- **Writes are gated.** When `AGENTLAB_API_KEYS` is set, configuring/clearing a
  provider requires the `X-API-Key` header.
  → `test_configure_requires_api_key_when_auth_enabled`
- **Clearing a key fully removes it** and reverts the provider to env/not-
  configured. → `test_clear_removes_secret_and_reverts_status`

## Adding a provider safely (developers)

Implement the `ModelProvider` interface (`complete` / `health_check` /
`redact_key`) and register it. Requirements:

- `redact_key()` must **never** return the full key.
- never log, return, or emit the raw key — strip auth headers from any error you
  surface.
- read the key from `Settings` (env/secrets-file), never hard-code or accept it
  from the client in a response.
- keep the planted-key leak test passing.

See [DEVELOPER_INTEGRATION_GUIDE.md](DEVELOPER_INTEGRATION_GUIDE.md).

## Your responsibilities

- **Do not commit keys.** `.env` and `.agentlab-secrets.json` are gitignored —
  keep it that way.
- Prefer environment variables or the local secrets file over inlining keys
  anywhere.
- **Rotate/revoke** any key you believe has leaked — AgentLab cannot revoke a key
  on your behalf.
- Respect each provider's terms of service.
- Tests and demos use the keyless **mock** provider and require no paid keys.

This maps to OWASP secrets-management guidance (centralized control, redaction,
rotation, and preventing leakage) and the BYOK guarantees above.
