from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "threshold_ratio": 0.80,
    "prune_days": 14,
    "aggressive_mode": False,
}


def get_base_dir(hermes_home: Optional[Path | str] = None) -> Path:
    if hermes_home is not None:
        base = Path(hermes_home)
    else:
        env_home = os.environ.get("HERMES_HOME")
        base = Path(env_home) if env_home else Path.home() / ".hermes"
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


def get_pending_continuation_path(base_dir: Optional[Path] = None) -> Path:
    return (base_dir or get_base_dir()) / ".pending_continuation"


def save_brief(brief: Dict[str, Any], base_dir: Optional[Path] = None) -> Path:
    session_id = brief.get("source_session_id") or f"session_{int(time.time())}"
    path = get_briefs_dir(base_dir) / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2)
    return path


def load_brief(session_id: str, base_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = get_briefs_dir(base_dir) / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load brief %s: %s", session_id, e)
        return None


def list_briefs(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    briefs = []
    briefs_dir = get_briefs_dir(base_dir)
    for p in briefs_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                briefs.append(data)
        except Exception:
            continue
    briefs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return briefs


def set_pending_continuation(session_id: str, base_dir: Optional[Path] = None) -> None:
    path = get_pending_continuation_path(base_dir)
    payload = {"session_id": session_id, "timestamp": time.time()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def get_pending_continuation(base_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = get_pending_continuation_path(base_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_pending_continuation(base_dir: Optional[Path] = None) -> None:
    path = get_pending_continuation_path(base_dir)
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
