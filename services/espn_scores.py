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
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

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

    day = datetime.now(EASTERN) - timedelta(days=days_back)
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

        h_team = home.get("team") or {}
        a_team = away.get("team") or {}
        h_name = h_team.get("abbreviation") or ""
        a_name = a_team.get("abbreviation") or ""

        # Nickname and city kept ALONGSIDE the abbreviation, not instead of
        # it - the prompt and fact lines already use the abbreviations and
        # changing them would change what the show says.
        #
        # These exist because the abbreviations are useless for working out
        # what a segment is ABOUT. Matching three-letter codes against prose
        # is a disaster: BAL matches "ball", PIT matches "pitcher", SEA
        # matches "season", COL matches "Colorado" and "collapse", MIN
        # matches "minutes". Every segment contains one of those, so every
        # segment looked like baseball. "Orioles" and "Baltimore" do not
        # have that problem.
        h_nick = h_team.get("shortDisplayName") or h_team.get("name") or ""
        a_nick = a_team.get("shortDisplayName") or a_team.get("name") or ""
        h_city = h_team.get("location") or ""
        a_city = a_team.get("location") or ''
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
            "espn_id": e.get("id"),
            "home": h_name, "away": a_name,
            "home_nick": h_nick, "away_nick": a_nick,
            "home_city": h_city, "away_city": a_city,
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



LANDMARK_VENUES = {
    "wrigley field": "Wrigley",
    "fenway park": "Fenway",
    "yankee stadium": "Yankee Stadium",
    "dodger stadium": "Dodger Stadium",
    "lambeau field": "Lambeau",
    "soldier field": "Soldier Field",
    "arrowhead stadium": "Arrowhead",
    "gillette stadium": "Gillette",
    "madison square garden": "the Garden",
    "oracle arena": "Oracle",
    "td garden": "TD Garden",
}
VENUE_LEAGUES = {"mlb", "nfl", "nba"}


def _stat_map(labels, values):
    """Zip labels to values rather than reading fixed positions - hardcoding
    index 7 for strikeouts works until ESPN reorders the columns, and then it
    silently reports the wrong number."""
    return {str(l).strip().upper(): v for l, v in zip(labels or [], values or [])}


def _to_num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def fetch_game_detail(league: str, event_id: str) -> dict:
    """Everything needed to roast a specific game. Returns {} on failure - a
    call must still fire with the plain result rather than not firing."""
    import json as _json
    from urllib.request import Request, urlopen

    lg = (league or "").lower()
    path = LEAGUE_PATHS.get(lg)
    if not path or not event_id:
        return {}
    sport, slug = path[0], path[1]

    url = f"{BASE}/{sport}/{slug}/summary?event={event_id}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as r:
            d = _json.load(r)
    except Exception as e:
        print(f"[espn] game detail failed for {league}/{event_id}: {e}", flush=True)
        return {}

    out = {"league": path[2], "event_id": str(event_id)}

    gi = d.get("gameInfo") or {}
    venue_full = ((gi.get("venue") or {}).get("fullName") or "").strip()
    if lg in VENUE_LEAGUES:
        out["venue"] = LANDMARK_VENUES.get(venue_full.lower())
    out["attendance"] = gi.get("attendance")
    out["duration"] = gi.get("gameDuration")

    comp = ((d.get("header") or {}).get("competitions") or [{}])[0]
    for side in (comp.get("competitors") or []):
        team = side.get("team") or {}
        nick = team.get("name") or team.get("shortDisplayName") or ""
        score = _to_num(side.get("score"))
        rec = ""
        for r in (side.get("record") or []):
            if r.get("type") in ("total", "overall") or not rec:
                rec = r.get("summary") or rec
        entry = {"team": nick, "score": score, "record": rec,
                 "home": side.get("homeAway") == "home"}
        if str(side.get("winner")).lower() == "true" or side.get("winner") is True:
            out["winner"] = entry
        else:
            out["loser"] = entry

    if out.get("winner") and out.get("loser"):
        w, l = out["winner"].get("score"), out["loser"].get("score")
        if w is not None and l is not None:
            out["margin"] = int(abs(w - l))
            out["one_run"] = out["margin"] <= 1
    out["lost_at_home"] = bool((out.get("loser") or {}).get("home"))

    out["bad_nights"] = _bad_nights(d, (out.get("loser") or {}).get("team"), lg)
    out.update(_collapse(d, out.get("loser") or {}))
    return out


_BAD_NIGHT_RULES = {
    "mlb":  [("H-AB", "hitless", None, "{n} for {d}"), ("K", ">=", 3, "struck out {v} times")],
    "nba":  [("TO", ">=", 4, "{v} turnovers"), ("PTS", "<=", 2, "{v} points")],
    "wnba": [("TO", ">=", 4, "{v} turnovers"), ("PTS", "<=", 2, "{v} points")],
    "nfl":  [("INT", ">=", 2, "{v} interceptions"), ("FUM", ">=", 2, "{v} fumbles")],
    "nhl":  [("+/-", "<=", -2, "a minus {v} night")],
}


