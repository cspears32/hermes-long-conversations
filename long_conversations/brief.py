from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def create_handoff_brief(
    source_session_id: str,
    topic: str,
    work_in_progress: str,
    decisions_made: Optional[List[str]] = None,
    active_state_files: Optional[List[str]] = None,
    key_assumptions: Optional[List[str]] = None,
    open_questions: Optional[List[str]] = None,
    dead_ends: Optional[List[str]] = None,
    next_step: str = "",
) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "source_session_id": source_session_id,
        "timestamp": time.time(),
        "topic": topic,
        "work_in_progress": work_in_progress,
        "decisions_made": decisions_made or [],
        "active_state_files": active_state_files or [],
        "key_assumptions": key_assumptions or [],
        "open_questions": open_questions or [],
        "dead_ends": dead_ends or [],
        "next_step": next_step,
    }


def format_brief_for_injection(brief: Dict[str, Any]) -> str:
    lines = [
        "## [Long Conversations] Continuation Handoff Brief",
        f"- **Source Session:** {brief.get('source_session_id', 'unknown')}",
        f"- **Topic:** {brief.get('topic', 'N/A')}",
        f"- **Work In Progress:** {brief.get('work_in_progress', 'N/A')}",
    ]
    if brief.get("decisions_made"):
        lines.append("- **Decisions Made:**")
        for item in brief["decisions_made"]:
            lines.append(f"  • {item}")
    if brief.get("active_state_files"):
        lines.append("- **Active Files / State:**")
        for item in brief["active_state_files"]:
            lines.append(f"  • {item}")
    if brief.get("key_assumptions"):
        lines.append("- **Key Assumptions:**")
        for item in brief["key_assumptions"]:
            lines.append(f"  • {item}")
    if brief.get("open_questions"):
        lines.append("- **Open Questions:**")
        for item in brief["open_questions"]:
            lines.append(f"  • {item}")
    if brief.get("dead_ends"):
        lines.append("- **Dead Ends (Avoid):**")
        for item in brief["dead_ends"]:
            lines.append(f"  • {item}")
    if brief.get("next_step"):
        lines.append(f"- **Immediate Next Step:** {brief.get('next_step')}")

    lines.append("\nPlease continue the conversation from this point seamlessly.")
    return "\n".join(lines)
