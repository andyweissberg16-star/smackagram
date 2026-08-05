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
Auto-Smack, which handles money and refunds.

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


# A RESERVE THE COSMETIC STUFF CANNOT TOUCH.
#
# Not everything reading from a feed matters equally. A scoreboard
# refreshing on the homepage is decoration. Auto-Smack checking
# whether a game finished decides whether somebody gets charged.
#
# Ordinary callers are refused at CASUAL_CEILING; the last few each minute
# are reserved for calls marked critical. So a busy board cannot starve the
# paid product.
CASUAL_CEILING = 25

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

# PER-SOURCE STATE.
#
# One shared cooldown was wrong, and wrong in the worst way: ESPN getting
# blocked also stopped Highlightly, which exists precisely to work when
# ESPN is down. An outage in the thing being replaced took out the
# replacement.
#
# Each source now has its own cooldown and its own budget. They cannot
# starve or block each other.
_state = {}


def _src(source):
    if source not in _state:
        _state[source] = {"recent": deque(), "blocked_until": 0.0,
                          "reason": "", "sent": 0, "refused_budget": 0,
                          "refused_cooling": 0, "errors": 0, "throttled": 0}
    return _state[source]


_lock = threading.Lock()
_recent = deque()          # timestamps of requests actually sent
_blocked_until = 0.0       # set when they push back
_last_reason = ""

_stats = {"sent": 0, "refused_budget": 0, "refused_cooling": 0,
          "errors": 0, "throttled": 0}


def status(source=None):
    """Every source, or one. The admin panel shows all of them."""
    now = time.time()
    with _lock:
        out = {}
        for name, st in _state.items():
            while st["recent"] and now - st["recent"][0] > 60:
                st["recent"].popleft()
            out[name] = {
                "open": now >= st["blocked_until"],
                "cooling_for": max(0, int(st["blocked_until"] - now)),
                "reason": st["reason"],
                "used_this_minute": len(st["recent"]),
                "ceiling": MAX_PER_MINUTE,
                "casual_ceiling": CASUAL_CEILING,
                "sent": st["sent"], "errors": st["errors"],
                "throttled": st["throttled"],
                "refused_budget": st["refused_budget"],
                "refused_cooling": st["refused_cooling"],
            }
        if source:
            return out.get(source, {})
        return out

def _note_throttle(reason, source="espn"):
    # A PAID PROVIDER IS NOT ESPN.
    #
    # The fifteen-minute cooldown exists because ESPN blocks an IP for
    # hours with no appeal, so hammering makes a bad situation worse.
    #
    # A 429 from a paid plan means the per-minute allowance was used. It
    # clears in sixty seconds. Sitting out fifteen minutes for that takes
    # a momentary limit and turns it into an outage - which is exactly
    # what happened when the picker searched on every keystroke.
    wait = COOLDOWN_SECONDS if source == "espn" else 60
    with _lock:
        st = _src(source)
        st["blocked_until"] = time.time() + wait
        st["reason"] = reason
        st["throttled"] += 1
    print(f"[gate] {source} PUSHED BACK ({reason}). Pausing {source} for "
          f"{wait}s. Other sources are unaffected.", flush=True)

    # TELL SOMEBODY. A data source going down takes the board, the show
    # and the picker with it, and on 4 August that went unnoticed for
    # hours because it only ever printed to a log.
    try:
        from services import alerts
        alerts.record(source, "blocked", reason, severity="error")
    except Exception:
        pass


def _allow(source, critical, label):
    """
    May this request go out? Checks THIS source's cooldown and budget only.

    Returns True to proceed. Prints its own reason when refusing.
    """
    now = time.time()
    with _lock:
        st = _src(source)
        if now < st["blocked_until"]:
            st["refused_cooling"] += 1
            left = int(st["blocked_until"] - now)
            print(f"[gate] {source} refused ({label}) - cooling {left}s",
                  flush=True)
            return False
        while st["recent"] and now - st["recent"][0] > 60:
            st["recent"].popleft()
        cap = MAX_PER_MINUTE if critical else CASUAL_CEILING
        if len(st["recent"]) >= cap:
            st["refused_budget"] += 1
            print(f"[gate] {source} refused ({label}) - {len(st['recent'])} "
                  f"this minute, ceiling {cap}", flush=True)
            return False
        st["recent"].append(now)
        st["sent"] += 1
        return True

def fetch(url, timeout=DEFAULT_TIMEOUT, label="", critical=False,
          source="espn"):
    """
    The urllib route through the gate.

    Returns parsed JSON, or None. None means "not available" and every
    caller already handles it.
    """
    if not _allow(source, critical, label or url[:48]):
        return None
    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many" in msg:
            _note_throttle("HTTP 429", source)
        elif "403" in msg or "Forbidden" in msg:
            _note_throttle("HTTP 403", source)
        with _lock:
            _src(source)["errors"] += 1
        print(f"[gate] {source} {label or url[:60]}: {type(e).__name__}: "
              f"{msg[:80]}", flush=True)
        return None

def reset(source=None):
    """Clear a cooldown by hand. One source, or all of them."""
    with _lock:
        for name, st in _state.items():
            if source and name != source:
                continue
            st["blocked_until"] = 0.0
            st["reason"] = ""
    print(f"[gate] cooldown cleared for {source or 'all sources'}",
          flush=True)

def get(url, params=None, timeout=DEFAULT_TIMEOUT, label="",
        critical=False, headers=None, source="espn"):
    """
    The requests-library route through the same gate.

    Several callers use requests rather than urlopen, which is why a sweep
    for urlopen alone missed six of them.
    """
    if not _allow(source, critical, label or url[:48]):
        return None
    try:
        import requests
        h = {"User-Agent": _UA}
        if headers:
            h.update(headers)
        r = requests.get(url, params=params or {}, timeout=timeout, headers=h)
        if r.status_code in (429, 403):
            _note_throttle(f"HTTP {r.status_code}", source)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many" in msg:
            _note_throttle("HTTP 429", source)
        elif "403" in msg or "Forbidden" in msg:
            _note_throttle("HTTP 403", source)
        with _lock:
            _src(source)["errors"] += 1
        print(f"[gate] {source} {label or url[:60]}: {type(e).__name__}: "
              f"{msg[:80]}", flush=True)
        return None
