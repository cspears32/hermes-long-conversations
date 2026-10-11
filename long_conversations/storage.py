from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        env_home = os.environ.get("HERMES_HOME")
        return Path(env_home) if env_home else Path.home() / ".hermes"

try:
    from gateway.session_context import get_session_env
except ImportError:
    def get_session_env(key: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(key, default)

logger = logging.getLogger(__name__)

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SCOPE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]{1,128}$")

DEFAULT_CONFIG: Dict[str, Any] = {
    "threshold_ratio": 0.80,
    "prune_days": 14,
    "aggressive_mode": False,
}


def validate_session_id(session_id: str) -> str:
    """Validate session_id matches ^[A-Za-z0-9_.-]{1,128}$."""
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.match(session_id):
        raise ValueError(
            f"Invalid session_id: {session_id!r}. Must match regex '^[A-Za-z0-9_.-]{{1,128}}$'"
        )
    return session_id


def validate_scope_key(scope_key: str) -> str:
    """Validate scope_key matches ^[A-Za-z0-9_.@:-]{1,128}$."""
    if not isinstance(scope_key, str) or not SCOPE_KEY_PATTERN.match(scope_key):
        raise ValueError(
            f"Invalid scope_key: {scope_key!r}. Must match regex '^[A-Za-z0-9_.@:-]{{1,128}}$'"
        )
    return scope_key


def get_base_dir(hermes_home: Optional[Path | str] = None) -> Path:
    if hermes_home is not None:
        base = Path(hermes_home)
    else:
        base = get_hermes_home()
    target = base / "long-conversations"
    target.mkdir(parents=True, exist_ok=True)
    (target / "briefs").mkdir(parents=True, exist_ok=True)
    return target


def get_config_path(base_dir: Optional[Path] = None) -> Path:
    return (base_dir or get_base_dir()) / "config.yaml"


def get_briefs_dir(base_dir: Optional[Path] = None) -> Path:
    d = (base_dir or get_base_dir()) / "briefs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_lineage_path(base_dir: Optional[Path] = None) -> Path:
    return (base_dir or get_base_dir()) / "lineage.json"


def get_pending_continuation_path(scope_key: Optional[str] = None, base_dir: Optional[Path] = None) -> Path:
    base = base_dir or get_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    if scope_key:
        valid_key = validate_scope_key(scope_key)
        pending_dir = base / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        return pending_dir / f"{valid_key}.json"
    return base / ".pending_continuation"


def _safe_brief_path(session_id: str, base_dir: Optional[Path] = None) -> Path:
    validate_session_id(session_id)
    briefs_dir = get_briefs_dir(base_dir)
    target_path = briefs_dir / f"{session_id}.json"
    if not target_path.resolve().is_relative_to(briefs_dir.resolve()):
        raise ValueError(f"Path traversal detected: {session_id!r}")
    return target_path


def save_brief(brief: Dict[str, Any], base_dir: Optional[Path] = None) -> Path:
    session_id = brief.get("source_session_id") or f"session_{int(time.time())}"
    path = _safe_brief_path(session_id, base_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2)
    return path


def load_brief(
    session_id: str,
    base_dir: Optional[Path] = None,
    caller_sender_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    path = _safe_brief_path(session_id, base_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if caller_sender_id and data.get("sender_id"):
                if data["sender_id"] != caller_sender_id:
                    logger.warning("Access denied to brief %s for sender %s", session_id, caller_sender_id)
                    return None
            return data
    except Exception as e:
        logger.error("Failed to load brief %s: %s", session_id, e)
        return None


def list_briefs(
    base_dir: Optional[Path] = None,
    caller_sender_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    briefs = []
    briefs_dir = get_briefs_dir(base_dir)
    for p in briefs_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if caller_sender_id and data.get("sender_id"):
                    if data["sender_id"] != caller_sender_id:
                        continue
                briefs.append(data)
        except Exception:
            continue
    briefs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return briefs


def set_pending_continuation(
    session_id: str,
    scope_key: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    validate_session_id(session_id)
    if scope_key:
        validate_scope_key(scope_key)
    path = get_pending_continuation_path(scope_key, base_dir)
    payload = {
        "session_id": session_id,
        "scope_key": scope_key,
        "timestamp": time.time(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def get_pending_continuation(
    scope_key: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = get_pending_continuation_path(scope_key, base_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_pending_continuation(
    scope_key: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    path = get_pending_continuation_path(scope_key, base_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def prune_old_briefs(days: int = 14, base_dir: Optional[Path] = None) -> int:
    cutoff = time.time() - (days * 86400)
    pruned_count = 0
    briefs_dir = get_briefs_dir(base_dir)
    for p in briefs_dir.glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                pruned_count += 1
        except OSError:
            continue
    return pruned_count


# ─── In-memory session usage tracking ───────────────────────────────────────

_SESSION_USAGE: Dict[str, Dict[str, Any]] = {}
_MAX_SESSION_USAGE_ENTRIES = 500


def record_session_usage(session_id: str, tokens: int, context_length: int = 0) -> None:
    """Record latest token usage and context window for a session, bounded to prevent memory growth."""
    if len(_SESSION_USAGE) >= _MAX_SESSION_USAGE_ENTRIES and session_id not in _SESSION_USAGE:
        oldest = min(_SESSION_USAGE.keys(), key=lambda k: _SESSION_USAGE[k].get("updated_at", 0))
        _SESSION_USAGE.pop(oldest, None)

    _SESSION_USAGE[session_id] = {
        "tokens": tokens,
        "context_length": context_length,
        "updated_at": time.time(),
    }


def get_session_usage(session_id: str) -> Dict[str, Any]:
    """Retrieve latest recorded token usage for a session."""
    return _SESSION_USAGE.get(session_id, {})


# ─── Config file support ───────────────────────────────────────────────────

def get_config(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read config.yaml, falling back to defaults."""
    config_path = get_config_path(base_dir)
    defaults = dict(DEFAULT_CONFIG)
    if not config_path.exists():
        return defaults
    if yaml is None:
        logger.warning("PyYAML not available; using default config")
        return defaults
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)
        return defaults
    except Exception as e:
        logger.error("Failed to read config: %s; using defaults", e)
        return defaults


def save_config(config: Dict[str, Any], base_dir: Optional[Path] = None) -> None:
    """Write config dict to config.yaml."""
    config_path = get_config_path(base_dir)
    if yaml is None:
        logger.error("Cannot save config — PyYAML not installed")
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)
    except Exception as e:
        logger.error("Failed to save config: %s", e)
