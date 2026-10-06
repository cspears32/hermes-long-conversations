from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import get_base_dir, get_lineage_path

logger = logging.getLogger(__name__)


def record_lineage(
    child_session_id: str,
    parent_session_id: str,
    topic: str = "",
    base_dir: Optional[Path] = None,
) -> None:
    path = get_lineage_path(base_dir)
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Could not read lineage graph: %s", e)

    data[child_session_id] = {
        "parent_session_id": parent_session_id,
        "timestamp": time.time(),
        "topic": topic,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Failed to write lineage graph: %s", e)


def get_parent_chain(session_id: str, base_dir: Optional[Path] = None) -> List[str]:
    path = get_lineage_path(base_dir)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    chain = []
    curr = session_id
    visited = set()
    while curr in data and curr not in visited:
        visited.add(curr)
        parent = data[curr].get("parent_session_id")
        if not parent:
            break
        chain.append(parent)
        curr = parent
    return chain
