import json
import pytest
from pathlib import Path
from long_conversations.storage import (
    save_brief,
    load_brief,
    list_briefs,
    set_pending_continuation,
    get_pending_continuation,
    clear_pending_continuation,
    prune_old_briefs,
)
from long_conversations.brief import create_handoff_brief, format_brief_for_injection
from long_conversations.lineage import record_lineage, get_parent_chain
from long_conversations.monitor import check_token_threshold
from long_conversations import register, handle_session_start


def test_brief_creation_and_storage(tmp_path):
    base_dir = tmp_path / "long-conversations"
    brief = create_handoff_brief(
        source_session_id="session_123",
        topic="Testing Long Conversations",
        work_in_progress="Writing unit tests",
        decisions_made=["Use pytest"],
        active_state_files=["tests/test_long_conversations.py"],
        next_step="Run the suite",
    )
    saved_path = save_brief(brief, base_dir=base_dir)
    assert saved_path.exists()

    loaded = load_brief("session_123", base_dir=base_dir)
    assert loaded is not None
    assert loaded["topic"] == "Testing Long Conversations"
    assert loaded["work_in_progress"] == "Writing unit tests"
    assert "pytest" in loaded["decisions_made"][0]

    all_briefs = list_briefs(base_dir=base_dir)
    assert len(all_briefs) == 1


def test_lineage_tracking(tmp_path):
    base_dir = tmp_path / "long-conversations"
    record_lineage("session_B", "session_A", topic="Phase 1", base_dir=base_dir)
    record_lineage("session_C", "session_B", topic="Phase 2", base_dir=base_dir)

    chain = get_parent_chain("session_C", base_dir=base_dir)
    assert chain == ["session_B", "session_A"]


def test_token_threshold_detection():
    class DummyEngine:
        last_total_tokens = 8500
        context_length = 10000
        threshold_tokens = 8000

    assert check_token_threshold(DummyEngine(), threshold_ratio=0.80) is True

    class DummyEngineLow:
        last_total_tokens = 5000
        context_length = 10000
        threshold_tokens = 8000

    assert check_token_threshold(DummyEngineLow(), threshold_ratio=0.80) is False


def test_plugin_registration():
    class MockCtx:
        def __init__(self):
            self.hooks = {}
            self.tools = {}

        def register_hook(self, name, handler):
            self.hooks[name] = handler

        def register_tool(self, name, description, handler):
            self.tools[name] = {"description": description, "handler": handler}

    ctx = MockCtx()
    register(ctx)

    assert "pre_llm_call" in ctx.hooks
    assert "on_session_start" in ctx.hooks
    assert "on_session_end" in ctx.hooks
    assert "long_conv_handoff" in ctx.tools
    assert "long_conv_load" in ctx.tools
    assert "long_conv_list" in ctx.tools
