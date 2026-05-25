# Benchmarks

## Local Regression Benchmark

Fast sanity check:

```powershell
python benchmark\coding_memory\run.py --suite synthetic --baseline evidence_gated_memory
```

This validates the memory package without Docker or remote datasets.

## Memory Eval Benchmarks

`benchmark/memory_eval` is the current main proof layer for the memory
subsystem. It does not evaluate generated patches. It checks whether the memory
module can recover facts, evidence, entities, temporal updates, and abstention
behavior with controlled local fixtures.

Memory baselines simulate context wipe: sessions are ingested, the memory object
is closed, the same SQLite database is reopened, and query-time context is built
with `recent_dialogue_limit=0`.

Run the included fixtures:

```powershell
python benchmark\memory_eval\run.py --suite longmemeval --baseline evidence_gated_memory --dataset benchmark\memory_eval\fixtures\longmemeval_lite.jsonl --limit 20
python benchmark\memory_eval\run.py --suite locomo_lite --baseline evidence_gated_memory --dataset benchmark\memory_eval\fixtures\locomo_lite.jsonl --limit 20
python benchmark\memory_eval\run.py --suite beam_lite --baseline evidence_gated_memory --beam-tokens 100000 --beam-cases 50
python benchmark\memory_eval\run.py --suite longmemeval --baseline all --dataset benchmark\memory_eval\fixtures\longmemeval_lite.jsonl --limit 20
```

For official/local dataset files, pass `--dataset path\to\data.jsonl`. The
loader accepts the internal case schema and common LongMemEval-like records with
`haystack_sessions` / `answer_session_ids`, plus LoCoMo-like `conversation` or
`dialogue` records. It does not download public datasets automatically.

Public-data helper:

```powershell
python benchmark\memory_eval\download_datasets.py --dataset locomo10
python benchmark\memory_eval\download_datasets.py --dataset longmemeval_s
```

The downloaded files are stored under the ignored local directory:

```text
benchmark/memory_eval/datasets/
```

Real-data smoke tests:

```powershell
python benchmark\memory_eval\run.py --suite locomo_lite --baseline evidence_gated_memory --dataset benchmark\memory_eval\datasets\locomo10.json --limit 5
python benchmark\memory_eval\run.py --suite longmemeval --baseline evidence_gated_memory --dataset benchmark\memory_eval\datasets\longmemeval_s_cleaned.json --limit 5
python benchmark\memory_eval\run.py --suite beam_lite --baseline evidence_gated_memory --beam-tokens 100000 --beam-cases 50
```

These runs verify adapter compatibility and evidence retrieval. They are not
official scores until run against the intended split with answer generation and
judge evaluation.

Latest real-data smoke results for `evidence_gated_memory`:

| Suite | Dataset | Limit | Retrieval / Term Recall | Evidence Source Coverage | Evidence Precision | Latency p50 | False Fact Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| LongMemEval-S | `longmemeval_s_cleaned.json` | 5 | 0.40 | 1.00 | 1.00 | 0.9048s | 0.00 |
| LoCoMo10 | `locomo10.json` | 5 | 0.00 | 0.80 | 0.80 | 0.5671s | 0.00 |
| BEAM-lite | synthetic 100K tokens | 1 | 1.00 | 1.00 | 1.00 | 0.0242s | 0.00 |

Larger partial run already completed on LongMemEval-S `limit=100`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.00 | 1,321 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.15 | 0.00 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.54 | 0.36 | 5,500,800 | 0.0007s | 0.00 |
| `keyword_fts_memory` | 100 | 0.39 | 0.87 | 182,969 | 0.5088s | 0.00 |
| `vector_rag_memory` | 100 | 0.38 | 0.67 | 184,067 | 0.7292s | 0.00 |

Status note: LongMemEval-S `evidence_gated_memory` at `limit=100` has not
completed yet. Treat the table above as a partial baseline comparison.

Publishing guidance:

- These numbers are valid as reproducible smoke results for the memory
  subsystem.
- Do not describe them as official LongMemEval / LoCoMo leaderboard scores.
- `Evidence Source Coverage` is currently more meaningful than final answer
  accuracy because this runner has not yet attached an answer generator or
  judge.

Baselines:

- `no_memory`
- `summary_memory`
- `long_context_only`
- `keyword_fts_memory`
- `vector_rag_memory`
- `evidence_gated_memory`

Legacy aliases still accepted by the runner:

- `rag_fts_memory`
- `entity_temporal_memory`

Metrics:

- `fixture_retrieval_hit_rate`
- `term_recall_rate`
- `expected_evidence_term_coverage`
- `evidence_source_term_coverage`
- `temporal_accuracy`
- `entity_link_hit_rate`
- `abstention_accuracy`
- `source_ref_coverage`
- `input_tokens`
- `latency_p50`
- `false_fact_rate`

Acceptance targets for local fixtures:

- `LongMemEval-lite retrieval_hit_rate >= 0.75`
- `temporal_accuracy >= 0.70`
- `abstention_accuracy >= 0.80`
- `false_fact_rate <= 0.10`
- `BEAM-lite 100K latency_p50 <= 1.5s`

Raw artifacts are written to:

```text
benchmark/memory_eval/results/<suite>_<baseline>/
  metrics.json
  cases.jsonl
  predictions.jsonl
  retrieval_logs.jsonl
  failures.md
  run_config.json
```

See `docs/EVAL_PROTOCOL.md` before publishing any benchmark claim.

## SWE-bench Memory Probe

SWE-bench is a mature benchmark built around real GitHub issues. The official
evaluation checks whether a generated patch passes repository tests inside a
Docker harness. This project now supports SWE-bench-format records for memory
evaluation before patch generation.

Expected fields:

- `instance_id`
- `repo`
- `base_commit`
- `problem_statement`
- `patch`
- `test_patch`
- `FAIL_TO_PASS`
- `PASS_TO_PASS`

Run the included tiny fixture:

```powershell
python benchmark\coding_memory\run.py --suite swe_bench_memory --baseline evidence_gated_memory --dataset benchmark\coding_memory\fixtures\swe_bench_mini.jsonl
python benchmark\coding_memory\run.py --suite swe_bench_memory --baseline summary_memory --dataset benchmark\coding_memory\fixtures\swe_bench_mini.jsonl
```

Outputs:

```text
benchmark/coding_memory/results/
```

For official SWE-bench harness integration, fill `model_patch` in:

```text
benchmark/coding_memory/results/swe_bench_predictions.jsonl
```

Then pass that predictions file to the official SWE-bench evaluation harness.

## What This Measures

The SWE-bench memory probe measures:

- whether failing tests and issue context survive context construction
- whether the task state can recover after failure logs
- whether false-DONE is blocked without test evidence
- whether state transitions like `DEBUGGING` require evidence refs
- prompt token cost of the memory context

It does not claim patch correctness by itself. Patch correctness must be
measured by the official SWE-bench Docker harness.
