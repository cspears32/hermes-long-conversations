from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .brief import create_handoff_brief, format_brief_for_injection
from .lineage import get_parent_chain
from .monitor import is_aggressive_mode
from .storage import (
    get_base_dir,
    get_config,
    list_briefs,
    load_brief,
    save_brief,
    save_config,
    set_pending_continuation,
)
from .telemetry import log_beta_event

logger = logging.getLogger(__name__)

HANDOFF_SCHEMA = {
    "name": "long_conv_handoff",
    "description": "Generate a handoff brief and prepare a continuation session.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Core subject or objective"},
            "work_in_progress": {"type": "string", "description": "Current status and active tasks"},
            "decisions_made": {"type": "array", "items": {"type": "string"}, "description": "Key choices settled"},
            "active_state_files": {"type": "array", "items": {"type": "string"}, "description": "Active files/configs"},
            "key_assumptions": {"type": "array", "items": {"type": "string"}, "description": "Working assumptions"},
            "open_questions": {"type": "array", "items": {"type": "string"}, "description": "Unresolved questions"},
            "dead_ends": {"type": "array", "items": {"type": "string"}, "description": "Approaches that failed"},
            "next_step": {"type": "string", "description": "Immediate next action"},
            "session_id": {"type": "string", "description": "Optional session ID override"},
        },
        "required": ["topic", "work_in_progress"],
    },
}

LOAD_SCHEMA = {
    "name": "long_conv_load",
    "description": "Load an existing handoff brief by session ID for continuation.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID of the brief to load"},
        },
        "required": ["session_id"],
    },
}

LIST_SCHEMA = {
    "name": "long_conv_list",
    "description": "List saved handoff briefs.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

CONFIG_GET_SCHEMA = {
    "name": "long_conv_config_get",
    "description": "Get current plugin configuration.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

CONFIG_SET_SCHEMA = {
    "name": "long_conv_config_set",
    "description": "Update plugin configuration (aggressive_mode, threshold_ratio, prune_days).",
    "parameters": {
        "type": "object",
        "properties": {
            "aggressive_mode": {"type": "boolean", "description": "Enable automatic aggressive handoffs"},
            "threshold_ratio": {"type": "number", "description": "Context threshold ratio (0.0 to 1.0)"},
            "prune_days": {"type": "integer", "description": "Days before stale briefs are cleaned"},
        },
    },
}


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
    log_beta_event("handoff_created", {"session_id": sid, "topic": topic})
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


def tool_long_conv_config_get() -> Dict[str, Any]:
    """Return current plugin configuration."""
    config = get_config()
    config["aggressive_mode"] = is_aggressive_mode()
    return {
        "success": True,
        "config": config,
    }


def tool_long_conv_config_set(
    aggressive_mode: Optional[bool] = None,
    threshold_ratio: Optional[float] = None,
    prune_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Update plugin configuration. Only sets fields that are provided."""
    config = get_config()
    changes = []
    
    if aggressive_mode is not None:
        config["aggressive_mode"] = aggressive_mode
        changes.append(f"aggressive_mode: {aggressive_mode}")
    
    if threshold_ratio is not None:
        if not (0.0 < threshold_ratio <= 1.0):
            return {"success": False, "error": "threshold_ratio must be between 0.0 and 1.0"}
        config["threshold_ratio"] = threshold_ratio
        changes.append(f"threshold_ratio: {threshold_ratio}")
    
    if prune_days is not None:
        if prune_days < 1:
            return {"success": False, "error": "prune_days must be >= 1"}
        config["prune_days"] = prune_days
        changes.append(f"prune_days: {prune_days}")
    
    if not changes:
        return {"success": True, "message": "No changes specified", "config": config}
    
    save_config(config)
    return {
        "success": True,
        "message": f"Config updated: {', '.join(changes)}",
        "config": config,
    }
