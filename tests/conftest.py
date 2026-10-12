import pytest

@pytest.fixture(autouse=True)
def clean_hermes_session_env(monkeypatch):
    """Ensure tests run in an isolated environment without ambient gateway session env vars leaking from the runner."""
    for var in [
        "HERMES_SESSION_USER_ID",
        "HERMES_SESSION_USER_NAME",
        "HERMES_SESSION_CHAT_ID",
        "HERMES_SESSION_PARENT_CHAT_ID",
        "HERMES_SESSION_THREAD_ID",
        "HERMES_SESSION_PLATFORM",
        "HERMES_SESSION_ID",
        "HERMES_SESSION_SCOPE_ID",
    ]:
        monkeypatch.delenv(var, raising=False)
