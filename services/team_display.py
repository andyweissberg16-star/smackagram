"""
Full, human-style team names for search — "New York Yankees", not "Yankees";
"Florida Gators", not "Florida".

CHAT_LEAGUES stores whatever is convenient for a chat room header: the mascot
alone for the pro leagues ("Yankees"), and the school alone for college
("Florida"). Neither is enough for search. "Florida" could be any sport and
any Florida school; "Yankees" can't be found by typing "new".

Soccer names in CHAT_LEAGUES are already complete ("Atlanta United FC") and
are left alone.

Nothing here hits the network or the database - it is derived once at import
from data already in the repo.
"""

from services import team_aliases, chat_team_lists

# Leagues whose CHAT_LEAGUES names are mascot-only and need a city prefix.
_NEEDS_CITY = ("nfl", "nba", "mlb", "nhl", "wnba")

# College lists. The four conferences are football; ncaab/ncaawb are basketball.
_COLLEGE = ("sec", "bigten", "big12", "acc", "ncaab", "ncaawb")

# What the badge in search results says. College entries name the sport too,
# because "Florida / SEC" told you nothing about which Florida or which sport.
LEAGUE_LABELS = {
    "nfl": "NFL", "nba": "NBA", "mlb": "MLB", "nhl": "NHL", "wnba": "WNBA",
    "sec": "SEC Football",
    "bigten": "Big Ten Football",
    "big12": "Big 12 Football",
    "acc": "ACC Football",
    "ncaab": "NCAA Men's Basketball",
    "ncaawb": "NCAA Women's Basketball",
    "mls": "MLS", "epl": "Premier League", "laliga": "La Liga",
    "bundesliga": "Bundesliga", "seriea": "Serie A",
}

# Authored by hand. The alias file only had usable mascots for 65 of 136
# college entries, and several of those were alternate names rather than
# mascots ("LSU Louisiana State", "Ole Miss Mississippi"), so deriving them
# produced nonsense. Keyed by school name, which is stable across the
# conference and NCAA lists.
COLLEGE_MASCOTS = {
    "Alabama":             "Crimson Tide",
    "Arizona":             "Wildcats",
    "Arizona State":       "Sun Devils",
    "Arkansas":            "Razorbacks",
    "Auburn":              "Tigers",
    "BYU":                 "Cougars",
    "Baylor":              "Bears",
    "Boston College":      "Eagles",
    "California":          "Golden Bears",
    "Cincinnati":          "Bearcats",
    "Clemson":             "Tigers",
    "Colorado":            "Buffaloes",
    "Creighton":           "Bluejays",
    "Duke":                "Blue Devils",
    "Florida":             "Gators",
    "Florida State":       "Seminoles",
    "Georgia":             "Bulldogs",
    "Georgia Tech":        "Yellow Jackets",
    "Gonzaga":             "Bulldogs",
    "Houston":             "Cougars",
    "Illinois":            "Fighting Illini",
    "Indiana":             "Hoosiers",
    "Iowa":                "Hawkeyes",
    "Iowa State":          "Cyclones",
    "Kansas":              "Jayhawks",
    "Kansas State":        "Wildcats",
    "Kentucky":            "Wildcats",
    "LSU":                 "Tigers",
    "Louisville":          "Cardinals",
    "Marquette":           "Golden Eagles",
    "Maryland":            "Terrapins",
    "Miami":               "Hurricanes",
    "Michigan":            "Wolverines",
    "Michigan State":      "Spartans",
    "Minnesota":           "Golden Gophers",
    "Mississippi State":   "Bulldogs",
    "Missouri":            "Tigers",
    "NC State":            "Wolfpack",
    "Nebraska":            "Cornhuskers",
    "North Carolina":      "Tar Heels",
    "Northwestern":        "Wildcats",
    "Notre Dame":          "Fighting Irish",
    "Ohio State":          "Buckeyes",
    "Oklahoma":            "Sooners",
    "Oklahoma State":      "Cowboys",
    "Ole Miss":            "Rebels",
    "Oregon":              "Ducks",
    "Penn State":          "Nittany Lions",
    "Pitt":                "Panthers",
    "Purdue":              "Boilermakers",
    "Rutgers":             "Scarlet Knights",
    "SMU":                 "Mustangs",
    "Saint Louis":         "Billikens",
    "San Diego State":     "Aztecs",
    "South Carolina":      "Gamecocks",
    "Stanford":            "Cardinal",
    "Syracuse":            "Orange",
    "TCU":                 "Horned Frogs",
    "Tennessee":           "Volunteers",
    "Texas":               "Longhorns",
    "Texas A&M":           "Aggies",
    "Texas Tech":          "Red Raiders",
    "UCF":                 "Knights",
    "UCLA":                "Bruins",
    "UConn":               "Huskies",
    "USC":                 "Trojans",
    "Utah":                "Utes",
    "Vanderbilt":          "Commodores",
    "Villanova":           "Wildcats",
    "Virginia":            "Cavaliers",
    "Virginia Tech":       "Hokies",
    "Wake Forest":         "Demon Deacons",
    "Washington":          "Huskies",
    "West Virginia":       "Mountaineers",
    "Wisconsin":           "Badgers",
    "Xavier":              "Musketeers",
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


def _aliases_for(league, code, short, full):
    """
    Everything worth matching against but not displaying. Includes the display
    name itself, which matters: the server matches games with `query in alias`,
    so a longer name typed into the box has to exist as an alias or the
    Locked & Loaded game lookup finds nothing.

    Only reach into the college alias tables for college leagues - codes
    collide across leagues (La Liga's Alaves is "ALA", same as Alabama).
    """
    sources = [league]
    if league in _COLLEGE:
        sources += ["ncaaf", "ncaab", "ncaawb"]
    seen = set()
    for src in sources:
        for a in team_aliases.TEAM_ALIASES.get(src, {}).get(code, []):
            seen.add(a.lower())
    seen.add(short.lower())
    seen.add(full.lower())
    if league in _COLLEGE and short in COLLEGE_MASCOTS:
        seen.add(COLLEGE_MASCOTS[short].lower())
    seen.discard("")
    return sorted(seen)


def all_teams():
    out = []
    for league, teams in chat_team_lists.CHAT_LEAGUES.items():
        for code, short in teams.items():
            if league in _NEEDS_CITY:
                full = _derive_pro(league, code, short) or short
            elif league in _COLLEGE and short in COLLEGE_MASCOTS:
                full = short + " " + COLLEGE_MASCOTS[short]
            else:
                full = short
            out.append({
                "code": code,
                "name": full,
                "short": short,
                "league": league,
                "league_label": LEAGUE_LABELS.get(league, league.upper()),
                "aliases": _aliases_for(league, code, short, full),
            })
    out.sort(key=lambda t: t["name"])
    return out


def register_aliases():
    """
    Teach the server-side matcher the names we now show people.

    `team_aliases.matches_search` tests `query in alias`, so "Florida Gators"
    would match nothing while the only aliases are "florida" and "gators".
    Every displayed name is registered here against the sport key the game
    lookup actually uses (the conferences all map to ncaaf).
    """
    sport_for = {"sec": "ncaaf", "bigten": "ncaaf", "big12": "ncaaf", "acc": "ncaaf"}
    for t in all_teams():
        sport = sport_for.get(t["league"], t["league"])
        table = team_aliases.TEAM_ALIASES.setdefault(sport, {})
        bucket = table.setdefault(t["code"], [])
        for extra in (t["name"].lower(), t["short"].lower()):
            if extra not in bucket:
                bucket.append(extra)


register_aliases()
