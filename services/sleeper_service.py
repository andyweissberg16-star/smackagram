"""
Sleeper integration for Smackcast. Supports NFL and NBA, since those are
the only sports Sleeper actually offers real season-long fantasy
leagues for (confirmed directly, not an assumption) — no MLB support
exists on the platform at all, so baseball leagues route through ESPN
only.

Sleeper's own API docs: https://docs.sleeper.com/
"""
import requests

BASE_URL = "https://api.sleeper.app/v1"

SUPPORTED_SPORTS = ("nfl", "nba")


def get_current_week(sport: str = "nfl") -> int | None:
    """
    Sleeper exposes the current week directly per sport — no need to
    calculate it from season start dates ourselves. Returns None if the
    league year hasn't started (offseason) or the request fails.
    """
    resp = requests.get(f"{BASE_URL}/state/{sport}", timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("week")


def find_leagues_by_username(username: str, season: str, sport: str = "nfl") -> list:
    """
    Given a Sleeper username, returns every league that user is in for
    the given sport and season. Each entry includes league_id and name,
    which is enough for the connect wizard to show a "pick your league"
    list when someone has more than one.
    """
    user_resp = requests.get(f"{BASE_URL}/user/{username}", timeout=10)
    if user_resp.status_code != 200 or not user_resp.json():
        return []
    sleeper_user_id = user_resp.json()["user_id"]

    leagues_resp = requests.get(f"{BASE_URL}/user/{sleeper_user_id}/leagues/{sport}/{season}", timeout=10)
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


_PLAYER_NAME_CACHE = {}


def _player_names(sport: str = "nfl") -> dict:
    """
    Maps Sleeper player_id -> real player name.

    Sleeper's matchup rows only ever contain player IDs, so this table is
    the only way to name an actual player. The dump is several MB, which
    is why it's fetched once per process and held in memory rather than
    per recap — a weekly cron generating a dozen recaps would otherwise
    pull it a dozen times.

    Returns an empty dict on any failure. Player detail is a bonus on top
    of the recap, never a prerequisite: callers must treat missing names
    as "no player data this week" and still produce a recap from the
    team totals.
    """
    if sport in _PLAYER_NAME_CACHE:
        return _PLAYER_NAME_CACHE[sport]
    try:
        resp = requests.get(f"{BASE_URL}/players/{sport}", timeout=30)
        if resp.status_code != 200:
            return {}
        names = {}
        for pid, info in (resp.json() or {}).items():
            name = info.get("full_name") or " ".join(
                x for x in [info.get("first_name"), info.get("last_name")] if x
            ).strip()
            if name:
                pos = info.get("position") or ""
                names[str(pid)] = f"{name} ({pos})" if pos else name
        _PLAYER_NAME_CACHE[sport] = names
        return names
    except Exception as e:
        print(f"[sleeper] player name lookup failed: {e}")
        return {}


def _standouts(entry: dict, names: dict) -> dict:
    """
    Picks the best and worst STARTER for one team from a Sleeper matchup
    row. Starters only — a big score on the bench is a different (and
    much funnier) story than a starter busting, and mixing the two would
    let the recap credit points that never counted.
    """
    starters = entry.get("starters") or []
    points = entry.get("players_points") or {}
    scored = []
    for pid in starters:
        # "0" is Sleeper's placeholder for an empty roster slot.
        if not pid or str(pid) == "0":
            continue
        name = names.get(str(pid))
        if not name:
            continue
        scored.append({"name": name, "points": round(float(points.get(str(pid), 0) or 0), 1)})
    if not scored:
        return {}
    scored.sort(key=lambda p: p["points"], reverse=True)
    return {"top": scored[0], "bust": scored[-1]}


def get_week_recap_data(league_id: str, week: int, sport: str = "nfl") -> dict | None:
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

    # Once per call, not once per matchup.
    player_names = _player_names(sport)

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
            # Empty dicts when the name lookup failed - the recap still
            # writes fine from totals alone, it just can't name players.
            "team_a_standouts": _standouts(a, player_names),
            "team_b_standouts": _standouts(b, player_names),
        })

    return {
        "week": week,
        "team_count": len(rosters),
        "matchups": matchup_list,
    }
