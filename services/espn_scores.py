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
    "ncaaw": ("basketball", "womens-college-basketball", "NCAAW", "points"),
    "ncaabb": ("baseball", "college-baseball", "NCAABB", "runs"),
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

    # Through the gate. This is the show's main scoreboard call - one per
    # league every morning - and it is the one that must not be the thing
    # that trips a block, because without it there is no show at all.
    from services import espn_gate
    d = espn_gate.get(url, params={"dates": date_str}, timeout=12,
                      label=f"finals {league}")
    if not d:
        return []
    events = d.get("events", []) or []

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
        # SPEAKABLE names, not abbreviations.
        #
        # These went out as h_name, which is ESPN's "abbreviation" - so the
        # writer was handed "PIT" and "BAL" and the voice read them as
        # letters. A listener heard "P I T" instead of "Pittsburgh".
        #
        # The nickname is what a human actually says; the city is the
        # fallback for the rare team whose short name is missing.
        h_say = h_nick or h_city or h_name
        a_say = a_nick or a_city or a_name
        winner, loser = (h_say, a_say) if hs > as_ else (a_say, h_say)

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
    from services import espn_gate
    d = espn_gate.get(url, params={"limit": limit}, timeout=12,
                      label=f"news {league}")
    if not d:
        return []
    articles = d.get("articles", []) or []

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
    # Through the gate, like everything else. It holds a ceiling on how
    # much leaves this server and stops entirely when ESPN pushes back -
    # the show fetches one of these per game, so on a heavy night this is
    # the biggest single consumer.
    from services import espn_gate
    d = espn_gate.fetch(url, timeout=12, label=f"detail {league}/{event_id}")
    if not d:
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
    out["stakes"] = game_stakes(d, lg, loser_team)
    out["bad_nights"] = _bad_nights(d, loser_team, lg)
    if lg in ("nba", "wnba", "ncaab", "ncaaw"):
        win_team = (out.get("winner") or {}).get("team")
        # The league matters: WNBA thresholds are lower, because a 25-point
        # night in a 40-minute game is not the same event as one in 48.
        out["nba_players"] = nba_players(d, loser_team, win_team, league=lg)
        out["nba_shooting"] = nba_team_shooting(d, loser_team)

    # Hockey. Its own block, not bent into the basketball one - a goalie is
    # not a point guard and the stats do not correspond.
    if lg == "nhl":
        out["nhl"] = nhl_detail(d, loser_team, win_team)

    # THE RAW BOX SCORE, KEPT.
    #
    # Everything above is PROCESSED - pitchers, bad nights, top-order
    # collapses. Useful, but there is no hitters list for baseball, so the
    # Smack Ball and the Clown Show had nothing to pick from and the layout
    # quietly fell back to a generic player slot. A real show ran with seven
    # slots instead of nine and nobody would have known why.
    #
    # Keeping the raw block lets the award pickers read what they need
    # without a second fetch. Roughly a couple of hundred KB per game -
    # against a show that peaks near 250MB, that is noise.
    if d.get("boxscore"):
        out["boxscore"] = d["boxscore"]

    if lg in ("nfl", "ncaaf"):
        out["stakes"] = game_stakes(d, lg, loser_team)
        win_team = (out.get("winner") or {}).get("team")
        out["nfl_players"] = nfl_skill_players(d, loser_team)
        out["upset"] = detect_upset(out)
        out["flow"] = nfl_game_flow(d, loser_team, win_team)
        out["leaders"] = nfl_leaders(d, loser_team, win_team)

    if lg in ("mlb", "ncaabb"):
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
    # Football. Labels read from whatever ESPN returns rather than assumed -
    # the probe has not yet sampled an NFL payload, so anything missing
    # simply does not fire instead of guessing.
    "nfl":  [("INT", ">=", 2, "{v} interceptions"),
             ("FUM", ">=", 1, "{v} fumbles lost"),
             ("SACKS", ">=", 4, "sacked {v} times"),
             ("LONG", "<=", 5, "a long gain of {v} yards all day")],
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
    if league == "nfl":
        # Football has no batting order and ESPN groups by position, so the
        # signal is WHICH group the player appears in. A quarterback throwing
        # picks is always the story; a backup safety missing a tackle is not.
        # Handled at the group level in _bad_nights rather than here, so
        # everyone in a scoring group qualifies.
        return True

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
            # Football: only the groups where a bad game actually matters.
            # ESPN splits the box score by position - passing, rushing,
            # receiving, defensive - and a roast about a punter is nobody's
            # idea of a good time.
            if league == "nfl":
                gname = (group.get("name") or group.get("type") or "").lower()
                if not any(k in gname for k in
                           ("passing", "rushing", "receiving", "fumbles")):
                    continue

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


def select_facts(detail: dict, max_supporting: int = 3, avoid: list = None) -> list:
    """
    Pick what actually goes in the call, rather than handing over everything.

    Fourteen facts for a 175-word call reads like a stat sheet. Worse, if the
    same facts are always present in the same order, every Locked & Loaded
    sounds identical - the analytics line in particular got stale after two
    listens.

    So: the result is always there, one LEAD is chosen from whichever angle
    is strongest tonight, and the rest is a random handful of what remains.
    Different shape every call, same underlying data.
    """
    import random

    if not detail:
        return []

    all_facts = roast_facts(detail)
    if not all_facts:
        return []

    # Facts already used on an earlier call to this same person about this
    # same game. Five people smacking one Cubs fan should produce five
    # different calls, not the same one five times - so anything already
    # spent is pushed to the back rather than reused.
    if avoid:
        spent = set(avoid)
        fresh = [f for f in all_facts if f not in spent]
        stale = [f for f in all_facts if f in spent]
        # The score line always stays first regardless.
        if all_facts and all_facts[0] in spent:
            fresh.insert(0, all_facts[0])
            stale = [f for f in stale if f != all_facts[0]]
        all_facts = fresh + stale

    # The score line is always first and always present.
    spine = [all_facts[0]]
    pool = all_facts[1:]

    def take(pred):
        for i, f in enumerate(pool):
            if pred(f):
                return pool.pop(i)
        return None

    # The lead - the single worst thing that happened. Ordered by how much
    # each is worth as an opening, and shuffled among equals so the same
    # angle does not lead every night.
    # Checked for every sport before anything sport-specific: a championship
    # or elimination loss outranks the whole box score.
    stakes_finders = [
        lambda f: "THEY LOST" in f,
        lambda f: "SEASON IS OVER" in f,
        lambda f: "ELIMINATION GAME" in f,
        lambda f: "ONE LOSS from elimination" in f,
        lambda f: "POSTSEASON game" in f,
    ]

    # The rest are sport-specific because the PHRASES are. Written against
    # baseball first, these find nothing in a football fact list - the call
    # would get a score and three random details with no lead at all.
    _lg = (detail.get("league") or "").upper()

    if _lg in ("NBA", "WNBA", "NCAAB", "NCAAW"):
        lead_finders = stakes_finders + [
            lambda f: "was still a minus" in f,
            lambda f: "a blowout" in f,
            lambda f: "one possession" in f,
            lambda f: "from the field" in f,
            lambda f: "the whole night was cold" in f,
            lambda f: "did the damage" in f,
            lambda f: "gave it away all night" in f,
            lambda f: "not enough" in f,
        ]
    elif _lg == "NFL":
        lead_finders = stakes_finders + [
            lambda f: "MASSIVE UPSET" in f,
            lambda f: "UPSET:" in f,
            lambda f: "OVERTIME" in f,
            lambda f: "field goal with" in f,
            lambda f: "last two minutes" in f,
            lambda f: "DEFENCE scored" in f,
            lambda f: "did nothing all day" in f,
            lambda f: "actually played well" in f,
            lambda f: "never in it" in f,
        ]
    else:
        lead_finders = stakes_finders + [
            lambda f: "was shelled" in f,
            lambda f: "shut out" in f,
            lambda f: "hit all night" in f or "hits all night" in f,
            lambda f: "on the season" in f,
            lambda f: "did not survive" in f,
            lambda f: "heart of the order" in f,
            lambda f: "took the loss" in f,
        ]
    # Collect every angle that is actually available tonight, then pick one
    # at random rather than always taking the first. Searching in fixed
    # order meant a shelled pitcher led every single call - the variety was
    # only ever in the supporting detail, which is not enough.
    candidates = []
    for finder in lead_finders:
        got = take(finder)
        if got:
            candidates.append(got)

    if candidates:
        lead = random.choice(candidates)
        spine.append(lead)
        # The ones not chosen go back in the pool - they are still good
        # material, just not the opening.
        pool.extend(c for c in candidates if c is not lead)

    # The analytics jab is good ONCE. Used every call it becomes the thing
    # people remember instead of the roast, so it appears about a quarter of
    # the time and is dropped entirely otherwise.
    analytics = take(lambda f: "analytics people" in f)
    keep_analytics = analytics and random.random() < 0.25

    # Everything else, shuffled, so the supporting detail differs each time.
    random.shuffle(pool)
    supporting = pool[:max_supporting]
    if keep_analytics:
        supporting = supporting[:max_supporting - 1] + [analytics]
        random.shuffle(supporting)

    return spine + supporting


def roast_facts(detail: dict) -> list:
    """The fact lines Smacky writes from, ordered by what they are worth."""
    if not detail:
        return []

    # Football is a different game with a different hierarchy - the upset
    # leads, the quarterback always answers for it, and the defence is
    # roasted as a unit. Handled separately rather than bent into the
    # baseball shape.
    if (detail.get("league") or "").upper() in ("NFL", "NCAAF"):
        return stakes_facts(detail) + nfl_roast_facts(detail)

    # Basketball, both leagues. Same box score shape, same
    # hierarchy - WNBA needs no separate path.
    # Hockey has its own hierarchy - the goalie answers for it, then whoever
    # did the damage. NHL had NO path at all and fell through to nothing.
    if (detail.get("league") or "").upper() in ("NHL",):
        return nhl_roast_facts(detail)
    if (detail.get("league") or "").upper() in ("NBA", "WNBA", "NCAAB", "NCAAW"):
        return nba_roast_facts(detail)
    # What the loss COST goes first and outranks the box score. A man
    # who just lost a World Series does not want a pitching line.
    f = list(stakes_facts(detail))
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

    def tokens(x):
        """
        Every word in a team name, separately. Matching the whole string
        fails the moment the two services disagree about format:
        SportsDataIO may store "Chicago Cubs" while ESPN returns "Cubs" and
        "Chicago" separately, and "chicagocubs" matches neither. A silent
        miss means every call quietly falls back to the scrambled scores.
        """
        out = set()
        raw = str(x or "")
        out.add(norm(raw))
        for part in raw.replace("-", " ").split():
            n = norm(part)
            if len(n) >= 4:
                out.add(n)
        return out - {""}

    want_home, want_away = tokens(home_team), tokens(away_team)
    if not (want_home and want_away):
        return None

    for back in range(days_back, days_back + 2):   # allow a day either side
        try:
            for g in fetch_finals(league, days_back=back):
                got = set()
                for key in ("home_nick", "away_nick", "home_city", "away_city"):
                    got |= tokens(g.get(key))

                # BOTH teams must be recognisable in the same game - matching
                # one is how you call somebody about the wrong game.
                if want_home & got and want_away & got and g.get("espn_id"):
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


