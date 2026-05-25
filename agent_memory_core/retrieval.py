import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from agent_memory_core.entities import query_entities
from agent_memory_core.models import RetrievalResult
from agent_memory_core.storage import MemoryStorage


SUMMARY_MAX_CHARS = 900
QUERY_STOPWORDS = {
    "about",
    "and",
    "can",
    "did",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "the",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

ENTITY_BASE_SCORES = {
    "file": 1.55,
    "function": 1.55,
    "class": 1.55,
    "test": 1.55,
    "error": 1.55,
    "command": 1.55,
    "goal": 0.25,
    "user_preference": 0.35,
}

TEMPORAL_MARKERS = {
    "现在",
    "最新",
    "之前",
    "上次",
    "过去",
    "当前",
    "后来",
    "current",
    "latest",
    "previous",
    "before",
    "last",
    "now",
}


class Retriever:
    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def retrieve(self, query: str, limit: int = 8) -> List[RetrievalResult]:
        query = query or ""
        results: Dict[Tuple[str, str], RetrievalResult] = {}
        temporal_intent = self._has_temporal_intent(query)
        query_entity_hits = query_entities(query)
        query_entity_norms = {item["normalized"] for item in query_entity_hits}
        query_files = self._extract_file_mentions(query)
        query_files.extend(
            item["text"] for item in query_entity_hits if item.get("entity_type") == "file"
        )

        for ref_id in self._extract_ref_ids(query):
            for row in self.storage.get_refs_by_ids([ref_id]):
                self._add_result(
                    results,
                    source="ref",
                    source_id=row["ref_id"],
                    title=row["kind"],
                    summary=row["summary"],
                    score=4.0,
                    signal="ref_exact",
                    metadata={"path": row["path"]},
                )

        for node in self.storage.get_focus_task_nodes(limit=3):
            ref_id = node.get("result_ref")
            if not ref_id:
                continue
            for row in self.storage.get_refs_by_ids([ref_id]):
                self._add_result(
                    results,
                    source="ref",
                    source_id=row["ref_id"],
                    title=row["kind"],
                    summary=row["summary"],
                    score=2.6 + float(node.get("importance") or 0.0),
                    signal="task_focus",
                    metadata={"path": row["path"], "node_id": node["node_id"]},
                )

        if self._looks_like_error_query(query):
            for row in self.storage.get_recent_refs(limit=4, kinds=["test", "command"]):
                self._add_result(
                    results,
                    source="ref",
                    source_id=row["ref_id"],
                    title=row["kind"],
                    summary=row["summary"],
                    score=2.4,
                    signal="failure_priority",
                    metadata={"path": row["path"]},
                )

        for row in self.storage.get_refs_for_files(query_files, limit=5):
            self._add_result(
                results,
                source="ref",
                source_id=row["ref_id"],
                title=row["kind"],
                summary=row["summary"],
                score=2.2,
                signal="file_match",
                metadata={"path": row["path"]},
            )

        self._add_entity_results(results, query, query_entity_norms, temporal_intent, limit=limit * 3)
        self._add_memory_item_results(results, query, temporal_intent, limit=limit * 3)

        for row in self.storage.search(query, limit=limit * 2):
            if row["source"] == "memory_item":
                continue
            self._add_result(
                results,
                source=row["source"],
                source_id=row["source_id"],
                title=row["title"],
                summary=row["summary"],
                score=float(row.get("score") or 1.0),
                signal="fts_bm25",
            )

        packed = sorted(results.values(), key=lambda item: item.score, reverse=True)[:limit]
        for item in packed:
            item.metadata["final_score"] = round(item.score, 4)
        self.storage.log_retrieval(
            query,
            [item.__dict__ for item in results.values()],
            [item.__dict__ for item in packed],
        )
        return packed

    def _add_entity_results(
        self,
        results: Dict[Tuple[str, str], RetrievalResult],
        query: str,
        query_entity_norms: Iterable[str],
        temporal_intent: bool,
        limit: int,
    ) -> None:
        normalized_query_entities = set(query_entity_norms)
        for row in self.storage.search_entities(query, limit=limit):
            normalized = row.get("normalized") or ""
            entity_type = row.get("entity_type") or "unknown"
            if entity_type in {"goal", "user_preference"} and normalized not in normalized_query_entities:
                continue
            confidence = float(row.get("confidence") or 0.0)
            score = ENTITY_BASE_SCORES.get(entity_type, 0.75) + confidence
            if normalized and normalized in normalized_query_entities:
                score += 0.5
            if temporal_intent:
                score += 0.25

            source_id = row.get("source_ref") or row.get("event_id") or row.get("entity_id")
            source = "ref" if row.get("source_ref") else "event" if row.get("event_id") else "entity"
            self._add_result(
                results,
                source=source,
                source_id=source_id,
                title=f"entity:{entity_type}",
                summary=f"{entity_type}: {row.get('entity_text')}",
                score=score,
                signal="entity_match",
                metadata={
                    "entity_id": row.get("entity_id"),
                    "entity_type": row.get("entity_type"),
                    "entity_text": row.get("entity_text"),
                    "normalized": normalized,
                    "source_ref": row.get("source_ref"),
                    "event_id": row.get("event_id"),
                },
            )

    def _add_memory_item_results(
        self,
        results: Dict[Tuple[str, str], RetrievalResult],
        query: str,
        temporal_intent: bool,
        limit: int,
    ) -> None:
        for item in self.storage.search_memory_items(query, limit=limit):
            metadata = item.get("metadata") or {}
            source_refs = item.get("source_refs") or []
            if metadata.get("unsupported") or not source_refs:
                continue
            score = 1.45 + float(item.get("confidence") or 0.0)
            if temporal_intent:
                score += 0.7
                score += min(float(item.get("goal_version") or 1), 5.0) * 0.08
            self._add_result(
                results,
                source="memory_item",
                source_id=item["item_id"],
                title=item["item_type"],
                summary=self._query_snippet(item["content"], query),
                score=score,
                signal="memory_item",
                metadata={
                    "source_refs": source_refs,
                    "entities": item.get("entities") or [],
                    "goal_version": item.get("goal_version"),
                    "created_at": item.get("created_at"),
                    "unsupported": bool(metadata.get("unsupported")),
                },
            )
            if temporal_intent:
                self._add_signal(results[("memory_item", item["item_id"])], "temporal_latest", 0.0)

    @staticmethod
    def _extract_ref_ids(text: str) -> List[str]:
        refs = re.findall(r"refs/ref_[A-Za-z0-9_\-]+\.md", text or "")
        return list(dict.fromkeys(refs))

    @staticmethod
    def _add_result(
        results: Dict[Tuple[str, str], RetrievalResult],
        source: str,
        source_id: Any,
        title: str,
        summary: str,
        score: float,
        signal: str,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        source_id = str(source_id or "")
        if not source_id:
            return
        key = (source, source_id)
        if key not in results:
            result = RetrievalResult(
                source=source,
                source_id=source_id,
                title=title,
                summary=summary,
                score=0.0,
                metadata=dict(metadata or {}),
            )
            result.metadata["signals"] = {}
            results[key] = result
        else:
            result = results[key]
            result.metadata.update(metadata or {})
        if signal == "entity_match":
            signals = result.metadata.setdefault("signals", {})
            previous = float(signals.get(signal) or 0.0)
            delta = max(0.0, float(score) - previous)
            result.score += delta
            signals[signal] = round(max(previous, float(score)), 4)
            return
        result.score += score
        Retriever._add_signal(result, signal, score)

    @staticmethod
    def _add_signal(result: RetrievalResult, signal: str, score: float) -> None:
        signals = result.metadata.setdefault("signals", {})
        signals[signal] = round(float(signals.get(signal) or 0.0) + float(score), 4)

    @staticmethod
    def _has_temporal_intent(query: str) -> bool:
        lowered = (query or "").lower()
        return any(marker in lowered for marker in TEMPORAL_MARKERS)

    @staticmethod
    def _looks_like_error_query(query: str) -> bool:
        lowered = (query or "").lower()
        markers = [
            "failed",
            "failure",
            "traceback",
            "error",
            "exception",
            "pytest",
            "失败",
            "报错",
            "异常",
        ]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _extract_file_mentions(text: str) -> List[str]:
        candidates = re.findall(r"[\w./\\-]+\.[A-Za-z0-9_]+", text or "")
        files: List[str] = []
        for item in candidates:
            files.append(item)
            files.append(Path(item).name)
        return list(dict.fromkeys(files))

    @staticmethod
    def _query_snippet(text: str, query: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
        text = str(text or "")
        if len(text) <= max_chars:
            return text
        lowered = text.lower()
        terms = list(
            dict.fromkeys(
                token.lower()
                for token in re.findall(r"[A-Za-z0-9_./:-]+", query or "")
                if len(token) > 2 and token.lower() not in QUERY_STOPWORDS
            )
        )
        terms.sort(key=len, reverse=True)
        positions = []
        for term in terms:
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"
            match = re.search(pattern, lowered)
            if match:
                positions.append(match.start())
        if not positions:
            return text[: max_chars - 3].rstrip() + "..."
        center = min(positions)
        start = max(0, center - max_chars // 3)
        end = min(len(text), start + max_chars)
        start = max(0, end - max_chars)
        prefix = "..." if start else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end].strip() + suffix
