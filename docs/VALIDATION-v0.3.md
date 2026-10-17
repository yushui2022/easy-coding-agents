# v0.3 validation — 2026-10-17

Environment: Windows, Python 3.11.1. All caches/build/install/test temporary directories were on G:.

## Regression

`python -B -m pytest -q -p no:cacheprovider --basetemp G:/DevCache/Temp/easy-coding-agents/pytest-v03`

Result: **69 passed, 1 skipped**, 108.26 seconds. The skipped case requires Windows symlink privileges. Includes upstream memory tests and the new CLI tests. A legacy provider test was isolated from the developer's private dotenv configuration; runtime behavior was not changed to satisfy the test.

Native protocol tests cover text, usage, headers, fragmented tool arguments, multiple tool results, truncation at each event boundary, output limits, malformed JSON, duplicate identities, unsupported blocks, cancellation/stream closure, HTTP errors, and environment precedence. Both protocols also run through real local HTTP servers with subprocess CLI execution, a file write, and a second process resuming the stored conversation. No paid model API was called.

## Package

Built `output/release/easy_coding_agent-0.3.0-py3-none-any.whl` using pip wheel with `--no-build-isolation --no-deps`. Size: 26,237 bytes. SHA256: `0bc9238bde570296c4313481cf4c766a7028a5405c5f7e2a0bbeb752f40b6884`.

Installed with `--no-deps --no-compile` into `G:/DevCache/Temp/easy-coding-agents/wheel-smoke-v03`. Outside the repository, `python -B -m eca --version` reported 0.3.0 and the native provider imported from that installation. Archive contents include only ECA source and package metadata.

## Limits

Live Anthropic service and Linux execution were not tested locally. Thinking, server tools, images, native transport retries, and OAuth subscriptions are not supported. CI is a template at `docs/ci-workflow.yml`, not an active GitHub Actions workflow: the current GitHub OAuth credential lacks workflow scope.

Upstream memory research is retained as a separate module; it has not been wired into the new CLI. Historical v0.2 validation remains in its original report.