def _parse_record(rec):
    """"9-4" or "9-4-1" into wins and losses."""
    if not rec:
        return None
    parts = str(rec).split("-")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def detect_upset(detail):
    """
    Did a good team lose to a bad one?

    In football this is the single biggest roasting point there is - bigger
    than any individual stat line. A 9-4 team losing to a 3-9 team IS the
    call; everything else is supporting detail. Seventeen games means one
    loss carries far more weight than it does in a 162-game baseball season.
    """
    w = _parse_record((detail.get("winner") or {}).get("record"))
    l = _parse_record((detail.get("loser") or {}).get("record"))
    if not w or not l:
        return None

    # Records include tonight's result, so back it out to compare how the
    # two teams looked going IN.
    win_w, win_l = w[0] - 1, w[1]
    los_w, los_l = l[0], l[1] - 1
    if win_w < 0 or los_l < 0:
        return None

    def pct(won, lost):
        total = won + lost
        return (won / total) if total else 0.5

    winner_pct = pct(win_w, win_l)
    loser_pct = pct(los_w, los_l)
    gap = loser_pct - winner_pct

    if gap < 0.20:
        return None

    return {
        "loser_record_before": f"{los_w}-{los_l}",
        "winner_record_before": f"{win_w}-{win_l}",
        "gap": round(gap, 2),
        # A losing team beating a winning one is the full humiliation.
        "beaten_by_losing_team": winner_pct < 0.500 and loser_pct > 0.500,
    }


# Confirmed against a real NFL payload (Browns/49ers, 30 Nov 2025). These
# are the labels ESPN actually returns, not an assumption about them.
_NFL_GROUPS = {
    "passing":   ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"],
    "rushing":   ["CAR", "YDS", "AVG", "TD", "LONG"],
    "receiving": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
    "fumbles":   ["FUM", "LOST", "REC"],
}


def nfl_skill_players(d, losing_team):
    """
    The offence, by name. Quarterback, backs, receivers, tight ends - the
    players who are supposed to score. Defence is roasted as a UNIT, never
    by name: giving up 26 points is a collective failure and singling out one
    safety is both unfair and less funny.
    """
    out = {"quarterback": None, "skill": [], "fumblers": []}

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team or "").lower():
            continue

        for group in (block.get("statistics") or []):
            gname = (group.get("name") or group.get("type") or "").lower()
            labels = group.get("labels") or []
            athletes = group.get("athletes") or []
            if not athletes:
                continue

            if gname == "passing":
                ath = athletes[0]          # the starter
                person = ath.get("athlete") or {}
                name = person.get("displayName")
                st = _stat_map(labels, ath.get("stats") or [])
                if not name:
                    continue
                qbr = _to_num(st.get("QBR"))
                sacks_raw = str(st.get("SACKS") or "")
                sacks = None
                if "-" in sacks_raw:
                    sacks = _to_num(sacks_raw.split("-")[0])
                out["quarterback"] = {
                    "name": name,
                    "line": st.get("C/ATT"),
                    "yards": st.get("YDS"),
                    "tds": _to_num(st.get("TD")),
                    "ints": _to_num(st.get("INT")),
                    "sacks_taken": int(sacks) if sacks is not None else None,
                    "qbr": qbr,
                    "rating": st.get("RTG"),
                    # ESPN's own composite. 16.3 is obviously terrible without
                    # anyone needing to know the scale, which is exactly what
                    # makes it usable on a phone call.
                    "awful": qbr is not None and qbr < 30,
                    "poor": qbr is not None and 30 <= qbr < 50,
                    "played_well": qbr is not None and qbr >= 65,
                }

            elif gname == "rushing":
                for ath in athletes[:2]:
                    person = ath.get("athlete") or {}
                    name = person.get("displayName")
                    st = _stat_map(labels, ath.get("stats") or [])
                    car, avg = _to_num(st.get("CAR")), _to_num(st.get("AVG"))
                    # Volume matters - a backup with two carries for one yard
                    # is not the story.
                    if name and car and car >= 10 and avg is not None and avg < 3.5:
                        out["skill"].append({
                            "name": name, "role": "running back",
                            "line": f"{int(car)} carries for {st.get('YDS')} yards",
                            "detail": f"{avg} a carry"})

            elif gname == "receiving":
                for ath in athletes[:3]:
                    person = ath.get("athlete") or {}
                    name = person.get("displayName")
                    st = _stat_map(labels, ath.get("stats") or [])
                    rec, tg = _to_num(st.get("REC")), _to_num(st.get("TGTS"))
                    yds = _to_num(st.get("YDS"))
                    # Thrown at repeatedly and did nothing with it.
                    if name and tg and tg >= 5 and rec is not None and (rec / tg) < 0.5:
                        out["skill"].append({
                            "name": name, "role": "receiver",
                            "line": f"{int(rec)} catches on {int(tg)} targets",
                            "detail": f"{st.get('YDS')} yards"})
                    elif name and tg and tg >= 6 and yds is not None and yds < 30:
                        out["skill"].append({
                            "name": name, "role": "receiver",
                            "line": f"{int(tg)} targets for {int(yds)} yards",
                            "detail": None})

            elif gname == "fumbles":
                for ath in athletes:
                    person = ath.get("athlete") or {}
                    name = person.get("displayName")
                    st = _stat_map(labels, ath.get("stats") or [])
                    fum, lost = _to_num(st.get("FUM")), _to_num(st.get("LOST"))
                    if name and fum and fum >= 1:
                        out["fumblers"].append({
                            "name": name, "fumbles": int(fum),
                            "lost": int(lost or 0)})

    return out


def nfl_roast_facts(detail):
    """
    Football facts, ordered by what actually matters.

    THE UPSET LEADS if there is one. A good team losing to a bad one is the
    single biggest roasting point in football - seventeen games means one
    loss carries weight a baseball loss never does, and it puts January in
    doubt. Everything else is supporting detail.

    QBR decides whether the quarterback gets roasted but NEVER appears in the
    script - the average listener has no idea what a 16.3 means, and
    explaining a scale mid-call kills the joke. Same rule as the win
    probability percentage.
    """
    f = []
    w = detail.get("winner") or {}
    l = detail.get("loser") or {}

    if w.get("team") and l.get("team"):
        ws, ls = w.get("score"), l.get("score")
        f.append(f"{w['team']} beat {l['team']} {int(ws)}-{int(ls)}"
                 if ws is not None and ls is not None
                 else f"{w['team']} beat {l['team']}")

    # THE UPSET. This leads.
    up = detail.get("upset")
    if up:
        if up.get("beaten_by_losing_team"):
            f.append(f"MASSIVE UPSET: {l['team']} were {up['loser_record_before']} "
                     f"and lost to a {up['winner_record_before']} team - a team "
                     f"with a LOSING record. This is the story of the call.")
        else:
            f.append(f"UPSET: {l['team']} were {up['loser_record_before']} and "
                     f"lost to a {up['winner_record_before']} team. Lead with this.")
        f.append("their season just got a lot harder - playoff maths, "
                 "momentum, all of it in question after a loss like that")

    if l.get("record"):
        f.append(f"{l['team']} are now {l['record']}")

    m = detail.get("margin")
    if m and m >= 17:
        f.append(f"lost by {m} - never in it")

    # How it ended. Losing on a kick as time expires is a completely
    # different wound from losing by thirty, and it deserves to lead when
    # there is no upset to lead with.
    fl = detail.get("flow") or {}
    if fl.get("went_to_overtime"):
        f.append("it went to OVERTIME - they had four quarters and needed a fifth, "
                 "and still lost")
    if fl.get("walkoff_field_goal"):
        f.append(f"lost it to a field goal with {fl.get('last_score_clock')} left - "
                 f"one kick, and that is the whole season in one swing of a leg")
    elif fl.get("decided_late"):
        f.append(f"decided in the last two minutes - {fl.get('last_score_clock')} "
                 f"on the clock when it went")
    if fl.get("defensive_touchdown"):
        f.append(f"their DEFENCE scored: {fl['defensive_touchdown']} - "
                 f"the offence handed over points")
    lp = fl.get("last_period_with_any_score")
    if lp and lp <= 2 and not fl.get("decided_late"):
        f.append("nobody scored after the first half - the whole second half "
                 "produced nothing")

    # The opposing player who did the damage, by name. Being taken apart by
    # one man is a better roast than anything aimed at the loser.
    for ldr in (detail.get("leaders", {}).get("theirs") or [])[:2]:
        pos = f" ({ldr['position']})" if ldr.get("position") else ""
        f.append(f"their {ldr['category']} leader {ldr['name']}{pos}: {ldr['line']}")

    # The quarterback. Named every time, because in football he answers for
    # it whether he played badly or not.
    qb = detail.get("nfl_players", {}).get("quarterback")
    if qb:
        if qb.get("awful"):
            f.append(f"quarterback {qb['name']} did nothing all day - "
                     f"{qb['line']} for {qb['yards']} yards")
        elif qb.get("poor"):
            f.append(f"quarterback {qb['name']} was ordinary at best - "
                     f"{qb['line']} for {qb['yards']} yards")
        elif qb.get("played_well"):
            f.append(f"quarterback {qb['name']} actually played well "
                     f"({qb['line']}, {qb['yards']} yards) - which makes losing worse, "
                     f"not better. Somebody else lost this.")
        if qb.get("ints"):
            f.append(f"{qb['name']} threw {int(qb['ints'])} interceptions")
        if qb.get("sacks_taken") and qb["sacks_taken"] >= 3:
            f.append(f"{qb['name']} was sacked {qb['sacks_taken']} times - "
                     f"the line never held")

    for p_ in (detail.get("nfl_players", {}).get("skill") or [])[:2]:
        extra = f", {p_['detail']}" if p_.get("detail") else ""
        f.append(f"{p_['role']} {p_['name']}: {p_['line']}{extra}")

    for fu in (detail.get("nfl_players", {}).get("fumblers") or [])[:2]:
        if fu["fumbles"] >= 2:
            f.append(f"{fu['name']} put the ball on the ground "
                     f"{fu['fumbles']} times")
        elif fu["lost"]:
            f.append(f"{fu['name']} lost a fumble")

    # The defence as a UNIT. Never by name - giving up points is collective,
    # and singling out one safety is unfair and less funny.
    if w.get("score") is not None:
        pts = int(w["score"])
        if pts >= 30:
            f.append(f"the defence gave up {pts} points - a total no-show")
        elif pts >= 24:
            f.append(f"the defence gave up {pts} points")

    if detail.get("lost_at_home"):
        v, att = detail.get("venue"), detail.get("attendance")
        f.append(f"lost at home at {v} in front of {att:,}" if v and att
                 else f"lost at home in front of {att:,}" if att
                 else "lost at home")

    return f


def _clock_secs(clock):
    """"4:09" into seconds remaining in the period."""
    try:
        m, sec = str(clock).split(":")
        return int(m) * 60 + int(sec)
    except (ValueError, AttributeError):
        return None


