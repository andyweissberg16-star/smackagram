"""
The gate every ESPN request goes through.
=========================================
One chokepoint, so no future caller can get this server blocked no matter
how it is written.

WHY THIS EXISTS
---------------
A 3MB league-wide injuries document was wired into roster lookups, which
meant a visitor typing in a search box caused a live request to ESPN.
Outbound traffic scaled with visitors, ESPN throttled the server, and
EVERY lookup started failing - the team picker, the daily show, and
Locked & Loaded, which handles money and refunds.

The specific fetch was the trigger. The real fault was that there was
nothing anywhere saying "that is too much".

WHAT IT GUARANTEES
------------------
1. A CEILING. No more than MAX_PER_MINUTE requests leave this server in any
   sixty seconds, whatever the calling code does. Over that, the call is
   refused HERE rather than sent - a local failure, costing nothing.

2. BACKOFF. A 429 or 403 stops ALL ESPN traffic for a cooling period.
   Retrying into a wall is how a short throttle becomes a long block.

3. HONESTY. Callers get None, exactly as they already do for a timeout.
   Every path already handles that, because a feed being unavailable was
   always possible.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not queue, retry or wait. A user request waiting on a rate limiter
is a page hanging. If the budget is spent, the answer is "not now" and the
site carries on without that data.
"""

import json
import threading
import time
from collections import deque
from urllib.request import Request, urlopen

# THE CEILING.
#
# Sized against the heaviest legitimate user, which is the daily show: five
# league scoreboards, then a detail call per game fetched six at a time. On
# a busy night that is a burst of twenty-odd within about fifteen seconds.
#
# At 20 the show lost its last game, so this is 35 - comfortable headroom
# for the busiest night, and still nowhere near enough for a runaway loop
# or a bot in a search box to become a problem.
#
# Worth remembering that SIZE matters as much as count: what actually got
# this server throttled was a 3MB document fetched repeatedly, not a high
# number of small requests.
MAX_PER_MINUTE = 35

# How long everything stops after they push back.
#
# Fifteen minutes is a guess at how long ESPN holds a grudge - nobody
# publishes that. It is long enough for a short throttle to clear and short
# enough that a morning show is not lost entirely.
#
# If a 403 persists past several cooldowns, the block is longer than this
# and the answer is patience rather than a shorter timer. /api/admin/espn-
# gate?reset=1 clears it by hand when you know it has passed.
COOLDOWN_SECONDS = 900

# A single fetch that blocks longer than this is holding up the whole site,
# because the server runs one worker.
DEFAULT_TIMEOUT = 8

# A BROWSER USER-AGENT.
#
# ESPN's public endpoints are stricter with non-browser agents on some
# paths, and the calls that were working on this project used a browser
# string while the ones that started failing used "smackagram/1.0".
#
# That may or may not be what tipped it into a 403 - a rate limit is the
# more likely cause - but identifying as a browser is free, and it removes
# one variable from a problem that is otherwise a waiting game.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_lock = threading.Lock()
_recent = deque()          # timestamps of requests actually sent
_blocked_until = 0.0       # set when they push back
_last_reason = ""

_stats = {"sent": 0, "refused_budget": 0, "refused_cooling": 0,
          "errors": 0, "throttled": 0}


def status():
    """For the admin panel - is the gate open, and how much is left."""
    now = time.time()
    with _lock:
        while _recent and now - _recent[0] > 60:
            _recent.popleft()
        return {
            "open": now >= _blocked_until,
            "cooling_for": max(0, int(_blocked_until - now)),
            "reason": _last_reason,
            "used_this_minute": len(_recent),
            "ceiling": MAX_PER_MINUTE,
            **_stats,
        }


def _note_throttle(reason):
    global _blocked_until, _last_reason
    with _lock:
        _blocked_until = time.time() + COOLDOWN_SECONDS
        _last_reason = reason
        _stats["throttled"] += 1
    print(f"[espn-gate] THEY PUSHED BACK ({reason}). Stopping all ESPN "
          f"traffic for {COOLDOWN_SECONDS // 60} minutes. Retrying into a "
          f"wall is how a short throttle becomes a long block.", flush=True)


# A RESERVE THE COSMETIC STUFF CANNOT TOUCH.
#
# Not everything that reads from ESPN matters equally. A scoreboard on the
# homepage refreshing is decoration. Locked & Loaded checking whether a game
# finished decides whether a call fires and whether somebody gets charged or
# refunded.
#
# Without this, a busy evening could spend the whole budget on scoreboard
# refreshes and leave the paid product unable to check its own results. So
# the last few requests each minute are reserved: ordinary callers are
# refused at CASUAL_CEILING, and only critical ones can use what is left.
CASUAL_CEILING = 25


