"""
Full, human-style team names for search — "New York Yankees", not "Yankees";
"UNLV Rebels", not nothing at all.

Two sources feed this:

* CHAT_LEAGUES (services/chat_team_lists.py) for the pro leagues and soccer.
  It stores the mascot alone ("Yankees"), which can't be found by typing
  "new", so the city is recovered from the alias table.
* NCAA_D1 (services/ncaa_d1.py) for college. CHAT_LEAGUES only ever held the
  four power football conferences and a hand-picked slice of basketball, so
  UNLV, Boise State, Notre Dame football, Navy, Memphis and about a hundred
  more schools simply weren't there to find.

A school appears once per sport it plays, because that's the question being
asked: "Florida Gators / SEC Football" and "Florida Gators / SEC Baseball"
are different teams to trash-talk about.

Nothing here hits the network or the database — it is derived once at import
from data already in the repo.
"""

from services import team_aliases, chat_team_lists, ncaa_d1

# Leagues whose CHAT_LEAGUES names are mascot-only and need a city prefix.
_NEEDS_CITY = ("nfl", "nba", "mlb", "nhl", "wnba")

# Everything in CHAT_LEAGUES that college data does NOT replace. The four
# conference keys and ncaab/ncaawb are deliberately absent: they're now built
# from ncaa_d1 instead, which covers every Division I school rather than 67.
_FROM_CHAT = ("nfl", "nba", "mlb", "nhl", "wnba",
              "mls", "epl", "laliga", "bundesliga", "seriea", "world_cup")

LEAGUE_LABELS = {
    "nfl": "NFL", "nba": "NBA", "mlb": "MLB", "nhl": "NHL", "wnba": "WNBA",
    "world_cup": "World Cup",
    "mls": "MLS", "epl": "Premier League", "laliga": "La Liga",
    "bundesliga": "Bundesliga", "seriea": "Serie A",
}

# A handful of pro teams have no usable alias entry to derive a city from.
_EXPLICIT = {
    ("wnba", "CON"): "Connecticut Sun",
    ("wnba", "GS"): "Golden State Valkyries",
    ("wnba", "PHO"): "Phoenix Mercury",
    ("wnba", "WAS"): "Washington Mystics",
}

_UPPER = {"fc", "cf", "sc", "ac", "afc", "ny", "la", "dc", "usc", "ucla",
          "lsu", "tcu", "smu", "byu", "unlv", "ucf", "vcu"}


def _title(s):
    out = []
    for w in s.split():
        if w in _UPPER:
            out.append(w.upper())
        elif w[0].isdigit():          # "49ers" must not become "49Ers"
            out.append(w)
        else:
            out.append(w[0].upper() + w[1:])
    return " ".join(out)


def _derive_pro(league, code, short):
    if (league, code) in _EXPLICIT:
        return _EXPLICIT[(league, code)]
    aliases = [a.lower() for a in team_aliases.TEAM_ALIASES.get(league, {}).get(code, [])]
    s = short.lower()
    # Prefer an alias that already reads as "<city> <mascot>". Longest wins so
    # we get "new york yankees" not "ny yankees" - and requiring it to END in
    # the mascot skips stale entries (the NHL table still lists "utah hockey
    # club", which no longer matches "mammoth").
    ending = [a for a in aliases if a.endswith(s) and len(a) > len(s)]
    if ending:
        return _title(max(ending, key=len))
    city = [a for a in aliases if a != s and s not in a and a not in s]
    if city:
        return _title(max(city, key=len) + " " + s)
    return None


def _pro_aliases(league, code, short, full):
    """
    Everything worth matching against but not displaying. Includes the display
    name itself, which matters: the server matches games with `query in alias`,
    so a longer name typed into the box has to exist as an alias or the
    Auto-Smack game lookup finds nothing.
    """
    seen = {a.lower() for a in team_aliases.TEAM_ALIASES.get(league, {}).get(code, [])}
    seen.add(short.lower())
    seen.add(full.lower())
    seen.discard("")
    return sorted(seen)


def _pro_teams():
    out = []
    for league in _FROM_CHAT:
        for code, short in chat_team_lists.CHAT_LEAGUES.get(league, {}).items():
            if league in _NEEDS_CITY:
                full = _derive_pro(league, code, short) or short
            else:
                full = short
            out.append({
                "code": code,
                "name": full,
                "short": short,
                "league": league,
                "league_label": LEAGUE_LABELS.get(league, league.upper()),
                "aliases": _pro_aliases(league, code, short, full),
            })
    return out


# Each college sport: the membership table, the sport key the game lookup
# uses, and how the badge reads. FCS is called out because otherwise "Patriot
# Football" and "Patriot Men's Basketball" are the only clue that one of them
# is a different division entirely.
_COLLEGE_SPORTS = (
    ("ncaaf",    ncaa_d1.FOOTBALL_FBS, "{conf} Football"),
    ("ncaaf",    ncaa_d1.FOOTBALL_FCS, "{conf} Football (FCS)"),
    ("ncaab",    ncaa_d1.BASKETBALL,   "{conf} Men's Basketball"),
    ("ncaabase", ncaa_d1.BASEBALL,     "{conf} Baseball"),
)


