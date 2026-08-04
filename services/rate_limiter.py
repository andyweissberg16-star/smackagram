import time
from collections import defaultdict

# In-memory only — resets on redeploy/restart, and won't work correctly if
# you ever scale to multiple server instances (each instance would track its
# own counts). Fine for now at low traffic; if you outgrow this, swap to
# Redis so all instances share one rate-limit counter.

_hits = defaultdict(list)

MAX_PREVIEWS_PER_HOUR = 5
WINDOW_SECONDS = 3600

# Smack Inbox lookups get their OWN bucket, deliberately separate from the
# preview bucket. Sharing one would mean somebody checking whether they'd
# been smacked would silently burn their voice-preview allowance on an
# unrelated page. The cap is higher because legitimate use genuinely
# involves several tries - people mistype their own number, or check a
# work phone and then a personal one.
MAX_INBOX_LOOKUPS_PER_HOUR = 20

# ONE preview before you need an account.
#
# The preview used to require a login, which meant a first-time visitor
# could not hear the product before creating an account - friction at the
# exact moment somebody is deciding whether to spend a dollar, and
# registering is a bigger ask than the dollar is.
#
# But previews cost real ElevenLabs credits with no purchase attached, so
# opening them completely is a standing bill anybody can run up.
#
# One is the sales pitch. The rest is where cost control belongs.
MAX_ANON_PREVIEWS_PER_HOUR = 1


def _recent(key: str, window_seconds: int) -> list:
    now = time.time()
    recent = [t for t in _hits[key] if now - t < window_seconds]
    _hits[key] = recent
    return recent


def is_limited(namespace: str, identifier: str, max_hits: int,
               window_seconds: int = WINDOW_SECONDS) -> bool:
    """Generic namespaced limiter. Each namespace counts independently."""
    return len(_recent(f"{namespace}:{identifier}", window_seconds)) >= max_hits


def record(namespace: str, identifier: str):
    _hits[f"{namespace}:{identifier}"].append(time.time())


def remaining(namespace: str, identifier: str, max_hits: int,
              window_seconds: int = WINDOW_SECONDS) -> int:
    return max(0, max_hits - len(_recent(f"{namespace}:{identifier}", window_seconds)))


# --- Preview limiter, kept as-is so existing callers don't change. ---

def is_rate_limited(identifier: str) -> bool:
    """Returns True if this identifier (e.g. IP address) has hit the cap."""
    return is_limited("preview", identifier, MAX_PREVIEWS_PER_HOUR)


def record_hit(identifier: str):
    record("preview", identifier)


def previews_remaining(identifier: str) -> int:
    return remaining("preview", identifier, MAX_PREVIEWS_PER_HOUR)
