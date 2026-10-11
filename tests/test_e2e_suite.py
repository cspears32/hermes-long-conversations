import json
import pytest
from pathlib import Path

from long_conversations.storage import (
    save_brief,
    load_brief,
    list_briefs,
    set_pending_continuation,
    get_pending_continuation,
)
from long_conversations.tools import (
    tool_long_conv_handoff,
    tool_long_conv_load,
    tool_long_conv_list,
)
from long_conversations import handle_pre_llm_call
from long_conversations.lineage import get_parent_chain


def test_full_lifecycle_and_isolation_e2e(tmp_path, monkeypatch):
    """End-to-end multi-session lifecycle, chat-isolation, and dispatch test."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    base_dir = tmp_path / "long-conversations"

    # Step 1: Session 1 in Chat A triggers auto-handoff via pre_llm_call
    history = [
        {"role": "user", "content": "Let's redesign the auth architecture for the API"},
        {"role": "assistant", "content": "I recommend JWT with refresh tokens"},
        {"role": "user", "content": "Agreed, let's also plan database schema migrations"},
    ]
    
    # Configure aggressive mode
    from long_conversations.storage import save_config
    save_config({"aggressive_mode": True, "threshold_ratio": 0.80}, base_dir=base_dir)

    res_turn = handle_pre_llm_call(
        platform="discord",
        chat_id="channel_general",
        session_id="session_parent_001",
        is_first_turn=False,
        context_ratio=0.85,  # Exceeds 80% threshold
        conversation_history=history,
    )
    # Aggressive auto-brief created and pending continuation set for channel_general
    brief = load_brief("session_parent_001", base_dir=base_dir)
    assert brief is not None
    assert "auth architecture" in brief["topic"]

    # Step 2: Isolation checks
    # 2a. Cron job runs -> no injection
    cron_res = handle_pre_llm_call(
        platform="cron",
        session_id="cron_run_123",
        is_first_turn=True,
    )
    assert cron_res is None

    # 2b. Subagent runs -> no injection
    sub_res = handle_pre_llm_call(
        platform="discord",
        chat_id="channel_general",
        session_id="subagent_task_99",
        is_subagent=True,
        is_first_turn=True,
    )
    assert sub_res is None

    # 2c. Unrelated chat runs -> no injection
    other_chat_res = handle_pre_llm_call(
        platform="discord",
        chat_id="channel_random",
        session_id="session_other_chat",
        is_first_turn=True,
    )
    assert other_chat_res is None

    # Step 3: Continuation in matching chat channel_general
    # First turn -> receives injected brief context
    first_turn_res = handle_pre_llm_call(
        platform="discord",
        chat_id="channel_general",
        session_id="session_child_002",
        is_first_turn=True,
        context_ratio=0.10,
    )
    assert first_turn_res is not None
    assert "context" in first_turn_res
    assert "session_parent_001" in first_turn_res["context"]
    assert "auth architecture" in first_turn_res["context"]

    # Lineage is established
    chain = get_parent_chain("session_child_002", base_dir=base_dir)
    assert chain == ["session_parent_001"]

    # Subsequent turn in same session -> returns None, no repeated injection
    next_turn_res = handle_pre_llm_call(
        platform="discord",
        chat_id="channel_general",
        session_id="session_child_002",
        is_first_turn=False,
        context_ratio=0.20,
    )
    assert next_turn_res is None

    # Step 4: Tool execution via standard dispatch contract (args: dict, **kwargs)
    # With context environment set
    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "channel_general")
    monkeypatch.setenv("HERMES_SESSION_ID", "session_child_002")
    handoff_out_raw = tool_long_conv_handoff(
        {"topic": "Second Phase", "work_in_progress": "Testing tools"},
        session_id="session_child_002",
    )
    assert isinstance(handoff_out_raw, str)
    handoff_out = json.loads(handoff_out_raw)
    assert handoff_out["success"] is True

    list_out_raw = tool_long_conv_list({})
    assert isinstance(list_out_raw, str)
    list_out = json.loads(list_out_raw)
    assert list_out["success"] is True
    assert list_out["count"] >= 2

    load_out_raw = tool_long_conv_load({"session_id": "session_child_002"})
    assert isinstance(load_out_raw, str)
    load_out = json.loads(load_out_raw)
    assert load_out["success"] is True
    assert "formatted_context" in load_out
