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

        def register_tool(self, name, **kwargs):
            self.tools[name] = kwargs

    ctx = MockCtx()
    register(ctx)

    assert "pre_llm_call" in ctx.hooks
    assert "on_session_start" in ctx.hooks
    assert "on_session_end" in ctx.hooks
    assert "long_conv_handoff" in ctx.tools
    assert "long_conv_load" in ctx.tools
    assert "long_conv_list" in ctx.tools


def test_beta_telemetry_opt_in(tmp_path, monkeypatch):
    from long_conversations.telemetry import log_beta_event, BETA_ENV_FLAG
    base_dir = tmp_path / "long-conversations"

    # Disabled by default
    monkeypatch.delenv(BETA_ENV_FLAG, raising=False)
    log_beta_event("test_event", {"foo": "bar"}, base_dir=tmp_path)
    assert not (base_dir / "beta_events.jsonl").exists()

    # Enabled via env flag
    monkeypatch.setenv(BETA_ENV_FLAG, "1")
    log_beta_event("test_event", {"foo": "bar"}, base_dir=tmp_path)
    log_path = base_dir / "beta_events.jsonl"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "test_event" in content
    assert "foo" in content


def test_config_save_and_load(tmp_path, monkeypatch):
    from long_conversations.storage import get_config, save_config, get_config_path
    from long_conversations.monitor import is_aggressive_mode, get_threshold_ratio_from_config

    base_dir = tmp_path / "long-conversations"

    # Default config
    monkeypatch.delenv("HERMES_HOME", raising=False)
    config = get_config(base_dir=base_dir)
    assert config["threshold_ratio"] == 0.80
    assert config["prune_days"] == 14
    assert config["aggressive_mode"] is False

    # Save and reload
    config["aggressive_mode"] = True
    config["threshold_ratio"] = 0.75
    config["prune_days"] = 7
    save_config(config, base_dir=base_dir)

    reloaded = get_config(base_dir=base_dir)
    assert reloaded["aggressive_mode"] is True
    assert reloaded["threshold_ratio"] == 0.75
    assert reloaded["prune_days"] == 7


def test_config_tools(tmp_path):
    from long_conversations.tools import (
        tool_long_conv_config_get,
        tool_long_conv_config_set,
    )

    # Get default
    result = tool_long_conv_config_get()
    assert result["success"] is True
    assert "config" in result

    # Set aggressive mode
    result = tool_long_conv_config_set({"aggressive_mode": True})
    assert result["success"] is True
    assert "aggressive_mode: True" in result["message"]

    # Invalid threshold
    result = tool_long_conv_config_set({"threshold_ratio": 1.5})
    assert result["success"] is False
    assert "threshold_ratio must be between" in result["error"]

    # Reload and verify
    result = tool_long_conv_config_get()
    assert result["config"]["aggressive_mode"] is True
