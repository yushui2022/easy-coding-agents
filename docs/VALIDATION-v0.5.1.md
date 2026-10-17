# v0.5.1 validation — 2026-10-17

Environment: Windows, Python 3.11.1; build, install, pip cache and temporary projects on G:.

## Regression

`python -B -m pytest -q -p no:cacheprovider --basetemp G:/DevCache/Temp/easy-coding-agents/pytest-v051`

**105 passed, 1 skipped**, 162.00 seconds. The skipped case requires Windows symlink privileges. Eight new doctor/recovery tests also passed in isolation.

Coverage: missing keys, malformed TOML, invalid project/state paths, configuration typos and types, credential-bearing endpoint parameters, read-only Git ignore/tracked-file checks, empty session listing without state creation, and file undo with broken model configuration. Existing runtime, memory, protocol and CLI tests remain included.

Running `python -B -m eca --doctor --json` in this repository returned ready=true with all local checks passing. This only confirms local readiness: no API request, key validation or filesystem write probe was performed.

## Package

Built `easy_coding_agent-0.5.1-py3-none-any.whl` with `pip wheel --no-build-isolation --no-deps`.
Size: 57,562 bytes. SHA256: `44679adf672fb068b9fec3bc060aaec7a459f6ba1dd36373d58efdd46856b7d1`.

Installed with `--no-deps --no-compile` into `G:/DevCache/Temp/easy-coding-agents/wheel-smoke-v051`. Outside the repository, the installed CLI diagnosed a missing API key, returned exit code 1 and did not create `.eca`. The doctor module imported from the isolated installation. Packaged Python sources match the checkout; `git diff --check` passed.

## Compatibility and limits

Doctor now returns a structured checks list and ready flag; errors produce exit code 1, warnings alone do not. It reports endpoint_origin rather than displaying potentially sensitive endpoint paths. Unknown agent options are rejected instead of silently ignored. Local session/review commands do not load model configuration.

No paid model APIs or Linux host were tested. The CI workflow remains a template, not an active hosted check.
