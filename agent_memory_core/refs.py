import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class RefStore:
    def __init__(self, refs_dir: Path):
        self.refs_dir = Path(refs_dir)
        self.refs_dir.mkdir(parents=True, exist_ok=True)

    def write_ref(
        self,
        *,
        content: str,
        kind: str,
        tool_name: Optional[str],
        node_id: Optional[str],
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = datetime.now()
        digest = hashlib.sha1(
            f"{now.isoformat()}:{tool_name}:{node_id}:{content[:2048]}".encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        ref_id = f"ref_{now.strftime('%Y%m%d_%H%M%S')}_{digest}"
        file_path = self.refs_dir / f"{ref_id}.md"
        rel_path = f"refs/{file_path.name}"
        header = {
            "ref_id": ref_id,
            "kind": kind,
            "tool_name": tool_name,
            "node_id": node_id,
            "created_at": now.isoformat(),
            "summary": summary,
            "metadata": metadata or {},
        }
        body = [
            "---",
            json.dumps(header, ensure_ascii=False, indent=2),
            "---",
            "",
            "# Offloaded Evidence",
            "",
            "## Summary",
            summary,
            "",
            "## Raw Content",
            "",
            "```text",
            content,
            "```",
            "",
        ]
        file_path.write_text("\n".join(body), encoding="utf-8")
        return {
            "ref_id": rel_path,
            "absolute_path": str(file_path),
            "size_chars": len(content),
        }