def nfl_game_flow(d, loser_team, winner_team):
    """
    How the game actually went, from scoringPlays.

    Football is decided late far more often than baseball, and losing on a
    field goal as time expires is a completely different wound from losing
    by thirty. Confirmed shape: each entry carries period, clock, type and
    full text - note the key is scoringPlays, NOT the flat plays array
    baseball uses, which comes back empty for NFL.
    """
    plays = d.get("scoringPlays") or []
    if not plays:
        return {}

    out = {"score_count": len(plays)}
    last = plays[-1]
    per = (last.get("period") or {}).get("number")
    secs = _clock_secs((last.get("clock") or {}).get("displayValue"))

    out["went_to_overtime"] = bool(per and per > 4)
    out["last_score_period"] = per
    out["last_score_text"] = (last.get("text") or "")[:150]
    out["last_score_type"] = (last.get("scoringType") or {}).get("name")

    # Decided at the death. Two minutes is the football threshold - that is
    # when the game stops being a game and becomes a situation.
    if per and per >= 4 and secs is not None and secs <= 120:
        out["decided_late"] = True
        out["last_score_clock"] = (last.get("clock") or {}).get("displayValue")
        if out["last_score_type"] == "field-goal":
            out["walkoff_field_goal"] = True

    # A defensive score - pick six or fumble return. The most humiliating
    # way to concede points, because your own offence gave them up.
    for pl in plays:
        text = (pl.get("text") or "").lower()
        if any(k in text for k in ("interception return", "int return",
                                   "fumble return", "pick-six", "pick six")):
            out["defensive_touchdown"] = (pl.get("text") or "")[:150]
            out["defensive_td_period"] = (pl.get("period") or {}).get("number")
            break

    # When did the loser last score? A team that stopped scoring in the
    # second quarter did not lose a game, they left one.
    loser_scores = [pl for pl in plays
                    if str(loser_team or "").lower() in (pl.get("text") or "").lower()]
    scoring_periods = [(pl.get("period") or {}).get("number")
                       for pl in plays if pl.get("period")]
    if scoring_periods:
        out["last_period_with_any_score"] = max(p for p in scoring_periods if p)

    return out


def nfl_leaders(d, loser_team, winner_team):
    """
    The opposing player who did the damage, by name.

    ESPN pre-formats these - "16/25, 149 YDS, 1 TD" - so they are read
    rather than parsed. Being taken apart by one named man is a better
    roast than anything aimed at the loser directly.
    """
    out = {"theirs": [], "yours": []}
    for team_block in (d.get("leaders") or []):
        name = ((team_block.get("team") or {}).get("displayName") or "")
        side = ("theirs" if str(winner_team or "").lower() in name.lower()
                else "yours" if str(loser_team or "").lower() in name.lower()
                else None)
        if not side:
            continue
        for cat in (team_block.get("leaders") or []):
            label = cat.get("displayName")
            for ldr in (cat.get("leaders") or [])[:1]:
                ath = (ldr.get("athlete") or {})
                who = ath.get("displayName")
                if not who:
                    continue
                out[side].append({
                    "category": label,
                    "name": who,
                    "position": ((ath.get("position") or {}).get("abbreviation")),
                    "line": ldr.get("displayValue"),
                })
    return out


# What a loss actually costs, ranked. A championship defeat makes every stat
# in the box score irrelevant - nobody who just lost a Super Bowl wants to
# hear about third down conversions.
STAKES_NONE = 0
STAKES_POSTSEASON = 1
STAKES_ELIMINATION = 2
STAKES_CHAMPIONSHIP = 3


def game_stakes(d, league, loser_team):
    """
    Was this a playoff game, an elimination, or the championship itself?

    seasonType is ESPN's own marker: 1 preseason, 2 regular, 3 postseason.
    Reliable across every league. The series state for baseball is read from
    seasonseries when it is there and simply absent when it is not - a
    missing series is far better than a wrong one, because telling somebody
    their season is over when it is not would be unforgivable in a product
    that trades on knowing the sport.
    """
    out = {"level": STAKES_NONE, "postseason": False}

    header = d.get("header") or {}
    season = header.get("season") or {}
    stype = season.get("type")
    if stype != 3:
        return out

    out["postseason"] = True
    out["level"] = STAKES_POSTSEASON
    out["year"] = season.get("year")

    comp = (header.get("competitions") or [{}])[0]
    notes = comp.get("notes") or []
    label = ""
    for n in notes:
        label = (n.get("headline") or n.get("type") or "") or label
    out["round"] = label

    low = (label or "").lower()
    lg = (league or "").lower()

    # The championship itself.
    if lg == "nfl" and "super bowl" in low:
        out["level"] = STAKES_CHAMPIONSHIP
        out["title"] = "the Super Bowl"
    elif lg == "mlb" and "world series" in low:
        out["level"] = STAKES_CHAMPIONSHIP
        out["title"] = "the World Series"
    elif lg == "nba" and "finals" in low:
        out["level"] = STAKES_CHAMPIONSHIP
        out["title"] = "the NBA Finals"
    elif lg == "nhl" and ("stanley cup" in low or "final" in low):
        out["level"] = STAKES_CHAMPIONSHIP
        out["title"] = "the Stanley Cup Final"

    # Single-elimination formats - lose and you are out, no series to save it.
    if lg == "nfl" or (lg == "mlb" and "wild card" in low):
        if out["level"] != STAKES_CHAMPIONSHIP:
            out["level"] = STAKES_ELIMINATION
            out["single_elimination"] = True

    # Series state, where the format is a series rather than one game.
    series = _series_state(d, loser_team)
    if series:
        out["series"] = series
        if series.get("eliminated"):
            out["level"] = max(out["level"], STAKES_ELIMINATION)
        if series.get("facing_elimination"):
            out["level"] = max(out["level"], STAKES_ELIMINATION)

    return out


def _series_state(d, loser_team):
    """
    Where the series stands. Read defensively - the shape of seasonseries
    has not been confirmed against a real postseason payload, so anything
    unrecognised is skipped rather than guessed at.
    """
    ss = d.get("seasonseries")
    if not ss:
        return None
    block = ss[0] if isinstance(ss, list) and ss else ss
    if not isinstance(block, dict):
        return None

    summary = block.get("summary") or block.get("title") or ""
    events = block.get("events") or []
    total = block.get("totalCompetitions") or len(events) or None

    out = {"summary": summary, "games_played": len(events) or None,
           "best_of": total}

    # "SEA leads 3-1" style summaries carry the state without needing the
    # individual games parsed.
    import re as _re
    m = _re.search(r"(\d+)\s*[-–]\s*(\d+)", str(summary))
    if m:
        hi, lo = int(m.group(1)), int(m.group(2))
        out["leader_wins"], out["trailer_wins"] = hi, lo
        loser_named = str(loser_team or "").lower() in str(summary).lower()

        # Best-of-seven needs four; best-of-five needs three.
        needed = 4 if (total or 7) >= 7 else 3
        if hi >= needed and not loser_named:
            out["eliminated"] = True
        elif hi == needed - 1 and not loser_named:
            out["facing_elimination"] = True

    return out or None


def stakes_facts(detail):
    """
    What the loss actually cost. This goes at the TOP of the fact list and
    overrides everything, because a man who just lost a championship does
    not want to hear about third down conversions. The season is over. That
    is the entire call.
    """
    st = detail.get("stakes") or {}
    lvl = st.get("level", 0)
    if not lvl:
        return []

    l = (detail.get("loser") or {}).get("team", "they")
    f = []

    if lvl >= STAKES_CHAMPIONSHIP:
        title = st.get("title", "the championship")
        f.append(f"THEY LOST {title.upper()}. This is the entire call. Nothing "
                 f"else in this game matters next to it - not the stats, not "
                 f"the players, not the score. {l} played the biggest game of "
                 f"the year and lost it.")
        f.append("lean into it completely: a full season, all of it, gone in "
                 "one night. Months of work. The one game everybody watches. "
                 "Better luck next year - and next year is a long way away")
        return f

    ser = st.get("series") or {}
    if ser.get("eliminated"):
        f.append(f"THEIR SEASON IS OVER. {l} were knocked out - the series is "
                 f"done, {ser.get('summary','')}. Everything else is a "
                 f"footnote. There is no next game.")
        f.append("no more baseball for them this year. Whatever they were "
                 "building toward, it stopped tonight")
        return f

    if st.get("single_elimination"):
        f.append(f"ELIMINATION GAME - {l} lost and they are OUT. One game, "
                 f"win or go home, and they went home. Season over.")
        return f

    if ser.get("facing_elimination"):
        f.append(f"they are now ONE LOSS from elimination - {ser.get('summary','')}. "
                 f"Their season is hanging by a thread and everybody watching "
                 f"knows it")
        f.append("build the dread: the ring they were chasing is getting "
                 "further away by the night, and there may not be another game")
        return f

    if st.get("postseason"):
        rnd = st.get("round") or "the playoffs"
        f.append(f"this was a POSTSEASON game - {rnd}. Playoff losses hurt in "
                 f"a way regular season losses do not, and there is a title "
                 f"at the end of this they are no longer walking toward")
    return f


# Confirmed against a real NBA payload (Magic/Grizzlies, 15 Jan 2026).
# Basketball has no batting order and no quarterback - the signals are
# MINUTES (under fifteen and nobody is the story), the starter flag, and
# plus-minus, which catches what points alone miss.
_NBA_LABELS = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO",
               "STL", "BLK", "OREB", "DREB", "PF", "+/-"]


def _made_attempted(v):
    """"12-22" into (12, 22). Also handles "4-18", "0-7"."""
    try:
        m, a = str(v).split("-")
        return int(m), int(a)
    except (ValueError, AttributeError):
        return None, None


# Basketball thresholds, scaled per league.
#
# These were NBA numbers applied to every basketball league. A WNBA game is
# 40 minutes rather than 48 and scores roughly 84 a side against 114, so a
# 25-point night there is the equivalent of about 34 in the NBA - almost
# nobody clears it, and the call falls back to the scoreline with no player
# named at all. Which is exactly what a real Locked & Loaded did.
#
# Scaled by 0.74, the ratio of the two leagues' scoring.
BALL_THRESHOLDS = {
    "nba":   {"star": 25, "sinker": -12, "minutes": 15, "blowout": 20, "scored": 20},
    "ncaab": {"star": 20, "sinker": -12, "minutes": 15, "blowout": 18, "scored": 18},
    "wnba":  {"star": 20, "sinker": -9,  "minutes": 11, "blowout": 15, "scored": 15},
    "ncaaw": {"star": 15, "sinker": -9,  "minutes": 11, "blowout": 14, "scored": 14},
}


