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
    get_session_usage,
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
    # Handlers should strictly accept args: dict, **kwargs and return JSON string
    handoff_raw = tool_long_conv_handoff(
        {"topic": "Review", "work_in_progress": "Testing handlers"},
        session_id="sess_h1",
    )
    assert isinstance(handoff_raw, str)
    handoff_res = json.loads(handoff_raw)
    assert handoff_res["success"] is True

    load_raw = tool_long_conv_load({"session_id": "sess_h1"})
    assert isinstance(load_raw, str)
    load_res = json.loads(load_raw)
    assert load_res["success"] is True

    list_raw = tool_long_conv_list()
    assert isinstance(list_raw, str)
    list_res = json.loads(list_raw)
    assert list_res["success"] is True

    cfg_get_raw = tool_long_conv_config_get()
    assert isinstance(cfg_get_raw, str)
    cfg_get = json.loads(cfg_get_raw)
    assert cfg_get["success"] is True

    cfg_set_raw = tool_long_conv_config_set({"aggressive_mode": False})
    assert isinstance(cfg_set_raw, str)
    cfg_set = json.loads(cfg_set_raw)
    assert cfg_set["success"] is True


def test_registry_dispatch_direct():
    # Test real dispatch through tools.registry.registry.dispatch
    import tools.registry as tool_reg

    # Register tool if not already present
    tool_reg.registry.register(
        name="test_long_conv_handoff",
        toolset="long-conversations",
        schema={"name": "test_long_conv_handoff", "description": "test", "parameters": {"type": "object"}},
        handler=tool_long_conv_handoff,
    )

    res_raw = tool_reg.registry.dispatch(
        "test_long_conv_handoff",
        {"topic": "Dispatch test", "work_in_progress": "Verifying real dispatch"},
        session_id="sess_disp_real",
    )
    assert isinstance(res_raw, str)
    res = json.loads(res_raw)
    assert res["success"] is True
    assert res["brief"]["source_session_id"] == "sess_disp_real"


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
    set_pending_continuation("sess_pending", scope_key="chat_test", base_dir=tmp_path / "long-conversations")

    # Cron should bypass injection
    cron_res = handle_pre_llm_call(
        platform="cron",
        chat_id="chat_test",
        is_first_turn=True,
        session_id="cron_session",
    )
    assert cron_res is None

    # Subagent should bypass injection
    subagent_res = handle_pre_llm_call(
        platform="subagent",
        chat_id="chat_test",
        is_first_turn=True,
        session_id="subagent_session",
    )
    assert subagent_res is None

    # is_subagent flag should also bypass
    subagent_flag_res = handle_pre_llm_call(
        is_subagent=True,
        chat_id="chat_test",
        is_first_turn=True,
        session_id="subagent_session_2",
    )
    assert subagent_flag_res is None

    # parent_session_id should also bypass
    parent_sess_res = handle_pre_llm_call(
        parent_session_id="sess_parent_123",
        chat_id="chat_test",
        is_first_turn=True,
        session_id="subagent_session_3",
    )
    assert parent_sess_res is None


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


def test_post_api_request_and_threshold_monitoring(tmp_path, monkeypatch):
    base_dir = tmp_path / "long-conversations"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Record usage via post_api_request hook
    from long_conversations import handle_post_api_request
    handle_post_api_request(
        session_id="sess_mon_1",
        usage={"total_tokens": 850},
        response={"usage": {"context_length": 1000}},
    )

    usage = get_session_usage("sess_mon_1")
    assert usage.get("tokens") == 850
    assert usage.get("context_length") == 1000

    # Test pre_llm_call picking up the recorded usage without explicit tokens in kwargs
    # Default threshold is 0.80, so 850/1000 = 85% should trigger a handoff recommendation injection
    res = handle_pre_llm_call(
        platform="discord",
        chat_id="chat_mon",
        session_id="sess_mon_1",
        is_first_turn=False,
    )
    assert res is not None
    assert "Context threshold reached (80%)" in res.get("context", "")


