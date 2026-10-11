from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

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
    record_session_usage,
    get_session_usage,
)
from .telemetry import log_beta_event
from .tools import (
    CONFIG_GET_SCHEMA,
    CONFIG_SET_SCHEMA,
    HANDOFF_SCHEMA,
    LIST_SCHEMA,
    LOAD_SCHEMA,
    tool_long_conv_config_get,
    tool_long_conv_config_set,
    tool_long_conv_handoff,
    tool_long_conv_list,
    tool_long_conv_load,
)

logger = logging.getLogger(__name__)


def _extract_brief_from_history(conversation_history: List[Dict[str, Any]], session_id: str) -> Dict[str, Any]:
    """Build auto-brief directly from conversation_history payload without reading state.db."""
    topic_parts = []
    message_count = len(conversation_history)
    for msg in conversation_history:
        if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content"):
            content = str(msg["content"])[:200]
            topic_parts.append(content)
            if len(topic_parts) >= 3:
                break

    topic_hint = " | ".join(topic_parts) if topic_parts else "Auto-generated session brief"
    return create_handoff_brief(
        source_session_id=session_id or f"session_{int(time.time())}",
        topic=topic_hint,
        work_in_progress=f"Session continuation after {message_count} messages",
        decisions_made=[f"Auto-generated at {time.strftime('%Y-%m-%d %H:%M:%S')}"],
        next_step="Review and continue in new session",
    )


def handle_pre_llm_call(**kwargs: Any) -> Optional[Dict[str, str]]:
    """Hook invoked before LLM generation.
    
    1. Skips cron jobs and subagent executions.
    2. On first turn (is_first_turn=True), injects any pending handoff brief via {"context": ...}.
    3. Monitors context fill and generates handoff brief if threshold is reached.
    """
    platform = kwargs.get("platform", "")
    if (
        platform in ("cron", "subagent")
        or kwargs.get("is_subagent")
        or kwargs.get("subagent_id")
        or kwargs.get("parent_session_id")
    ):
        return None

    session_id = kwargs.get("session_id", "")
    sender_id = kwargs.get("sender_id") or ""
    scope_key = kwargs.get("chat_id") or kwargs.get("channel_id") or sender_id or ""
    if not scope_key and platform in ("cli", "terminal", ""):
        scope_key = "local"
    is_first_turn = kwargs.get("is_first_turn", False)

    injection_context: Optional[str] = None

    # First turn: check for pending continuation (scoped only, no unscoped fallback)
    if is_first_turn and scope_key:
        try:
            pending = get_pending_continuation(scope_key=scope_key)

            if pending and "session_id" in pending:
                parent_id = pending["session_id"]
                brief = load_brief(parent_id)
                if brief:
                    current_id = session_id or "active_session"
                    record_lineage(
                        child_session_id=str(current_id),
                        parent_session_id=parent_id,
                        topic=brief.get("topic", ""),
                    )
                    injection_context = format_brief_for_injection(brief)
                    logger.info("Long Conversations: Brief injected for session %s (from %s)", current_id, parent_id)
                clear_pending_continuation(scope_key=scope_key)
            prune_old_briefs(days=get_config().get("prune_days", 14))
        except Exception as e:
            logger.debug("Error during first-turn injection check: %s", e)

    # Monitor context fill: check recorded usage from post_api_request or kwargs
    try:
        threshold_ratio = get_threshold_ratio_from_config()
        usage_data = get_session_usage(session_id) if session_id else {}
        tokens = (
            kwargs.get("tokens")
            or kwargs.get("last_total_tokens")
            or usage_data.get("tokens", 0)
        )
        context_length = (
            kwargs.get("context_length")
            or kwargs.get("context_window")
            or usage_data.get("context_length", 0)
        )
        context_ratio = kwargs.get("context_ratio")
        
        triggered = False
        if context_ratio is not None and isinstance(context_ratio, (int, float)):
            triggered = context_ratio >= threshold_ratio
        elif context_length and tokens:
            triggered = (tokens / context_length) >= threshold_ratio

        if triggered:
            if is_aggressive_mode():
                history = kwargs.get("conversation_history") or []
                brief = _extract_brief_from_history(history, session_id)
                if sender_id:
                    brief["sender_id"] = sender_id
                save_brief(brief)
                set_pending_continuation(brief["source_session_id"], scope_key=scope_key or None)
                log_beta_event("auto_brief_generated", {"session_id": brief["source_session_id"]})
                logger.info("Long Conversations: Auto-brief saved for session %s", brief["source_session_id"])
            else:
                logger.info("Long Conversations: Token threshold reached (%.0f%%). Recommending handoff.", threshold_ratio * 100)
                if not injection_context:
                    injection_context = (
                        f"Context threshold reached ({threshold_ratio * 100:.0f}%). "
                        "Consider generating a handoff brief using long_conv_handoff to preserve state for continuation."
                    )
    except Exception as e:
        logger.debug("Error during pre_llm_call threshold check: %s", e)

    if injection_context:
        return {"context": injection_context}
    return None


def handle_post_api_request(**kwargs: Any) -> None:
    """Observer hook after API response: record tokens and context length for threshold monitoring."""
    session_id = kwargs.get("session_id")
    if not session_id:
        return
    usage = kwargs.get("usage") or {}
    total_tokens = usage.get("total_tokens") or usage.get("prompt_tokens") or 0
    response = kwargs.get("response") or {}
    context_length = (
        kwargs.get("context_length")
        or (response.get("usage") or {}).get("context_length")
        or 0
    )
    if total_tokens:
        record_session_usage(session_id, tokens=total_tokens, context_length=context_length)


def handle_session_start(**kwargs: Any) -> None:
    """Session start lifecycle hook (no-op as injection moved to pre_llm_call)."""
    pass


def handle_session_end(**kwargs: Any) -> None:
    """Session end lifecycle hook."""
    pass


def register(ctx: Any) -> None:
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("pre_llm_call", handle_pre_llm_call)
        ctx.register_hook("post_api_request", handle_post_api_request)
        ctx.register_hook("on_session_start", handle_session_start)
        ctx.register_hook("on_session_end", handle_session_end)

    if hasattr(ctx, "register_tool"):
        ctx.register_tool(
            name="long_conv_handoff",
            toolset="long-conversations",
            schema=HANDOFF_SCHEMA,
            handler=tool_long_conv_handoff,
            description="Generate a handoff brief and prepare a continuation session.",
        )
        ctx.register_tool(
            name="long_conv_load",
            toolset="long-conversations",
            schema=LOAD_SCHEMA,
            handler=tool_long_conv_load,
            description="Load an existing handoff brief by session ID for continuation.",
        )
        ctx.register_tool(
            name="long_conv_list",
            toolset="long-conversations",
            schema=LIST_SCHEMA,
            handler=tool_long_conv_list,
            description="List saved handoff briefs.",
        )
        ctx.register_tool(
            name="long_conv_config_get",
            toolset="long-conversations",
            schema=CONFIG_GET_SCHEMA,
            handler=tool_long_conv_config_get,
            description="Get current plugin configuration.",
        )
        ctx.register_tool(
            name="long_conv_config_set",
            toolset="long-conversations",
            schema=CONFIG_SET_SCHEMA,
            handler=tool_long_conv_config_set,
            description="Update plugin configuration (aggressive_mode, threshold_ratio, prune_days).",
        )