def nba_players(d, losing_team, winning_team, league="nba"):
    """
    Who actually lost this game.

    The trap here is roasting a man who played well. A real extraction
    flagged Jaren Jackson Jr. for four turnovers in a game where he scored
    THIRTY on 12-of-22 - he was the best player on the floor. What the raw
    line missed was his plus-minus: minus twenty-one, in a game they lost by
    seven. The team was twenty-one points worse with him out there.
    """
    _T = BALL_THRESHOLDS.get((league or "nba").lower(), BALL_THRESHOLDS["nba"])
    out = {"cold": [], "sinkers": [], "star_carried": None, "their_star": None}

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        side = ("losing" if nick.lower() == str(losing_team or "").lower()
                else "winning" if nick.lower() == str(winning_team or "").lower()
                else None)
        if not side:
            continue

        for group in (block.get("statistics") or []):
            labels = group.get("labels") or []
            for ath in (group.get("athletes") or []):
                if ath.get("didNotPlay"):
                    continue
                person = ath.get("athlete") or {}
                name = person.get("displayName")
                if not name:
                    continue
                st = _stat_map(labels, ath.get("stats") or [])

                mins = _to_num(st.get("MIN"))
                # Under fifteen minutes nobody is the story. This is the
                # filter that stops a bench player who played six minutes
                # being roasted for scoring two.
                if mins is None or mins < _T["minutes"]:
                    continue

                pts = _to_num(st.get("PTS"))
                made, att = _made_attempted(st.get("FG"))
                pm = _to_num(str(st.get("+/-", "")).replace("+", ""))
                starter = bool(ath.get("starter"))

                entry = {"name": name, "minutes": int(mins), "points": int(pts or 0),
                         "fg": st.get("FG"), "made": made, "attempts": att,
                         "plus_minus": int(pm) if pm is not None else None,
                         "starter": starter, "turnovers": _to_num(st.get("TO")),
                         "rebounds": _to_num(st.get("REB")),
                         "assists": _to_num(st.get("AST"))}

                if side == "losing":
                    # Cold shooting - the classic bad night. Volume matters:
                    # 4-for-18 is a story, 1-for-3 is a quiet evening.
                    if att and att >= 10 and made is not None and (made / att) < 0.35:
                        out["cold"].append(entry)
                    # The floor sank while they played. Worse than any single
                    # stat because it survives a good-looking box score.
                    if pm is not None and pm <= _T["sinker"] and starter:
                        out["sinkers"].append(entry)
                    # A star who did his job and still lost.
                    out.setdefault("_all_losing", []).append(entry)
                    # The starting five's combined total. A quiet top scorer
                    # is one thing; a whole starting five that managed forty
                    # between them is the story.
                    if starter:
                        # int, because _to_num returns a float and "38.0
                        # points" read aloud is wrong.
                        out["starters_pts"] = (out.get("starters_pts") or 0) + int(pts or 0)
                        out["starters_n"] = (out.get("starters_n") or 0) + 1
                    # ANY 19+ NIGHT gets named, not only the leader. Two
                    # players at 21 and 19 is a different story from one at
                    # 21, and a call that mentions only the top scorer throws
                    # the second away.
                    if (pts or 0) >= 19:
                        out.setdefault("notable_losing", []).append(entry)
                    if pts and pts >= _T["star"]:
                        cur = out["star_carried"]
                        if not cur or pts > cur["points"]:
                            out["star_carried"] = entry
                else:
                    # THE WINNING SIDE'S TOP SCORER, whatever she scored.
                    #
                    # No threshold. This is the easy target and it is always
                    # available: somebody did this to you, and naming her is
                    # the point. A threshold here only ever produced calls
                    # that named nobody, which is worse than naming somebody
                    # who had a merely good night.
                    cur = out["their_star"]
                    if not cur or (pts or 0) > (cur.get("points") or 0):
                        out["their_star"] = entry
                    if (pts or 0) >= 19:
                        out.setdefault("notable_winning", []).append(entry)

    out["cold"].sort(key=lambda x: (x["made"] or 0) / (x["attempts"] or 1))
    out["sinkers"].sort(key=lambda x: x["plus_minus"] or 0)

    # ALWAYS NAME SOMEBODY.
    #
    # The thresholds decide who counts as a STAR. They should not decide
    # whether anyone is mentioned at all - a real WNBA call went out naming
    # nobody, because a 40-minute game rarely produces the 25-point night the
    # NBA numbers were asking for.
    #
    # If nobody cleared the bar, the top scorer on each side is named anyway.
    # Fourteen points might not be a star turn, but it is still who led the
    # game, and "their best player managed fourteen" is a perfectly good line.
    # Flagged so the writer knows which it is and does not oversell a quiet
    # night.
    if not out.get("star_carried") and out.get("_all_losing"):
        top = max(out["_all_losing"], key=lambda x: x.get("points") or 0)
        if top.get("points"):
            out["star_carried"] = {**top, "modest": True}
    if not out.get("their_star") and out.get("_all_winning"):
        top = max(out["_all_winning"], key=lambda x: x.get("points") or 0)
        if top.get("points"):
            out["their_star"] = {**top, "modest": True}
    out.pop("_all_losing", None)
    out.pop("_all_winning", None)
    return out