def fetch(url, timeout=DEFAULT_TIMEOUT, label="", critical=False):
    """
    The only way out to ESPN.

    Returns the parsed JSON, or None. None means "not available" and every
    caller already handles it, because a timeout was always possible.
    """
    now = time.time()

    with _lock:
        if now < _blocked_until:
            _stats["refused_cooling"] += 1
            left = int(_blocked_until - now)
            print(f"[espn-gate] refused ({label or url[:48]}) - cooling for "
                  f"another {left}s", flush=True)
            return None

        while _recent and now - _recent[0] > 60:
            _recent.popleft()

        cap = MAX_PER_MINUTE if critical else CASUAL_CEILING
        if len(_recent) >= cap:
            _stats["refused_budget"] += 1
            kind = "critical" if critical else "ordinary"
            print(f"[espn-gate] refused ({label or url[:48]}) - {len(_recent)} "
                  f"this minute, {kind} ceiling is {cap}. The last "
                  f"{MAX_PER_MINUTE - CASUAL_CEILING} are reserved for calls "
                  f"that decide whether somebody gets charged.", flush=True)
            return None

        _recent.append(now)
        _stats["sent"] += 1

    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        msg = str(e)
        # 429 is rate limiting. 403 is often the same thing worn differently.
        if "429" in msg or "Too Many" in msg:
            _note_throttle("HTTP 429")
        elif "403" in msg or "Forbidden" in msg:
            _note_throttle("HTTP 403")
        with _lock:
            _stats["errors"] += 1
        print(f"[espn-gate] {label or url[:60]}: {type(e).__name__}: "
              f"{msg[:80]}", flush=True)
        return None


def reset():
    """Clear the cooldown by hand, from the admin panel."""
    global _blocked_until, _last_reason
    with _lock:
        _blocked_until = 0.0
        _last_reason = ""
    print("[espn-gate] cooldown cleared manually", flush=True)


def get(url, params=None, timeout=DEFAULT_TIMEOUT, label="",
        critical=False, headers=None, source="espn"):
    """
    The requests-library route through the same gate.

    Several ESPN callers use requests.get rather than urlopen - which is why
    a sweep for urlopen missed them entirely and left six calls going
    straight out. Same budget, same cooldown, same accounting.

    Returns parsed JSON or None.
    """
    now = time.time()

    with _lock:
        if now < _blocked_until:
            _stats["refused_cooling"] += 1
            print(f"[espn-gate] refused ({label or url[:48]}) - cooling for "
                  f"another {int(_blocked_until - now)}s", flush=True)
            return None
        while _recent and now - _recent[0] > 60:
            _recent.popleft()
        cap = MAX_PER_MINUTE if critical else CASUAL_CEILING
        if len(_recent) >= cap:
            _stats["refused_budget"] += 1
            print(f"[espn-gate] refused ({label or url[:48]}) - {len(_recent)} "
                  f"this minute, ceiling {cap}", flush=True)
            return None
        _recent.append(now)
        _stats["sent"] += 1

    try:
        import requests
        # Extra headers for callers that need them - Highlightly requires an
        # API key header, ESPN needs none.
        h = {"User-Agent": _UA}
        if headers:
            h.update(headers)
        r = requests.get(url, params=params or {}, timeout=timeout, headers=h)
        if r.status_code in (429, 403):
            # ONLY ESPN GETS THE FULL SHUTDOWN.
            #
            # The cooldown exists because ESPN blocks an IP for hours with
            # no way to appeal. A paid provider returning 429 means the
            # plan's rate limit was hit - annoying, self-correcting within
            # the minute, and NOT a reason to stop talking to ESPN as well.
            #
            # Stopping everything because one provider rate-limited us
            # would turn a small problem into an outage.
            if source == "espn":
                _note_throttle(f"HTTP {r.status_code}")
            else:
                print(f"[espn-gate] {source} returned {r.status_code} "
                      f"({label}) - not tripping the ESPN cooldown",
                      flush=True)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many" in msg:
            _note_throttle("HTTP 429")
        elif "403" in msg or "Forbidden" in msg:
            _note_throttle("HTTP 403")
        with _lock:
            _stats["errors"] += 1
        print(f"[espn-gate] {label or url[:60]}: {type(e).__name__}: "
              f"{msg[:80]}", flush=True)
        return None
