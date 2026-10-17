from typing import Any, Dict, List

from agent_memory_core.models import QualityGateResult, TaskState


class QualityGate:
    def check(self, proposal: Dict[str, Any], verification_refs: List[str]) -> QualityGateResult:
        violations: List[str] = []
        required: List[str] = []

        claims = proposal.get("claims") or []
        for claim in claims:
            claim_type = str(claim.get("type") or claim.get("claim_type") or "").lower()
            evidence = self._refs(claim.get("evidence_refs"))
            if claim_type in {"file_content", "file", "code"} and not evidence:
                violations.append("file_claim_requires_read")
                required.append("Read or search the relevant file and attach an evidence ref.")
            if claim_type in {"error", "test_failure", "diagnosis"} and not evidence:
                violations.append("error_claim_requires_log")
                required.append("Read the command/test failure log before diagnosing the error.")
            if claim_type in {"memory", "long_term_memory"} and not evidence:
                violations.append("memory_requires_source")
                required.append("Attach source refs before treating a memory as fact.")

        target_state = str(
            proposal.get("to")
            or proposal.get("wants_to_enter")
            or proposal.get("proposed_next_state")
            or proposal.get("next_state")
            or ""
        ).upper()
        from_state = str(proposal.get("from") or proposal.get("from_state") or "").upper()
        evidence_for_transition = self._refs(proposal.get("evidence_refs"))

        if target_state and target_state != from_state:
            if target_state in {TaskState.DEBUGGING.value, TaskState.TESTING.value} and not evidence_for_transition:
                violations.append("state_transition_requires_evidence")
                required.append("Attach command/test evidence refs for TESTING or DEBUGGING transitions.")
            if target_state == TaskState.EDITING.value:
                has_file_evidence = bool(evidence_for_transition or self._refs(proposal.get("file_refs")))
                if not has_file_evidence:
                    violations.append("editing_requires_context_evidence")
                    required.append("Read or search relevant files before entering EDITING.")

        if target_state == TaskState.DONE.value:
            evidence = self._refs(proposal.get("evidence_refs"))
            unverified_reason = str(proposal.get("unverified_reason") or "").strip()
            has_verification = bool(verification_refs or evidence)
            if not has_verification and not unverified_reason:
                violations.append("done_requires_verification")
                required.append("Run a relevant test/check or explicitly state why verification is unavailable.")

        if proposal.get("goal_changed") and not proposal.get("goal_version"):
            violations.append("goal_change_requires_replan")
            required.append("Create a new goal version and restate the current target.")

        if proposal.get("memory_conflict") and not self._refs(proposal.get("evidence_refs")):
            violations.append("conflict_requires_traceback")
            required.append("Trace the conflicting memory back to refs/events before using it.")

        accepted = not violations
        return QualityGateResult(
            accepted=accepted,
            blocked_reason="" if accepted else "; ".join(violations),
            required_actions=required,
            fallback_state=TaskState.UNKNOWN.value if not accepted else "",
            violations=violations,
        )

    @staticmethod
    def _refs(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []
