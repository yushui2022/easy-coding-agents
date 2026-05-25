# Evaluation Protocol

This project separates memory-subsystem evaluation from full coding-agent
evaluation.

## Scope

Memory benchmarks measure whether `agent_memory_core` can retrieve the right
facts, evidence refs, temporal updates, and abstention context. They do not
claim patch correctness.

Full agent benchmarks, such as the official SWE-bench Docker harness, measure
whether the agent generates a patch that applies and passes repository tests.

## Required Reporting

Every public result must include:

- repository commit hash
- dataset name and split
- case count
- answer model, if answer generation is used
- judge model, if judged QA is used
- temperature and seed settings
- baseline list
- exact command
- raw predictions
- retrieval logs
- failure cases

## Memory Evaluation Rules

1. Use the same answer model and prompt across baselines. Only the memory system
   may change.
2. Do not use oracle evidence sessions as the main score. Oracle runs are upper
   bounds only.
3. Simulate context wipe for memory baselines: ingest sessions, close the memory
   object, reopen the same database, and query with `recent_dialogue_limit=0`.
4. Report lightweight fixture metrics as term-level regression metrics, not
   official benchmark scores.
5. Keep source refs in raw artifacts so evidence can be audited.

## Baselines

- `no_memory`
- `summary_memory`
- `rag_fts_memory`
- `entity_temporal_memory`
- `evidence_gated_memory`

Optional future baselines:

- vector RAG memory
- full-context upper bound
- oracle evidence upper bound
- external memory systems with reproducible adapters

## Memory Metrics

For local lite fixtures:

- `fixture_retrieval_hit_rate`
- `term_recall_rate`
- `expected_evidence_term_coverage`
- `source_ref_coverage`
- `temporal_accuracy`
- `abstention_accuracy`
- `false_fact_rate`
- `input_tokens`
- `latency_p50`

For official datasets with answer generation:

- `answer_accuracy`
- `retrieval_recall@k`
- `evidence_precision@k`
- `source_ref_coverage`
- `knowledge_update_accuracy`
- `temporal_accuracy`
- `abstention_accuracy`
- `false_fact_rate`
- `input_tokens_mean`
- `input_tokens_p95`
- `latency_p50`
- `latency_p95`

## Artifacts

Each benchmark run writes:

```text
benchmark/memory_eval/results/<suite>_<baseline>/
  metrics.json
  cases.jsonl
  predictions.jsonl
  retrieval_logs.jsonl
  failures.md
  run_config.json
```

`predictions.jsonl` is memory-only in the current runner; `hypothesis` is left
empty until answer generation is added. `retrieval_logs.jsonl` contains the
selected memory rows and signal breakdowns.

## Claiming Results

Acceptable:

> Evidence-Gated Memory passed our local LongMemEval-inspired regression suite
> with context wipe and source-ref artifacts.

Not acceptable:

> Evidence-Gated Memory achieved an official LongMemEval score.

Acceptable only after running the official harness:

> The full easy-coding-agent achieved X resolved rate on SWE-bench Lite.
