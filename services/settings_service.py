"""
Runtime settings, changeable without a deploy.

Deliberately a generic key/value store rather than one-off columns. The first
two settings are the 2FA switches, but the same machinery will carry the show's
league selection, runtime bounds and kill switch - and a table that grows by
rows rather than migrations is the right shape for that.

Values are cached in-process because these are read on every login, and a
database round trip per request for a boolean would be silly. The cache is
short-lived so a change from the admin panel takes effect within seconds on
every worker rather than needing a restart.
"""

import os
import time

from models import db, Setting

_cache = {}
_cache_at = 0
_CACHE_TTL = 15   # seconds - long enough to matter, short enough to feel instant


# The env vars stay as the fallback, so a database that hasn't been seeded
# behaves exactly as it did before this existed.
DEFAULTS = {
    "twofactor_customers": os.environ.get("TWO_FACTOR_CUSTOMERS", "0") == "1",
    "twofactor_admins": os.environ.get("TWO_FACTOR_ADMINS", "0") == "1",
    # SMACK BACK WITHOUT PHONE VERIFICATION - David's call, Aug 6 2026.
    #
    # Twilio's A2P review is stuck, so there is no way to text a code.
    # Until it clears, POSSESSION OF THE NUMBER IS THE AUTHENTICATOR:
    # type the number, see the smacks sent to it, smack back. The
    # trade-off is understood - anyone who knows a number can hear
    # what was sent to it - and accepted for launch. Flip this to True
    # the day Twilio clears and the code-text flow takes over again;
    # every path checks this flag at runtime, so re-enabling is one
    # admin toggle, no deploy.
    "smackback_requires_verification":
        os.environ.get("SMACKBACK_REQUIRES_VERIFICATION", "0") == "1",
}


def _load():
    global _cache, _cache_at
    now = time.time()
    if _cache and (now - _cache_at) < _CACHE_TTL:
        return _cache
    try:
        rows = Setting.query.all()
        _cache = {r.key: r.value for r in rows}
        _cache_at = now
    except Exception as e:
        # A settings table that isn't there yet must not take the site down -
        # fall through to defaults.
        print(f"[settings] read failed, using defaults: {e}")
        return {}
    return _cache


def get_bool(key: str) -> bool:
    raw = _load().get(key)
    if raw is None:
        return DEFAULTS.get(key, False)
    return raw == "1"


def get_str(key: str, default: str = "") -> str:
    raw = _load().get(key)
    return default if raw is None else raw


def set_value(key: str, value, changed_by: str = "") -> None:
    """Writes a setting and clears the cache so it applies immediately."""
    global _cache_at
    if isinstance(value, bool):
        value = "1" if value else "0"
    value = str(value)

    row = Setting.query.filter_by(key=key).first()
    before = row.value if row else "(unset)"
    if row:
        row.value = value
        row.updated_by = changed_by
    else:
        db.session.add(Setting(key=key, value=value, updated_by=changed_by))
    db.session.commit()

    _cache_at = 0     # force a reload on next read
    print(f"[settings] {changed_by or 'system'} set {key}: {before} -> {value}")


def all_settings() -> dict:
    """Everything the admin panel needs to render the toggles."""
    return {
        "twofactor_customers": get_bool("twofactor_customers"),
        "twofactor_admins": get_bool("twofactor_admins"),
    }
