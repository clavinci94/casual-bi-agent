"""Rate limiting via slowapi (in-memory, per-IP).

For single-instance Render deployments this is sufficient. For multi-
instance, swap the backing store (slowapi supports Redis via the
LIMITER_STORAGE_URL env).
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_DEFAULT_LIMIT = os.environ.get("BIQ_RATE_LIMIT", "120/minute")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_DEFAULT_LIMIT],
    storage_uri=os.environ.get("LIMITER_STORAGE_URL"),
    headers_enabled=True,
)