def test_multi_user_isolation(tmp_path, monkeypatch):
    """Test multi-user isolation under real registry dispatch without synthetic kwargs."""
    import tools.registry as tool_reg

    base_dir = tmp_path / "long-conversations"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Register tools into registry
    tool_reg.registry.register(
        name="long_conv_handoff",
        toolset="long-conversations",
        schema={"name": "long_conv_handoff", "description": "handoff", "parameters": {"type": "object"}},
        handler=tool_long_conv_handoff,
    )
    tool_reg.registry.register(
        name="long_conv_list",
        toolset="long-conversations",
        schema={"name": "long_conv_list", "description": "list", "parameters": {"type": "object"}},
        handler=tool_long_conv_list,
    )
    tool_reg.registry.register(
        name="long_conv_load",
        toolset="long-conversations",
        schema={"name": "long_conv_load", "description": "load", "parameters": {"type": "object"}},
        handler=tool_long_conv_load,
    )

    # User A creates handoff via real registry dispatch (only session_id in kwargs, matching core dispatcher)
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "user_a")
    monkeypatch.setenv("HERMES_SESSION_ID", "sess_user_a")
    tool_reg.registry.dispatch(
        "long_conv_handoff",
        {"topic": "User A Secret", "work_in_progress": "Classified"},
        session_id="sess_user_a",
    )

    # User B lists briefs via real registry dispatch -> should not see User A's brief
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "user_b")
    monkeypatch.setenv("HERMES_SESSION_ID", "sess_user_b")
    list_b_raw = tool_reg.registry.dispatch("long_conv_list", {}, session_id="sess_user_b")
    list_b = json.loads(list_b_raw)
    assert list_b["count"] == 0

    # User A lists briefs via real registry dispatch -> sees their own brief
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "user_a")
    monkeypatch.setenv("HERMES_SESSION_ID", "sess_user_a")
    list_a_raw = tool_reg.registry.dispatch("long_conv_list", {}, session_id="sess_user_a")
    list_a = json.loads(list_a_raw)
    assert list_a["count"] == 1
    assert list_a["briefs"][0]["source_session_id"] == "sess_user_a"

    # User B attempts to load User A's brief via real registry dispatch -> denied
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "user_b")
    monkeypatch.setenv("HERMES_SESSION_ID", "sess_user_b")
    load_b_raw = tool_reg.registry.dispatch("long_conv_load", {"session_id": "sess_user_a"}, session_id="sess_user_b")
    load_b = json.loads(load_b_raw)
    assert load_b["success"] is False
    assert "No brief found" in load_b["error"] or "denied" in load_b.get("error", "").lower()


def test_scope_key_validation_with_matrix_identifiers(tmp_path):
    base_dir = tmp_path / "long-conversations"
    matrix_scope = "@alice:matrix.org"
    set_pending_continuation("sess_matrix", scope_key=matrix_scope, base_dir=base_dir)

    pending = get_pending_continuation(scope_key=matrix_scope, base_dir=base_dir)
    assert pending is not None
    assert pending["session_id"] == "sess_matrix"


def test_cli_and_terminal_default_scoping(tmp_path, monkeypatch):
    """Test that CLI or terminal sessions without chat/sender context default to 'local' scope."""
    import tools.registry as tool_reg

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "cli")
    monkeypatch.delenv("HERMES_SESSION_USER_ID", raising=False)
    monkeypatch.delenv("HERMES_SESSION_CHAT_ID", raising=False)

    res_raw = tool_reg.registry.dispatch(
        "long_conv_handoff",
        {"topic": "CLI Task", "work_in_progress": "Local terminal work"},
        session_id="sess_cli_1",
    )
    assert json.loads(res_raw)["success"] is True

    # Pending continuation should be retrievable via 'local' scope
    pending = get_pending_continuation(scope_key="local")
    assert pending is not None
    assert pending["session_id"] == "sess_cli_1"

    # Pre-LLM call in CLI should pick up the continuation
    injected = handle_pre_llm_call(platform="cli", session_id="sess_cli_2", is_first_turn=True)
    assert injected is not None
    assert "CLI Task" in injected.get("context", "")


def test_multi_user_isolation_without_session_env(tmp_path, monkeypatch):
    """Verify that if HERMES_SESSION_USER_ID is missing (e.g. anonymous or malformed runtime),
    isolation defaults safely and briefs cannot be cross-loaded."""
    import tools.registry as tool_reg

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_SESSION_USER_ID", raising=False)
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)

    # Save a brief with sender_id stamped
    save_brief({
        "source_session_id": "sess_secret_user",
        "sender_id": "user_protected",
        "timestamp": "2026-10-10T12:00:00",
        "topic": "Confidential",
        "work_in_progress": "Do not leak",
    })

    # Unauthenticated/anonymous caller lists briefs -> should NOT receive user_protected's brief
    list_raw = tool_reg.registry.dispatch("long_conv_list", {}, session_id="sess_anon")
    list_res = json.loads(list_raw)
    assert list_res["count"] == 0

    # Unauthenticated caller tries to load user_protected's brief -> should fail
    load_raw = tool_reg.registry.dispatch("long_conv_load", {"session_id": "sess_secret_user"}, session_id="sess_anon")
    load_res = json.loads(load_raw)
    assert load_res["success"] is False
