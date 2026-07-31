"""
Real final scores, from ESPN's public scoreboard.

WHY NOT SPORTSDATAIO. Verified against ten MLB finals on 2026-07-30: every
winner was correct, every SCORE was wrong. Boston won 5-4; SportsDataIO
reported 13-11. Seattle lost by 4; it reported an 11-run margin. The
scrambling looks like a ~2.5-3x multiplier, which preserves ordering (so
Locked & Loaded, which only asks who lost, is unaffected) but destroys the
actual numbers.

That's fatal here, because margins ARE the content. A show announcing an
11-run beating that was a 4-run game loses its credibility in one sentence
to anyone who watched.

ESPN's scoreboard is free, keyless and returns real finals. It is also
UNOFFICIAL and undocumented - it can change or close without notice. The
failure mode is acceptable: yesterday's episode keeps playing, and the site
carries on. That's a better trade than confidently reporting invented scores.
"""

import requests
from datetime import datetime, timedelta

BASE = "https://site.api.espn.com/apis/site/v2/sports"

# ESPN groups leagues under a sport path.
LEAGUE_PATHS = {
    "mlb":  ("baseball", "mlb",       "MLB",  "runs"),
    "wnba": ("basketball", "wnba",    "WNBA", "points"),
    "nfl":  ("football", "nfl",       "NFL",  "points"),
    "nba":  ("basketball", "nba",     "NBA",  "points"),
    "nhl":  ("hockey", "nhl",         "NHL",  "goals"),
    "ncaaf": ("football", "college-football", "NCAAF", "points"),
    "ncaab": ("basketball", "mens-college-basketball", "NCAAB", "points"),
}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_finals(league: str, days_back: int = 1) -> list[dict]:
    """
    One league's finished games for a given day.

    Only returns games ESPN marks as completed - anything live or scheduled
    is skipped, since a show built at 6am should only discuss games that
    actually ended.
    """
    cfg = LEAGUE_PATHS.get(league)
    if not cfg:
        return []
    sport_path, league_path, label, unit = cfg

    day = datetime.utcnow() - timedelta(days=days_back)
    date_str = day.strftime("%Y%m%d")
    url = f"{BASE}/{sport_path}/{league_path}/scoreboard"

    try:
        resp = requests.get(url, params={"dates": date_str}, timeout=15)
        if resp.status_code != 200:
            print(f"[espn] {league} {date_str} -> HTTP {resp.status_code}")
            return []
        events = resp.json().get("events", []) or []
    except Exception as e:
        print(f"[espn] {league} fetch failed: {e}")
        return []

    games = []
    for e in events:
        comps = e.get("competitions") or []
        if not comps:
            continue
        c = comps[0]

        status = ((c.get("status") or {}).get("type") or {})
        if not status.get("completed"):
            continue

        sides = c.get("competitors") or []
        if len(sides) != 2:
            continue

        # ESPN orders competitors home-first.
        home = next((s for s in sides if s.get("homeAway") == "home"), sides[0])
        away = next((s for s in sides if s.get("homeAway") == "away"), sides[1])

        hs, as_ = _int(home.get("score")), _int(away.get("score"))
        if hs is None or as_ is None or hs == as_:
            continue

        h_name = (home.get("team") or {}).get("abbreviation") or ""
        a_name = (away.get("team") or {}).get("abbreviation") or ""
        winner, loser = (h_name, a_name) if hs > as_ else (a_name, h_name)

        # Records come through as "58-49" - the loser's gives the show a way
        # to say how bad the season has been, not just the night.
        loser_record = ""
        for s in sides:
            if (s.get("team") or {}).get("abbreviation") == loser:
                for r in (s.get("records") or []):
                    if r.get("type") in ("total", "overall"):
                        loser_record = r.get("summary", "")

        games.append({
            "league": label,
            "unit": unit,
            "home": h_name, "away": a_name,
            "home_score": hs, "away_score": as_,
            "winner": winner, "loser": loser,
            "margin": abs(hs - as_),
            "loser_at_home": hs < as_,
            "loser_record": loser_record,
            "periods": _int((c.get("status") or {}).get("period")),
            "notes": (c.get("notes") or [{}])[0].get("headline", "") if c.get("notes") else "",
            "date": date_str,
        })

    print(f"[espn] {league}: {len(games)} finals on {date_str}")
    return games


def fetch_news(league: str, limit: int = 12) -> list[dict]:
    """
    Headlines from ESPN's public news feed, same base URL as the scoreboard.

    Supporting material only. Scores remain the spine of the show - they're
    always there, never tragic, and now actually true. Headlines add the human
    texture a box score can't: a firing, a trade, a feud, a quote.

    The safety screen in news_service still applies to anything from here.
    """
    cfg = LEAGUE_PATHS.get(league)
    if not cfg:
        return []
    sport_path, league_path, label, _ = cfg

    url = f"{BASE}/{sport_path}/{league_path}/news"
    try:
        resp = requests.get(url, params={"limit": limit}, timeout=15)
        if resp.status_code != 200:
            print(f"[espn] {league} news -> HTTP {resp.status_code}")
            return []
        articles = resp.json().get("articles", []) or []
    except Exception as e:
        print(f"[espn] {league} news failed: {e}")
        return []

    out = []
    for a in articles:
        headline = (a.get("headline") or "").strip()
        if not headline:
            continue
        out.append({
            "league": label,
            "sport": league,
            "title": headline,
            "content": (a.get("description") or "").strip(),
            "published": a.get("published", ""),
            "source": "ESPN",
        })

    print(f"[espn] {league}: {len(out)} headlines")
    return out