def _college_code(sport, key, suffix):
    """
    The code SportsDataIO sends for this school, when we know it.

    Only schools with a feed code can be joined to a live game. For the rest
    we mint a stable internal code so the entry still has an identity - the
    search itself runs against the name and aliases, not the code, so those
    schools are fully findable; it's the game lookup that can't reach them.
    """
    real = ncaa_d1.FEED_CODES.get(sport, {}).get(key)
    if real:
        return real
    slug = "".join(c for c in key.upper() if c.isalnum())[:10]
    return slug + suffix


def _college_teams():
    out = []
    for sport, table, label in _COLLEGE_SPORTS:
        suffix = "-BSB" if sport == "ncaabase" else ("-FB" if "Football" in label else "-BB")
        for key, conf in table.items():
            school, mascot = ncaa_d1.SCHOOLS[key]
            full = school + " " + mascot
            # Aliases carry the pieces someone might actually type: the school
            # on its own, the mascot on its own, the full name, and whatever
            # the feed already knew this team by.
            aliases = {school.lower(), mascot.lower(), full.lower(), key.lower()}
            code = _college_code(sport, key, suffix)
            for a in team_aliases.TEAM_ALIASES.get(sport, {}).get(code, []):
                aliases.add(a.lower())
            aliases.discard("")
            out.append({
                "code": code,
                "name": full,
                "short": school,
                "league": sport,
                "league_label": label.format(conf=conf),
                "aliases": sorted(aliases),
            })

    # Women's basketball still comes from CHAT_LEAGUES - there is no D1-wide
    # women's table here yet - but it can at least borrow the conference so
    # the badge says something useful instead of just "NCAAWB".
    by_school = {v[0]: k for k, v in ncaa_d1.SCHOOLS.items()}
    for code, short in chat_team_lists.CHAT_LEAGUES.get("ncaawb", {}).items():
        key = by_school.get(short)
        conf = ncaa_d1.BASKETBALL.get(key) if key else None
        mascot = ncaa_d1.SCHOOLS[key][1] if key else None
        full = (short + " " + mascot) if mascot else short
        aliases = {short.lower(), full.lower()}
        for a in team_aliases.TEAM_ALIASES.get("ncaawb", {}).get(code, []):
            aliases.add(a.lower())
        if mascot:
            aliases.add(mascot.lower())
        aliases.discard("")
        out.append({
            "code": code,
            "name": full,
            "short": short,
            "league": "ncaawb",
            "league_label": ("%s Women's Basketball" % conf) if conf else "NCAA Women's Basketball",
            "aliases": sorted(aliases),
        })
    return out


# Football first, then men's hoops, then baseball, then the rest - so a school
# that plays several sports lists its sports in a predictable order instead of
# alphabetically by conference name.
_SPORT_ORDER = {"ncaaf": 0, "ncaab": 1, "ncaabase": 2, "ncaawb": 3}


def _trim(team):
    """
    Drop aliases the browser would never need.

    The client already scores a bare substring of the name (and the code and
    the short name), so an alias contained in one of those can only ever
    duplicate a match it would make anyway - and it costs bytes on a list
    that now covers every Division I school. What survives is the genuinely
    different way of saying it: "vols", "terps", "niners", "runnin rebels",
    "southern california". Across the full list this drops 3,742 aliases to
    312 and takes about a fifth off the payload.
    """
    n = team["name"].lower()
    s = (team["short"] or "").lower()
    c = (team["code"] or "").lower()
    team["aliases"] = [a for a in team["aliases"]
                       if a not in n and a not in s and a not in c]
    return team


def all_teams():
    out = _pro_teams() + _college_teams()
    out.sort(key=lambda t: (t["name"], _SPORT_ORDER.get(t["league"], -1),
                            t["league_label"]))
    return [_trim(t) for t in out]


def register_aliases():
    """
    Teach the server-side matcher the names we now show people.

    `team_aliases.matches_search` tests `query in alias`, so "Florida Gators"
    would match nothing while the only aliases are "florida" and "gators".

    The code registered against matters. The game lookup calls matches_search
    with whatever code SportsDataIO sent, so a name filed under an internal
    chat-room code is invisible to it - which is exactly the bug this used to
    have: Auburn's chat code is "AUB" but the feed says "AUBRN", so picking
    "Auburn Tigers" from search found no games. Only codes the feed can
    actually produce are written here.
    """
    for t in all_teams():
        sport = t["league"]
        table = team_aliases.TEAM_ALIASES.get(sport)
        if table is None or t["code"] not in table:
            # Either a league with no alias table (soccer, college baseball)
            # or a school the feed has no code for. Nothing to teach.
            continue
        bucket = table[t["code"]]
        for extra in (t["name"].lower(), t["short"].lower()):
            if extra not in bucket:
                bucket.append(extra)


register_aliases()
