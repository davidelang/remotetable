"""Rate-limit detection helpers (contract schema_version 1)."""

from __future__ import annotations

import re
from typing import Optional


def is_rate_limit_error(message: Optional[str]) -> bool:
    if not message or not str(message).strip():
        return False
    m = str(message)
    lower = m.lower()
    if any(
        s in lower
        for s in (
            "ratelimitexceeded",
            "resource_exhausted",
            "quota exceeded",
            "write requests per minute",
            "read requests per minute",
            "read_requests",
            "write_requests",
            "user-rate limit exceeded",
            "http 429",
            "status code 429",
            "statuscode=429",
        )
    ):
        return True
    return bool(re.search(r"\b429\b", m))
