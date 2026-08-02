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

    loser_team = (out.get("loser") or {}).get("team")
    out["bad_nights"] = _bad_nights(d, loser_team, lg)
    if lg == "mlb":
        out["losing_pitcher"] = _losing_pitcher(d, loser_team)
        out["top_order"] = _top_order_collapse(d, loser_team)
        out["team_offense"] = _team_offense(d, loser_team)
        win_team = (out.get("winner") or {}).get("team")
        out["pitchers"] = evaluate_pitchers(d, loser_team, win_team)
        out["season_swings"] = season_vs_tonight(d, loser_team, win_team)
    out.update(_collapse(d, out.get("loser") or {}))
    return out


_BAD_NIGHT_RULES = {
    "mlb":  [("H-AB", "hitless", None, "{n} for {d}"), ("K", ">=", 3, "struck out {v} times")],
    "nba":  [("TO", ">=", 4, "{v} turnovers"), ("PTS", "<=", 2, "{v} points")],
    "wnba": [("TO", ">=", 4, "{v} turnovers"), ("PTS", "<=", 2, "{v} points")],
    "nfl":  [("INT", ">=", 2, "{v} interceptions"), ("FUM", ">=", 2, "{v} fumbles")],
    "nhl":  [("+/-", "<=", -2, "a minus {v} night")],
}


def _is_principal(ath, league):
    """
    Is this somebody worth roasting?

    The eight-hole hitter going 0 for 4 is a Tuesday. The three-hitter going
    0 for 4 is the story. Every sport has a signal for "this is one of your
    guys" and it is the difference between material and noise.
    """
    order = ath.get("batOrder")
    if league in ("mlb",):
        try:
            return order is not None and 1 <= int(order) <= 5
        except (TypeError, ValueError):
            return False
    # Everywhere else, a starter is the bar.
    return bool(ath.get("starter"))


def _bad_nights(d, losing_team, league):
    """Named players on the LOSING side who stunk. Only the losing team -
    roasting the winner's stars is not the product - and only the players
    who were supposed to be good."""
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
                if not _is_principal(ath, league):
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

    # Pitching, both sides. A quality start is six innings and three earned
    # or fewer - anything well short of that is a bad outing, and the RATE
    # matters more than the raw number: two innings and five earned is far
    # worse than six and five, even though the second line looks uglier.
    pit = detail.get("pitchers") or {}
    for p in (pit.get("losing_side") or []):
        if p.get("starter"):
            bits = [f"{p['innings']} innings"] if p.get("innings") else []
            if p.get("earned") is not None:
                bits.append(f"{p['earned']} earned")
            if p.get("hits"):
                bits.append(f"{p['hits']} hits")
            f.append(f"starting pitcher {p['name']} " +
                     ("was shelled" if p.get("shelled") else "took the loss") +
                     (" - " + ", ".join(bits) if bits else ""))
            if p.get("chased"):
                f.append(f"{p['name']} did not survive the third")
            elif p.get("short_outing"):
                f.append(f"{p['name']} was pulled before the fifth - no quality start")
            if p.get("season_era"):
                f.append(f"{p['name']} carries a {p['season_era']} ERA")
        elif p.get("arsonist"):
            f.append(f"reliever {p['name']} gave up {p['earned']} more "
                     f"in {p['innings']} innings")

    # The opposing starter cruising is its own insult.
    for p in (pit.get("winning_side") or []):
        if p.get("starter") and p.get("quality_start"):
            f.append(f"their starter {p['name']} went {p['innings']} innings "
                     f"and gave up {p['earned']} - a quality start, comfortable")
            break

    # Season versus tonight. Losing to a man batting .190 who picked today
    # to remember how is the sharpest line available.
    sw = detail.get("season_swings") or {}
    for e in (sw.get("overperformed") or [])[:2]:
        tag = " - barely above the Mendoza line" if e.get("mendoza") else ""
        f.append(f"{e['name']} went {e['hits']} for {e['at_bats']} against you "
                 f"while hitting {e['season_avg']} on the season{tag}")
    for e in (sw.get("underperformed") or [])[:2]:
        f.append(f"{e['name']} hits {e['season_avg']} and went "
                 f"{e['hits']} for {e['at_bats']} when it mattered")

    # The starting pitcher who wore it. In baseball this is the single best
    # target on the list - he lost the game and the box score says how.
    lp = detail.get("losing_pitcher")
    if lp and lp.get("name"):
        bits = []
        if lp.get("innings"):
            bits.append(f"{lp['innings']} innings")
        if lp.get("earned"):
            bits.append(f"{lp['earned']} earned")
        if lp.get("hits"):
            bits.append(f"{lp['hits']} hits")
        if lp.get("homers") and _to_num(lp["homers"]):
            bits.append(f"{lp['homers']} home runs")
        line = ", ".join(bits)
        f.append(f"starting pitcher {lp['name']} took the loss"
                 + (f" - {line}" if line else ""))
        if lp.get("chased"):
            f.append(f"{lp['name']} did not survive the third - pulled early")
        elif lp.get("short_outing"):
            f.append(f"{lp['name']} was pulled before the fifth")

    # What the WHOLE lineup managed. A team with three hits all night is a
    # better roast than any one player - nine men failing together.
    off = detail.get("team_offense") or {}
    if off.get("one_hit"):
        f.append(f"the entire team managed {off['hits']} hit all night")
    elif off.get("shut_down"):
        f.append(f"the entire team managed {off['hits']} hits all night")
    if off.get("shut_out"):
        f.append("shut out - did not score at all")
    if off.get("struck_out_a_lot"):
        f.append(f"struck out {off['strikeouts']} times as a team")
    if off.get("stranded_runners"):
        f.append(f"left {off['left_on_base']} runners on base")
    if off.get("errors"):
        f.append(f"{off['errors']} errors in the field")

    # Whole top of the order going quiet beats any single bad line.
    to = detail.get("top_order")
    if to:
        f.append(f"{to['count']} of the top {to['of']} hitters were held hitless - "
                 f"the entire heart of the order")

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