def nba_team_shooting(d, losing_team):
    """Whole-team shooting. 38 percent is a night nobody enjoyed."""
    for block in ((d.get("boxscore") or {}).get("teams") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        if nick.lower() != str(losing_team or "").lower():
            continue
        vals = {}
        for stat in (block.get("statistics") or []):
            key = (stat.get("name") or stat.get("abbreviation") or "").strip().lower()
            if key:
                vals[key] = stat.get("displayValue")
        out = {}
        for k in ("fieldgoalpct", "fieldgoalspct", "fgpct"):
            if k in vals:
                pct = _to_num(str(vals[k]).replace("%", ""))
                if pct is not None:
                    out["fg_pct"] = pct
                    out["cold_night"] = pct < 42.0
                break
        for k in ("threepointfieldgoalpct", "threepointpct"):
            if k in vals:
                pct = _to_num(str(vals[k]).replace("%", ""))
                if pct is not None:
                    out["three_pct"] = pct
                    out["cold_from_three"] = pct < 30.0
                break
        for k in ("turnovers", "totalturnovers"):
            if k in vals:
                tov = _to_num(vals[k])
                if tov is not None:
                    out["turnovers"] = int(tov)
                    out["careless"] = tov >= 18
                break
        return out or None
    return None


# How to name somebody. Varied HERE rather than asked for in the prompt,
# because a prompt-level "vary this" has been ignored repeatedly on this
# project - the construction cap, the cross-league teases, the grouping rule.
#
# The point is only that a name gets said. A call that reports a scoreline
# and no people sounds like a results service; a call that says "you let
# Stewart put 27 on you" sounds like somebody watched it.
# "You" as a hinge - the sentence starts on the listener and lands on the
# team. That is what keeps it clean AND makes it funnier: the insult is
# always about the club they chose, never about them.
CHOSE_THIS = [
    "you chose to be a fan of the worst team in the league and today it "
    "showed its gratitude",
    "you woke up and picked this franchise. It picked violence right back",
    "somewhere along the line you decided this was your team. Tonight was "
    "the invoice",
    "you support a team that lost like that. Freely. On purpose",
    "nobody made you a fan of this lot. That is the part that gets me",
    "you have chosen a life of this, and tonight was a fairly typical "
    "Tuesday in it",
]

ALLOWED_IT = [
    "you let {name} put up {pts} on you",
    "{name} got {pts} and nobody on your side seemed bothered",
    "{name} scored {pts}. Was anybody guarding that, or was it optional",
    "somebody was supposed to be on {name}. {pts} says otherwise",
    "{name} helped themselves to {pts} of yours",
    "{pts} for {name}, and it looked easy",
    "you gave {name} {pts} like it was a gift",
    "{name} put {pts} on your head and walked off",
    "{name} had {pts} before your bench finished sitting down",
]

WASTED_IT = [
    "{name} gave you {pts} and you lost anyway - what exactly was everybody "
    "else doing",
    "{name} did their part with {pts}. Nobody else turned up",
    "{pts} from {name} and it bought you nothing",
    "you wasted {pts} from {name}. That takes effort",
    "{name} scored {pts} in a losing effort, which is the saddest phrase in "
    "sport",
    "{name} had {pts}. The rest of your roster was a rumour",
    "{pts} from {name} and it still went in the L column",
]

LED_THEM = [
    "{name} led them with {pts} - that is all it took to beat you",
    "{pts} was enough. {name} did not even need a big night",
    "{name} topped them with {pts}. That was the bar and you could not clear it",
    "they got {pts} out of {name} and that was the whole plan",
    "{name} had {pts} and never had to find another gear",
]

BEST_YOU_HAD = [
    "{name} led you with {pts} - that was the best anybody managed",
    "your leading scorer was {name} with {pts}. Let that sit",
    "{pts} from {name} was your high point. Your HIGH point",
    "{name} top-scored for you with {pts}, which tells you everything",
    "the best you had was {pts} from {name}",
]

# NOBODY GOT GOING.
#
# The losing side's best effort being under 19 is its own roast - it is not
# that a star was let down, it is that nobody turned up at all.
NO_SCORING = [
    "your best scorer had {pts}. That is not a bad night, that is a bad team",
    "{name} led you with {pts}. Nobody on your roster reached twenty",
    "top scorer: {name}, {pts} points. That is the whole story",
    "not one of you got to twenty. {name} came closest with {pts}",
    "{pts} was your ceiling tonight, courtesy of {name}",
    "{name} was your leading man at {pts}. Read that again",
    "your leading scorer had {pts}. A quiet Tuesday at the gym beats that",
]

# The starting five, combined.
STARTING_FIVE = [
    "your starting five combined for {pts}. Five people. {pts} points",
    "the whole starting five managed {pts} between them",
    "{pts} from your starters. All five of them. Together",
    "your first five put up {pts} combined, which is one decent night split "
    "five ways",
    "add up your entire starting five and you get {pts}",
    "five starters, {pts} points. Somebody should check on them",
]

# THE CAITLIN STANDARD.
#
# Fires rarely and only in the WNBA. The bit works because Smacky cannot be
# objective, not because he says her name constantly - mentioned every call
# it stops being a bit and becomes a tic, which is the failure mode of every
# running joke on this project.
#
# Never at anyone's expense: the joke is Smacky's own lost objectivity.
CLARK_LINES = [
    "Caitlin Clark would have had that by the third quarter, but nobody "
    "asked me",
    "I am not saying Caitlin Clark would have won that game by herself. I am "
    "thinking it, though",
    "somewhere Caitlin Clark watched that and felt nothing, which is the "
    "correct response",
    "that is not a Caitlin Clark number. I do not make the rules",
    "Caitlin Clark was not involved in this game and it still would have "
    "been better if she was",
    "I have been asked to stop comparing everybody to Caitlin Clark. I have "
    "considered it",
    "no Caitlin Clark in this one, which explains a lot",
]


# The two that were still fixed lines.
CARRIED_IT = [
    "{name} put up {pts} and it still was not enough - nobody else showed up",
    "{name} gave you {pts} and got nothing back from anybody",
    "{pts} from {name} against four passengers",
    "{name} carried {pts} of the load. The rest of you watched",
    "{name} had {pts}. Everybody else combined to be a problem",
]

DID_DAMAGE = [
    "you let {name} do the damage: {bits}",
    "{name} did what they liked: {bits}",
    "the whole night was {name}: {bits}",
    "you had no answer for {name}: {bits}",
    "{name} picked you apart: {bits}",
]


def _named(pool, name, pts, used):
    """One line about a player, never the same shape twice in a call."""
    import random as _r
    fresh = [x for x in pool if x not in used]
    line = _r.choice(fresh or pool)
    used.add(line)
    return line.format(name=name, pts=pts)


def nba_roast_facts(detail):
    """
    Basketball facts. No single player wears the loss the way a quarterback
    or a starting pitcher does, so the hierarchy is different: the collapse
    if there was one, then the man the floor sank behind, then cold
    shooting, then their star who did the damage.
    """
    _T = BALL_THRESHOLDS.get((detail.get("league") or "nba").lower(),
                             BALL_THRESHOLDS["nba"])
    # Shapes already used in THIS call, so no two player mentions land the
    # same way. The variation has to be per call, not per pool.
    _used = set()
    f = list(stakes_facts(detail))
    w = detail.get("winner") or {}
    l = detail.get("loser") or {}

    if w.get("team") and l.get("team"):
        ws, ls = w.get("score"), l.get("score")
        f.append(f"{w['team']} beat {l['team']} {int(ws)}-{int(ls)}"
                 if ws is not None and ls is not None
                 else f"{w['team']} beat {l['team']}")
    if l.get("record"):
        f.append(f"{l['team']} are now {l['record']}")

    m = detail.get("margin")
    if m and m >= _T["blowout"]:
        f.append(f"lost by {m} - a blowout, never competitive")
    elif m and m <= 3:
        f.append(f"lost by {m} - one possession, and they could not get it")

    p = detail.get("nba_players") or {}

    # The floor sank behind them. This survives a good-looking box score,
    # which is the point - a man can score thirty and still be the reason.
    for sink in (p.get("sinkers") or [])[:1]:
        if sink.get("points", 0) >= _T["scored"]:
            f.append(f"{sink['name']} scored {sink['points']} and was still a "
                     f"minus {abs(sink['plus_minus'])} - the team was worse "
                     f"with him out there, which takes some doing")
        else:
            f.append(f"{sink['name']} was a minus {abs(sink['plus_minus'])} in "
                     f"{sink['minutes']} minutes - every time he touched the "
                     f"floor it got worse")

    for cold in (p.get("cold") or [])[:2]:
        f.append(f"{cold['name']} shot {cold['fg']} from the field in "
                 f"{cold['minutes']} minutes")

    # Compare by NAME, not by object. A dict comparison let the same player
    # appear twice with opposite framings - "the team was worse with him out
    # there" immediately followed by "nobody helped him", about one man.
    star = p.get("star_carried")
    sunk_names = {x["name"] for x in (p.get("sinkers") or [])}
    if star and star["name"] not in sunk_names:
        # "modest" means nobody cleared the star threshold and this is simply
        # the top scorer. Saying "put up 14 and it still was not enough"
        # oversells a quiet night - a listener knows 14 is not a star turn,
        # and Smacky claiming otherwise makes him sound like he did not watch.
        if star.get("modest"):
            # Under 19 is a different roast from a quiet star night - it is
            # not that somebody was let down, it is that nobody turned up.
            pool = NO_SCORING if (star.get("points") or 0) < 19 else BEST_YOU_HAD
            f.append(_named(pool, star["name"], star["points"], _used))
        else:
                f.append(_named(CARRIED_IT, star["name"], star["points"], _used))

    # WHO DID IT TO YOU.
    #
    # The winning side's leading scorer, always, whatever the number. She is
    # the easy target and the one the recipient will actually feel - a call
    # that says "you lost by nine" lands nowhere near one that says "this
    # woman put up sixteen on you".
    #
    # The wording scales so a modest night is not oversold. A listener knows
    # sixteen is not a monster game, and Smacky pretending otherwise makes
    # him sound like he did not watch.
    # THE DEFENCE ALLOWED IT.
    #
    # The point of naming her is not the stat line - it is that somebody was
    # supposed to be guarding her. "She scored 27" is a fact; "you let her
    # score 27" is a roast, and it is the same sentence pointed at the person
    # receiving the call.
    for x in (p.get("notable_winning") or [])[:2]:
        if x is p.get("their_star"):
            continue        # the leader is covered below, do not say it twice
        f.append(_named(ALLOWED_IT, x["name"], x["points"], _used))

    # A BIG NIGHT WASTED.
    #
    # Somebody on the losing side going for 20+ and STILL losing is the
    # sharper joke - it is not that they had nobody, it is that they had
    # somebody and it did not matter.
    # The "nobody else showed up" line below covers the leading scorer, so
    # skip her here - the same player carrying the same joke twice in one
    # call is exactly the repetition that makes it sound generated.
    _carried = (p.get("star_carried") or {}).get("name")
    for x in (p.get("notable_losing") or [])[:2]:
        if (x.get("points") or 0) >= 20 and x.get("name") != _carried:
            f.append(_named(WASTED_IT, x["name"], x["points"], _used))

    # THE STARTING FIVE, combined.
    #
    # Only when it is genuinely bad - a good starting five total is not a
    # joke, and reporting it anyway is how a roast turns into a box score.
    _sp, _sn = p.get("starters_pts"), p.get("starters_n")
    if _sp and _sn and _sn >= 4:
        _lg = (detail.get("league") or "nba").lower()
        _floor = 45 if _lg in ("wnba", "ncaaw") else 55
        if _sp < _floor:
            import random as _r2
            _shape = _r2.choice([x for x in STARTING_FIVE if x not in _used]
                                or STARTING_FIVE)
            _used.add(_shape)
            f.append(_shape.format(pts=_sp))

    # THEY CHOSE THIS TEAM.
    #
    # Only on a heavy defeat - "you chose this" after a one-point loss is
    # mean rather than funny, because a one-point loss is not the team's
    # fault. Roughly one call in four when it does apply, so it stays a
    # closing jab rather than the whole call.
    if (detail.get("margin") or 0) >= _T["blowout"]:
        import random as _rc
        if _rc.random() < 0.25:
            f.append(_rc.choice(CHOSE_THIS))

    # THE CAITLIN STANDARD, rarely.
    #
    # Roughly one call in six, WNBA only. Capped in CODE because every
    # running joke on this project has been over-used the moment it was left
    # to a prompt - and a bit that fires every time is a tic.
    if (detail.get("league") or "").lower() == "wnba":
        import random as _r3
        if _r3.random() < 0.17:
            f.append(_r3.choice(CLARK_LINES))

    their = p.get("their_star")
    if their and (their.get("points") or 0) < _T["star"]:
        f.append(_named(LED_THEM, their["name"], their["points"], _used))
    elif their:
        bits = f"{their['points']} points on {their['fg']}"
        if their.get("rebounds"):
            bits += f", {int(their['rebounds'])} boards"
        # "their guy" in a WNBA recap is simply wrong, and a listener notices
        # immediately. The name alone does the job in either league.
        import random as _r
        _shapes = [x for x in DID_DAMAGE if x not in _used] or DID_DAMAGE
        _pick = _r.choice(_shapes)
        _used.add(_pick)
        f.append(_pick.format(name=their["name"], bits=bits))

    sh = detail.get("nba_shooting") or {}
    if sh.get("cold_night"):
        f.append(f"shot {sh['fg_pct']} percent as a team - the whole night was cold")
    if sh.get("cold_from_three"):
        f.append(f"{sh['three_pct']} percent from three")
    if sh.get("careless"):
        f.append(f"{sh['turnovers']} turnovers - gave it away all night")

    # The analytics line. NEVER a bare percentage - Smacky disputes it, he
    # does not recite it. Same rule as everywhere else.
    if detail.get("blew_it"):
        f.append(f"the analytics people had {l.get('team','them')} well ahead "
                 f"({detail.get('favoured_pct')}%) and they still lost - "
                 f"DISPUTE this, never state the number, you were never asked")
    elif detail.get("was_favoured"):
        f.append(f"the analytics people had {l.get('team','them')} favoured "
                 f"({detail.get('favoured_pct')}%) - DISPUTE it, never say the number")

    if detail.get("lost_at_home"):
        att = detail.get("attendance")
        f.append(f"lost at home in front of {att:,}" if att else "lost at home")

    return f


# ---------------------------------------------------------------------------
# The Smack Board - live scores
# ---------------------------------------------------------------------------
# Everything above reads FINISHED games. The board needs games in progress,
# which is a different filter on the same endpoint.
#
# Cached server-side and shared. A hundred people watching the board must not
# become a hundred requests to ESPN - that is how an unofficial endpoint
# stops answering you.

_BOARD_CACHE = {}          # league -> (fetched_at, games)
# 15s. The board is where somebody sits watching a close finish waiting to
# fire the moment it ends, and 45s made that feel broken - stacked with the
# client poll it was up to 90s behind.
#
# The cache is per-league, so this is one call to ESPN every 15 seconds no
# matter how many people are watching, not one per visitor.
# 30 seconds, not 15.
#
# At 15 the board alone was 20 requests a minute across five leagues -
# sustained, whenever anybody had the page open - which on a busy live
# evening put the total at 28 against a ceiling of 35. Too close.
#
# This is a SCOREBOARD, not a play-by-play. Nobody can tell the difference
# between a score that is 15 seconds old and one that is 30, and halving
# it buys back ten requests a minute for the things that actually need
# them - Locked & Loaded deciding whether somebody gets charged.
BOARD_CACHE_SECONDS = 30


def _rows_from_payload(data, lg):
    """
    Turn one ESPN scoreboard payload into display rows.

    Pulled out of fetch_board so the same parsing serves both today's games
    and the forward look-ahead when today is empty - two copies of this
    would drift apart the first time either was touched.
    """
    games = []
    for e in (data.get("events") or []):
        comps = e.get("competitions") or []
        if not comps:
            continue
        c = comps[0]
        sides = c.get("competitors") or []
        if len(sides) != 2:
            continue

        home = next((x for x in sides if x.get("homeAway") == "home"), sides[0])
        away = next((x for x in sides if x.get("homeAway") == "away"), sides[1])

        st = ((c.get("status") or {}).get("type") or {})
        state = st.get("state")            # pre | in | post

        def side(x):
            t = x.get("team") or {}
            rec = ""
            for r in (x.get("records") or []):
                if r.get("type") in ("total", "overall") or not rec:
                    rec = r.get("summary") or rec
            colour = t.get("color")
            return {
                "nick": t.get("name") or t.get("shortDisplayName") or "",
                "abbr": t.get("abbreviation") or "",
                "city": t.get("location") or "",
                "score": _int(x.get("score")),
                "record": rec,
                # ESPN gives colours without the hash.
                "colour": ("#" + colour) if colour and not colour.startswith("#") else colour,
                "logo": t.get("logo"),
            }

        h, a = side(home), side(away)

        # Who is behind right now. This is what the smack button points at,
        # and it is the whole reason the board exists.
        losing = None
        if state in ("in", "post") and h["score"] is not None and a["score"] is not None:
            if h["score"] < a["score"]:
                losing = "home"
            elif a["score"] < h["score"]:
                losing = "away"

        games.append({
            "espn_id": e.get("id"),
            "state": state,
            "final": state == "post",
            "live": state == "in",
            "upcoming": state == "pre",
            "status": st.get("shortDetail") or st.get("description") or "",
            "clock": (c.get("status") or {}).get("displayClock"),
            "period": (c.get("status") or {}).get("period"),
            "start": e.get("date"),
            "venue": ((c.get("venue") or {}).get("fullName")),
            "home": h, "away": a,
            "losing": losing,
        })

    # Live first, then upcoming, then finished - what somebody opening the
    # board actually wants to see in that order.
    return games


def fetch_board(league: str, force: bool = False) -> list:
    """
    Every game for a league today - live, finished and upcoming.

    Returns display-ready rows. Anything the endpoint does not give us is
    absent rather than guessed at, and a failure returns whatever was last
    cached rather than an empty board.
    """
    import time as _t

    lg = (league or "").lower()
    cfg = LEAGUE_PATHS.get(lg)
    if not cfg:
        return []

    cached = _BOARD_CACHE.get(lg)
    if cached and not force and (_t.time() - cached[0]) < BOARD_CACHE_SECONDS:
        return cached[1]

    sport_path, league_path = cfg[0], cfg[1]
    url = f"{BASE}/{sport_path}/{league_path}/scoreboard"

    # Through the gate. Falls back to the cached board when refused, which
    # is exactly right - a slightly stale scoreboard beats an empty one.
    from services import espn_gate
    data = espn_gate.get(url, timeout=12, label=f"board {lg}")
    if not data:
        return cached[1] if cached else []

    games = _rows_from_payload(data, lg)
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (order.get(g["state"], 3), g.get("start") or ""))

    # Nothing on today? Look forward a fortnight.
    #
    # ESPN's scoreboard defaults to today, and out of season that means an
    # empty board - or worse, for the NFL it quietly returns next week's
    # fixtures which then get labelled "today". A league with no game for
    # three days should show what is coming rather than nothing at all.
    if not games and fallback_url:
        try:
            from services import espn_gate
            _d2 = espn_gate.get(fallback_url, timeout=12,
                                label=f"board-ahead {lg}")
            if not _d2:
                raise ValueError("no data")
            games = _rows_from_payload(_d2, lg)
            games.sort(key=lambda g: g.get('start') or '')
            for g in games:
                # Flagged so the page can say UPCOMING rather than TODAY.
                g['future'] = True
        except Exception as e:
            print(f'[board] {lg} upcoming lookup failed: {e}', flush=True)
            games = []

    _BOARD_CACHE[lg] = (_t.time(), games)
    return games


