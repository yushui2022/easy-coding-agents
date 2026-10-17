# v0.4 validation — 2026-10-17

## Regression

Environment: Windows, Python 3.11.1. Temporary files, build outputs, pip cache and isolated installation are on G:.

Command: `python -B -m pytest -q -p no:cacheprovider --basetemp G:/DevCache/Temp/easy-coding-agents/pytest-v04` with `ECA_TEST_TMP` set to the project test cache.

Result: **86 passed, 1 skipped**, 226.06 seconds. The skipped test requires Windows symlink privileges. The suite includes the existing memory research tests, both model protocols and 17 new maturity tests.

New coverage includes:

- Byte-exact restoration of original CRLF and uncommitted content; a real Git staging test verifies the index stays unchanged.
- Refusal to undo over newer user content, reverse-order multi-edit undo, new-file removal, session isolation, and snapshot persistence after reopening the database.
- Write-ahead snapshots, failed writes, interruption after writing but before marking success, and interrupted undo recovery.
- Automatic compaction retaining the newest complete tool exchange, preserving the full archive and original user request, and failed summaries leaving archived history intact.
- Persisted stop reasons without sensitive exception bodies; bounded transient retries, no retry after visible partial text, permanent failures, and cancellation during backoff.
- Real local HTTP subprocess CLI tests for both OpenAI-compatible and Anthropic protocols now include listing changes, accepting one, and undoing it in separate processes. These review operations issue no model requests.

No paid model API was called. Live provider availability and Linux behavior have not been verified locally. The GitHub Actions configuration remains a template because the existing OAuth credential lacks workflow scope.

## Package

Wheel: `output/release/easy_coding_agent-0.4.0-py3-none-any.whl`.

Size: 31,529 bytes. SHA256: `cec3f1af812cbf28b5aff330e6e91f54b16acee04892dfeb7cd5e2548ec55d03`.

Built with `pip wheel --no-build-isolation --no-deps`; installed with `--no-deps --no-compile` into `G:/DevCache/Temp/easy-coding-agents/wheel-smoke-v04`. Outside the repository, the installed package reports version 0.4.0 and imports the changes/retry modules successfully. Archive source matches the checkout and contains only runtime source and distribution metadata. `git diff --check` passed.

## Scope

Snapshots cover ECA write/edit contents only. They do not restore shell effects, file permissions, directory structure or arbitrary external edits. Each edit has its own ID; undo older edits in reverse order. Accepting an edit is a review marker, not a Git commit or a deferred write. Snapshots stay local in `.eca/sessions.sqlite3` and are not automatically pruned.

Compaction is a model-generated, potentially lossy summary and consumes API requests; complete history remains stored. Retry is bounded and only applies to transient model failures before visible text output. Neither retries nor `/continue` blindly replay completed tools. Both features are configurable in `eca.toml`.
