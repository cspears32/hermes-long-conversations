import json
import pytest
from pathlib import Path

from long_conversations.storage import (
    save_brief,
    load_brief,
    validate_session_id,
    set_pending_continuation,
    get_pending_continuation,
    clear_pending_continuation,
    get_base_dir,
)
from long_conversations.tools import (
    tool_long_conv_handoff,
    tool_long_conv_load,
    tool_long_conv_list,
    tool_long_conv_config_get,
    tool_long_conv_config_set,
)
from long_conversations import handle_pre_llm_call


def test_session_id_regex_validation():
    # Valid IDs
    assert validate_session_id("session_123") == "session_123"
    assert validate_session_id("abc-DEF_0.9") == "abc-DEF_0.9"

    # Invalid IDs
    with pytest.raises(ValueError, match="Invalid session_id"):
        validate_session_id("")

    with pytest.raises(ValueError, match="Invalid session_id"):
        validate_session_id("../malicious")

    with pytest.raises(ValueError, match="Invalid session_id"):
        validate_session_id("session;rm -rf")

    with pytest.raises(ValueError, match="Invalid session_id"):
        validate_session_id("a" * 129)


def test_path_traversal_confinement(tmp_path):
    base_dir = tmp_path / "long-conversations"
    with pytest.raises(ValueError):
        load_brief("../../etc/passwd", base_dir=base_dir)

    with pytest.raises(ValueError):
        save_brief({"source_session_id": "../escaped"}, base_dir=base_dir)


def test_tools_handler_contract():
    # Handlers should strictly accept args: dict, **kwargs
    handoff_res = tool_long_conv_handoff(
        {"topic": "Review", "work_in_progress": "Testing handlers"},
        session_id="sess_h1",
    )
    assert handoff_res["success"] is True

    load_res = tool_long_conv_load({"session_id": "sess_h1"})
    assert load_res["success"] is True

    list_res = tool_long_conv_list()
    assert list_res["success"] is True

    cfg_get = tool_long_conv_config_get()
    assert cfg_get["success"] is True

    cfg_set = tool_long_conv_config_set({"aggressive_mode": False})
    assert cfg_set["success"] is True


def test_registry_dispatch_simulation():
    # Simulate tools.registry.registry.dispatch
    def simulate_dispatch(handler, args, **kwargs):
        return handler(args, **kwargs)

    res = simulate_dispatch(
        tool_long_conv_handoff,
        {"topic": "Dispatch test", "work_in_progress": "Verifying dispatch signature"},
        session_id="sess_disp_1",
    )
    assert res["success"] is True
    assert res["brief"]["source_session_id"] == "sess_disp_1"


def test_chat_scoped_continuation(tmp_path):
    base_dir = tmp_path / "long-conversations"
    set_pending_continuation("sess_chat_A", scope_key="chat_1", base_dir=base_dir)

    # Retrieval in matching scope
    pending_a = get_pending_continuation(scope_key="chat_1", base_dir=base_dir)
    assert pending_a is not None
    assert pending_a["session_id"] == "sess_chat_A"

    # Retrieval in different scope returns None
    pending_b = get_pending_continuation(scope_key="chat_2", base_dir=base_dir)
    assert pending_b is None


def test_cron_and_subagent_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    set_pending_continuation("sess_pending", base_dir=tmp_path / "long-conversations")

    # Cron should bypass injection
    cron_res = handle_pre_llm_call(
        platform="cron",
        is_first_turn=True,
        session_id="cron_session",
    )
    assert cron_res is None

    # Subagent should bypass injection
    subagent_res = handle_pre_llm_call(
        is_subagent=True,
        is_first_turn=True,
        session_id="subagent_session",
    )
    assert subagent_res is None


def test_pre_llm_call_first_turn_injection(tmp_path, monkeypatch):
    base_dir = tmp_path / "long-conversations"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    brief_data = {
        "source_session_id": "parent_sess",
        "topic": "Handoff Topic",
        "work_in_progress": "Handoff WIP",
        "decisions_made": [],
        "active_state_files": [],
        "key_assumptions": [],
        "open_questions": [],
        "dead_ends": [],
        "next_step": "Proceed to phase 2",
    }
    save_brief(brief_data, base_dir=base_dir)
    set_pending_continuation("parent_sess", scope_key="chat_100", base_dir=base_dir)

    # First turn in chat_100 -> injects brief
    turn1_res = handle_pre_llm_call(
        platform="discord",
        chat_id="chat_100",
        is_first_turn=True,
        session_id="child_sess",
        tokens=100,
        context_length=1000,
    )
    assert turn1_res is not None
    assert "context" in turn1_res
    assert "Handoff Topic" in turn1_res["context"]

    # Second turn -> returns None
    turn2_res = handle_pre_llm_call(
        platform="discord",
        chat_id="chat_100",
        is_first_turn=False,
        session_id="child_sess",
        tokens=200,
        context_length=1000,
    )
    assert turn2_res is None
