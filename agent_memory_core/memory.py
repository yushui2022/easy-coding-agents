import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_memory_core.entities import extract_entities
from agent_memory_core.gates import QualityGate
from agent_memory_core.models import QualityGateResult, TaskState
from agent_memory_core.refs import RefStore
from agent_memory_core.retrieval import Retriever
from agent_memory_core.storage import MemoryStorage
from agent_memory_core.summarizer import classify_tool_result, extract_files_from_args, summarize_text


class CodingMemory:
    def __init__(
        self,
        project_root: str = ".",
        workspace: str = ".agent_memory",
        offload_threshold_chars: int = 1600,
        recent_dialogue_limit: int = 10,
    ):
        self.project_root = Path(project_root).resolve()
        self.workspace = (self.project_root / workspace).resolve()
        self.refs_dir = self.workspace / "refs"
        self.sessions_dir = self.workspace / "sessions"
        self.task_maps_dir = self.workspace / "task_maps"
        self.exports_dir = self.workspace / "exports"
        for directory in (self.refs_dir, self.sessions_dir, self.task_maps_dir, self.exports_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.storage = MemoryStorage(self.workspace / "memory.db")
        self.refs = RefStore(self.refs_dir)
        self.retriever = Retriever(self.storage)
        self.gate = QualityGate()
        self.offload_threshold_chars = offload_threshold_chars
        self.recent_dialogue_limit = recent_dialogue_limit
        self._verification_refs: List[str] = []
        self._recent_evidence_refs: List[str] = []

    async def record_user_message(self, text: str) -> None:
        event_id = self._id("evt_user")
        summary = summarize_text(text, max_chars=500)
        self.storage.insert_event(
            event_id=event_id,
            kind="message",
            role="user",
            content=str(text),
            summary=summary,
        )
        entities = extract_entities(text, role="user")
        self.storage.insert_entities(entities, event_id=event_id, metadata={"role": "user"})
        self.storage.insert_memory_item(
            item_id=self._id("item"),
            item_type="user_goal",
            content=str(text),
            source_refs=[event_id],
            entities=entities,
            confidence=0.55,
            metadata={"role": "user"},
        )
        current = self.storage.get_task_state()
        goal = current.get("goal") or str(text)[:240]
        bump = False
        if current.get("state") in {TaskState.DONE.value, TaskState.UNKNOWN.value} and str(text).strip():
            goal = str(text)[:240]
            bump = current.get("state") == TaskState.DONE.value
        self.storage.update_task_state(
            TaskState.UNDERSTANDING.value,
            goal=goal,
            reason="User request received.",
            confidence=0.7,
            next_actions=["Clarify goal if needed.", "Gather code or log evidence before making claims."],
            bump_goal_version=bump,
        )

    async def record_assistant_message(self, text: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        event_id = self._id("evt_asst")
        metadata = {"tool_calls": tool_calls or []}
        self.storage.insert_event(
            event_id=event_id,
            kind="message",
            role="assistant",
            content=str(text or ""),
            summary=summarize_text(text, max_chars=500),
            metadata=metadata,
        )
        if text and not tool_calls:
            for claim in self.extract_claims(text, evidence_refs=self._recent_evidence_refs, event_id=event_id):
                self.storage.insert_claim(**claim)
                claim_entities = extract_entities(claim["text"], role="assistant")
                self.storage.insert_entities(
                    claim_entities,
                    event_id=event_id,
                    metadata={"claim_id": claim["claim_id"], "role": "assistant"},
                )
                self.storage.insert_memory_item(
                    item_id=self._id("item"),
                    item_type=claim["claim_type"],
                    content=claim["text"],
                    source_refs=claim["evidence_refs"],
                    entities=claim_entities,
                    confidence=claim["confidence"],
                    metadata={"claim_id": claim["claim_id"], "unsupported": not bool(claim["evidence_refs"])},
                )

    async def record_tool_result(
        self,
        name: str,
        args: Optional[Dict[str, Any]],
        result: Any,
        tool_call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        args = args or {}
        result_text = str(result or "")
        kind, state, status = classify_tool_result(name, args, result_text)
        summary = summarize_text(result_text)
        node_id = self.storage.next_task_node_id()
        ref = self.refs.write_ref(
            content=result_text,
            kind=kind,
            tool_name=name,
            node_id=node_id,
            summary=summary,
            metadata={"args": args, "tool_call_id": tool_call_id},
        )
        ref_id = ref["ref_id"]
        self.storage.insert_ref(
            ref_id=ref_id,
            path=ref["absolute_path"],
            kind=kind,
            summary=summary,
            tool_name=name,
            node_id=node_id,
            size_chars=ref["size_chars"],
            metadata={"tool_call_id": tool_call_id},
        )

        stored_content = result_text
        if len(result_text) > self.offload_threshold_chars:
            stored_content = self._offloaded_notice(name, node_id, summary, ref_id)

        event_id = self._id("evt_tool")
        self.storage.insert_event(
            event_id=event_id,
            kind=kind,
            role="tool",
            content=stored_content,
            summary=summary,
            tool_name=name,
            tool_args=args,
            ref_id=ref_id,
            metadata={"node_id": node_id, "tool_call_id": tool_call_id},
        )
        entities = extract_entities(result_text, args=args, role="tool")
        self.storage.insert_entities(entities, source_ref=ref_id, event_id=event_id, metadata={"tool_name": name})
        self.storage.insert_memory_item(
            item_id=self._id("item"),
            item_type=kind,
            content=summary,
            source_refs=[ref_id],
            entities=entities,
            confidence=0.8,
            metadata={"tool_name": name, "node_id": node_id},
        )
        self.storage.upsert_task_node(
            node_id=node_id,
            goal=self.storage.get_task_state().get("goal", ""),
            status=status,
            node_type=self._node_type_for_kind(kind, state),
            importance=self._importance_for_kind(kind, state, result_text),
            is_current_focus=True,
            tool_name=name,
            summary=summary,
            files=extract_files_from_args(args),
            result_ref=ref_id,
            next_action=self._next_action_for_state(state),
        )
        evidence_refs = [ref_id]
        self._remember_evidence(ref_id)
        if kind == "test" and state == TaskState.TESTING.value:
            self._verification_refs.append(ref_id)
        transition = await self.propose_state_transition(
            {
                "to": state,
                "reason": f"Tool result recorded: {name}",
                "evidence_refs": evidence_refs,
                "next_actions": [self._next_action_for_state(state)],
                "confidence": 0.75,
            }
        )
        if not transition.accepted:
            self.storage.update_task_state(
                TaskState.UNKNOWN.value,
                reason=f"Tool-derived state transition blocked: {transition.blocked_reason}",
                confidence=0.2,
                evidence_refs=evidence_refs,
                next_actions=transition.required_actions,
            )
        return {
            "event_id": event_id,
            "node_id": node_id,
            "result_ref": ref_id,
            "summary": summary,
            "kind": kind,
            "state": state,
            "transition_accepted": transition.accepted,
        }

    def extract_claims(
        self,
        text: str,
        evidence_refs: Optional[List[str]] = None,
        event_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        refs = list(dict.fromkeys(evidence_refs or []))
        claims: List[Dict[str, Any]] = []
        for sentence in self._split_claim_sentences(text):
            claim_type = self._classify_claim(sentence)
            if not claim_type:
                continue
            claims.append(
                {
                    "claim_id": self._id("claim"),
                    "text": sentence,
                    "claim_type": claim_type,
                    "evidence_refs": refs,
                    "confidence": 0.65 if refs else 0.25,
                    "event_id": event_id,
                    "metadata": {"auto_extracted": True, "unsupported": not bool(refs)},
                }
            )
        return claims

    def validate_final_answer(self, text: str, task_profile: str = "coding_task") -> QualityGateResult:
        state = self.storage.get_task_state()
        evidence_refs = list(dict.fromkeys(state.get("evidence_refs") or self._recent_evidence_refs))
        verification_refs = self._verification_refs or self._recent_verification_refs()
        claims = self.extract_claims(text, evidence_refs=evidence_refs)
        wants_done = self._looks_like_done(text)
        proposal: Dict[str, Any] = {"claims": claims}
        if wants_done:
            proposal["to"] = TaskState.DONE.value
            proposal["evidence_refs"] = verification_refs
            if task_profile == "simple_answer":
                proposal["unverified_reason"] = "Simple answer task does not require code/test verification."
            elif not verification_refs and self._has_unverified_disclaimer(text):
                proposal["unverified_reason"] = "Assistant explicitly stated verification is unavailable or not run."
        return self.gate.check(proposal, verification_refs)

    async def build_prompt_context(self, current_user_request: Optional[str] = None) -> List[Dict[str, Any]]:
        task_state = self.storage.get_task_state()
        task_nodes = self.storage.get_task_nodes(limit=12)
        memories = self.storage.get_memories_with_sources(limit=8)
        query = current_user_request or task_state.get("goal") or ""
        retrieved = self.retriever.retrieve(query, limit=8) if query else []
        recent = self.storage.get_recent_events(limit=self.recent_dialogue_limit, roles=["user", "assistant", "tool"])

        memory_block = self._render_memory_block(task_state, task_nodes, memories, retrieved)
        messages = [{"role": "system", "content": memory_block}]
        for event in recent:
            role = event.get("role") or "user"
            if role not in {"user", "assistant", "tool"}:
                continue
            content = event.get("content") or event.get("summary") or ""
            if not content:
                continue
            if role == "tool":
                msg = {
                    "role": "user",
                    "content": (
                        "<tool_evidence>\n"
                        f"tool: {event.get('tool_name') or 'unknown'}\n"
                        f"ref: {event.get('ref_id') or 'inline'}\n"
                        f"{content}\n"
                        "</tool_evidence>"
                    ),
                }
            else:
                msg = {"role": role, "content": content}
            messages.append(msg)
        return messages

    async def check_quality_gate(self, proposal: Dict[str, Any]) -> QualityGateResult:
        return self.gate.check(proposal, self._verification_refs)

    async def propose_state_transition(self, proposal: Dict[str, Any]) -> QualityGateResult:
        current = self.storage.get_task_state()
        enriched = dict(proposal or {})
        enriched.setdefault("from", current.get("state") or TaskState.UNKNOWN.value)
        result = self.gate.check(enriched, self._verification_refs)
        target_state = str(
            enriched.get("to")
            or enriched.get("next_state")
            or enriched.get("proposed_next_state")
            or ""
        ).upper()
        event_id = self._id("evt_state")
        self.storage.insert_event(
            event_id=event_id,
            kind="state",
            role="system",
            content=json.dumps(enriched, ensure_ascii=False),
            summary=(
                f"State transition {enriched.get('from')} -> {target_state or '(none)'} "
                f"{'accepted' if result.accepted else 'blocked'}"
            ),
            metadata={
                "accepted": result.accepted,
                "violations": result.violations,
                "required_actions": result.required_actions,
            },
        )
        if result.accepted and target_state:
            self.storage.update_task_state(
                target_state,
                reason=str(enriched.get("reason") or "State transition accepted."),
                confidence=float(enriched.get("confidence") or 0.75),
                evidence_refs=enriched.get("evidence_refs") or [],
                next_actions=enriched.get("next_action_candidates") or enriched.get("next_actions") or [],
                bump_goal_version=bool(enriched.get("goal_changed")),
            )
        return result

    async def commit_task_outcome(self, result: Dict[str, Any]) -> None:
        state = TaskState.DONE.value if result.get("success") else TaskState.UNKNOWN.value
        self.storage.update_task_state(
            state,
            reason=str(result.get("reason") or "Task outcome committed."),
            confidence=float(result.get("confidence") or 0.8),
            evidence_refs=result.get("evidence_refs") or self._verification_refs,
            next_actions=[],
        )

    async def add_memory(
        self,
        content: str,
        memory_type: str = "Decision",
        source_refs: Optional[List[str]] = None,
        confidence: float = 0.8,
    ) -> str:
        memory_id = self._id("mem")
        self.storage.insert_memory(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            source_refs=source_refs or [],
            confidence=confidence,
        )
        entities = extract_entities(content, role="memory")
        self.storage.insert_entities(entities, source_ref=(source_refs or [None])[0], metadata={"memory_id": memory_id})
        self.storage.insert_memory_item(
            item_id=self._id("item"),
            item_type=memory_type,
            content=content,
            source_refs=source_refs or [],
            entities=entities,
            confidence=confidence,
            metadata={"memory_id": memory_id},
        )
        return memory_id

    async def save_session(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.sessions_dir / f"session_{timestamp}.md"
        state = self.storage.get_task_state()
        nodes = self.storage.get_task_nodes(limit=20)
        recent = self.storage.get_recent_events(limit=20, roles=["user", "assistant", "tool"])
        lines = [
            "# Evidence-Gated Memory Session",
            "",
            "## Current Task State",
            "```json",
            json.dumps(state, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Task Map",
            self.render_mermaid(nodes),
            "",
            "## Task Nodes",
        ]
        for node in nodes:
            lines.append(f"### {node.get('node_id')} - {node.get('status')}")
            lines.append(node.get("summary") or "")
            files = node.get("files") or []
            if files:
                lines.append(f"files: {', '.join(files)}")
            if node.get("result_ref"):
                lines.append(f"ref: {node['result_ref']}")
            lines.append("")
        lines.extend(
            [
                "",
            "## Recent Events",
            ]
        )
        for event in recent:
            lines.append(f"### {event.get('role') or event.get('kind')} - {event.get('event_id')}")
            lines.append(event.get("summary") or event.get("content") or "")
            if event.get("ref_id"):
                lines.append(f"ref: {event['ref_id']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        latest = self.sessions_dir / "latest.md"
        latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        return str(path)

    def render_mermaid(self, nodes: Optional[List[Dict[str, Any]]] = None) -> str:
        nodes = nodes if nodes is not None else self.storage.get_task_nodes(limit=12)
        if not nodes:
            return "```mermaid\nflowchart TD\n    EMPTY[\"No task nodes yet\"]\n```"
        lines = ["```mermaid", "flowchart TD"]
        previous = None
        for node in nodes:
            node_id = node["node_id"]
            node_type = node.get("node_type") or "tool"
            focus = "*" if node.get("is_current_focus") else ""
            label = self._safe_label(f"{focus}{node_id} {node_type}: {node.get('summary') or ''}")
            shape_start, shape_end = self._shape_for_node_type(node_type)
            lines.append(f"    {node_id}{shape_start}\"{label}\"{shape_end}")
            if previous:
                lines.append(f"    {previous} --> {node_id}")
            previous = node_id
        lines.append("```")
        return "\n".join(lines)

    def _render_memory_block(
        self,
        task_state: Dict[str, Any],
        task_nodes: List[Dict[str, Any]],
        memories: List[Dict[str, Any]],
        retrieved: List[Any],
    ) -> str:
        sections = [
            "<evidence_gated_memory>",
            "<quality_gates>",
            "- No file-content claim without read/search/ref evidence.",
            "- No error diagnosis without command/test log evidence.",
            "- Do not claim DONE without verification evidence or an explicit unverified reason.",
            "- Do not use long-term memory as fact unless it has source refs.",
            "- If memories conflict, trace back to refs/events before deciding.",
            "- If the user changes the goal, restate the goal and replan.",
            "- Before final answers, key claims should be supported by current evidence refs.",
            "</quality_gates>",
            "",
            "<current_task_state>",
            json.dumps(task_state, ensure_ascii=False, indent=2),
            "</current_task_state>",
            "",
            "<task_map>",
            self.render_mermaid(task_nodes),
            "</task_map>",
            "",
            "<user_project_memories>",
        ]
        if memories:
            for item in memories:
                sections.append(f"- [{item['memory_type']}] {item['content']} (sources: {', '.join(item['source_refs'])})")
        else:
            sections.append("- No sourced long-term memories yet.")
        sections.extend(["</user_project_memories>", "", "<evidence_summaries>"])
        if retrieved:
            for item in retrieved:
                summary = summarize_text(item.summary, max_chars=700)
                source_refs = item.metadata.get("source_refs") or []
                refs = f" (sources: {', '.join(source_refs)})" if source_refs else ""
                sections.append(f"- [{item.source}:{item.source_id}] {summary}{refs}")
        else:
            sections.append("- No retrieved evidence for the current query.")
        sections.extend(["</evidence_summaries>", "</evidence_gated_memory>"])
        return "\n".join(sections)

    @staticmethod
    def _offloaded_notice(tool_name: str, node_id: str, summary: str, ref_id: str) -> str:
        return (
            "[Offloaded Tool Result]\n"
            f"tool: {tool_name}\n"
            f"node_id: {node_id}\n"
            f"summary: {summary}\n"
            f"result_ref: {ref_id}"
        )

    @staticmethod
    def _next_action_for_state(state: str) -> str:
        mapping = {
            TaskState.GATHERING_CONTEXT.value: "Use the evidence to plan the next step.",
            TaskState.EDITING.value: "Run a focused verification after edits.",
            TaskState.TESTING.value: "If checks passed, summarize with verification refs.",
            TaskState.DEBUGGING.value: "Read the last error/log evidence before diagnosing.",
            TaskState.UNDERSTANDING.value: "Proceed based on the user's latest answer.",
        }
        return mapping.get(state, "Gather more evidence or replan.")

    @staticmethod
    def _node_type_for_kind(kind: str, state: str) -> str:
        if kind == "file_read":
            return "evidence"
        if kind == "diff":
            return "change"
        if kind == "test":
            return "verification" if state == TaskState.TESTING.value else "blocker"
        if kind == "command":
            return "blocker" if state == TaskState.DEBUGGING.value else "evidence"
        if kind == "user_interaction":
            return "decision"
        return "tool"

    @staticmethod
    def _importance_for_kind(kind: str, state: str, result_text: str) -> float:
        if state == TaskState.DEBUGGING.value:
            return 0.95
        if kind in {"test", "diff"}:
            return 0.9
        if kind == "file_read":
            return 0.75
        if "Error:" in str(result_text) or "Traceback" in str(result_text):
            return 0.9
        return 0.5

    @staticmethod
    def _shape_for_node_type(node_type: str) -> tuple[str, str]:
        shapes = {
            "evidence": ("[", "]"),
            "change": ("{{", "}}"),
            "verification": ("([", "])"),
            "blocker": ("[/", "/]"),
            "decision": ("{", "}"),
        }
        return shapes.get(node_type, ("[", "]"))

    def _remember_evidence(self, ref_id: str) -> None:
        self._recent_evidence_refs = [ref_id] + [ref for ref in self._recent_evidence_refs if ref != ref_id]
        self._recent_evidence_refs = self._recent_evidence_refs[:8]

    def _recent_verification_refs(self) -> List[str]:
        rows = self.storage.get_recent_refs(limit=5, kinds=["test"])
        return [row["ref_id"] for row in rows if row.get("ref_id")]

    def _split_claim_sentences(self, text: str) -> List[str]:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized:
            return []
        pieces = re.split(r"(?<=[。！？.!?])\s+|[;\n]+", normalized)
        return [piece.strip(" -\t")[:500] for piece in pieces if len(piece.strip()) >= 12][:8]

    @staticmethod
    def _classify_claim(sentence: str) -> str:
        lowered = sentence.lower()
        if any(token in lowered for token in ["traceback", "exception", "error", "failed", "失败", "报错", "异常", "原因"]):
            return "diagnosis"
        if any(token in lowered for token in ["file", ".py", ".js", ".ts", "函数", "类", "模块", "代码", "文件"]):
            return "file_content"
        if any(token in lowered for token in ["remember", "preference", "decision", "长期记忆", "偏好", "决定"]):
            return "memory"
        return ""

    @staticmethod
    def _looks_like_done(text: str) -> bool:
        lowered = str(text or "").lower()
        done_markers = [
            "done",
            "completed",
            "fixed",
            "implemented",
            "tests passed",
            "已完成",
            "完成了",
            "修复了",
            "实现了",
            "已修复",
            "测试通过",
        ]
        return any(marker in lowered for marker in done_markers)

    @staticmethod
    def _has_unverified_disclaimer(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = [
            "未验证",
            "没有运行测试",
            "无法测试",
            "not verified",
            "tests not run",
            "could not run tests",
        ]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _safe_label(text: str) -> str:
        compact = " ".join(str(text).replace("\n", " ").split())
        compact = compact.replace('"', "'").replace("[", "(").replace("]", ")")
        return compact[:100]

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"
