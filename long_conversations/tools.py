from __future__ import annotations

import json
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
            "scope_key": {"type": "string", "description": "Optional chat or scope key to bind continuation"},
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
            "scope_key": {"type": "string", "description": "Optional chat or scope key to bind continuation"},
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


def tool_long_conv_handoff(args: dict, **kwargs: Any) -> str:
    topic = args.get("topic", "")
    work_in_progress = args.get("work_in_progress", "")
    decisions_made = args.get("decisions_made")
    active_state_files = args.get("active_state_files")
    key_assumptions = args.get("key_assumptions")
    open_questions = args.get("open_questions")
    dead_ends = args.get("dead_ends")
    next_step = args.get("next_step", "")
    session_id = args.get("session_id") or kwargs.get("session_id") or "current_session"
    sender_id = args.get("sender_id") or kwargs.get("sender_id") or ""
    scope_key = (
        args.get("scope_key")
        or kwargs.get("chat_id")
        or kwargs.get("channel_id")
        or (f"sess_{session_id}" if session_id else None)
    )

    try:
        brief = create_handoff_brief(
            source_session_id=session_id,
            topic=topic,
            work_in_progress=work_in_progress,
            decisions_made=decisions_made,
            active_state_files=active_state_files,
            key_assumptions=key_assumptions,
            open_questions=open_questions,
            dead_ends=dead_ends,
            next_step=next_step,
        )
        if sender_id:
            brief["sender_id"] = sender_id
        save_brief(brief)
        set_pending_continuation(session_id, scope_key=scope_key)
        log_beta_event("handoff_created", {"session_id": session_id, "topic": topic})
        return json.dumps({
            "success": True,
            "message": f"Handoff brief saved for session '{session_id}'. Ready for continuation in a fresh session.",
            "brief": brief,
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception("Failed to create handoff brief: %s", e)
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


def tool_long_conv_load(args: dict, **kwargs: Any) -> str:
    session_id = args.get("session_id", "")
    caller_sender_id = args.get("sender_id") or kwargs.get("sender_id") or ""
    scope_key = (
        args.get("scope_key")
        or kwargs.get("chat_id")
        or kwargs.get("channel_id")
        or (f"sess_{session_id}" if session_id else None)
    )
    if not session_id:
        return json.dumps({"success": False, "error": "session_id is required"}, ensure_ascii=False)

    brief = load_brief(session_id, caller_sender_id=caller_sender_id or None)
    if not brief:
        return json.dumps({
            "success": False,
            "error": f"No brief found for session ID: {session_id}",
        }, ensure_ascii=False)
    try:
        set_pending_continuation(session_id, scope_key=scope_key)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "message": f"Loaded brief for '{session_id}' as pending continuation.",
        "formatted_context": format_brief_for_injection(brief),
    }, ensure_ascii=False)


def tool_long_conv_list(args: Optional[dict] = None, **kwargs: Any) -> str:
    args_dict = args or {}
    caller_sender_id = args_dict.get("sender_id") or kwargs.get("sender_id") or ""
    briefs = list_briefs(caller_sender_id=caller_sender_id or None)
    return json.dumps({
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
    }, ensure_ascii=False)


def tool_long_conv_config_get(args: Optional[dict] = None, **kwargs: Any) -> str:
    """Return current plugin configuration."""
    config = get_config()
    config["aggressive_mode"] = is_aggressive_mode()
    return json.dumps({
        "success": True,
        "config": config,
    }, ensure_ascii=False)


def tool_long_conv_config_set(args: dict, **kwargs: Any) -> str:
    """Update plugin configuration. Only sets fields that are provided."""
    config = get_config()
    changes = []
    
    aggressive_mode = args.get("aggressive_mode")
    threshold_ratio = args.get("threshold_ratio")
    prune_days = args.get("prune_days")

    if aggressive_mode is not None:
        config["aggressive_mode"] = bool(aggressive_mode)
        changes.append(f"aggressive_mode: {aggressive_mode}")
    
    if threshold_ratio is not None:
        try:
            val = float(threshold_ratio)
            if not (0.0 < val <= 1.0):
                return json.dumps({"success": False, "error": "threshold_ratio must be between 0.0 and 1.0"}, ensure_ascii=False)
            config["threshold_ratio"] = val
            changes.append(f"threshold_ratio: {val}")
        except (ValueError, TypeError):
            return json.dumps({"success": False, "error": "threshold_ratio must be a valid float"}, ensure_ascii=False)
    
    if prune_days is not None:
        try:
            val = int(prune_days)
            if val < 1:
                return json.dumps({"success": False, "error": "prune_days must be >= 1"}, ensure_ascii=False)
            config["prune_days"] = val
            changes.append(f"prune_days: {val}")
        except (ValueError, TypeError):
            return json.dumps({"success": False, "error": "prune_days must be a valid integer"}, ensure_ascii=False)
    
    if not changes:
        return json.dumps({"success": True, "message": "No changes specified", "config": config}, ensure_ascii=False)
    
    save_config(config)
    return json.dumps({
        "success": True,
        "message": f"Config updated: {', '.join(changes)}",
        "config": config,
    }, ensure_ascii=False)
