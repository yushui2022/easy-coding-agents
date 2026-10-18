# Real-repository editing acceptance

`repository_eval.py` runs ECA against a pinned DeerFlow Git archive in a fresh
directory. It never checks out, resets or edits the source repository. Supply
`DEEPSEEK_API_KEY` through the process environment, not a tracked config file.

```powershell
python -B benchmark/repository_eval.py --source G:\Projects\deer-flow
```

Outputs go to `output/repository-eval/run-*` on the project drive. Each run
retains its source archive, working copy, baseline and final contract output,
usage, tool names, verification workflow and patch. No package installation is
needed. The command may incur model charges; missing price snapshots mean
unknown cost, not zero. The default limit is 30 turns and 600 seconds, with one
workflow repair attempt. Model aliases may change upstream.

The task migrates a public channel thread lookup helper and its callers/tests,
and prevents a connected message from falling back to the global store when its
connection repository is unavailable. The external contract exercises seven
interface/behavior cases against the actual identity and message modules.
Package initializers are bypassed and store/repository boundaries use AsyncMock;
this is not the complete upstream integration suite.

Independent checks preserve unrelated files, the Git index, original assertions,
the unrelated identity-attachment helper and a same-named local test stub. All
caller changes except one optional documentation reference must be the exact
public identifier migration. The model cannot pass simply by claiming success.
This is a bounded task contract, not an adversarial security certification.

The snapshot excludes two unrelated skill-scanner files, listed in the JSON
report. During the first preparation, one extracted test became unreadable and
then absent; the cause was not established. Both files were already absent in
the source working tree. No host-protection changes are made or recommended.

The default tool output limit is raised to 120,000 characters for this fixture:
its nested AGENTS guidance exceeds ECA's normal 24,000-character limit. Rules
remain enforced. Context is bounded at 200,000 characters / 65,536 tokens.
This larger configuration is part of the benchmark and must be reported when
comparing results. A successful run would not establish that default settings
handle arbitrarily large guidance files.

One task does not establish a general large-repository success rate. Separate
coverage is still needed for real dependency installation, upstream integration
tests, concurrent changes, process-crash recovery and other languages.

To re-run only verification on a previously accepted model patch, use
`python -B benchmark/reverify_repository.py --run output/repository-eval/run-...`.
It checks the original patch and contract hashes, creates a separate verification
session, and makes no model API calls. It preserves the original report and saves
a new timestamped reverification report. This is not a new model coding trial.
