"""
What is happening to this team RIGHT NOW.
=========================================
The core Smackagram generator receives four things: a team name, a recipient
name, a sensitivity level and some optional topics. No record, no streak, no
last result, nothing from ESPN at all.

So while Locked & Loaded gets full box scores and the Daily Smack gets
layouts and awards, the flagship product has been writing from the model's
vague memory of a team. That is why every Cowboys smack sounds like every
other Cowboys smack.

WHAT THIS IS FOR
----------------
Not to replace the archetype jokes - those are funny BECAUSE they are
timeless, and "your bullpen is a rumour" lands whether or not it is true
tonight. This adds the layer underneath: they are 3-7, they have lost four
straight, they were beaten by fourteen on Sunday.

The blend is the point. The archetype makes it funny; the fact makes it
land TODAY.

DESIGNED TO FAIL QUIETLY
------------------------
Off-season, an unknown team name, ESPN being slow - all of these return
nothing and the generator carries on exactly as it does now. A smack that
goes out without live data is the current product. A smack that fails to go
out is a refund.
"""

import json
import re
import threading
import time
from urllib.request import Request, urlopen

BASE = "https://site.api.espn.com/apis/site/v2/sports"

# EVERY LEAGUE IN THE TEAM PICKER.
#
# This started with seven, while the picker offered 1,205 teams across
# fourteen leagues - so 439 of them, including all the football (soccer) and
# college baseball, had no roster at all. Somebody picking Arsenal would tap
# "a player" and get an empty list.
#
# The KEYS match team_display's league codes exactly, because that is what
# the picker sends. The values are ESPN's own paths, which do not always
# agree with ours - "epl" here is "eng.1" there.
LEAGUES = {
    "nfl":       ("football", "nfl"),
    "nba":       ("basketball", "nba"),
    "wnba":      ("basketball", "wnba"),
    "mlb":       ("baseball", "mlb"),
    "nhl":       ("hockey", "nhl"),
    "ncaaf":     ("football", "college-football"),
    "ncaab":     ("basketball", "mens-college-basketball"),
    "ncaawb":    ("basketball", "womens-college-basketball"),
    "ncaabase":  ("baseball", "college-baseball"),
    "mls":       ("soccer", "usa.1"),
    "epl":       ("soccer", "eng.1"),
    "laliga":    ("soccer", "esp.1"),
    "seriea":    ("soccer", "ita.1"),
    "bundesliga": ("soccer", "ger.1"),
}

# Team lists change once a season; records change once a day. An hour is
# generous and keeps a busy evening from making the same call repeatedly.
_TTL = 3600
_cache = {}
_lock = threading.Lock()


