import os
import requests
from datetime import datetime, timedelta, timezone

# SportsDataIO — paid, documented, SLA-backed sports data provider.
# Replaces the earlier free ESPN integration, which worked but was
# unofficial and could change/break without notice — not something to
# depend on for a feature that authorizes and captures real payments.
#
# IMPORTANT: SportsDataIO's free trial returns SCRAMBLED data — real,
# accurate results only come on a paid plan. Don't trust trial-mode
# results for confirming this feature actually works correctly.

SPORT_PATHS = {
    "nfl": "nfl",
    "nba": "nba",
    "mlb": "mlb",
    "nhl": "nhl",
    "ncaaf": "cfb",  # SportsDataIO uses "cfb" for college football, not "ncaaf"
}

BASE = "https://api.sportsdata.io/v3"


def _api_key() -> str:
    return os.environ["SPORTSDATA_API_KEY"]


def _get(sport: str, endpoint: str) -> dict | list:
    path = SPORT_PATHS[sport]
    resp = requests.get(
        f"{BASE}/{path}/scores/json/{endpoint}",
        params={"key": _api_key()},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_upcoming_games(sport: str = "nfl", hours_ahead: int = 48) -> list[dict]:
    """
    Returns games kicking off within the given window — powers the
    "load a smackagram" game picker, which only shows games inside 48h.

    SportsDataIO's GamesByDate takes a single date, not a range, so we
    query today and tomorrow (covers a 48h window) and filter by the
    actual kickoff time.
    """
    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    today = datetime.now(timezone.utc).date()
    dates_to_check = [today, today + timedelta(days=1), today + timedelta(days=2)]

    games = []
    seen_ids = set()

    for d in dates_to_check:
        date_str = d.strftime("%Y-%b-%d").upper()  # SportsDataIO's expected format, e.g. 2026-SEP-10
        try:
            events = _get(sport, f"GamesByDate/{date_str}")
        except requests.HTTPError:
            continue

        for event in events:
            game_id = str(event.get("GameID") or event.get("GameKey"))
            if game_id in seen_ids:
                continue

            start_raw = event.get("DateTime") or event.get("Day")
            if not start_raw:
                continue
            start = datetime.fromisoformat(start_raw).replace(tzinfo=timezone.utc)
            if start > cutoff:
                continue

            games.append({
                "game_id": game_id,
                "sport": sport,
                "home_team": event.get("HomeTeamName") or event.get("HomeTeam"),
                "away_team": event.get("AwayTeamName") or event.get("AwayTeam"),
                "start_time": start.isoformat(),
            })
            seen_ids.add(game_id)

    return games


def get_game_result(game_id: str, sport: str = "nfl") -> dict | None:
    """
    Checks a single game's current state. Returns None if still in progress.
    Returns a result dict once the game is officially final:
        {"status": "final", "winner": "Cowboys", "loser": "Eagles", "home_score": 27, "away_score": 20}

    Trusts the Status field from SportsDataIO (e.g. "Final", "F/OT"), not
    just "score is higher" — that alone would misfire mid-game or in OT.
    """
    # SportsDataIO doesn't have a simple "get one game by ID" for every
    # sport, so we pull today's (and yesterday's, in case it's a late game
    # that finished after midnight UTC) slate and find the matching game.
    today = datetime.now(timezone.utc).date()
    for d in [today, today - timedelta(days=1)]:
        date_str = d.strftime("%Y-%b-%d").upper()
        try:
            events = _get(sport, f"GamesByDate/{date_str}")
        except requests.HTTPError:
            continue

        for event in events:
            event_id = str(event.get("GameID") or event.get("GameKey"))
            if event_id != str(game_id):
                continue

            status = (event.get("Status") or "").lower()

            if status in ("postponed", "canceled", "suspended"):
                return {"status": "postponed"}

            if not status.startswith("final") and status != "f/ot":
                return None  # scheduled, in progress, halftime, etc.

            home_score = event.get("HomeScore")
            away_score = event.get("AwayScore")
            if home_score is None or away_score is None:
                return None

            if home_score == away_score:
                return {"status": "tie"}

            home_name = event.get("HomeTeamName") or event.get("HomeTeam")
            away_name = event.get("AwayTeamName") or event.get("AwayTeam")

            if home_score > away_score:
                winner, loser = home_name, away_name
            else:
                winner, loser = away_name, home_name

            return {
                "status": "final",
                "winner": winner,
                "loser": loser,
                "home_score": home_score,
                "away_score": away_score,
            }

    return None  # game not found in today/yesterday's slate — check again next run


def get_game_summary(game_id: str, sport: str = "nfl") -> dict:
    """
    Pulls the real details of a finished game — final score, plus whatever
    box-score-level detail SportsDataIO's core Scores feed includes. This
    is the raw material fed to the AI so the auto-generated roast
    references real things that actually happened, not generic filler.

    NOTE: SportsDataIO's core Scores API is stats-focused, not narrative —
    it won't hand you an editorial headline like "missed the game-winning
    shot" the way ESPN's summary endpoint did. That kind of narrative
    detail lives in SportsDataIO's separate News/editorial feed, which may
    need its own subscription check. For now, this builds facts from the
    box score (final score, quarter-by-quarter if available) — solid,
    verifiable material, just less colorful than a news headline would be.

    Returns a dict with a "key_facts" list of plain-English strings ready
    to hand to the trash talk generator.
    """
    today = datetime.now(timezone.utc).date()
    key_facts = []

    for d in [today, today - timedelta(days=1)]:
        date_str = d.strftime("%Y-%b-%d").upper()
        try:
            events = _get(sport, f"GamesByDate/{date_str}")
        except requests.HTTPError:
            continue

        for event in events:
            event_id = str(event.get("GameID") or event.get("GameKey"))
            if event_id != str(game_id):
                continue

            home_name = event.get("HomeTeamName") or event.get("HomeTeam")
            away_name = event.get("AwayTeamName") or event.get("AwayTeam")
            home_score = event.get("HomeScore")
            away_score = event.get("AwayScore")

            if home_score is not None and away_score is not None:
                key_facts.append(f"Final score: {home_name} {home_score} - {away_name} {away_score}")

            # Quarter/period-by-period breakdown, if present — useful for
            # referencing things like a blown lead or a late collapse
            quarters = event.get("Quarters") or event.get("Periods")
            if quarters:
                home_line = "-".join(str(q.get("HomeScore", "")) for q in quarters)
                away_line = "-".join(str(q.get("AwayScore", "")) for q in quarters)
                if home_line and away_line:
                    key_facts.append(f"Period-by-period — {home_name}: {home_line} | {away_name}: {away_line}")

            return {"key_facts": key_facts}

    return {"key_facts": key_facts}
