from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from .brief import create_handoff_brief, format_brief_for_injection
from .lineage import record_lineage
from .monitor import check_token_threshold, get_threshold_ratio_from_config, is_aggressive_mode
from .storage import (
    clear_pending_continuation,
    get_base_dir,
    get_config,
    get_pending_continuation,
    load_brief,
    list_briefs,
    prune_old_briefs,
    save_brief,
    save_config,
    set_pending_continuation,
)
from .telemetry import log_beta_event
from .tools import (
    tool_long_conv_config_get,
    tool_long_conv_config_set,
    tool_long_conv_handoff,
    tool_long_conv_list,
    tool_long_conv_load,
)

logger = logging.getLogger(__name__)


def _extract_session_metadata() -> Dict[str, Any]:
    """Extract session metadata from state.db for auto-brief generation.
    
    Reads the last N messages and creates a minimal brief with topic hints.
    """
    import sqlite3
    from pathlib import Path
    
    home = Path.home() / ".hermes"
    db_path = home / "state.db"
    
    if not db_path.exists():
        return {}
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get current session info
        cur.execute("""
            SELECT session_id, created_at, parent_session_id 
            FROM sessions 
            WHERE ended_at IS NULL OR ended_at = ''
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        
        if row:
            session_id = dict(row)["session_id"]
            created_at = dict(row)["created_at"]
            
            # Get last 20 messages for topic extraction
            cur.execute("""
                SELECT role, content, timestamp 
                FROM messages 
                WHERE session_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 20
            """, (session_id,))
            messages = [dict(r) for r in cur.fetchall()]
            
            # Extract topic from first few user messages
            topic_parts = []
            for msg in reversed(messages):
                if msg["role"] == "user" and msg["content"]:
                    content = str(msg["content"])[:200]
                    topic_parts.append(content)
                    if len(topic_parts) >= 3:
                        break
            
            conn.close()
            
            return {
                "session_id": session_id,
                "created_at": created_at,
                "topic_hint": " | ".join(topic_parts) if topic_parts else "Unknown topic",
                "message_count": len(messages),
                "parent_session_id": dict(row)["parent_session_id"] or "",
            }
        conn.close()
    except Exception as e:
        logger.debug("Failed to extract session metadata: %s", e)
    
    return {}


def handle_pre_llm_call(ctx: Any, **kwargs: Any) -> None:
    try:
        engine = getattr(ctx, "context_engine", None)
        if engine is None:
            return
        
        # Read threshold from config
        threshold_ratio = get_threshold_ratio_from_config()
        
        if check_token_threshold(engine, threshold_ratio=threshold_ratio):
            aggressive = is_aggressive_mode()
            
            if aggressive:
                # Auto-generate brief from session metadata
                logger.info("Long Conversations: Aggressive mode — auto-generating brief at %.0f%% threshold", threshold_ratio * 100)
                metadata = _extract_session_metadata()
                
                brief = create_handoff_brief(
                    source_session_id=metadata.get("session_id", "unknown"),
                    topic=metadata.get("topic_hint", "Auto-generated brief"),
                    work_in_progress=f"Session at {threshold_ratio:.0%} context capacity ({metadata.get('message_count', 0)} messages)",
                    decisions_made=[f"Auto-generated at {time.strftime('%Y-%m-%d %H:%M:%S')}"],
                    next_step="Review and continue in new session",
                )
                save_brief(brief)
                set_pending_continuation(brief["source_session_id"])
                log_beta_event("auto_brief_generated", {"session_id": brief["source_session_id"]})
                logger.info("Long Conversations: Auto-brief saved for session %s", brief["source_session_id"])
            else:
                logger.info("Long Conversations: Token threshold reached (%.0f%%). Recommending handoff.", threshold_ratio * 100)
    except Exception as e:
        logger.debug("pre_llm_call hook error: %s", e)


def handle_session_start(ctx: Any, **kwargs: Any) -> None:
    try:
        pending = get_pending_continuation()
        if pending and "session_id" in pending:
            parent_id = pending["session_id"]
            brief = load_brief(parent_id)
            if brief:
                current_id = getattr(ctx, "session_id", "active_session")
                record_lineage(
                    child_session_id=str(current_id),
                    parent_session_id=parent_id,
                    topic=brief.get("topic", ""),
                )
                if hasattr(ctx, "inject_message"):
                    ctx.inject_message("user", format_brief_for_injection(brief))
                logger.info("Long Conversations: Brief injected for session %s (from %s)", current_id, parent_id)
            clear_pending_continuation()
        prune_old_briefs(days=get_config().get("prune_days", 14))
    except Exception as e:
        logger.debug("on_session_start hook error: %s", e)


def handle_session_end(ctx: Any, **kwargs: Any) -> None:
    pass


def register(ctx: Any) -> None:
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("pre_llm_call", handle_pre_llm_call)
        ctx.register_hook("on_session_start", handle_session_start)
        ctx.register_hook("on_session_end", handle_session_end)

    if hasattr(ctx, "register_tool"):
        ctx.register_tool(
            name="long_conv_handoff",
            description="Generate a handoff brief and prepare a continuation session.",
            handler=tool_long_conv_handoff,
        )
        ctx.register_tool(
            name="long_conv_load",
            description="Load an existing handoff brief by session ID for continuation.",
            handler=tool_long_conv_load,
        )
        ctx.register_tool(
            name="long_conv_list",
            description="List saved handoff briefs.",
            handler=tool_long_conv_list,
        )
        ctx.register_tool(
            name="long_conv_config_get",
            description="Get current plugin configuration.",
            handler=tool_long_conv_config_get,
        )
        ctx.register_tool(
            name="long_conv_config_set",
            description="Update plugin configuration (aggressive_mode, threshold_ratio, prune_days).",
            handler=tool_long_conv_config_set,
        )
