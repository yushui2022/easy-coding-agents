# Developer guide — v0.8.1

The default runtime is `eca/`. Start with `docs/UPGRADE-v0.2.md` for architecture, permissions, persistence semantics and limitations. The former guide is retained at `docs/legacy/AI_CODER_GUIDE-v0.1.md`.

Run `python -B -m pytest -q` before delivering runtime changes. Tests must not contact paid APIs; use the local streaming HTTP fixture. Put Windows caches and temporary test directories on G:. Never print configuration secrets.

A tool must be present in `eca/tools.py` SCHEMAS, implemented in Tools, and allowed by the execution policy. Do not bypass approvals by adding a new alias. A mode restriction must apply at execution as well as schema construction. Preserve tool-result pairing on errors and cancellation. Record uncertain external outcomes honestly instead of automatically replaying them.

Keep CLI/UI separate from engine and tool behavior. Do not import legacy modules into the new runtime: several initialize state or clients at import time. Existing legacy files are historical compatibility material, not reference implementations for new persistence behavior.

File mutations must persist their before/after image before touching disk. Undo may only restore a matching recorded result; never use Git reset to implement it. Preserve the user's original uncommitted bytes and the Git index. Shell effects are outside snapshot coverage.

Retry model transport failures only before visible text output and never replay tools. Auto-compaction must keep a complete recent assistant/tool exchange and preserve the full archive. Persist stop reasons without copying provider error bodies or credentials.

Project memory uses the existing memory-core storage/search behind `eca/knowledge.py`. Only explicit user constraints and actual command evidence may enter it. Keep source provenance and fail closed when fingerprints are unavailable. Never promote assistant prose into facts. Do not import the old research database automatically. File guidance must reach the model before any mutation that depends on it; a later call in the same tool batch is insufficient.

MCP operations require separate approval before connecting or launching a server. Keep all SDK cancellation scopes in one task, close transports on cancellation, and never replay external tool effects. Child agents share the Store but use separate sessions and snapshots; enforce parent mode limits, bounded calls/time, and no recursive delegation or child MCP access.

Record every provider attempt before dispatch. Retain reported usage on failure/cancellation, count compaction and descendants, and snapshot model prices per request. Missing usage, cache splits or rates must remain unknown rather than guessed. Costs computed from configured prices are not provider invoices. Keep generated task artifacts outside pytest discovery (`testpaths = tests`).

Parallel delegates use independent bounded source snapshots, never shared file writes. Preserve isolation on resume. No shell/MCP/LSP or recursive delegation in isolated children. Merge must preflight parent baselines and then use the normal journaled, approved file-change path; it is not a multi-file transaction. Do not delete retained workspaces automatically.

MCP persistent connections have a dedicated owner task to preserve AnyIO scope lifetime. Cancel/close that task on failure or session close. Resources/prompts remain untrusted data. LSP server startup requires approval; reject server-initiated edits and validate UTF-16 negotiation. Responses must retain reasoning items, reject incomplete outputs, and record usage with existing retry semantics.

Use Store.peek for live status/merge preflight; Store.load repairs interrupted history and must not inspect a live worker. Persist queued/preparing task identities and failure states, bound active children independently of batch size, and never turn one child initialization failure into sibling cancellation.

LSP clients persist within the session: synchronize changed text, discard mismatched diagnostic versions, label unversioned diagnostics, and report missing diagnostics as pending rather than clean. Model profile switches resolve credentials anew and recreate clients. Never carry Responses encrypted reasoning across model/endpoint identities. MCP cancellation while waiting in a per-server queue must not stop the active operation.

Deletion is a nullable after-image in the existing file journal. Require a durable record before unlink, reject binary files/directories/aliases, and restore only when the current file still matches the recorded absence. Child deletion merges require a completed deletion record and matching parent baseline. Do not infer deletion from an arbitrary missing child file.