def _get(url, timeout=8):
    try:
        req = Request(url, headers={"User-Agent": "smackagram/1.0"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[team-state] fetch failed {url[:70]}: {e}", flush=True)
        return None


def _cached(key, build):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]
    val = build()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def _norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _teams(league):
    """Every team in a league, with record and id."""
    def build():
        sport, path = LEAGUES[league]
        d = _get(f"{BASE}/{sport}/{path}/teams?limit=400")
        out = []
        try:
            groups = ((d.get("sports") or [{}])[0].get("leagues") or [{}])[0]
            for t in (groups.get("teams") or []):
                team = t.get("team") or {}
                out.append({
                    "id": team.get("id"),
                    "name": team.get("name"),
                    "nick": team.get("shortDisplayName"),
                    "full": team.get("displayName"),
                    "location": team.get("location"),
                    "abbr": team.get("abbreviation"),
                    "league": league,
                })
        except Exception:
            pass
        return out
    return _cached(f"teams:{league}", build)


def find_team(name, league=None):
    """
    Resolve what somebody typed into a real team.

    People type "cowboys", "Dallas", "DAL", "the cowboys". All of those
    should work, and a miss must be silent rather than an error - the smack
    still goes out, just without live data.
    """
    want = _norm(name)
    if not want:
        return None

    leagues = [league] if league in LEAGUES else list(LEAGUES)
    best = None
    for lg in leagues:
        for t in _teams(lg):
            for field in ("nick", "name", "full", "location", "abbr"):
                v = _norm(t.get(field))
                if not v:
                    continue
                if v == want:
                    return t                      # exact wins immediately
                # "dallas cowboys" typed, "cowboys" stored - and the reverse
                if best is None and (want in v or v in want) and len(want) >= 4:
                    best = t
    return best


def team_state(name, league=None):
    """
    The team's current situation, in plain language a writer can use.

    Returns None when there is nothing useful - off-season, unknown team,
    ESPN unavailable. The caller must treat that as normal.
    """
    t = find_team(name, league)
    if not t or not t.get("id"):
        return None

    def build():
        sport, path = LEAGUES[t["league"]]
        d = _get(f"{BASE}/{sport}/{path}/teams/{t['id']}")
        if not d:
            return None
        team = (d.get("team") or {})

        out = {"team": t["nick"] or t["name"], "league": t["league"].upper(),
               "facts": []}

        # Record and standing.
        for item in (team.get("record") or {}).get("items", []):
            summary = item.get("summary")
            if summary:
                out["record"] = summary
                break
        st = team.get("standingSummary")
        if st:
            out["standing"] = st

        # Recent results - the useful part. A record is a number; "lost four
        # straight, the last one by nineteen" is a joke.
        ev = (team.get("nextEvent") or [])
        out["next"] = None
        if ev:
            try:
                comp = (ev[0].get("competitions") or [{}])[0]
                out["next"] = ev[0].get("shortName")
            except Exception:
                pass

        return out

    state = _cached(f"state:{t['league']}:{t['id']}", build)
    if not state:
        return None

    # Recent form, fetched separately so a schedule failure does not cost us
    # the record too.
    form = _recent_form(t)
    if form:
        state = {**state, **form}

    state["facts"] = _to_lines(state)
    return state if state["facts"] else None


def _recent_form(t):
    """Last few results: streak, and how the most recent loss looked."""
    def build():
        sport, path = LEAGUES[t["league"]]
        d = _get(f"{BASE}/{sport}/{path}/teams/{t['id']}/schedule")
        if not d:
            return None

        played = []
        for ev in (d.get("events") or []):
            comp = (ev.get("competitions") or [{}])[0]
            status = ((comp.get("status") or {}).get("type") or {})
            if not status.get("completed"):
                continue
            sides = comp.get("competitors") or []
            if len(sides) != 2:
                continue
            mine = next((c for c in sides if str((c.get("team") or {}).get("id")) == str(t["id"])), None)
            them = next((c for c in sides if c is not mine), None)
            if not mine or not them:
                continue
            try:
                ms = int((mine.get("score") or {}).get("value")
                         if isinstance(mine.get("score"), dict) else mine.get("score"))
                ts = int((them.get("score") or {}).get("value")
                         if isinstance(them.get("score"), dict) else them.get("score"))
            except (TypeError, ValueError):
                continue
            played.append({
                "won": ms > ts,
                "mine": ms, "theirs": ts,
                "opp": ((them.get("team") or {}).get("shortDisplayName")
                        or (them.get("team") or {}).get("name")),
                "home": mine.get("homeAway") == "home",
            })

        if not played:
            return None

        # Newest last in ESPN's schedule, so walk backwards.
        played.reverse()
        streak, kind = 0, played[0]["won"]
        for g in played:
            if g["won"] == kind:
                streak += 1
            else:
                break

        last_loss = next((g for g in played if not g["won"]), None)
        return {
            "streak": streak,
            "streak_kind": "won" if kind else "lost",
            "last": played[0],
            "last_loss": last_loss,
            "recent": played[:5],
        }
    return _cached(f"form:{t['league']}:{t['id']}", build)


def _to_lines(state):
    """
    Turn the numbers into sentences a writer can actually use.

    Deliberately plain. Smacky adds the joke; this only supplies the true
    thing to build it on, and a fact dressed up here would fight the voice.
    """
    f = []
    team = state.get("team") or "they"

    if state.get("record"):
        f.append(f"{team} are {state['record']} this season")
    if state.get("standing"):
        f.append(f"they sit {state['standing']}")

    n, kind = state.get("streak"), state.get("streak_kind")
    if n and n >= 2:
        f.append(f"they have {kind} {n} in a row")

    last = state.get("last")
    if last:
        verb = "beat" if last["won"] else "lost to"
        where = "at home" if last["home"] else "on the road"
        f.append(f"last time out they {verb} {last['opp']} "
                 f"{last['mine']}-{last['theirs']} {where}")

    ll = state.get("last_loss")
    if ll and (not last or last["won"]):
        f.append(f"their last defeat was {ll['theirs']}-{ll['mine']} "
                 f"to {ll['opp']}")

    return f


# Misses are remembered too.
#
# Without this, an unrecognised team name costs SEVEN HTTP requests - one per
# league - every single time somebody types it, while they wait at checkout.
# "Bob's fantasy team" would be looked up in the NFL, NBA, WNBA, MLB, NHL and
# both college leagues, fail in all of them, and do it again on the next
# order.
_misses = {}
_MISS_TTL = 900


def facts_for(team_name, league=None, limit=4, timeout_s=3.0):
    """
    The one function the generator calls.

    Never raises. Returns [] when there is nothing, which the caller must
    treat as completely normal - a smack without live data is the current
    product; a smack that fails to send is a refund.
    """
    key = f"{_norm(team_name)}:{league or 'any'}"
    now = time.time()
    with _lock:
        miss = _misses.get(key)
        if miss and now - miss < _MISS_TTL:
            return []

    result = []
    done = threading.Event()

    def work():
        nonlocal result
        try:
            st = team_state(team_name, league)
            if st:
                result = (st.get("facts") or [])[:limit]
        except Exception as e:
            print(f"[team-state] unavailable for {team_name}: {e}", flush=True)
        finally:
            done.set()

    # HARD TIME LIMIT. This runs while somebody is waiting for their call to
    # be written, so it gets three seconds and then we go without it. Slow
    # live data is worse than none.
    th = threading.Thread(target=work, daemon=True)
    th.start()
    if not done.wait(timeout=timeout_s):
        print(f"[team-state] timed out on {team_name}, writing without it",
              flush=True)
        return []

    if not result:
        with _lock:
            _misses[key] = now
    return result


def roster(name, league=None, limit=60):
    """
    The players actually on this team, for the name picker.

    ONLY THIS TEAM'S ROSTER, not every player in every league. They have
    already chosen the team, so the list is 25-50 names rather than tens of
    thousands - smaller to hold, faster to search, and it cannot offer
    somebody who plays for a different club.

    That last part is the point. A misspelled or invented name reaching the
    generator produces a call about a person who does not exist, and neither
    the sender nor the recipient would know until it had already been said
    down the phone.

    Returns [] on anything unexpected, and the picker then simply has no
    suggestions.
    """
    t = find_team(name, league)
    if not t or not t.get("id"):
        return []

    def build():
        sport, path = LEAGUES[t["league"]]
        d = _get(f"{BASE}/{sport}/{path}/teams/{t['id']}/roster")
        if not d:
            return []
        out = []
        # ESPN nests this differently per sport - a flat list for some, split
        # into position groups for others. Handle both rather than guessing.
        groups = d.get("athletes") or []
        for g in groups:
            people = g.get("items") if isinstance(g, dict) and "items" in g else [g]
            for a in (people or []):
                if not isinstance(a, dict):
                    continue
                nm = a.get("displayName") or a.get("fullName")
                if not nm:
                    continue
                out.append({
                    "name": nm,
                    "position": ((a.get("position") or {}).get("abbreviation")
                                 if isinstance(a.get("position"), dict)
                                 else a.get("position")),
                    "number": a.get("jersey"),
                })
        # THE COACH GOES IN TOO.
        #
        # Rarely picked, but when it is picked it is the best option on the
        # list - a football coach in particular is often the whole story of
        # a defeat in a way no single player is. Fourth and one, timeouts
        # left, a challenge nobody understood.
        #
        # ESPN puts this in different places depending on the sport, so both
        # are checked rather than assuming one.
        for blob in (d.get("coach"), (d.get("team") or {}).get("coach")):
            if not blob:
                continue
            people = blob if isinstance(blob, list) else [blob]
            for c in people:
                if not isinstance(c, dict):
                    continue
                nm = (c.get("displayName")
                      or " ".join(x for x in (c.get("firstName"),
                                              c.get("lastName")) if x).strip())
                if nm:
                    # Marked so the picker can label it - "Head Coach" next
                    # to the name tells somebody instantly why it is there.
                    out.append({"name": nm, "position": "Head Coach",
                                "number": None, "is_coach": True})

        # De-duplicate, keep the order ESPN gave (usually by position).
        seen, clean = set(), []
        for p in out:
            if p["name"].lower() in seen:
                continue
            seen.add(p["name"].lower())
            clean.append(p)
        return clean[:limit]

    try:
        return _cached(f"roster:{t['league']}:{t['id']}", build) or []
    except Exception as e:
        print(f"[team-state] roster failed for {name}: {e}", flush=True)
        return []
