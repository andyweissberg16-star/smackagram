import requests
from datetime import datetime, timedelta, timezone

# ESPN's undocumented site API. Free, no auth required, but unofficial —
# ESPN can change or remove these endpoints without notice. Fine for launch,
# worth migrating to a paid/documented provider (SportRadar etc.) once
# real revenue depends on this being reliably up.

SPORT_PATHS = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "ncaaf": "football/college-football",
}

BASE = "https://site.api.espn.com/apis/site/v2/sports"


def get_upcoming_games(sport: str = "nfl", hours_ahead: int = 48) -> list[dict]:
    """
    Returns games kicking off within the given window — powers the
    "load a smackagram" game picker, which only shows games inside 48h.
    """
    path = SPORT_PATHS[sport]
    resp = requests.get(f"{BASE}/{path}/scoreboard", timeout=10)
    resp.raise_for_status()
    events = resp.json().get("events", [])

    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    games = []

    for event in events:
        start = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        if start > cutoff:
            continue

        competitors = event["competitions"][0]["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        games.append({
            "game_id": event["id"],
            "sport": sport,
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "start_time": event["date"],
        })

    return games


def get_game_result(game_id: str, sport: str = "nfl") -> dict | None:
    """
    Checks a single game's current state. Returns None if still in progress.
    Returns a result dict once the game is officially final:
        {"status": "final", "winner": "Cowboys", "loser": "Eagles", "home_score": 27, "away_score": 20}

    Trusts status.type.name from ESPN (e.g. "STATUS_FINAL"), not just
    "score is higher" — that alone would misfire mid-game or during OT.
    """
    path = SPORT_PATHS[sport]
    resp = requests.get(f"{BASE}/{path}/scoreboard/{game_id}", timeout=10)
    resp.raise_for_status()
    event = resp.json()

    status_name = event["status"]["type"]["name"]

    if status_name in ("STATUS_POSTPONED", "STATUS_CANCELED"):
        return {"status": "postponed"}

    if status_name != "STATUS_FINAL":
        return None  # still scheduled, in progress, halftime, OT, etc.

    competitors = event["competitions"][0]["competitors"]
    home = next(c for c in competitors if c["homeAway"] == "home")
    away = next(c for c in competitors if c["homeAway"] == "away")
    home_score, away_score = int(home["score"]), int(away["score"])

    if home_score == away_score:
        return {"status": "tie"}

    winner, loser = (home, away) if home_score > away_score else (away, home)
    return {
        "status": "final",
        "winner": winner["team"]["displayName"],
        "loser": loser["team"]["displayName"],
        "home_score": home_score,
        "away_score": away_score,
    }
