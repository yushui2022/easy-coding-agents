# Background processes

ECA can keep a development server or watcher running while the main agent works.
The model has five tools: `process_start`, `process_list`, `process_logs`,
`process_wait`, and `process_stop`. These tools are available in code mode only.

Interactive commands (no model request):

```text
/run npm run dev
/jobs
/logs JOB_ID
/stop JOB_ID
```

Starting a command displays it for explicit host-shell approval. `--allow-shell`
also authorizes background commands in one-shot mode. Docker mode and child agents
cannot start host background jobs. Stopping accepts only an ID from this runtime,
never an arbitrary operating-system PID. Explicit `/stop` works after switching
to plan/chat mode so users can still clean up their own jobs.

The default lifetime is 600 seconds. The model can request 1–3600 seconds through
`process_start`. At most four jobs run concurrently; the last 16 job records are
retained in memory. Each output stream retains at most 64 KiB, and returned log
excerpts are additionally bounded. Output is untrusted. `process_wait` waits for
a literal string for at most 60 seconds; a match is not a health check. Test the
actual service before reporting success.

Jobs survive normal model turns and cancellation of a log wait. Normal session
close, `/new`, `/resume`, or switching to a different configured model profile
closes the runtime and stops its jobs. One-shot jobs end when that task exits.
Jobs and logs are not persisted or reattached after restart. Hard application
crashes and commands that detach/daemonize child processes are not covered by
normal cleanup; run foreground server commands and inspect externally if needed.

This is host-shell execution, not a sandbox. It inherits the host environment
and runs from the project directory. Only the configured model API key is
redacted from returned logs; avoid commands that print secrets.

Source checkout usage: `python -m eca`. An older globally installed `ecs` package
must be updated separately before these commands are available there.

Validation: `python -B -m pytest tests/test_background.py -q` exercises a real
local HTTP server, response contents, port release, lifetime expiry, normal
cleanup, log bounds, exit codes, approval/mode guards and cancellation of waits.

2026-10-18 Windows validation: full suite **310 passed, 6 skipped** (206.30s).
The subsequently added CLI dispatch/approval test was included in a separate
background suite run: **6 passed** (16.26s). No external model API calls were
needed. Optional Docker/MCP acceptance tests were not enabled in this run.
