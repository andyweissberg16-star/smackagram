import time
from collections import defaultdict

# In-memory only — resets on redeploy/restart, and won't work correctly if
# you ever scale to multiple server instances (each instance would track its
# own counts). Fine for now at low traffic; if you outgrow this, swap to
# Redis so all instances share one rate-limit counter.

_hits = defaultdict(list)

MAX_PREVIEWS_PER_HOUR = 5
WINDOW_SECONDS = 3600


def is_rate_limited(identifier: str) -> bool:
    """Returns True if this identifier (e.g. IP address) has hit the cap."""
    now = time.time()
    recent = [t for t in _hits[identifier] if now - t < WINDOW_SECONDS]
    _hits[identifier] = recent
    return len(recent) >= MAX_PREVIEWS_PER_HOUR


def record_hit(identifier: str):
    _hits[identifier].append(time.time())


def previews_remaining(identifier: str) -> int:
    now = time.time()
    recent = [t for t in _hits[identifier] if now - t < WINDOW_SECONDS]
    return max(0, MAX_PREVIEWS_PER_HOUR - len(recent))
