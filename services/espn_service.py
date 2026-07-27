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
"""
import requests

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"


def _cookies(swid: str = None, espn_s2: str = None) -> dict:
    """Only private leagues need these — public leagues work with an
    empty cookie dict, which requests treats the same as no cookies."""
    if not swid or not espn_s2:
        return {}
    return {"swid": swid, "espn_s2": espn_s2}


def get_league_info(league_id: str, season: str, swid: str = None, espn_s2: str = None) -> dict | None:
    """
    Basic league details — name and team count, and also doubles as the
    connection test: if the cookies are wrong or missing for a private
    league, ESPN returns a 401/403 here rather than partial data.
    """
    resp = requests.get(
        f"{BASE_URL}/{season}/segments/0/leagues/{league_id}",
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


def get_week_recap_data(league_id: str, season: str, week: int, swid: str = None, espn_s2: str = None) -> dict | None:
    """
    Pulls one week's matchup data. ESPN returns team names as separate
    location + nickname fields (e.g. "Andy's" + "Avengers") rather than
    one combined string the way Sleeper does, so those get joined here
    to keep the shape of the returned data identical to
    sleeper_service.get_week_recap_data — this is what lets
    scheduler.py treat both platforms the same way downstream.
    """
    resp = requests.get(
        f"{BASE_URL}/{season}/segments/0/leagues/{league_id}",
        params={"view": "mMatchupScore", "scoringPeriodId": week},
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
        })

    if not matchup_list:
        return None

    return {
        "week": week,
        "team_count": len(teams),
        "matchups": matchup_list,
    }