# ---------------------------------------------------------------------------
# Ticker tags
# ---------------------------------------------------------------------------
# Two or three words of Smacky next to each game on the homepage ticker.
#
# Rules rather than a model call. The homepage is the busiest page on the site
# and a Claude call per visit would add cost and a second of latency - for
# three words. The score already carries the joke: down nine in the fourth is
# a different line from down one in the ninth, and that is all a tag this
# short needs to know.
#
# Several per bucket so the same game does not read identically on a refresh.

_TAGS = {
    "blowout_live":    ["MERCY. RING THEM.", "THIS IS ABUSE.",
                        "SOMEBODY CALL SOMEBODY.", "IT IS OVER. GO.", "PILE ON."],
    "comfortable_live":["COMFORTABLE. FOR NOW.", "SLIPPING AWAY.",
                        "GETTING UGLY.", "TROUBLE BREWING."],
    "close_live":      ["TOO CLOSE. WAIT.", "HOLD YOUR FIRE.",
                        "NOT YET.", "ARM IT INSTEAD."],
    "tied_live":       ["NOBODY IS WINNING.", "STALEMATE. BORING.",
                        "SOMEBODY DO SOMETHING."],
    "blowout_final":   ["HUMILIATING. RING THEM.", "THAT IS A CALL.",
                        "NO SURVIVORS.", "SEND IT NOW."],
    "final":           ["SOMEBODY LOST.", "GO ON THEN.", "RING THEM.", "THEY KNOW."],
    "close_final":     ["LOST BY ONE. BRUTAL.", "SO CLOSE. RING THEM.",
                        "THAT WILL STING."],
    "upcoming":        ["ARM IT NOW.", "SET THE TRAP.",
                        "BET AGAINST THEM.", "LOAD IT UP."],
}

# A hiding means different things by sport - nine runs is a massacre in
# baseball, nine points is a close game in basketball.
_BLOWOUT = {"mlb": 7, "nfl": 17, "ncaaf": 21, "nba": 20,
            "wnba": 18, "ncaab": 18, "ncaaw": 18, "nhl": 4}
_CLOSE   = {"mlb": 1, "nfl": 3, "ncaaf": 3, "nba": 4,
            "wnba": 4, "ncaab": 4, "ncaaw": 4, "nhl": 1}


def ticker_tag(game, league):
    """Two or three words of Smacky for one game."""
    import random

    lg = (league or "").lower()
    big, tight = _BLOWOUT.get(lg, 10), _CLOSE.get(lg, 2)

    if game.get("upcoming"):
        return random.choice(_TAGS["upcoming"])

    hs = (game.get("home") or {}).get("score")
    as_ = (game.get("away") or {}).get("score")
    if hs is None or as_ is None:
        return random.choice(_TAGS["upcoming"])

    margin = abs(hs - as_)

    if game.get("final"):
        if margin >= big:
            return random.choice(_TAGS["blowout_final"])
        if margin <= tight:
            return random.choice(_TAGS["close_final"])
        return random.choice(_TAGS["final"])

    if margin == 0:
        return random.choice(_TAGS["tied_live"])
    if margin >= big:
        return random.choice(_TAGS["blowout_live"])
    if margin <= tight:
        return random.choice(_TAGS["close_live"])
    return random.choice(_TAGS["comfortable_live"])


# ---------------------------------------------------------------------------
# Board quips — Smacky's line on each scoreboard card
# ---------------------------------------------------------------------------
# Two or three words under the score. Same reasoning as the ticker tags:
# rules, not a model call, because the board refreshes every 15 seconds and a
# Claude call per card per refresh would be absurd. The score already carries
# the joke.
#
# Twenty-odd per bucket because twelve cards are on screen at once and a pool
# of five would visibly repeat - the same sameness problem flagged for the
# generators, just more obvious here because they sit side by side.
#
# board_quips() deals WITHOUT REPLACEMENT across one response, so no two
# visible cards can carry the same line.

_QUIPS = {
    # Nil. The funniest thing on any scoreboard and worth its own bucket -
    # "goose egg" only works at zero.
    "shutout_final": [
        "GOOSE EGG.", "NOTHING. ZERO. NIL.", "THEY NEVER SHOWED UP.",
        "SCORELESS AND SPEECHLESS.", "NOT ONE.", "BLANKED.",
        "A WHOLE LOT OF NOTHING.", "THEY FORGOT TO SCORE.",
        "SHUT OUT AND SHUT UP.", "ZERO. IN INK.",
        "NO RUNS, NO HITS, NO DIGNITY.", "THE SCOREBOARD IS EMBARRASSED.",
        "COULD NOT BUY ONE.", "COMPLETELY BLANK.", "NIL. ABSOLUTELY NIL.",
        "THEY BROUGHT NOTHING.", "SCORELESS. RUTHLESS.",
        "A DONUT ON THE BOARD.", "NOT A SINGLE ONE.", "EMPTY-HANDED.",
    ],
    "shutout_live": [
        "STILL NOTHING.", "GOOSE EGG SO FAR.", "SCORELESS AND SINKING.",
        "NOT ON THE BOARD YET.", "STILL WAITING.", "NOTHING DOING.",
        "BLANK SO FAR.", "ZERO AND FALLING.", "THEY HAVE NOT STARTED.",
        "NO SIGN OF LIFE.", "STILL EMPTY.", "NOT A ONE.",
        "SOMEBODY SCORE.", "COMPLETELY SHUT DOWN.", "NOTHING ON THE BOARD.",
        "STILL ON ZERO.", "NO REPLY.", "SILENT SO FAR.",
        "NOT TROUBLING THE SCORER.", "SCORELESS AND SHRINKING.",
    ],
    "blowout_live": [
        "MERCY.", "THIS IS ABUSE.", "IT IS OVER.", "PILE ON.",
        "SOMEBODY STOP IT.", "GETTING EMBARRASSING.", "NO CONTEST.",
        "CALL IT OFF.", "ABSOLUTE DEMOLITION.", "THEY GAVE UP.",
        "RUNNING RIOT.", "COMPLETELY OUTCLASSED.", "TURN IT OFF.",
        "THIS IS NOT A GAME.", "TAKING A BEATING.", "TOTAL COLLAPSE.",
        "NOTHING LEFT.", "TIME TO GO HOME.", "OUT OF THEIR DEPTH.",
        "SOMEBODY CALL SOMEBODY.",
    ],
    "comfortable_live": [
        "SLIPPING AWAY.", "GETTING UGLY.", "TROUBLE BREWING.",
        "COMFORTABLE. FOR NOW.", "STARTING TO HURT.", "PULLING CLEAR.",
        "GOING THE WRONG WAY.", "IN CONTROL.", "LOSING THE THREAD.",
        "DRIFTING.", "THIS IS TURNING.", "STRETCHING THE LEAD.",
        "SLOWLY UNRAVELLING.", "NOT LOOKING GOOD.", "IN CHARGE.",
        "STARTING TO SHOW.", "THE GAP IS GROWING.", "FALLING BEHIND.",
        "LOOKING SHAKY.", "ONE-WAY TRAFFIC.",
    ],
    "close_live": [
        "TOO CLOSE. WAIT.", "HOLD YOUR FIRE.", "NOT YET.",
        "ARM IT INSTEAD.", "ANYONE'S GAME.", "TIGHT ONE.",
        "STILL ANYBODY'S.", "NOTHING IN IT.", "COMING DOWN TO THE WIRE.",
        "PATIENCE.", "TOO EARLY TO GLOAT.", "NECK AND NECK.",
        "SIT ON YOUR HANDS.", "STILL LIVE.", "ONE SCORE EITHER WAY.",
        "DO NOT JINX IT.", "KNIFE EDGE.", "NOT DECIDED.",
        "WAIT FOR IT.", "STILL IN THE BALANCE.",
    ],
    "tied_live": [
        "NOBODY'S WINNING.", "STALEMATE.", "SOMEBODY DO SOMETHING.",
        "DEADLOCKED.", "ALL SQUARE.", "NOTHING BETWEEN THEM.",
        "LEVEL PEGGING.", "SOMEBODY BREAK IT.", "PERFECTLY EVEN.",
        "NEITHER WILL BUDGE.", "STUCK.", "DEAD EVEN.",
        "NOBODY BLINKING.", "TIED AND TENSE.", "STILL EQUAL.",
        "NOT A THING IN IT.", "TOTAL DEADLOCK.", "EVEN STEVENS.",
        "SOMEBODY TAKE CHARGE.", "SQUARE AND SILENT.",
    ],
    "blowout_final": [
        "HUMILIATING.", "NO SURVIVORS.", "THAT IS A CALL.",
        "SEND IT NOW.", "COMPLETELY DISMANTLED.", "NOT A CONTEST.",
        "ABSOLUTE HIDING.", "THEY WERE DESTROYED.", "CALL IT OFF.",
        "TOTAL WIPEOUT.", "BRUTAL.", "NOWHERE NEAR IT.",
        "A MASSACRE.", "THAT IS EMBARRASSING.", "NOT EVEN CLOSE.",
        "THOROUGHLY BEATEN.", "TAKEN APART.", "NO EXCUSES LEFT.",
        "SOMEBODY OWES AN APOLOGY.", "OUTCLASSED ALL DAY.",
    ],
    "close_final": [
        "LOST BY ONE. BRUTAL.", "SO CLOSE.", "THAT WILL STING.",
        "AGONISING.", "THEY WILL FEEL THAT.", "INCHES AWAY.",
        "CRUEL.", "THAT ONE HURTS.", "NEARLY. NOT QUITE.",
        "HEARTBREAKER.", "ONE SCORE SHORT.", "GUTTING.",
        "SO NEARLY.", "THAT IS A LONG DRIVE HOME.", "PAINFULLY CLOSE.",
        "A WHISKER.", "THEY HAD IT.", "LOST IT LATE.",
        "THAT WILL KEEP THEM UP.", "MARGINS.",
    ],
    "final": [
        "SOMEBODY LOST.", "GO ON THEN.", "RING THEM.", "THEY KNOW.",
        "THAT IS THAT.", "DONE AND DUSTED.", "TIME TO CALL.",
        "IT IS SETTLED.", "NO ARGUMENT.", "BEATEN.",
        "THE BOOKS ARE CLOSED.", "ALL OVER.", "NOTHING TO DISCUSS.",
        "RESULT IS IN.", "THEY LOST. FACT.", "FINAL AND FILED.",
        "SOMEBODY IS QUIET TONIGHT.", "THAT IS ON THE RECORD.",
        "GAME OVER.", "NO COMING BACK.",
    ],
    "upcoming": [
        "PICK A LOSER.", "ARM IT NOW.", "SET THE TRAP.",
        "BET AGAINST THEM.", "LOAD IT UP.", "CHOOSE A SIDE.",
        "SOMEBODY WILL LOSE.", "GET AHEAD OF IT.", "LINE ONE UP.",
        "READY WHEN THEY ARE.", "CALL IT EARLY.", "PLACE YOUR BET.",
        "ONE OF THEM GOES HOME SAD.", "SET IT AND FORGET IT.",
        "WAITING ON A WINNER.", "SOMEBODY IS ABOUT TO REGRET THIS.",
        "LOCK IT IN.", "DECIDE NOW, LAUGH LATER.",
        "PICK THE ONE WHO FOLDS.", "GET IT ARMED.",
    ],
}


