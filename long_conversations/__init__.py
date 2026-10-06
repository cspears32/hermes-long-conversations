from __future__ import annotations

import logging
from typing import Any, Dict

from .brief import format_brief_for_injection
from .lineage import record_lineage
from .monitor import check_token_threshold
from .storage import (
    clear_pending_continuation,
    get_pending_continuation,
    load_brief,
    prune_old_briefs,
)
from .tools import tool_long_conv_handoff, tool_long_conv_list, tool_long_conv_load

logger = logging.getLogger(__name__)


def handle_pre_llm_call(ctx: Any, **kwargs: Any) -> None:
    try:
        engine = getattr(ctx, "context_engine", None)
        if engine and check_token_threshold(engine, threshold_ratio=0.80):
            logger.info("Long Conversations: Token threshold reached. Recommending handoff.")
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
            clear_pending_continuation()
        prune_old_briefs(days=14)
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
