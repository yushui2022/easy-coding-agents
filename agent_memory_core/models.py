from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskState(str, Enum):
    UNDERSTANDING = "UNDERSTANDING"
    GATHERING_CONTEXT = "GATHERING_CONTEXT"
    PLANNING = "PLANNING"
    EDITING = "EDITING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    WAITING_USER = "WAITING_USER"
    DONE = "DONE"
    UNKNOWN = "UNKNOWN"


@dataclass
class QualityGateResult:
    accepted: bool
    blocked_reason: str = ""
    required_actions: List[str] = field(default_factory=list)
    fallback_state: str = TaskState.UNKNOWN.value
    violations: List[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    source: str
    source_id: str
    title: str
    summary: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolEvidence:
    kind: str
    summary: str
    ref_id: Optional[str]
    node_id: str
    state: str
    status: str