def _quip_bucket(game, league):
    """Which pool this game's situation belongs to."""
    lg = (league or "").lower()
    big = _BLOWOUT.get(lg, 10)
    tight = _CLOSE.get(lg, 2)

    if game.get("upcoming"):
        return "upcoming"

    hs = (game.get("home") or {}).get("score")
    as_ = (game.get("away") or {}).get("score")
    if hs is None or as_ is None:
        return "upcoming"

    margin = abs(hs - as_)
    loser_scored = min(hs, as_)
    final = bool(game.get("final"))

    # Nil gets its own bucket - it is the funniest thing on a scoreboard and
    # "goose egg" makes no sense at any other score.
    if loser_scored == 0 and margin > 0:
        return "shutout_final" if final else "shutout_live"

    if final:
        if margin >= big:
            return "blowout_final"
        if margin <= tight:
            return "close_final"
        return "final"

    if margin == 0:
        return "tied_live"
    if margin >= big:
        return "blowout_live"
    if margin <= tight:
        return "close_live"
    return "comfortable_live"


def board_quips(games, league):
    """
    A line for every game on the board, with NO TWO THE SAME.

    Dealt without replacement across the whole response. Twelve cards drawing
    independently from one pool would repeat visibly, which on a grid where
    they sit side by side looks like the site only knows five jokes.
    """
    import random

    used = set()
    out = []
    for g in games:
        bucket = _quip_bucket(g, league)

        # Who is losing, by nickname. Upcoming games have no loser, and a
        # tie has no single one either - both fall back to generic.
        loser = None
        if g.get("losing") == "home":
            loser = (g.get("home") or {}).get("nick")
        elif g.get("losing") == "away":
            loser = (g.get("away") or {}).get("nick")

        # Mixed rather than replaced. Every card naming a team reads like a
        # template; roughly half and half keeps it varied while still telling
        # somebody scanning the board WHICH fan is having a bad night.
        named = _team_quip_pool(bucket, loser)
        generic = _QUIPS.get(bucket, [])
        pool = (named + generic) if (named and random.random() < 0.55) else (generic + named)

        fresh = [q for q in pool if q not in used]
        if not fresh:                      # exhausted - allow reuse
            fresh = pool or ["\u2014"]
        pick = random.choice(fresh)
        used.add(pick)
        out.append(pick)
    return out


# ---------------------------------------------------------------------------
# Quips that name the losing team
# ---------------------------------------------------------------------------
# "CARDINALS GOT DESTROYED" says more than "HUMILIATING" - it tells somebody
# scanning the board which fan is having a bad night, which is the whole
# reason they are looking.
#
# Mixed with the generic pool rather than replacing it. Every card naming a
# team reads like a template; roughly half and half keeps it varied.
#
# {t} is the losing side's nickname, already stripped of the city.

_TEAM_QUIPS = {
    "shutout_final": [
        "{t} SCORED NOTHING.", "{t} GOT BLANKED.", "NOT ONE FOR {t}.",
        "{t} FORGOT TO SCORE.", "{t}: A BIG FAT ZERO.",
        "{t} NEVER SHOWED UP.", "SHUT OUT: {t}.",
        "{t} BROUGHT NOTHING.", "{t} GOT SHUT DOWN.",
        "A GOOSE EGG FOR {t}.", "{t} MANAGED ZERO.", "{t} DREW A BLANK.",
    ],
    "shutout_live": [
        "{t} STILL ON ZERO.", "NOTHING FROM {t} YET.",
        "{t} CANNOT BUY ONE.", "STILL NOTHING FOR {t}.",
        "{t} ARE INVISIBLE.", "NO SIGN OF {t}.",
        "{t} HAVE NOT STARTED.", "{t}: STILL BLANK.",
        "SOMEBODY WAKE {t} UP.", "{t} ARE NOT TROUBLING ANYONE.",
        "{t} STILL WAITING.", "NOT A ONE FROM {t}.",
    ],
    "blowout_live": [
        "{t} GETTING DESTROYED.", "{t} ARE COOKED.",
        "SOMEBODY STOP THIS FOR {t}.", "{t} HAVE GIVEN UP.",
        "{t} ARE BEING DISMANTLED.", "MERCY ON {t}.",
        "{t} ARE OUT OF THEIR DEPTH.", "{t} HAVE COLLAPSED.",
        "IT IS OVER FOR {t}.", "{t} ARE TAKING A BEATING.",
        "{t} SHOULD GO HOME.", "{t} ARE GETTING RUN OVER.",
    ],
    "comfortable_live": [
        "{t} ARE SLIPPING.", "TROUBLE FOR {t}.",
        "{t} ARE FADING.", "GETTING AWAY FROM {t}.",
        "{t} ARE IN BOTHER.", "{t} LOSING THE THREAD.",
        "NOT LOOKING GOOD FOR {t}.", "{t} ARE DRIFTING.",
        "{t} ARE BEHIND AND SINKING.", "{t} NEED SOMETHING.",
        "{t} ARE LOOKING SHAKY.", "{t} ARE CHASING IT.",
    ],
    "close_live": [
        "{t} ARE STILL IN IT.", "TOO CLOSE TO CALL ON {t}.",
        "{t} HANGING ON.", "NOT OVER FOR {t} YET.",
        "{t} ARE RIGHT THERE.", "GIVE {t} A MINUTE.",
        "{t} COULD STILL DO IT.", "HOLD OFF ON {t}.",
        "{t} ARE NOT DONE.", "{t} ARE CLINGING ON.",
        "STILL ANYONE'S, {t} INCLUDED.", "WAIT ON {t}.",
    ],
    "blowout_final": [
        "{t} GOT DESTROYED.", "{t} GOT TAKEN APART.",
        "{t} NEVER STOOD A CHANCE.", "{t} GOT HUMILIATED.",
        "{t} WERE NOWHERE NEAR IT.", "{t} GOT ROLLED.",
        "{t} GOT DISMANTLED.", "{t} WERE OUTCLASSED.",
        "SOMEBODY CHECK ON {t}.", "{t} GOT WIPED OUT.",
        "{t} LOST IT BADLY.", "A MASSACRE FOR {t}.",
    ],
    "close_final": [
        "{t} LOST IT LATE.", "{t} WILL FEEL THAT ONE.",
        "{t} CAME UP SHORT.", "{t} HAD IT AND LOST IT.",
        "CRUEL ON {t}.", "{t} FELL A SCORE SHORT.",
        "{t} WERE INCHES AWAY.", "{t} LOST BY A WHISKER.",
        "AGONISING FOR {t}.", "{t} SO NEARLY HAD IT.",
        "{t} LOST THE TIGHT ONE.", "THAT ONE HURTS {t}.",
    ],
    "final": [
        "{t} LOST.", "{t} GOT BEATEN.", "{t} ARE QUIET TONIGHT.",
        "BAD NIGHT FOR {t}.", "{t} WENT DOWN.",
        "{t} HAVE NO ARGUMENT.", "IT IS ON THE RECORD: {t} LOST.",
        "{t} GOT DONE.", "{t} FANS WILL NOT WANT TO TALK.",
        "{t} CAME SECOND.", "{t} LOST. FACT.", "NOTHING FOR {t}.",
    ],
}


def _team_quip_pool(bucket, loser_nick):
    """Team-named phrases for this bucket, filled in, or empty if unusable."""
    if not loser_nick:
        return []
    nick = str(loser_nick).strip().upper()
    if not nick or len(nick) > 16:      # long names wrap and ruin the card
        return []
    return [q.replace("{t}", nick) for q in _TEAM_QUIPS.get(bucket, [])]


def game_result(league: str, event_id: str) -> dict | None:
    """
    Who won, from ESPN, for one specific game.

    Locked & Loaded has been deciding this from SportsDataIO, whose free tier
    scrambles scores by roughly 2.5x. The winner survived that - which is why
    it worked at all - but "who lost" surviving a scrambled score is luck, not
    a guarantee, and this is the one place on the site where getting it wrong
    costs somebody real money and needs a refund.

    ESPN is already used for the roast facts on the very same call. It should
    decide the outcome too.

    Returns None while the game is unfinished, so the caller keeps polling.
    """
    import json as _json
    from urllib.request import Request, urlopen

    cfg = LEAGUE_PATHS.get((league or "").lower())
    if not cfg or not event_id:
        return None
    sport_path, league_path = cfg[0], cfg[1]

    url = (f"{BASE}/{sport_path}/{league_path}/summary?event={event_id}")
    # Through the gate. This one decides whether a Locked & Loaded call
    # fires and whether somebody gets charged, so it must fail CLEANLY -
    # returning None keeps the caller polling rather than firing on a
    # guess, which is exactly the right behaviour when ESPN is unavailable.
    from services import espn_gate
    # CRITICAL. This decides whether a Locked & Loaded call fires and
    # whether somebody is charged or refunded. It gets the reserved budget
    # that scoreboard refreshes cannot touch.
    d = espn_gate.fetch(url, timeout=12, label=f"result {event_id}",
                        critical=True)
    if not d:
        return None

    comp = (((d.get("header") or {}).get("competitions") or [{}])[0])
    status = (((comp.get("status") or {}).get("type") or {}))
    state = (status.get("state") or "").lower()

    if status.get("name", "").upper() in ("STATUS_POSTPONED", "STATUS_CANCELED"):
        return {"status": "postponed"}
    if state != "post" or not status.get("completed"):
        return None                     # still going - poll again

    sides = comp.get("competitors") or []
    if len(sides) != 2:
        return None

    def name(c):
        t = c.get("team") or {}
        return t.get("name") or t.get("shortDisplayName") or t.get("displayName") or ""

    try:
        a, b = sides[0], sides[1]
        sa, sb = int(a.get("score")), int(b.get("score"))
    except (TypeError, ValueError):
        return None

    if sa == sb:
        return {"status": "tie"}

    win, lose = (a, b) if sa > sb else (b, a)
    home = next((c for c in sides if c.get("homeAway") == "home"), sides[0])
    away = next((c for c in sides if c.get("homeAway") == "away"), sides[1])

    return {
        "status": "final",
        "winner": name(win),
        "loser": name(lose),
        "home_team": name(home),
        "away_team": name(away),
        "home_score": int(home.get("score") or 0),
        "away_score": int(away.get("score") or 0),
        "source": "espn",
    }