def _ip_to_outs(ip):
    """
    Baseball writes innings as 5.2 meaning five and TWO THIRDS, not five
    point two. Treating it as a decimal quietly understates every partial
    inning, so it is converted to outs and back.
    """
    n = _to_num(ip)
    if n is None:
        return None
    whole = int(n)
    frac = round((n - whole) * 10)
    if frac not in (0, 1, 2):
        return whole * 3          # unexpected format, keep the whole innings
    return whole * 3 + frac


def _outs_to_innings(outs):
    if outs is None:
        return None
    return outs / 3.0


def evaluate_pitchers(d, losing_team, winning_team):
    """
    Every pitcher who threw, both sides, rated on what they actually did.

    A quality start is the real benchmark - six innings or more with three
    earned runs or fewer. Anything well short of that is a bad outing, and
    two innings with five earned is a disaster regardless of who won.

    Relievers count. A bullpen arsonist who torched a lead in the eighth is
    better material than the starter who left with the game tied.
    """
    out = {"losing_side": [], "winning_side": []}

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() == str(losing_team or "").lower():
            bucket = "losing_side"
        elif nick.lower() == str(winning_team or "").lower():
            bucket = "winning_side"
        else:
            continue

        for group in (block.get("statistics") or []):
            gname = (group.get("name") or group.get("type") or "").lower()
            if "pitch" not in gname:
                continue
            labels = group.get("labels") or []
            for idx, ath in enumerate(group.get("athletes") or []):
                person = ath.get("athlete") or {}
                name = person.get("displayName") or person.get("shortName")
                if not name:
                    continue
                st = _stat_map(labels, ath.get("stats") or [])

                def pick(*names):
                    for n in names:
                        if n in st and st[n] not in (None, "", "-"):
                            return st[n]
                    return None

                outs = _ip_to_outs(pick("IP"))
                er = _to_num(pick("ER"))
                runs = _to_num(pick("R"))
                hits = _to_num(pick("H"))
                walks = _to_num(pick("BB"))
                ks = _to_num(pick("K", "SO"))
                hr = _to_num(pick("HR"))
                era = pick("ERA")

                if outs is None:
                    continue
                innings = _outs_to_innings(outs)
                earned = er if er is not None else runs

                entry = {
                    "name": name,
                    "starter": idx == 0,
                    "innings": pick("IP"),
                    "innings_num": round(innings, 2),
                    "earned": int(earned) if earned is not None else None,
                    "hits": int(hits) if hits is not None else None,
                    "walks": int(walks) if walks is not None else None,
                    "strikeouts": int(ks) if ks is not None else None,
                    "homers": int(hr) if hr is not None else None,
                    "season_era": era,
                }

                # The real benchmark. Six innings, three earned or fewer.
                if idx == 0 and earned is not None:
                    entry["quality_start"] = innings >= 6.0 and earned <= 3
                    entry["missed_quality"] = not entry["quality_start"]

                # Rate matters more than the raw number. Two innings and five
                # earned is far worse than six innings and five earned, even
                # though the second one looks worse on the line.
                if earned is not None and innings > 0:
                    rate = earned / innings
                    entry["er_per_inning"] = round(rate, 2)
                    entry["shelled"] = rate >= 2.0 and earned >= 3
                    entry["rough"] = rate >= 1.0 and earned >= 3

                if idx == 0:
                    entry["chased"] = innings < 3.0
                    entry["short_outing"] = innings < 5.0
                else:
                    # A reliever giving up runs at all is worth naming.
                    entry["arsonist"] = bool(earned and earned >= 2)

                out[bucket].append(entry)

    return out


