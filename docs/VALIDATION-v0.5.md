# v0.5 validation — 2026-10-17

## Regression

Environment: Windows, Python 3.11.1. Caches, temporary projects and build/install outputs are on G:.

Full command: `python -B -m pytest -q -p no:cacheprovider --basetemp G:/DevCache/Temp/easy-coding-agents/pytest-v05`.
Result: **96 passed, 1 skipped**, 141.31 seconds. The skipped case requires Windows symlink privileges.

After adding CLI memory-command coverage and bounding context by complete records, targeted command `python -B -m pytest tests/test_knowledge.py -q -p no:cacheprovider` passed **11 tests** in 22.18 seconds. The targeted run overlaps the full run; counts should not be summed.

Coverage includes:

- Actual engine tool results create source-qualified records; closing/reopening storage and starting a new session recalls relevant historical commands.
- Changing source content marks command evidence stale and removes it from injected memory. Failed, timed-out, ambiguous, and code-changing executions are not promoted.
- Assistant prose never becomes a project fact. Explicit user constraints can be inspected and deleted from both records and FTS search.
- The CLI remember/memory/forget commands retain provenance and notify the conversation after removal. Automatic memory can be disabled without opening its database.
- Hierarchical rules are ordered by directory scope, block the entire tool batch until the next model request, reload after changes, exclude unrelated directories, and reject oversize output rather than silently truncating rules.
- A temporary Git fixture actually executes `python -B -m unittest discover -s checks` through the shell tool and stores its successful exit evidence. Other engine scenarios use deterministic provider/command fixtures. No paid model API was used; these are not claims of measured productivity gains on external repositories.

## Packaging

Wheel: `output/release/easy_coding_agent-0.5.0-py3-none-any.whl`, 57,131 bytes.
SHA256: `9e931491cd0e1027abb47f0b948c8d45797d949fc3aa0e4ebcaa356cd89790f1`.

Built with `pip wheel --no-build-isolation --no-deps` and installed with `--no-deps --no-compile` into `G:/DevCache/Temp/easy-coding-agents/wheel-smoke-v05`. From outside the repository, the installed package reports 0.5.0; both ECA and agent_memory_core import from that target. An isolated project successfully writes, retrieves and deletes a confirmed memory through the installed adapter. All 22 packaged Python modules match repository sources. `git diff --check` passed.

## Boundaries

This integrates the existing core's storage and FTS search, not its whole research orchestration pipeline. Old `.agent_memory` data is not imported. No assistant claim extractor or research DONE-state gate runs in the CLI.

Fingerprints cover bounded, eligible project files, not installed dependencies, environment variables or external systems. Matching evidence describes a historical command exit code, not a current correctness guarantee. Rules are delivered to the model before file edits; semantic compliance and arbitrary shell effects are not sandboxed. Deletion removes active memory/search entries but does not erase existing session transcripts or tool logs.

Linux and live paid providers were not tested locally. CI remains a template under docs because current GitHub credentials lack workflow scope.