# ---------------------------------------------------------------------------
# Hockey
# ---------------------------------------------------------------------------
#
# NHL was armable but had NO fact path at all - roast_facts fell through and
# returned nothing, so a Locked & Loaded on a hockey game got the scoreline
# and silence. The same fault the WNBA had, for a different reason.

NHL_GOALIE = [
    "your goalie {name} let in {goals} on {shots} shots",
    "{name} faced {shots} and {goals} got past. Do the arithmetic",
    "{goals} goals on {shots} shots for {name}. That is a save percentage "
    "you can hear",
    "{name} was in net for all {goals} of those",
    "somebody should check whether {name} knew the game had started - "
    "{goals} on {shots}",
]

NHL_SCORER = [
    "you let {name} put up {pts} on you",
    "{name} had {pts} and your defence watched",
    "{pts} for {name}, and nobody laid a glove on them",
    "{name} did what they liked out there: {pts}",
]

NHL_SHUTOUT = [
    "you were shut out. Sixty minutes and not one goal",
    "zero. On the scoreboard, all night. Sixty full minutes of nothing",
    "a shutout. You did not manage a single goal in an entire hockey game",
]

NHL_SHOTS = [
    "{shots} shots and nothing to show for it",
    "you took {shots} shots and scored {goals}. Volume is not the problem",
    "{shots} attempts, {goals} of them went in. Somebody will watch that tape",
]


def nhl_roast_facts(detail: dict) -> list:
    """
    Hockey's own hierarchy: the goalie answers for it, then whoever did the
    damage, then the shot count.

    Deliberately NOT bent into the basketball shape - a goalie is not a
    point guard and "plus-minus" means something different on ice.
    """
    import random as _r

    f = []
    w = detail.get("winner") or {}
    l = detail.get("loser") or {}
    if w.get("team") and l.get("team"):
        f.append(f"{w['team']} beat {l['team']}")
    if l.get("record"):
        f.append(f"{l['team']} are now {l['record']}")

    m = detail.get("margin")
    if detail.get("one_goal") or m == 1:
        f.append("lost it by a single goal")
    elif m and m >= 5:
        f.append(f"lost by {m} - not close at any point")

    h = detail.get("nhl") or {}
    used = set()

    def pick(pool, **kw):
        fresh = [x for x in pool if x not in used] or pool
        line = _r.choice(fresh)
        used.add(line)
        return line.format(**kw)

    if h.get("shutout"):
        f.append(pick(NHL_SHUTOUT))

    g = h.get("goalie")
    if g and g.get("name") and g.get("goals_against") is not None:
        f.append(pick(NHL_GOALIE, name=g["name"], goals=g["goals_against"],
                      shots=g.get("shots_faced") or "a pile of"))

    for s in (h.get("their_scorers") or [])[:2]:
        if s.get("points"):
            f.append(pick(NHL_SCORER, name=s["name"], pts=s["points"]))

    # "1 goals" read aloud is wrong, and this is spoken audio.
    if h.get("shots") and (h.get("goals") is not None):
        if h["shots"] >= 25 and h["goals"] <= 1:
            f.append(pick(NHL_SHOTS, shots=h["shots"], goals=h["goals"]))

    return f


def nhl_detail(d, losing_team, winning_team):
    """Goalie, scorers and shot totals from an NHL box score."""
    out = {"goalie": None, "their_scorers": [], "shots": None, "goals": None,
           "shutout": False}

    for block in ((d.get("boxscore") or {}).get("players") or []):
        team = (block.get("team") or {})
        nick = team.get("name") or team.get("shortDisplayName") or ""
        losing = nick.lower() == str(losing_team or "").lower()
        winning = nick.lower() == str(winning_team or "").lower()
        if not (losing or winning):
            continue

        for group in (block.get("statistics") or []):
            labels = [str(x).upper() for x in (group.get("labels") or [])]
            name_l = (group.get("name") or "").lower()

            for ath in (group.get("athletes") or []):
                nm = ((ath.get("athlete") or {}).get("displayName") or "")
                if not nm:
                    continue
                st = _stat_map(labels, ath.get("stats") or [])

                # The losing goalie wears it.
                if losing and ("goalie" in name_l or "SA" in labels):
                    ga = _to_num(st.get("GA"))
                    sa = _to_num(st.get("SA"))
                    if ga is not None and (out["goalie"] is None
                                           or ga > (out["goalie"]["goals_against"] or 0)):
                        out["goalie"] = {"name": nm,
                                         "goals_against": int(ga),
                                         "shots_faced": int(sa) if sa else None}
                # Who did the damage.
                elif winning:
                    pts = _to_num(st.get("P")) or _to_num(st.get("PTS"))
                    if pts and pts >= 2:
                        out["their_scorers"].append({"name": nm,
                                                     "points": int(pts)})

    out["their_scorers"].sort(key=lambda x: -x["points"])
    return out


# ---------------------------------------------------------------------------
# ELSEWHERE - everything that is not a main block
# ---------------------------------------------------------------------------
#
# One minute of the show for whatever else happened. These sports do not
# play daily, or do not carry enough weight for a block of their own, but a
# UFC knockout or a Premier League thrashing is worth twenty seconds.
#
# It also solves a seasonal problem. In August only baseball and the WNBA
# are running, which is why a real episode had eleven games in it. This
# fills that gap without waiting for the NFL.

ELSEWHERE_PATHS = {
    # Head-to-head, so there is always a loser to roast.
    "nfl_pre": ("football", "nfl", "NFL PRESEASON"),
    "mls":     ("soccer", "usa.1", "MLS"),
    "epl":     ("soccer", "eng.1", "PREMIER LEAGUE"),
    "ucl":     ("soccer", "uefa.champions", "CHAMPIONS LEAGUE"),
    "ufc":     ("mma", "ufc", "UFC"),
}


def fetch_elsewhere(days_back: int = 1, limit: int = 6) -> list:
    """
    A handful of results from everything outside the main blocks.

    Deliberately shallow - the scoreline and nothing else. This gets about
    a minute of the show, which is four or five one-liners, so fetching
    box scores for it would be work nobody hears.

    Returns [] on any failure. A show that loses this segment is a show
    that is slightly shorter, which is not a problem worth an exception.
    """
    import json as _json
    from urllib.request import Request, urlopen

    day = datetime.now(EASTERN) - timedelta(days=days_back)
    date_str = day.strftime("%Y%m%d")
    out = []

    for key, (sport_path, league_path, label) in ELSEWHERE_PATHS.items():
        # Through the gate. This one loops five leagues, so it is exactly
        # the shape of thing that should not be able to run away with the
        # budget - and losing it costs a minute of the show, nothing more.
        from services import espn_gate
        url = (f"{BASE}/{sport_path}/{league_path}/scoreboard"
               f"?dates={date_str}")
        d = espn_gate.fetch(url, timeout=8, label=f"elsewhere {key}")
        if not d:
            continue

        for ev in (d.get("events") or [])[:4]:
            comp = ((ev.get("competitions") or [{}])[0])
            status = ((comp.get("status") or {}).get("type") or {})
            if not status.get("completed"):
                continue
            sides = comp.get("competitors") or []
            if len(sides) != 2:
                continue

            def nm(c):
                t = c.get("team") or c.get("athlete") or {}
                return (t.get("shortDisplayName") or t.get("displayName")
                        or t.get("name") or "")

            try:
                a, b = sides[0], sides[1]
                sa = int(a.get("score") or 0)
                sb = int(b.get("score") or 0)
            except (TypeError, ValueError):
                continue

            if not nm(a) or not nm(b):
                continue

            if sa == sb:
                out.append({"league": label, "drawn": True,
                            "a": nm(a), "b": nm(b), "score": f"{sa}-{sb}"})
            else:
                w, l = (a, b) if sa > sb else (b, a)
                out.append({
                    "league": label,
                    "winner": nm(w),
                    "loser": nm(l),
                    "score": f"{max(sa, sb)}-{min(sa, sb)}",
                    "margin": abs(sa - sb),
                })

    # Spread across sports rather than four football results and nothing
    # else - the point of this segment is breadth.
    spread, seen = [], {}
    for row in out:
        n = seen.get(row["league"], 0)
        if n < 2:
            spread.append(row)
            seen[row["league"]] = n + 1
    return spread[:limit]


# ---------------------------------------------------------------------------
# ONE CALL PER LEAGUE, NOT ONE PER GAME
# ---------------------------------------------------------------------------
#
# Locked & Loaded polls for results every two minutes and made a request PER
# GAME. Fifteen armed games meant fifteen requests every two minutes -
# traffic that scales with how well the product is selling, which is exactly
# the wrong way round.
#
# A single scoreboard call returns EVERY game in the league at once. Fifteen
# calls become one, and it stays one whether five games are armed or fifty.
#
# This is the difference between "fine at current traffic" and not having to
# think about it again.

_RESULTS_CACHE = {}      # league -> (fetched_at, {event_id: result})
_RESULTS_TTL = 45        # a finished game does not un-finish


def league_results(league: str) -> dict:
    """
    Every finished game in a league right now, keyed by event id.

    One request, cached briefly. Returns {} if unavailable, which leaves
    callers polling rather than guessing - the correct behaviour when money
    depends on the answer.
    """
    lg = (league or "").lower()
    cfg = LEAGUE_PATHS.get(lg)
    if not cfg:
        return {}

    # time is imported locally elsewhere in this module rather than at the
    # top, so it must be imported here too - without this every call raised
    # NameError and fell straight through to the per-game path, quietly
    # undoing the batching.
    import time as _time
    now = _time.time()
    hit = _RESULTS_CACHE.get(lg)
    if hit and (now - hit[0]) < _RESULTS_TTL:
        return hit[1]

    sport_path, league_path = cfg[0], cfg[1]
    url = f"{BASE}/{sport_path}/{league_path}/scoreboard"

    from services import espn_gate
    # Critical: this is what decides whether somebody gets charged.
    d = espn_gate.get(url, timeout=12, label=f"results {lg}", critical=True)
    if not d:
        # Keep serving the last good answer rather than reporting no
        # finished games, which would look like every game is still running.
        return hit[1] if hit else {}

    out = {}
    for ev in (d.get("events") or []):
        comp = ((ev.get("competitions") or [{}])[0])
        status = ((comp.get("status") or {}).get("type") or {})
        if not status.get("completed"):
            continue
        sides = comp.get("competitors") or []
        if len(sides) != 2:
            continue
        try:
            a, b = sides[0], sides[1]
            sa, sb = int(a.get("score") or 0), int(b.get("score") or 0)
        except (TypeError, ValueError):
            continue
        if sa == sb:
            continue

        def _nm(c):
            t = c.get("team") or {}
            return (t.get("displayName") or t.get("shortDisplayName")
                    or t.get("name") or "")

        w, l = (a, b) if sa > sb else (b, a)
        out[str(ev.get("id"))] = {
            "final": True,
            "winner": _nm(w), "loser": _nm(l),
            "winner_score": max(sa, sb), "loser_score": min(sa, sb),
            "margin": abs(sa - sb),
        }

    _RESULTS_CACHE[lg] = (now, out)
    print(f"[espn] {lg}: {len(out)} finished game(s) in one call", flush=True)
    return out
