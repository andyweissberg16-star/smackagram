"""
Sleeper integration for Smackcast — the first fantasy platform supported,
since Sleeper has a genuinely open, free, public API (no auth, no OAuth,
just a username or league ID). ESPN and Yahoo follow the same general
shape but need private-league cookies or OAuth respectively; those live
in their own service files once built.

Sleeper's own API docs: https://docs.sleeper.com/
"""
import requests

BASE_URL = "https://api.sleeper.app/v1"


def get_current_nfl_week() -> int | None:
    """
    Sleeper exposes the current NFL week directly — no need to
    calculate it from season start dates ourselves. Returns None if the
    league year hasn't started (offseason) or the request fails.
    """
    resp = requests.get(f"{BASE_URL}/state/nfl", timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("week")


def find_leagues_by_username(username: str, season: str) -> list:
    """
    Given a Sleeper username, returns every NFL league that user is in
    for the given season. Each entry includes league_id and name, which
    is enough for the connect wizard to show a "pick your league" list
    when someone has more than one.
    """
    user_resp = requests.get(f"{BASE_URL}/user/{username}", timeout=10)
    if user_resp.status_code != 200 or not user_resp.json():
        return []
    sleeper_user_id = user_resp.json()["user_id"]

    leagues_resp = requests.get(f"{BASE_URL}/user/{sleeper_user_id}/leagues/nfl/{season}", timeout=10)
    if leagues_resp.status_code != 200:
        return []

    return [
        {
            "league_id": league["league_id"],
            "name": league["name"],
            "team_count": league["total_rosters"],
        }
        for league in leagues_resp.json()
    ]


def get_league_info(league_id: str) -> dict | None:
    """Basic league details — name and team count, used to confirm the
    connection and drive the recap length scaling."""
    resp = requests.get(f"{BASE_URL}/league/{league_id}", timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return {
        "league_id": league_id,
        "name": data.get("name"),
        "team_count": data.get("total_rosters"),
        "season": data.get("season"),
    }


def get_week_recap_data(league_id: str, week: int) -> dict | None:
    """
    Pulls everything needed to write one week's recap: who played whom,
    the final scores, and each team's display name. Sleeper splits this
    across three separate endpoints (rosters, users, matchups) that all
    need to be joined together by roster_id, since none of them alone
    has the full picture.
    """
    rosters_resp = requests.get(f"{BASE_URL}/league/{league_id}/rosters", timeout=10)
    users_resp = requests.get(f"{BASE_URL}/league/{league_id}/users", timeout=10)
    matchups_resp = requests.get(f"{BASE_URL}/league/{league_id}/matchups/{week}", timeout=10)

    if rosters_resp.status_code != 200 or users_resp.status_code != 200 or matchups_resp.status_code != 200:
        return None

    rosters = rosters_resp.json()
    users = users_resp.json()
    matchups = matchups_resp.json()

    if not matchups:
        return None  # this week hasn't happened yet / no data available

    # Map roster_id -> owner's display name (falling back to team_name
    # if they've set one, since that's often more personality-driven
    # than their raw Sleeper username).
    user_by_id = {u["user_id"]: u for u in users}
    roster_owner_name = {}
    for roster in rosters:
        owner = user_by_id.get(roster.get("owner_id"), {})
        team_name = (owner.get("metadata") or {}).get("team_name")
        roster_owner_name[roster["roster_id"]] = team_name or owner.get("display_name") or f"Team {roster['roster_id']}"

    # Group matchups by matchup_id to pair up head-to-head opponents —
    # Sleeper returns one row per team, not one row per matchup, so
    # this reconstructs the actual pairings.
    grouped = {}
    for entry in matchups:
        grouped.setdefault(entry["matchup_id"], []).append(entry)

    matchup_list = []
    for matchup_id, entries in grouped.items():
        if len(entries) != 2:
            continue  # bye week or malformed data, skip
        a, b = entries
        matchup_list.append({
            "team_a": roster_owner_name.get(a["roster_id"], "Unknown Team"),
            "team_a_score": a.get("points", 0),
            "team_b": roster_owner_name.get(b["roster_id"], "Unknown Team"),
            "team_b_score": b.get("points", 0),
        })

    return {
        "week": week,
        "team_count": len(rosters),
        "matchups": matchup_list,
    }
