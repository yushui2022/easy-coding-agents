# Coding Memory Benchmark

This benchmark is focused on coding-agent memory, not generic RAG. It supports
two modes:

- `synthetic`: a small local sanity benchmark for fast regression checks.
- `swe_bench_memory`: a SWE-bench-format memory probe using real benchmark
  fields such as `instance_id`, `repo`, `base_commit`, `problem_statement`,
  `patch`, `test_patch`, `FAIL_TO_PASS`, and `PASS_TO_PASS`.

The SWE-bench memory probe does not replace the official Docker execution
harness. It tests the memory layer's ability to preserve issue context,
failing-test evidence, task recovery state, and false-DONE prevention before
the agent emits a patch.

Baselines:

- `no_memory`: only recent context.
- `summary_memory`: synthetic AU2-style summary.
- `rag_fts_memory`: SQLite/FTS retrieval without quality gates.
- `evidence_gated_memory`: refs + task map + FTS + quality gates.

Run:

```powershell
python benchmark\coding_memory\run.py --baseline evidence_gated_memory
python benchmark\coding_memory\run.py --baseline summary_memory
```

Run the SWE-bench-format memory probe on a local JSONL subset:

```powershell
python benchmark\coding_memory\run.py --suite swe_bench_memory --baseline evidence_gated_memory --dataset benchmark\coding_memory\fixtures\swe_bench_mini.jsonl --limit 5
python benchmark\coding_memory\run.py --suite swe_bench_memory --baseline summary_memory --dataset benchmark\coding_memory\fixtures\swe_bench_mini.jsonl --limit 5
```

Outputs are written to `benchmark/coding_memory/results/`.

For official SWE-bench execution, use the generated prediction skeleton:

```text
benchmark/coding_memory/results/swe_bench_predictions.jsonl
```

The memory benchmark writes `memory_context_tokens` and `retrieval_hit` for
analysis. A real patching agent must fill `model_patch` before running the
official SWE-bench harness.
