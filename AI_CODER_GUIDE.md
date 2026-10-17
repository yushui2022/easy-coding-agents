# Developer guide — v0.4

The default runtime is `eca/`. Start with `docs/UPGRADE-v0.2.md` for architecture, permissions, persistence semantics and limitations. The former guide is retained at `docs/legacy/AI_CODER_GUIDE-v0.1.md`.

Run `python -B -m pytest -q` before delivering runtime changes. Tests must not contact paid APIs; use the local streaming HTTP fixture. Put Windows caches and temporary test directories on G:. Never print configuration secrets.

A tool must be present in `eca/tools.py` SCHEMAS, implemented in Tools, and allowed by the execution policy. Do not bypass approvals by adding a new alias. A mode restriction must apply at execution as well as schema construction. Preserve tool-result pairing on errors and cancellation. Record uncertain external outcomes honestly instead of automatically replaying them.

Keep CLI/UI separate from engine and tool behavior. Do not import legacy modules into the new runtime: several initialize state or clients at import time. Existing legacy files are historical compatibility material, not reference implementations for new persistence behavior.

File mutations must persist their before/after image before touching disk. Undo may only restore a matching recorded result; never use Git reset to implement it. Preserve the user's original uncommitted bytes and the Git index. Shell effects are outside snapshot coverage.

Retry model transport failures only before visible text output and never replay tools. Auto-compaction must keep a complete recent assistant/tool exchange and preserve the full archive. Persist stop reasons without copying provider error bodies or credentials.
