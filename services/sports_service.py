import os
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from services import team_aliases

# US sports leagues organize games by the date they're played in US time,
# not UTC. Using raw UTC "today" caused a real bug: in the evening on the
# US east coast (after ~8PM EDT / 7PM EST), it's already past midnight
# UTC, so UTC "today" is actually tomorrow relative to the US — meaning
# live games happening RIGHT NOW would silently vanish from search
# results, since the wrong date bucket was being queried entirely.
_US_EASTERN = ZoneInfo("America/New_York")


def _today_us_eastern():
    return datetime.now(_US_EASTERN).date()


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
    "ncaaf": "cfb",       # SportsDataIO uses "cfb" for college football
    "ncaab": "cbb",       # college basketball
    "wnba": "wnba",
    "ncaawb": "cwbb",     # college women's basketball — "wbb" returned 404, trying this instead
    "soccer": "soccer",   # note: soccer may need a competition/league ID param — flagged for testing
}

BASE = "https://api.sportsdata.io/v3"


def _api_key() -> str:
    return os.environ["SPORTSDATA_API_KEY"]


def _get(sport: str, endpoint: str) -> dict | list:
    path = SPORT_PATHS[sport]

    if sport == "soccer":
        # Soccer is on API v4 (not v3) — endpoint string is built by the
        # caller to already include the competition ID in the right spot
        # (GamesByDate/{competition}/{date}), since that ordering differs
        # from every other sport here.
        url = f"https://api.sportsdata.io/v4/soccer/scores/json/{endpoint}"
    else:
        url = f"{BASE}/{path}/scores/json/{endpoint}"

    resp = requests.get(url, params={"key": _api_key()}, timeout=10)
    print(f"[sportsdata] GET {url} -> {resp.status_code}, body starts: {resp.text[:300]!r}")
    resp.raise_for_status()
    return resp.json()


# The free trial only grants soccer access to the UEFA Champions League.
# MLS, Premier League, etc. require upgrading past the trial. Searches for
# non-Champions-League teams (like LA Galaxy, an MLS team) won't return
# results right now — not a bug, just outside what this plan includes.
SOCCER_TRIAL_COMPETITION_ID = 3


def _games_by_date_endpoint(sport: str, date_str: str) -> str:
    """Builds the correct GamesByDate path — soccer needs the competition ID inserted before the date."""
    if sport == "soccer":
        return f"GamesByDate/{SOCCER_TRIAL_COMPETITION_ID}/{date_str}"
    return f"GamesByDate/{date_str}"


