# v0.2 validation — 2026-10-17

Environment: Windows, Python 3.11.1, openai 2.15.0, prompt_toolkit 3.0.52. Code: local working tree in G:/Projects/easy-coding-agents. No commit or release has been published.

## Automated suite

Command: `python -B -m unittest discover -s tests -v` with `ECA_TEST_TMP=G:/DevCache/Temp/easy-coding-agents/tests` and `PYTHONUTF8=1`.

Final full run: **25 tests discovered; 24 passed, 1 skipped; no failures** (35.957 seconds). The symlink-escape test was skipped because this Windows account cannot create test symlinks. Path traversal, protected path and case variants were tested independently.

Coverage includes:

- Fragmented streaming tool arguments and rejection of incomplete model responses.
- CLI subprocess → localhost HTTP/SSE fixture → file write → persisted tool exchange → new subprocess resume with previous context.
- File approvals including denial and error strings, unique edit checks, CRLF preservation, changes during approval.
- Code/Plan/Chat execution policy, secret/internal paths, duplicate process lock.
- Markdown and tool roundtrip, recovery from completed journal entries, unknown side effects, reused provider call IDs.
- Cancellation during approval and process startup, delayed-write prevention, timeout termination, bounded output with exit code.
- Full-turn context trimming, archive-preserving summarization, repeated-tool stopping, configuration precedence.

The first integration run exposed system-proxy interception of loopback requests; local endpoints now bypass environment/system proxies. A Windows file-lock read failure and a cancellation race during process creation were also corrected before the final run.

## Interactive checks

Launched `python -B -m eca` in an actual PTY. Verified welcome panel, `/help` command table, `/mode plan` prompt update, `/status` output, and `/exit` with exit code 0. This did not issue a model request.

`main.py --doctor` recognized the existing ModelScope key without printing it. The diagnostic explicitly reports `network_checked: false`.

## Packaging

Built a Python wheel using `pip wheel . --no-build-isolation --no-deps`, with cache and temporary directories on G:. Wheel contents are limited to the `eca` package and package metadata; no `.env`, legacy sessions, or venv is included.

## What these checks do not prove

No paid/live model endpoint was called. Real provider/model tool-use quality, provider availability, API quotas, and production-scale sessions remain unverified. The configured GitHub Actions Windows/Linux matrix has not been run here. Detached child processes, hostile filesystem races, sandbox guarantees, and exact-once arbitrary external side effects are outside the implemented guarantees. This is a tested development release, not feature parity with established coding CLIs.

Wheel installation smoke check: installed with `--no-deps --no-compile --target G:/DevCache/Temp/easy-coding-agents/wheel-smoke`; from outside the repository, `python -B -m eca --version` returned `Easy Coding Agent 0.2.0`, and the imported package path was the isolated installation. Final wheel size: 22,470 bytes. SHA256: `16bea419c49f17aa92f74eba057e7d99781cf9a781edea65cbc325ff81219a21`.