def _bad_nights(d, losing_team, league):
    """Named players on the LOSING side who stunk. Only the losing team -
    roasting the winner's stars is not the product."""
    rules = _BAD_NIGHT_RULES.get(league) or []
    if not rules or not losing_team:
        return []

    found = []
    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team).lower():
            continue
        for group in (block.get("statistics") or []):
            labels = group.get("labels") or []
            for ath in (group.get("athletes") or []):
                person = (ath.get("athlete") or {})
                name = person.get("displayName") or person.get("shortName")
                if not name:
                    continue
                stats = _stat_map(labels, ath.get("stats") or [])
                for label, op, thresh, phrasing in rules:
                    raw = stats.get(label)
                    if raw in (None, "", "-"):
                        continue
                    if op == "hitless":
                        try:
                            hits, ab = str(raw).split("-")
                            if int(hits) == 0 and int(ab) >= 3:
                                found.append({"name": name,
                                              "line": phrasing.format(n=hits, d=ab),
                                              "spot": ath.get("batOrder"),
                                              "position": (ath.get("position") or {}).get("abbreviation")})
                        except (ValueError, AttributeError):
                            pass
                        continue
                    v = _to_num(raw)
                    if v is None:
                        continue
                    if (v >= thresh) if op == ">=" else (v <= thresh):
                        found.append({"name": name,
                                      "line": phrasing.format(v=int(abs(v))),
                                      "spot": ath.get("batOrder"),
                                      "position": (ath.get("position") or {}).get("abbreviation")})
    merged = {}
    for f in found:
        m = merged.setdefault(f["name"], {**f, "lines": []})
        m["lines"].append(f["line"])
    for m in merged.values():
        m["line"] = " and ".join(m.pop("lines"))
    return list(merged.values())[:3]


def _collapse(d, loser):
    """Was it thrown away, and were they favoured? The percentage NEVER
    reaches the call - it only decides whether there is a joke here."""
    out = {"was_favoured": False, "blew_it": False, "favoured_pct": None}
    wp = d.get("winprobability") or []
    if not wp or not loser:
        return out

    loser_is_home = bool(loser.get("home"))
    series = []
    for pt in wp:
        home = pt.get("homeWinPercentage")
        if home is None:
            continue
        series.append(home if loser_is_home else 1.0 - home)
    if not series:
        return out

    # The loser's line must END near zero. If it finishes high the series has
    # been read against the wrong side - a caught bug, not a hypothetical.
    if series[-1] > 0.15:
        return out

    peak = max(series)
    if peak >= 0.55:
        out["was_favoured"] = True
        out["favoured_pct"] = int(round(peak * 100))
    if peak >= 0.80:
        out["blew_it"] = True
    return out


def roast_facts(detail: dict) -> list:
    """The fact lines Smacky writes from, ordered by what they are worth."""
    if not detail:
        return []
    f = []
    w = detail.get("winner") or {}
    l = detail.get("loser") or {}

    if w.get("team") and l.get("team"):
        ws, ls = w.get("score"), l.get("score")
        if ws is not None and ls is not None:
            f.append(f"{w['team']} beat {l['team']} {int(ws)}-{int(ls)}")
        else:
            f.append(f"{w['team']} beat {l['team']}")
    if l.get("record"):
        f.append(f"{l['team']} are now {l['record']}")

    m = detail.get("margin")
    if detail.get("one_run"):
        f.append("lost it by a single run")
    elif m and m >= 10:
        f.append(f"lost by {m} - not close at any point")

    for b in (detail.get("bad_nights") or []):
        spot = f", batting {b['spot']}" if b.get("spot") else ""
        pos = f" ({b['position']})" if b.get("position") else ""
        f.append(f"{b['name']}{pos}{spot} went {b['line']}")

    if detail.get("blew_it"):
        f.append(f"the analytics people had {l.get('team','them')} at "
                 f"{detail.get('favoured_pct')}% and they still lost - a genuine collapse")
    elif detail.get("was_favoured"):
        f.append(f"the analytics people had {l.get('team','them')} favoured at "
                 f"{detail.get('favoured_pct')}% and they lost anyway")

    if detail.get("lost_at_home"):
        v, att = detail.get("venue"), detail.get("attendance")
        if v and att:
            f.append(f"lost at home at {v} in front of {att:,}")
        elif att:
            f.append(f"lost at home in front of {att:,}")
        else:
            f.append("lost at home")

    if detail.get("duration"):
        f.append(f"game took {detail['duration']}")
    return f
