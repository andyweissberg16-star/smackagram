"""
Balldontlie — the fallback, and the only source for WNBA.
========================================================

WHY THIS EXISTS
---------------
ESPN now returns 403 to Render on the FIRST request, then the gate cools
for fourteen minutes. That is not rate limiting - rate limiting looks
like many requests and then a block. One request refused instantly is an
IP block, and the same URL returns 200 from a laptop, which confirms it.

So the fallback that was meant to catch a Highlightly outage has been
dead in production. That left Highlightly as a single point of failure
for every sport - and Auto-Smack takes money for calls that depend on
knowing a result, so a bad night there is a night of refunds.

It also left WNBA with no source at all, since Highlightly does not
carry it.

WHAT THIS ONE ACTUALLY GIVES US
-------------------------------
Confirmed live on 5 August, not inferred:

    all six sports answer      nba wnba mlb nfl nhl ncaab
    WNBA has real fixtures     Phoenix 106 Chicago 101
    NO BOX SCORES              MLB 401 (paid), WNBA 404
    FIVE REQUESTS A MINUTE     x-ratelimit-limit: 5

THE SCORING SUMMARY IS THE INTERESTING PART
-------------------------------------------
No box scores sounds worse than it is. MLB games come back with plays:

    "Lee homered to right center (410 feet)"
    "Duran homered to left (406 feet)"   - ninth, already 5-0 down

For writing a smack that is arguably BETTER than a box score. A box
score says somebody went 0-for-4. This says the Rangers made five errors
and scored once in the ninth of a game they had already lost, which is
the joke rather than the raw material for one.

FIVE A MINUTE IS THE REAL CONSTRAINT
------------------------------------
It goes through the same gate as everything else, with its own ceiling of
four - deliberately under the limit, because a ceiling set exactly at the
limit leaves no room for a retry or two requests landing in one second.

That is enough for WNBA, which has a handful of games a night. It is NOT
enough to serve the daily show for every league, and this is not meant
to.
"""

import os

BASES = {
    "nba":   "https://api.balldontlie.io/v1",
    "wnba":  "https://api.balldontlie.io/wnba/v1",
    "mlb":   "https://api.balldontlie.io/mlb/v1",
    "nfl":   "https://api.balldontlie.io/nfl/v1",
    "nhl":   "https://api.balldontlie.io/nhl/v1",
    "ncaab": "https://api.balldontlie.io/ncaab/v1",
}

# Their field names differ by sport - WNBA says visitor_team where MLB
# says away_team, and scores sit in different places. Normalising here
# means nothing downstream has to know.
_AWAY_KEYS = ("away_team", "visitor_team")


def _key():
    return os.environ.get("BALLDONTLIE_KEY")


def _get(sport, path, params=None, ttl=60):
    base = BASES.get(sport)
    key = _key()
    if not base or not key:
        return None
    from services import espn_gate
    return espn_gate.get(f"{base}/{path}", params=params or {},
                         timeout=12, label=f"bdl {sport} {path}",
                         source="balldontlie",
                         headers={"Authorization": key})


def _team_name(block):
    """Their team objects use different keys per sport."""
    if not isinstance(block, dict):
        return ""
    return (block.get("full_name") or block.get("display_name")
            or block.get("name") or "")


def _sides(row):
    """(home, away) names from a game row, whatever the sport calls them."""
    home = _team_name(row.get("home_team"))
    away = ""
    for k in _AWAY_KEYS:
        if row.get(k):
            away = _team_name(row[k])
            break
    return home, away


def _scores(row):
    """
    (home_score, away_score), which live in different places by sport.

    WNBA puts them flat on the row. MLB nests them under
    home_team_data.runs. Getting this wrong means calling a winner to
    tell them they lost, so it is worth the explicitness.
    """
    if row.get("home_score") is not None:
        return row.get("home_score"), row.get("away_score")
    h = (row.get("home_team_data") or {})
    a = (row.get("away_team_data") or {})
    return h.get("runs", h.get("score")), a.get("runs", a.get("score"))


def finals(sport, date_str):
    """
    Finished games on a date, in the same shape highlightly.finals uses,
    so a caller can swap one for the other without knowing which answered.
    """
    d = _get(sport, "games", {"dates[]": date_str, "per_page": 50})
    rows = (d or {}).get("data") if isinstance(d, dict) else None
    out = {}
    for r in (rows or []):
        status = str(r.get("status", "")).lower()
        # "STATUS_FINAL" on MLB, "post" on WNBA. Anything else is a game
        # still being played, and calling somebody about a game in
        # progress is how you get the result wrong.
        if "final" not in status and status != "post":
            continue
        home, away = _sides(r)
        hs, aws = _scores(r)
        if not home or not away or hs is None or aws is None:
            continue
        out[(home, away)] = {
            "home": home, "away": away,
            "home_score": hs, "away_score": aws,
            "winner": home if hs > aws else away,
            "loser": away if hs > aws else home,
            "id": r.get("id"),
            "venue": r.get("venue"),
            # The bit a box score cannot give us.
            "plays": [p.get("play") for p in (r.get("scoring_summary") or [])
                      if p.get("play")][:8],
            "source": "balldontlie",
        }
    return out


def board(sport, date_str):
    """Everything on a date, finished or not, for the Smack Board."""
    d = _get(sport, "games", {"dates[]": date_str, "per_page": 50})
    rows = (d or {}).get("data") if isinstance(d, dict) else None
    games = []
    for r in (rows or []):
        home, away = _sides(r)
        if not home or not away:
            continue
        hs, aws = _scores(r)
        status = str(r.get("status", ""))
        games.append({
            "home_team": home, "away_team": away,
            "home_score": hs, "away_score": aws,
            "final": ("final" in status.lower() or status == "post"),
            "is_live": status.lower() in ("in", "in_progress", "live"),
            "id": r.get("id"),
            "source": "balldontlie",
        })
    return games


def covers(sport):
    """Whether this source can answer for a sport at all."""
    return sport in BASES and bool(_key())
