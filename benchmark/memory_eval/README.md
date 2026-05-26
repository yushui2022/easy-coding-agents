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
python benchmark\memory_eval\run.py --suite beam_lite --baseline evidence_gated_memory --beam-tokens 100000 --beam-cases 50
python benchmark\memory_eval\run.py --suite longmemeval --baseline all --dataset benchmark\memory_eval\fixtures\longmemeval_lite.jsonl --limit 20
```

The loader also normalizes common official-style schemas:

- LongMemEval-like records with `question`, `answer`, `question_type`,
  `haystack_sessions`, and `answer_session_ids`.
- LoCoMo-like records with `question`, `answer`, and `conversation` /
  `dialogue` style history.

Official dataset files are not downloaded automatically. Pass local JSON/JSONL
files with `--dataset`.

## Download Public Data

Use the helper script to download public benchmark files into the ignored local
dataset directory:

```powershell
python benchmark\memory_eval\download_datasets.py --dataset locomo10
python benchmark\memory_eval\download_datasets.py --dataset longmemeval_s
```

Then run small real-data smoke tests:

```powershell
python benchmark\memory_eval\run.py --suite locomo_lite --baseline evidence_gated_memory --dataset benchmark\memory_eval\datasets\locomo10.json --limit 5
python benchmark\memory_eval\run.py --suite longmemeval --baseline evidence_gated_memory --dataset benchmark\memory_eval\datasets\longmemeval_s_cleaned.json --limit 5
python benchmark\memory_eval\run.py --suite beam_lite --baseline evidence_gated_memory --beam-tokens 100000 --beam-cases 50
```

These smoke runs verify adapter compatibility and evidence retrieval. They are
not official dataset-level scores until run with the full split and answer
generation / judge evaluation.

## Latest Real-Data Smoke Results

These results were produced with `evidence_gated_memory` after ingesting the
sessions, closing memory, reopening the same SQLite database, and querying with
`recent_dialogue_limit=0`.

| Suite | Dataset | Limit | Retrieval / Term Recall | Evidence Source Coverage | Evidence Precision | Latency p50 | False Fact Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| LongMemEval-S | `longmemeval_s_cleaned.json` | 5 | 0.40 | 1.00 | 1.00 | 0.9048s | 0.00 |
| LoCoMo10 | `locomo10.json` | 5 | 0.00 | 0.80 | 0.80 | 0.5671s | 0.00 |
| BEAM-lite | synthetic 100K tokens | 1 | 1.00 | 1.00 | 1.00 | 0.0242s | 0.00 |

## Larger Results

These larger runs are still memory-subsystem results. They do not represent
official LongMemEval / LoCoMo answer-accuracy scores because the runner does
not yet attach an answer generator or judge.

LongMemEval-S `limit=100`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.00 | 1,321 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.15 | 0.00 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.54 | 0.36 | 5,500,800 | 0.0007s | 0.00 |
| `keyword_fts_memory` | 100 | 0.39 | 0.87 | 182,969 | 0.5088s | 0.00 |
| `vector_rag_memory` | 100 | 0.38 | 0.67 | 184,067 | 0.7292s | 0.00 |
| `evidence_gated_memory` | 100 | 0.40 | 0.87 | 178,117 | 0.9138s | 0.00 |

LoCoMo10 `limit=100`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 100 | 0.01 | 0.02 | 1,141 | 0.0000s | 0.00 |
| `summary_memory` | 100 | 0.02 | 0.02 | 11,400 | 0.0000s | 0.00 |
| `long_context_only` | 100 | 0.19 | 0.99 | 1,792,483 | 0.0000s | 0.00 |
| `keyword_fts_memory` | 100 | 0.06 | 0.74 | 110,028 | 0.0241s | 0.00 |
| `vector_rag_memory` | 100 | 0.06 | 0.58 | 187,057 | 0.0411s | 0.00 |
| `evidence_gated_memory` | 100 | 0.06 | 0.74 | 182,886 | 0.0943s | 0.00 |

BEAM-lite `100K tokens / 50 cases`:

| Baseline | Cases | Retrieval / Term Recall | Evidence Source Coverage | Input Tokens | Latency p50 | False Fact Rate |
|---|---:|---:|---:|---:|---:|---:|
| `no_memory` | 50 | 0.00 | 0.00 | 450 | 0.0000s | 1.00 |
| `summary_memory` | 50 | 0.00 | 0.00 | 650 | 0.0000s | 1.00 |
| `long_context_only` | 50 | 1.00 | 1.00 | 5,910,300 | 0.0000s | 0.00 |
| `keyword_fts_memory` | 50 | 1.00 | 1.00 | 70,940 | 0.0131s | 0.00 |
| `vector_rag_memory` | 50 | 0.16 | 0.16 | 71,200 | 0.0308s | 0.84 |
| `evidence_gated_memory` | 50 | 1.00 | 1.00 | 109,140 | 0.0242s | 0.00 |

Interpretation:

- `Evidence Source Coverage` checks whether the retrieved source text contains
  the expected evidence terms. This is the most relevant metric for the current
  memory-only runner.
- `Retrieval / Term Recall` checks whether expected answer terms appear in the
  built memory context. It is not a judged final-answer metric.
- LoCoMo10 currently exposes a real gap: the memory system can often recover
  evidence ids, but the runner does not yet generate or judge final answers.

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

## Metrics

- `fixture_retrieval_hit_rate`: expected answer terms are present in the built memory context.
- `term_recall_rate`: term-level recall for lite regression fixtures.
- `expected_evidence_term_coverage`: expected evidence terms are present.
- `evidence_source_term_coverage`: expected evidence terms are present in retrieved source summaries.
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
