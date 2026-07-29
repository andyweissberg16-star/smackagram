"""
Full, human-style team names for search — "New York Yankees", not "Yankees".

CHAT_LEAGUES stores short names (the mascot) for the four major US leagues and
the WNBA, which is fine for a chat room header but useless for search: nobody
finds the Yankees by typing "new" if the only stored string is "Yankees".

Soccer and college names in CHAT_LEAGUES are already complete ("Atlanta United
FC", "Boston College"), so they are left alone.

Nothing here hits the network or the database - it is derived once at import
from data already in the repo.
"""

from services import team_aliases, chat_team_lists

# Leagues whose CHAT_LEAGUES names are mascot-only and need a city prefix.
_NEEDS_CITY = ("nfl", "nba", "mlb", "nhl", "wnba")

# Conference lists whose teams also appear in the NCAA alias tables.
_COLLEGE = ("sec", "bigten", "big12", "acc", "ncaab", "ncaawb")

# A handful of teams have no usable alias entry to derive a city from.
_EXPLICIT = {
    ("wnba", "CON"): "Connecticut Sun",
    ("wnba", "GS"): "Golden State Valkyries",
    ("wnba", "PHO"): "Phoenix Mercury",
    ("wnba", "WAS"): "Washington Mystics",
}

# Tokens that should stay upper-case when we title-case a lower-case alias.
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


def _derive(league, code, short):
    """Best full name for a team, or None if we can't do better than `short`."""
    if (league, code) in _EXPLICIT:
        return _EXPLICIT[(league, code)]
    aliases = [a.lower() for a in team_aliases.TEAM_ALIASES.get(league, {}).get(code, [])]
    s = short.lower()
    # Prefer an alias that already reads as "<city> <mascot>". Longest wins, so
    # we get "new york yankees" rather than "ny yankees" - but note this also
    # excludes stale full names that don't end in the current mascot (the NHL
    # entry still lists "utah hockey club", which no longer matches "mammoth").
    ending = [a for a in aliases if a.endswith(s) and len(a) > len(s)]
    if ending:
        return _title(max(ending, key=len))
    # Otherwise find a city-ish alias and prepend it.
    city = [a for a in aliases if a != s and s not in a and a not in s]
    if city:
        return _title(max(city, key=len) + " " + s)
    return None


def _extra_aliases(league, code, short):
    """
    Everything else worth matching against but not worth displaying: the
    mascot for college teams, short forms like "niners" and "bucs", the
    abbreviated city forms.

    Only reach into the college alias tables for college conferences. Codes
    collide across leagues - La Liga's Alaves is "ALA", the same code Alabama
    uses - so pulling college aliases in for every league made "crimson"
    match a Spanish football club.
    """
    sources = [league]
    if league in _COLLEGE:
        sources += ["ncaaf", "ncaab", "ncaawb"]
    seen = set()
    for src in sources:
        for a in team_aliases.TEAM_ALIASES.get(src, {}).get(code, []):
            seen.add(a.lower())
    seen.discard(short.lower())
    return sorted(seen)


def all_teams():
    out = []
    for league, teams in chat_team_lists.CHAT_LEAGUES.items():
        for code, short in teams.items():
            name = short
            if league in _NEEDS_CITY:
                name = _derive(league, code, short) or short
            out.append({
                "code": code,
                "name": name,
                "short": short,
                "league": league,
                "aliases": _extra_aliases(league, code, short),
            })
    out.sort(key=lambda t: t["name"])
    return out
