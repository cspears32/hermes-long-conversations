from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .brief import create_handoff_brief, format_brief_for_injection
from .lineage import get_parent_chain
from .storage import (
    get_base_dir,
    list_briefs,
    load_brief,
    save_brief,
    set_pending_continuation,
)

logger = logging.getLogger(__name__)


def tool_long_conv_handoff(
    topic: str,
    work_in_progress: str,
    decisions_made: Optional[List[str]] = None,
    active_state_files: Optional[List[str]] = None,
    key_assumptions: Optional[List[str]] = None,
    open_questions: Optional[List[str]] = None,
    dead_ends: Optional[List[str]] = None,
    next_step: str = "",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    sid = session_id or "current_session"
    brief = create_handoff_brief(
        source_session_id=sid,
        topic=topic,
        work_in_progress=work_in_progress,
        decisions_made=decisions_made,
        active_state_files=active_state_files,
        key_assumptions=key_assumptions,
        open_questions=open_questions,
        dead_ends=dead_ends,
        next_step=next_step,
    )
    save_brief(brief)
    set_pending_continuation(sid)
    return {
        "success": True,
        "message": f"Handoff brief saved for session '{sid}'. Ready for continuation in a fresh session.",
        "brief": brief,
    }


def tool_long_conv_load(session_id: str) -> Dict[str, Any]:
    brief = load_brief(session_id)
    if not brief:
        return {
            "success": False,
            "error": f"No brief found for session ID: {session_id}",
        }
    set_pending_continuation(session_id)
    return {
        "success": True,
        "message": f"Loaded brief for '{session_id}' as pending continuation.",
        "formatted_context": format_brief_for_injection(brief),
    }


def tool_long_conv_list() -> Dict[str, Any]:
    briefs = list_briefs()
    return {
        "success": True,
        "count": len(briefs),
        "briefs": [
            {
                "source_session_id": b.get("source_session_id"),
                "topic": b.get("topic"),
                "timestamp": b.get("timestamp"),
            }
            for b in briefs
        ],
    }