def season_vs_tonight(d, losing_team, winning_team):
    """
    Who played wildly out of character, either way.

    The sharpest roast available is a nobody having a career night against
    you - a man hitting .190 who picked today to remember how. The box score
    carries the season average alongside the game line, so this is two
    numbers compared, not a new lookup.
    """
    found = {"overperformed": [], "underperformed": []}

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        side = ("winning" if nick.lower() == str(winning_team or "").lower()
                else "losing" if nick.lower() == str(losing_team or "").lower()
                else None)
        if not side:
            continue

        for group in (block.get("statistics") or []):
            gname = (group.get("name") or group.get("type") or "").lower()
            if "bat" not in gname:
                continue
            labels = group.get("labels") or []
            for ath in (group.get("athletes") or []):
                person = ath.get("athlete") or {}
                name = person.get("displayName") or person.get("shortName")
                if not name:
                    continue
                st = _stat_map(labels, ath.get("stats") or [])

                avg = _to_num(st.get("AVG"))
                hab = st.get("H-AB")
                if avg is None or not hab:
                    continue
                try:
                    hits, ab = (int(x) for x in str(hab).split("-"))
                except (ValueError, AttributeError):
                    continue
                if ab < 2:
                    continue

                entry = {"name": name, "hits": hits, "at_bats": ab,
                         "season_avg": st.get("AVG"),
                         "team": nick, "side": side}

                # A weak hitter having a big night, on the winning side.
                # This is the material: you lost to a man batting .190.
                if side == "winning" and hits >= 2 and avg < 0.230:
                    entry["mendoza"] = avg < 0.200
                    found["overperformed"].append(entry)

                # One of your good hitters disappearing.
                if side == "losing" and hits == 0 and ab >= 3 and avg >= 0.270:
                    found["underperformed"].append(entry)

    return found


def find_event_id(league: str, home_team: str, away_team: str,
                  days_back: int = 1) -> str | None:
    """
    Find ESPN's id for a game by TEAMS AND DATE rather than by id.

    The two services do not share ids: a Locked & Loaded smackagram stores
    SportsDataIO's GameID, which will never resolve against ESPN. Matching on
    who played and when is the only bridge, and it is done at fire time
    rather than arm time because a game armed three days out may not exist in
    ESPN's scoreboard yet.

    Matches on nicknames, which are unambiguous - abbreviations are not, and
    matching those against anything is how "BAL" started matching "ball".
    """
    if not (home_team or away_team):
        return None

    def norm(x):
        return "".join(ch for ch in str(x or "").lower() if ch.isalnum())

    want = {norm(home_team), norm(away_team)} - {""}
    if not want:
        return None

    for back in range(days_back, days_back + 2):   # allow a day either side
        try:
            for g in fetch_finals(league, days_back=back):
                got = {norm(g.get("home_nick")), norm(g.get("away_nick")),
                       norm(g.get("home_city")), norm(g.get("away_city"))} - {""}
                # Both teams must be recognisable in the same game.
                if len(want & got) >= 2 and g.get("espn_id"):
                    return str(g["espn_id"])
        except Exception as e:
            print(f"[espn] event lookup failed ({league}, back={back}): {e}", flush=True)
    return None


