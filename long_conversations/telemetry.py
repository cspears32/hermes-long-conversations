from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .storage import get_base_dir

logger = logging.getLogger(__name__)

BETA_ENV_FLAG = "HERMES_LONG_CONV_BETA_LOG"


def is_beta_logging_enabled() -> bool:
    return os.environ.get(BETA_ENV_FLAG, "").strip() in ("1", "true", "yes")


def log_beta_event(
    event_type: str,
    metadata: Dict[str, Any],
    base_dir: Optional[Path] = None,
) -> None:
    if not is_beta_logging_enabled():
        return

    root = get_base_dir(base_dir)
    log_path = root / "beta_events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "event_type": event_type,
        "metadata": metadata,
    }

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.debug("Beta telemetry logging failed: %s", e)
