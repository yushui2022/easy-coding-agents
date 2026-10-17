import json
from typing import Any, Dict, Iterable, List


def expand_records(records: List[Dict[str, Any]], suite: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for record in records:
        if "qa" in record and any(key in record for key in ("conversation", "dialogue", "dialog")):
            for index, qa in enumerate(record.get("qa") or []):
                merged = dict(qa)
                merged["conversation"] = record.get("conversation") or record.get("dialogue") or record.get("dialog")
                merged["sample_id"] = record.get("sample_id")
                merged.setdefault("question_id", f"{record.get('sample_id', 'locomo')}_{index}")
                cases.append(merged)
                if len(cases) >= limit:
                    return cases
            continue
        cases.append(record)
        if len(cases) >= limit:
            return cases
    return cases


def normalize_record(record: Dict[str, Any], suite: str = "", index: int = 0) -> Dict[str, Any]:
    if "sessions" in record and "query" in record:
        return record
    if "haystack_sessions" in record or "question_date" in record:
        return normalize_longmemeval(record, index=index)
    if any(key in record for key in ("conversation", "conversations", "dialogue", "dialog")):
        return normalize_locomo(record, index=index)
    return normalize_generic(record, suite=suite, index=index)


def normalize_longmemeval(record: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    question_type = str(record.get("question_type") or "")
    answer = _answer_text(record.get("answer"))
    answer_session_ids = [str(item) for item in record.get("answer_session_ids") or []]
    raw_sessions = _longmemeval_sessions(record)
    sessions = flatten_sessions(raw_sessions, answer_session_ids=answer_session_ids)
    should_abstain = "abstention" in question_type.lower() or _looks_unknown_answer(answer)
    return {
        "case_id": str(record.get("question_id") or f"longmemeval_{index}"),
        "sessions": sessions,
        "query": str(record.get("question") or ""),
        "expected_answer_terms": [] if should_abstain else ([answer] if answer else []),
        "expected_evidence_terms": answer_session_ids,
        "expected_entities": [],
        "temporal_mode": infer_temporal_mode(question_type, str(record.get("question") or "")),
        "should_abstain": should_abstain,
        "metadata": {
            "source_suite": "longmemeval",
            "question_type": question_type,
            "question_date": record.get("question_date"),
            "answer_session_ids": answer_session_ids,
            "raw_answer": record.get("answer"),
        },
    }


def normalize_locomo(record: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    question = str(record.get("question") or record.get("query") or "")
    answer = _answer_text(record.get("answer"))
    sessions = flatten_sessions(
        record.get("conversation")
        or record.get("conversations")
        or record.get("dialogue")
        or record.get("dialog")
        or []
    )
    return {
        "case_id": str(record.get("question_id") or record.get("id") or f"locomo_{index}"),
        "sessions": sessions,
        "query": question,
        "expected_answer_terms": [answer] if answer and not _looks_unknown_answer(answer) else [],
        "expected_evidence_terms": [str(item) for item in record.get("evidence") or []],
        "expected_entities": [],
        "temporal_mode": infer_temporal_mode(str(record.get("category") or ""), question),
        "should_abstain": _looks_unknown_answer(answer),
        "metadata": {"source_suite": "locomo", "raw_answer": record.get("answer")},
    }


def normalize_generic(record: Dict[str, Any], suite: str = "", index: int = 0) -> Dict[str, Any]:
    content = record.get("content") or record.get("context") or record.get("history") or ""
    return {
        "case_id": str(record.get("case_id") or record.get("id") or f"{suite or 'case'}_{index}"),
        "sessions": [{"role": "user", "content": _to_text(content), "metadata": {}}],
        "query": str(record.get("query") or record.get("question") or ""),
        "expected_answer_terms": [_answer_text(record.get("answer"))] if record.get("answer") else [],
        "expected_evidence_terms": [],
        "expected_entities": [],
        "temporal_mode": "none",
        "should_abstain": False,
        "metadata": {"source_suite": suite or "generic"},
    }


def flatten_sessions(raw_sessions: Any, answer_session_ids: Iterable[str] = ()) -> List[Dict[str, Any]]:
    sessions: List[Dict[str, Any]] = []
    answer_ids = {str(item) for item in answer_session_ids}
    if isinstance(raw_sessions, dict):
        locomo_sessions = _locomo_session_dict_to_list(raw_sessions)
        iterable = locomo_sessions if locomo_sessions else list(raw_sessions.values())
    elif isinstance(raw_sessions, list):
        iterable = raw_sessions
    else:
        iterable = [raw_sessions]

    for index, session in enumerate(iterable):
        if isinstance(session, list):
            session = {"session_id": f"session_{index}", "messages": session}
        if isinstance(session, dict):
            session_id = str(
                session.get("session_id")
                or session.get("id")
                or session.get("sessionId")
                or f"session_{index}"
            )
            date = session.get("date") or session.get("timestamp") or session.get("created_at") or ""
            messages = (
                session.get("messages")
                or session.get("conversation")
                or session.get("dialogue")
                or session.get("turns")
            )
            if isinstance(messages, list):
                body = "\n".join(_message_content(message) for message in messages if _message_content(message))
                if body:
                    sessions.append(
                        {
                            "role": "user",
                            "content": _with_session_prefix(session_id, date, body),
                            "metadata": {
                                "source_session_id": session_id,
                                "source_date": date,
                                "is_answer_session": session_id in answer_ids,
                            },
                        }
                    )
                continue
            body = _message_content(session)
        else:
            session_id = f"session_{index}"
            date = ""
            body = _to_text(session)
        if body:
            sessions.append(
                {
                    "role": "user",
                    "content": _with_session_prefix(session_id, date, body),
                    "metadata": {
                        "source_session_id": session_id,
                        "source_date": date,
                        "is_answer_session": session_id in answer_ids,
                    },
                }
            )
    return sessions


def _longmemeval_sessions(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    sessions = []
    raw_sessions = record.get("haystack_sessions") or []
    ids = record.get("haystack_session_ids") or []
    dates = record.get("haystack_dates") or []
    for index, session in enumerate(raw_sessions):
        fallback_id = str(ids[index]) if index < len(ids) else f"session_{index}"
        fallback_date = dates[index] if index < len(dates) else ""
        if isinstance(session, dict):
            item = dict(session)
            item.setdefault("session_id", fallback_id)
            item.setdefault("date", fallback_date)
            sessions.append(item)
            continue
        sessions.append({"session_id": fallback_id, "date": fallback_date, "messages": session})
    return sessions


def infer_temporal_mode(label: str, question: str) -> str:
    lowered = f"{label} {question}".lower()
    if any(term in lowered for term in ["latest", "current", "now", "现在", "最新", "当前", "knowledge-update"]):
        return "latest"
    if any(term in lowered for term in ["previous", "before", "earlier", "last", "之前", "过去", "上次"]):
        return "historical"
    if any(term in lowered for term in ["temporal", "time"]):
        return "latest"
    return "none"


def _with_session_prefix(session_id: str, date: Any, body: str) -> str:
    date_text = f" date:{date}" if date else ""
    return f"session:{session_id}{date_text}\n{body}"


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("speaker") or "user").lower()
        if "assistant" in role or role in {"ai", "bot"}:
            return "assistant"
        if "tool" in role:
            return "tool"
    return "user"


def _message_content(message: Any) -> str:
    if not isinstance(message, dict):
        return _to_text(message)
    prefix = []
    if message.get("dia_id"):
        prefix.append(f"dia_id:{message['dia_id']}")
    if message.get("speaker"):
        prefix.append(f"speaker:{message['speaker']}")
    for key in ("content", "text", "message", "utterance", "value"):
        value = message.get(key)
        if value:
            body = _to_text(value)
            return f"{' '.join(prefix)}\n{body}" if prefix else body
    return _to_text(message)


def _locomo_session_dict_to_list(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    sessions = []
    for key, value in sorted(raw.items()):
        if not key.startswith("session_") or key.endswith("_date_time") or not isinstance(value, list):
            continue
        date = raw.get(f"{key}_date_time") or raw.get(f"{key}_date") or ""
        sessions.append({"session_id": key, "date": date, "messages": value})
    return sessions


def _answer_text(answer: Any) -> str:
    if isinstance(answer, list):
        return " ".join(_to_text(item) for item in answer if _to_text(item)).strip()
    return _to_text(answer).strip()


def _looks_unknown_answer(answer: str) -> bool:
    lowered = str(answer or "").lower()
    return any(
        marker in lowered
        for marker in [
            "unknown",
            "not mentioned",
            "not enough",
            "cannot determine",
            "no information",
            "unanswerable",
        ]
    )


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