def _losing_pitcher(d, losing_team):
    """
    The starter who wore the loss, and how early he was pulled.

    Written to read whatever labels come back rather than assume them - the
    probe only sampled the batting group, so the pitching column names are
    not confirmed. Anything it cannot find is simply absent instead of
    guessed at.
    """
    if not losing_team:
        return None

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team).lower():
            continue

        for group in (block.get("statistics") or []):
            gname = (group.get("name") or group.get("type") or "").lower()
            if "pitch" not in gname:
                continue
            labels = group.get("labels") or []
            athletes = group.get("athletes") or []
            if not athletes:
                continue

            # The starter is listed first in ESPN's pitching group.
            starter = athletes[0]
            person = starter.get("athlete") or {}
            name = person.get("displayName") or person.get("shortName")
            if not name:
                return None

            stats = _stat_map(labels, starter.get("stats") or [])

            def pick(*names):
                for n in names:
                    if n in stats and stats[n] not in (None, "", "-"):
                        return stats[n]
                return None

            innings = pick("IP")
            earned = pick("ER")
            runs = pick("R")
            hits = pick("H")
            walks = pick("BB")
            homers = pick("HR")

            out = {"name": name, "innings": innings, "earned": earned,
                   "runs": runs, "hits": hits, "walks": walks, "homers": homers}

            # How early did he get the hook? Anything under five is short,
            # under three is a genuine hiding.
            ip = _to_num(innings)
            if ip is not None:
                out["ip_num"] = ip
                out["short_outing"] = ip < 5.0
                out["chased"] = ip < 3.0
            return out
    return None


def _top_order_collapse(d, losing_team):
    """
    Did the whole top of the order go quiet? Four guys each going 0 for 4 is
    a better line than any one of them individually - it stops being a bad
    night and becomes a team-wide failure.
    """
    if not losing_team:
        return None

    hitless, total = [], 0
    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team).lower():
            continue
        for group in (block.get("statistics") or []):
            gname = (group.get("name") or group.get("type") or "").lower()
            if "bat" not in gname:
                continue
            labels = group.get("labels") or []
            for ath in (group.get("athletes") or []):
                order = ath.get("batOrder")
                try:
                    spot = int(order)
                except (TypeError, ValueError):
                    continue
                if not 1 <= spot <= 5:
                    continue
                total += 1
                stats = _stat_map(labels, ath.get("stats") or [])
                hab = stats.get("H-AB")
                if not hab:
                    continue
                try:
                    h, ab = str(hab).split("-")
                    if int(h) == 0 and int(ab) >= 3:
                        hitless.append(spot)
                except ValueError:
                    pass

    if total >= 4 and len(hitless) >= 3:
        return {"count": len(hitless), "of": total, "spots": sorted(hitless)}
    return None


def _team_offense(d, losing_team):
    """
    What the whole lineup managed, not just the good hitters.

    A team getting three hits all night is a better roast than any individual
    line - it stops being one guy's bad day and becomes nine men failing
    together. Read from the team totals block rather than by adding up
    players, since ESPN already does that sum and doing it again invites
    disagreement with the official line.
    """
    if not losing_team:
        return None

    for block in ((d.get("boxscore") or {}).get("teams") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team).lower():
            continue

        vals = {}
        for stat in (block.get("statistics") or []):
            key = (stat.get("name") or stat.get("abbreviation") or "").strip().lower()
            v = stat.get("displayValue")
            if key and v not in (None, ""):
                vals[key] = v

        def pick(*names):
            for n in names:
                if n in vals:
                    return vals[n]
            return None

        hits = _to_num(pick("hits", "h"))
        runs = _to_num(pick("runs", "r"))
        ks = _to_num(pick("strikeouts", "so", "k"))
        lob = _to_num(pick("leftonbase", "lob"))
        errors = _to_num(pick("errors", "e"))

        out = {}
        if hits is not None:
            out["hits"] = int(hits)
            # Three or fewer is a genuinely bad night for a whole lineup.
            out["shut_down"] = hits <= 3
            out["one_hit"] = hits <= 1
        if runs is not None:
            out["runs"] = int(runs)
            out["shut_out"] = runs == 0
        if ks is not None:
            out["strikeouts"] = int(ks)
            out["struck_out_a_lot"] = ks >= 12
        if lob is not None:
            out["left_on_base"] = int(lob)
            out["stranded_runners"] = lob >= 9
        if errors is not None and errors >= 2:
            out["errors"] = int(errors)
        return out or None
    return None
