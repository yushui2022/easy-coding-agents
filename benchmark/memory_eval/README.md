# Memory Eval Benchmarks

`benchmark/memory_eval` measures the memory subsystem itself, not end-to-end
patch correctness. Memory baselines ingest sessions, close the memory object,
reopen the same database, and query with `recent_dialogue_limit=0` to simulate
context wipe.

It supports three local suites:

- `longmemeval`: multi-session long-term memory, temporal updates, abstention.
- `locomo_lite`: long conversation style relationship and event recall.
- `beam_lite`: synthetic scale stress for retrieval latency and token cost.

## Run

```powershell
python benchmark\memory_eval\run.py --suite longmemeval --baseline evidence_gated_memory --dataset benchmark\memory_eval\fixtures\longmemeval_lite.jsonl --limit 20
python benchmark\memory_eval\run.py --suite locomo_lite --baseline evidence_gated_memory --dataset benchmark\memory_eval\fixtures\locomo_lite.jsonl --limit 20
python benchmark\memory_eval\run.py --suite beam_lite --baseline evidence_gated_memory --beam-tokens 100000
```

The loader also normalizes common official-style schemas:

- LongMemEval-like records with `question`, `answer`, `question_type`,
  `haystack_sessions`, and `answer_session_ids`.
- LoCoMo-like records with `question`, `answer`, and `conversation` /
  `dialogue` style history.

Official dataset files are not downloaded automatically. Pass local JSON/JSONL
files with `--dataset`.

Baselines:

- `no_memory`
- `summary_memory`
- `rag_fts_memory`
- `entity_temporal_memory`
- `evidence_gated_memory`

## Metrics

- `fixture_retrieval_hit_rate`: expected answer terms are present in the built memory context.
- `term_recall_rate`: term-level recall for lite regression fixtures.
- `expected_evidence_term_coverage`: expected evidence terms are present.
- `temporal_accuracy`: temporal cases return the expected current or historical fact.
- `entity_link_hit_rate`: expected entity terms are preserved in context.
- `abstention_accuracy`: unknown facts are not hallucinated.
- `source_ref_coverage`: retrieved rows carry event/ref/source metadata.
- `input_tokens`: approximate context token cost.
- `latency_p50`: median context construction or retrieval latency.
- `false_fact_rate`: abstention cases where an unsupported expected answer appeared.

The runner writes summary JSON/Markdown plus raw artifacts to:

```text
benchmark/memory_eval/results/
benchmark/memory_eval/results/<suite>_<baseline>/
```