def get_upcoming_games(sport: str = "nfl", hours_ahead: int = 48, team_query: str = None) -> list[dict]:
    """
    Returns games kicking off within the given window — powers the
    "load a smackagram" game picker, which only shows games inside 48h.

    If team_query is given, only returns games involving a team matching
    that search (checked against SportsDataIO's raw code plus known city/
    nickname aliases — see team_aliases.py — so "yankees" or "New York
    Yankees" both correctly match "NYY").

    SportsDataIO's GamesByDate takes a single date, not a range, so we
    query today and tomorrow (covers a 48h window) and filter by the
    actual kickoff time.
    """
    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    today = _today_us_eastern()
    dates_to_check = [today, today + timedelta(days=1), today + timedelta(days=2)]

    games = []
    seen_ids = set()

    for d in dates_to_check:
        date_str = d.strftime("%Y-%b-%d").upper()  # SportsDataIO's expected format, e.g. 2026-SEP-10
        try:
            events = _get(sport, _games_by_date_endpoint(sport, date_str))
        except requests.HTTPError as e:
            print(f"[sportsdata] HTTPError for {sport} {date_str}: {e}")
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

            status = event.get("Status", "")
            home_score = event.get("HomeScore") if event.get("HomeScore") is not None else event.get("HomeTeamRuns")
            away_score = event.get("AwayScore") if event.get("AwayScore") is not None else event.get("AwayTeamRuns")

            home_code = event.get("HomeTeam") or ""
            away_code = event.get("AwayTeam") or ""

            if team_query:
                if not (team_aliases.matches_search(sport, home_code, team_query)
                        or team_aliases.matches_search(sport, away_code, team_query)):
                    continue

            # Human-readable "where things stand" string for in-progress
            # games — differs by sport (innings vs quarters vs periods)
            period_display = None
            if status.lower() == "inprogress":
                if sport == "mlb":
                    inning = event.get("Inning")
                    half = event.get("InningHalf")
                    if inning:
                        half_word = "Top" if half == "T" else "Bottom" if half == "B" else ""
                        period_display = f"{half_word} {inning}".strip()
                elif sport == "nhl":
                    period = event.get("Period")
                    if period:
                        period_display = f"Period {period}"
                else:
                    quarter = event.get("Quarter") or event.get("Period")
                    if quarter:
                        period_display = f"Q{quarter}" if str(quarter).isdigit() else str(quarter)

            games.append({
                "game_id": game_id,
                "sport": sport,
                "home_team": event.get("HomeTeamName") or team_aliases.get_display_name(sport, home_code),
                "away_team": event.get("AwayTeamName") or team_aliases.get_display_name(sport, away_code),
                "home_team_code": home_code,
                "away_team_code": away_code,
                "start_time": start.isoformat(),
                "status": status,
                "is_live": status.lower() == "inprogress",
                "home_score": home_score,
                "away_score": away_score,
                "period_display": period_display,
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
    today = _today_us_eastern()
    checked_dates = []
    for d in [today, today - timedelta(days=1)]:
        checked_dates.append(d.strftime("%Y-%b-%d").upper())
        date_str = d.strftime("%Y-%b-%d").upper()
        try:
            events = _get(sport, _games_by_date_endpoint(sport, date_str))
        except requests.HTTPError as e:
            print(f"[sportsdata] HTTPError for {sport} {date_str}: {e}")
            continue

        for event in events:
            event_id = str(event.get("GameID") or event.get("GameKey"))
            if event_id != str(game_id):
                continue

            status = (event.get("Status") or "").lower()

            if status in ("postponed", "canceled", "suspended"):
                return {"status": "postponed"}

            if not status.startswith("final") and status != "f/ot":
                # Log the actual status. Without this, "waiting for the feed to
                # mark it final" and "we never found the game at all" both look
                # like silence, and they need completely different fixes.
                print(f"[sportsdata] game {game_id} ({sport}) found, status={status!r} — not final yet")
                return None

            # SportsDataIO uses different score field names per sport
            # (e.g. MLB uses HomeTeamRuns/AwayTeamRuns, not HomeScore/
            # AwayScore) — this was a real bug: assuming one fixed field
            # name meant scores always came back None for MLB, so a
            # "Final" game was silently treated as "still in progress"
            # forever. Try every known variant instead.
            home_score = (
                event.get("HomeScore")
                if event.get("HomeScore") is not None
                else event.get("HomeTeamRuns")
                if event.get("HomeTeamRuns") is not None
                else event.get("HomeTeamScore")
                if event.get("HomeTeamScore") is not None
                else event.get("HomePoints")
            )
            away_score = (
                event.get("AwayScore")
                if event.get("AwayScore") is not None
                else event.get("AwayTeamRuns")
                if event.get("AwayTeamRuns") is not None
                else event.get("AwayTeamScore")
                if event.get("AwayTeamScore") is not None
                else event.get("AwayPoints")
            )
            if home_score is None or away_score is None:
                # Final, but no readable score - means SportsDataIO used a field
                # name we don't know for this sport. Previously silent, and it
                # looked exactly like a game still in progress.
                print(f"[sportsdata] game {game_id} ({sport}) is FINAL but no score field matched. "
                      f"Available keys: {sorted(event.keys())}")
                return None

            if home_score == away_score:
                return {"status": "tie"}

            home_name = event.get("HomeTeamName") or team_aliases.get_display_name(sport, event.get("HomeTeam", ""))
            away_name = event.get("AwayTeamName") or team_aliases.get_display_name(sport, event.get("AwayTeam", ""))

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


    # Fell through every slate without matching the id. This is NOT the same as
    # "still in progress" - it means the armed record points at a game the feed
    # isn't returning, and it will wait forever. Worth shouting about.
    print(f"[sportsdata] game {game_id} ({sport}) NOT FOUND in slates for {checked_dates} — "
          f"armed smackagrams on this game will never fire until this resolves")
    return None


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
    today = _today_us_eastern()
    key_facts = []

    for d in [today, today - timedelta(days=1)]:
        date_str = d.strftime("%Y-%b-%d").upper()
        try:
            events = _get(sport, _games_by_date_endpoint(sport, date_str))
        except requests.HTTPError as e:
            print(f"[sportsdata] HTTPError for {sport} {date_str}: {e}")
            continue

        for event in events:
            event_id = str(event.get("GameID") or event.get("GameKey"))
            if event_id != str(game_id):
                continue

            home_name = event.get("HomeTeamName") or team_aliases.get_display_name(sport, event.get("HomeTeam", ""))
            away_name = event.get("AwayTeamName") or team_aliases.get_display_name(sport, event.get("AwayTeam", ""))
            home_score = (
                event.get("HomeScore")
                if event.get("HomeScore") is not None
                else event.get("HomeTeamRuns")
                if event.get("HomeTeamRuns") is not None
                else event.get("HomeTeamScore")
                if event.get("HomeTeamScore") is not None
                else event.get("HomePoints")
            )
            away_score = (
                event.get("AwayScore")
                if event.get("AwayScore") is not None
                else event.get("AwayTeamRuns")
                if event.get("AwayTeamRuns") is not None
                else event.get("AwayTeamScore")
                if event.get("AwayTeamScore") is not None
                else event.get("AwayPoints")
            )

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


def get_all_teams(sport: str) -> list[dict]:
    """
    Pulls SportsDataIO's Teams reference endpoint — the ground-truth list
    of every real team code + name for a sport. Not used anywhere in the
    live app; exists purely as a one-time validation tool to check our
    hand-built TEAM_ALIASES/DISPLAY_NAMES tables (in team_aliases.py)
    against SportsDataIO's actual codes, since a mismatch there (like the
    White Sox being filed under "CWS" when SportsDataIO actually uses
    "CHW") silently breaks search/display for that team with no error.
    """
    path = SPORT_PATHS[sport]
    if sport == "soccer":
        # Soccer lives on API v4, not v3 like every other sport here, and
        # SportsDataIO's docs confirm soccer endpoints are competition-
        # scoped (same pattern GamesByDate already needs) — the plain
        # /Teams attempt correctly 404'd, confirming it needs the
        # competition ID. Back to that version, now with real error
        # surfacing in place if this guess is still not quite right.
        url = f"https://api.sportsdata.io/v4/soccer/scores/json/Teams/{SOCCER_TRIAL_COMPETITION_ID}"
    else:
        url = f"{BASE}/{path}/scores/json/Teams"
    resp = requests.get(url, params={"key": _api_key()}, timeout=15)
    resp.raise_for_status()
    return resp.json()


# THE LEAGUES AUTO-SMACK MAY ACCEPT MONEY FOR.
#
# An armed smackagram is a promise: "when this game ends, the call
# fires." That promise is only keepable for leagues the result
# resolvers can actually answer for. Soccer/MLS is deliberately
# absent - SportsDataIO's free tier covers Champions League only,
# and no other source carries it - so an MLS order would sit armed
# forever, silently, and turn into a refund and an angry customer.
# Add a league here ONLY once a result source demonstrably covers it.
AUTO_SMACK_SPORTS = {
    "mlb",      # statsapi + highlightly + balldontlie + sportsdataio
    "wnba",     # balldontlie + highlightly + sportsdataio
    "nba",      # three sources
    "nfl",      # three sources
    "nhl",      # highlightly + sportsdataio
    "ncaaf",    # highlightly + sportsdataio
    "ncaab",    # three sources
    "ncaawb",   # sportsdataio only - single-source, watch it in season
}
