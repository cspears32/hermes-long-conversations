from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def check_token_threshold(
    context_engine: Any,
    threshold_ratio: float = 0.80,
) -> bool:
    if context_engine is None:
        return False

    last_tokens = getattr(context_engine, "last_total_tokens", 0)
    context_length = getattr(context_engine, "context_length", 0)
    threshold_tokens = getattr(context_engine, "threshold_tokens", 0)

    if context_length > 0:
        return last_tokens >= (context_length * threshold_ratio)
    if threshold_tokens > 0:
        return last_tokens >= (threshold_tokens * threshold_ratio)
    return False
