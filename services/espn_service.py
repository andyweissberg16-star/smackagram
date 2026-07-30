"""
ESPN integration for Smackcast. Unlike Sleeper, ESPN has no official
public fantasy API — this uses the same unofficial, reverse-engineered
endpoint the broader fantasy football developer community has used for
years (lm-api-reads.fantasy.espn.com). Because it's unofficial, ESPN
could change or break it without notice — that's a real, known risk of
this platform specifically, not a bug in this integration.

Public leagues need nothing extra. Private leagues (most leagues among
friends) require the league owner to grab two cookie values from their
own browser session — SWID and espn_s2 — since ESPN has no OAuth-style
flow for third parties the way Yahoo does. The connect wizard walks
them through getting these.

Supports football, basketball, and baseball — ESPN uses a different
internal game code per sport in the URL itself.
"""
import requests

# ESPN's internal game codes per sport, baked into the URL path itself.
GAME_CODES = {"nfl": "ffl", "nba": "fba", "mlb": "flb"}


def _base_url(sport: str) -> str:
    game_code = GAME_CODES.get(sport, "ffl")
    return f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/{game_code}/seasons"


def _cookies(swid: str = None, espn_s2: str = None) -> dict:
    """Only private leagues need these — public leagues work with an
    empty cookie dict, which requests treats the same as no cookies."""
    if not swid or not espn_s2:
        return {}
    return {"swid": swid, "espn_s2": espn_s2}


def get_current_matchup_period(league_id: str, season: str, sport: str = "nfl", swid: str = None, espn_s2: str = None) -> int | None:
    """
    ESPN's own league status includes the current matchup period
    directly — using this instead of borrowing Sleeper's week-state
    endpoint, since that doesn't exist for baseball at all (Sleeper has
    no MLB leagues) and isn't guaranteed to line up with ESPN's own
    internal period numbering even for football/basketball.
    """
    resp = requests.get(
        f"{_base_url(sport)}/{season}/segments/0/leagues/{league_id}",
        params={"view": "mStatus"},
        cookies=_cookies(swid, espn_s2),
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("status", {}).get("currentMatchupPeriod")


def get_league_info(league_id: str, season: str, sport: str = "nfl", swid: str = None, espn_s2: str = None) -> dict | None:
    """
    Basic league details — name and team count, and also doubles as the
    connection test: if the cookies are wrong or missing for a private
    league, ESPN returns a 401/403 here rather than partial data.
    """
    resp = requests.get(
        f"{_base_url(sport)}/{season}/segments/0/leagues/{league_id}",
        params={"view": "mTeam"},
        cookies=_cookies(swid, espn_s2),
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return {
        "league_id": league_id,
        "name": data.get("settings", {}).get("name"),
        "team_count": len(data.get("teams", [])),
        "season": season,
    }


def _standouts(side: dict) -> dict:
    """
    Best and worst STARTER for one ESPN team in a matchup, matching the
    shape sleeper_service._standouts returns so the recap prompt doesn't
    care which platform the league came from.

    ESPN marks bench slots with lineupSlotId 20 (bench) and 21 (IR);
    everything else is a starter. Filtering those out matters because a
    bench player's points never counted toward the score.
    """
    entries = ((side.get("rosterForCurrentScoringPeriod") or {}).get("entries") or [])
    scored = []
    for e in entries:
        if e.get("lineupSlotId") in (20, 21):
            continue
        player = (e.get("playerPoolEntry") or {}).get("player") or {}
        name = player.get("fullName")
        if not name:
            continue
        pts = e.get("playerPoolEntry", {}).get("appliedStatTotal")
        if pts is None:
            pts = 0
        scored.append({"name": name, "points": round(float(pts), 1)})
    if not scored:
        return {}
    scored.sort(key=lambda p: p["points"], reverse=True)
    return {"top": scored[0], "bust": scored[-1]}


def get_week_recap_data(league_id: str, season: str, week: int, sport: str = "nfl", swid: str = None, espn_s2: str = None) -> dict | None:
    """
    Pulls one week's matchup data. ESPN returns team names as separate
    location + nickname fields (e.g. "Andy's" + "Avengers") rather than
    one combined string the way Sleeper does, so those get joined here
    to keep the shape of the returned data identical to
    sleeper_service.get_week_recap_data — this is what lets
    scheduler.py treat both platforms the same way downstream.

    Only supports Head-to-Head Points scoring right now — Rotisserie
    leagues have no weekly matchups at all (nothing to recap week to
    week), and Head-to-Head Categories compares several stats
    separately rather than one combined score, a genuinely different
    data shape this doesn't attempt to handle yet.
    """
    resp = requests.get(
        f"{_base_url(sport)}/{season}/segments/0/leagues/{league_id}",
        # mBoxscore (rather than mMatchupScore) is what makes ESPN return
        # per-player roster entries alongside the totals. Player names come
        # inline here, so no separate ID->name lookup is needed the way
        # Sleeper requires.
        params={"view": ["mBoxscore", "mMatchupScore"], "scoringPeriodId": week},
        cookies=_cookies(swid, espn_s2),
        timeout=10,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    teams = data.get("teams", [])
    team_name_by_id = {}
    for t in teams:
        full_name = f"{t.get('location', '').strip()} {t.get('nickname', '').strip()}".strip()
        team_name_by_id[t["id"]] = full_name or f"Team {t['id']}"

    schedule = data.get("schedule", [])
    matchup_list = []
    for entry in schedule:
        if entry.get("matchupPeriodId") != week:
            continue
        home = entry.get("home", {})
        away = entry.get("away", {})
        if not home or not away:
            continue  # bye week
        matchup_list.append({
            "team_a": team_name_by_id.get(home.get("teamId"), "Unknown Team"),
            "team_a_score": home.get("totalPoints", 0),
            "team_b": team_name_by_id.get(away.get("teamId"), "Unknown Team"),
            "team_b_score": away.get("totalPoints", 0),
            # Empty dicts if this league/view didn't return rosters - the
            # recap still writes from totals alone.
            "team_a_standouts": _standouts(home),
            "team_b_standouts": _standouts(away),
        })

    if not matchup_list:
        return None

    return {
        "week": week,
        "team_count": len(teams),
        "matchups": matchup_list,
    }
