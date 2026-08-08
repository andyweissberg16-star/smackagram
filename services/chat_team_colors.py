# Real team brand colors (primary color, not trademarked - colors
# themselves aren't protectable IP the way logos are) and real division
# structures, used to give the Smack Chat browse view actual visual
# identity instead of identical gray boxes for every team.

TEAM_COLORS = {
    "nfl": {
        "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D",
        "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14", "CLE": "#311D00",
        "DAL": "#003594", "DEN": "#FB4F14", "DET": "#0076B6", "GB": "#203731",
        "HOU": "#03202F", "IND": "#002C5F", "JAX": "#006778", "KC": "#E31837",
        "LAC": "#0080C6", "LAR": "#003594", "LV": "#000000", "MIA": "#008E97",
        "MIN": "#4F2683", "NE": "#002244", "NO": "#D3BC8D", "NYG": "#0B2265",
        "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SEA": "#002244",
        "SF": "#AA0000", "TB": "#D50A0A", "TEN": "#0C2340", "WAS": "#5A1414",
    },
    "nba": {
        "ATL": "#E03A3E", "BOS": "#007A33", "BKN": "#000000", "CHA": "#1D1160",
        "CHI": "#CE1141", "CLE": "#860038", "DAL": "#00538C", "DEN": "#0E2240",
        "DET": "#C8102E", "GS": "#1D428A", "HOU": "#CE1141", "IND": "#002D62",
        "LAC": "#C8102E", "LAL": "#552583", "MEM": "#5D76A9", "MIA": "#98002E",
        "MIL": "#00471B", "MIN": "#0C2340", "NO": "#0C2340", "NY": "#F58426",
        "OKC": "#007AC1", "ORL": "#0077C0", "PHI": "#006BB6", "PHO": "#1D1160",
        "POR": "#E03A3E", "SAC": "#5A2D81", "SA": "#C4CED4", "TOR": "#CE1141",
        "UTA": "#002B5C", "WAS": "#002B5C",
    },
    "mlb": {
        "ARI": "#A71930", "ATL": "#CE1141", "BAL": "#DF4601", "BOS": "#BD3039",
        "CHC": "#0E3386", "CHW": "#27251F", "CIN": "#C6011F", "CLE": "#00385D",
        "COL": "#333366", "DET": "#0C2340", "HOU": "#EB6E1F", "KC": "#004687",
        "LAA": "#BA0021", "LAD": "#005A9C", "MIA": "#00A3E0", "MIL": "#12284B",
        "MIN": "#002B5C", "NYM": "#002D72", "NYY": "#003087", "ATH": "#003831",
        "PHI": "#E81828", "PIT": "#FDB827", "SD": "#2F241D", "SF": "#FD5A1E",
        "SEA": "#0C2C56", "STL": "#C41E3A", "TB": "#092C5C", "TEX": "#003278",
        "TOR": "#134A8E", "WSH": "#AB0003",
    },
    "nhl": {
        "ANA": "#F47A38", "UTA": "#69B3E7", "BOS": "#FFB81C", "BUF": "#002654",
        "CGY": "#C8102E", "CAR": "#CC0000", "CHI": "#CF0A2C", "COL": "#6F263D",
        "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00",
        "FLA": "#C8102E", "LA": "#111111", "MIN": "#154734", "MON": "#AF1E2D",
        "NAS": "#FFB81C", "NJ": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8",
        "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJ": "#006D75",
        "SEA": "#99D9D9", "STL": "#002F87", "TB": "#002868", "TOR": "#00205B",
        "VAN": "#00205B", "VEG": "#B4975A", "WAS": "#041E42", "WPG": "#041E42",
    },
    "wnba": {
        "ATL": "#C8102E", "CHI": "#418FDE", "CON": "#F05023", "DAL": "#0C2340",
        "GS": "#FFA400", "IND": "#FFC633", "LA": "#702F8A", "LV": "#000000",
        "MIN": "#236192", "NY": "#86CEBC", "PHO": "#3C286E", "SEA": "#2C5234",
        "WAS": "#E03A3E",
    },
}

# Real division structures for the four major leagues + WNBA — used to
# group the team grid instead of one flat undifferentiated list.
DIVISIONS = {
    "nfl": {
        "AFC East": ["BUF", "MIA", "NE", "NYJ"],
        "AFC North": ["BAL", "CIN", "CLE", "PIT"],
        "AFC South": ["HOU", "IND", "JAX", "TEN"],
        "AFC West": ["DEN", "KC", "LAC", "LV"],
        "NFC East": ["DAL", "NYG", "PHI", "WAS"],
        "NFC North": ["CHI", "DET", "GB", "MIN"],
        "NFC South": ["ATL", "CAR", "NO", "TB"],
        "NFC West": ["ARI", "LAR", "SF", "SEA"],
    },
    "nba": {
        "Atlantic": ["BOS", "BKN", "NY", "PHI", "TOR"],
        "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
        "Southeast": ["ATL", "CHA", "MIA", "ORL", "WAS"],
        "Northwest": ["DEN", "MIN", "OKC", "POR", "UTA"],
        "Pacific": ["GS", "LAC", "LAL", "PHO", "SAC"],
        "Southwest": ["DAL", "HOU", "MEM", "NO", "SA"],
    },
    "mlb": {
        "AL East": ["BAL", "BOS", "NYY", "TB", "TOR"],
        "AL Central": ["CHW", "CLE", "DET", "KC", "MIN"],
        "AL West": ["ATH", "HOU", "LAA", "SEA", "TEX"],
        "NL East": ["ATL", "MIA", "NYM", "PHI", "WSH"],
        "NL Central": ["CHC", "CIN", "MIL", "PIT", "STL"],
        "NL West": ["ARI", "COL", "LAD", "SD", "SF"],
    },
    "nhl": {
        "Atlantic": ["BOS", "BUF", "DET", "FLA", "MON", "OTT", "TB", "TOR"],
        "Metropolitan": ["CAR", "CBJ", "NJ", "NYI", "NYR", "PHI", "PIT", "WAS"],
        "Central": ["CHI", "COL", "DAL", "MIN", "NAS", "STL", "UTA", "WPG"],
        "Pacific": ["ANA", "CGY", "EDM", "LA", "SJ", "SEA", "VAN", "VEG"],
    },
    "wnba": {
        "Eastern": ["ATL", "CHI", "CON", "IND", "NY", "WAS"],
        "Western": ["DAL", "GS", "LA", "LV", "MIN", "PHO", "SEA"],
    },
}


# ---------------------------------------------------------------------------
# Looking a colour up from a team NAME
# ---------------------------------------------------------------------------
# Keyed by NICKNAME rather than abbreviation, because abbreviations collide
# across leagues and the wall does not know which sport it is looking at.
# CLE is the Browns, the Guardians AND the Cavaliers - merging the leagues
# turned Cleveland brown into Cleveland navy.
#
# Values are each team's real identity colour, lifted where the true one is
# too dark to read on a black card - but always keeping the HUE. Brown stays
# brown, navy stays navy, green stays green.

TEAM_NAME_COLORS = {
    # Real official primary colours. Some are near-black (Yankees navy,
    # Raiders black) - readable_color_for_name() lifts those to stay legible
    # on the dark card while keeping the hue. Do NOT pre-lighten here; store
    # the true colour and let that function do the work.

    # --- NFL ---
    "cardinals": "#97233F",   "falcons": "#A71930",   "ravens": "#241773",
    "bills": "#00338D",       "panthers": "#0085CA",  "bears": "#0B162A",
    "bengals": "#FB4F14",     "browns": "#311D00",    "cowboys": "#003594",
    "broncos": "#FB4F14",     "lions": "#0076B6",     "packers": "#203731",
    "texans": "#03202F",      "colts": "#002C5F",     "jaguars": "#006778",
    "chiefs": "#E31837",      "raiders": "#A5ACAF",   "chargers": "#0080C6",
    "rams": "#003594",        "dolphins": "#008E97",  "vikings": "#4F2683",
    "patriots": "#002244",    "saints": "#D3BC8D",    "giants": "#0B2265",
    "jets": "#125740",        "eagles": "#004C54",    "steelers": "#FFB612",
    "49ers": "#AA0000",        "niners": "#AA0000",   "seahawks": "#69BE28",
    "buccaneers": "#D50A0A",  "bucs": "#D50A0A",      "titans": "#0C2340",
    "commanders": "#5A1414",

    # --- MLB ---
    "diamondbacks": "#A71930","braves": "#CE1141",     "orioles": "#DF4601",
    "red sox": "#BD3039",     "white sox": "#C4CED4",  "cubs": "#0E3386",
    "reds": "#C6011F",        "guardians": "#00385D",  "rockies": "#333366",
    "tigers": "#0C2340",      "astros": "#EB6E1F",     "royals": "#004687",
    "angels": "#BA0021",      "dodgers": "#005A9C",    "marlins": "#00A3E0",
    "brewers": "#12284B",     "twins": "#002B5C",      "mets": "#FF5910",
    "yankees": "#003087",     "athletics": "#003831",  "phillies": "#E81828",
    "pirates": "#FDB827",     "padres": "#2F241D",     "mariners": "#0C2C56",
    "rangers": "#003278",     "blue jays": "#134A8E",  "nationals": "#AB0003",
    "rays": "#092C5C",

    # --- NBA ---
    "hawks": "#E03A3E",       "celtics": "#007A33",    "nets": "#C4CED4",
    "hornets": "#1D1160",     "bulls": "#CE1141",      "cavaliers": "#860038",
    "mavericks": "#00538C",   "nuggets": "#0E2240",    "pistons": "#C8102E",
    "warriors": "#1D428A",    "rockets": "#CE1141",    "pacers": "#002D62",
    "clippers": "#C8102E",    "lakers": "#552583",     "grizzlies": "#5D76A9",
    "heat": "#98002E",        "bucks": "#00471B",      "timberwolves": "#0C2340",
    "pelicans": "#0C2340",    "knicks": "#F58426",     "thunder": "#007AC1",
    "magic": "#0077C0",       "sixers": "#006BB6",     "76ers": "#006BB6",
    "suns": "#E56020",        "trail blazers": "#CE1141", "blazers": "#CE1141",
    "kings": "#5A2D81",       "spurs": "#C4CED4",      "raptors": "#CE1141",
    "jazz": "#002B5C",        "wizards": "#002B5C",

    # --- WNBA ---
    "aces": "#A7A8AA",        "dream": "#E31837",      "sky": "#5091CD",
    "sun": "#F05023",         "wings": "#0C2340",      "fever": "#002D62",
    "sparks": "#552583",      "storm": "#2C5234",      "lynx": "#0C2340",
    "mercury": "#201747",     "mystics": "#002B5C",    "liberty": "#00A9A5",
    "valkyries": "#552583",   "fire": "#E31837",

    # --- NHL ---
    "ducks": "#F47A38",       "mammoth": "#5B8AC9",    "bruins": "#FFB81C",
    "sabres": "#002654",      "flames": "#C8102E",     "hurricanes": "#CC0000",
    "blackhawks": "#CF0A2C",  "avalanche": "#6F263D",  "blue jackets": "#002654",
    "stars": "#006847",       "red wings": "#CE1126",  "oilers": "#FF4C00",
    "kings": "#111111",       "wild": "#154734",
    "canadiens": "#AF1E2D",   "predators": "#FFB81C",  "devils": "#CE1126",
    "islanders": "#00539B",   "senators": "#C8102E",
    "flyers": "#F74902",      "penguins": "#FCB514",   "sharks": "#006D75",
    "kraken": "#001628",      "blues": "#002F87",      "lightning": "#002868",
    "maple leafs": "#00205B", "golden knights": "#B4975A", "capitals": "#C8102E",
    "canucks": "#00205B",

    # --- World Cup countries (real national colours) ---
    "argentina": "#75AADB",   "brazil": "#FFDF00",     "france": "#002654",
    "england": "#CF081F",     "spain": "#C60B1E",      "germany": "#000000",
    "portugal": "#006600",    "netherlands": "#FF6200","belgium": "#FFD100",
    "croatia": "#FF0000",     "uruguay": "#5CB8E6",    "mexico": "#006847",
    "usa": "#3C3B6E",         "united states": "#3C3B6E", "colombia": "#FCD116",
    "japan": "#BC002D",       "south korea": "#003478","morocco": "#C1272D",
    "senegal": "#00853F",     "switzerland": "#D52B1E","denmark": "#C60C30",
    "poland": "#DC143C",      "wales": "#C8102E",      "serbia": "#C6363C",
    "ecuador": "#FFD100",     "ghana": "#006B3F",      "cameroon": "#007A5E",
    "canada": "#FF0000",      "qatar": "#8A1538",      "saudi arabia": "#006C35",
    "australia": "#00843D",   "tunisia": "#E70013",    "iran": "#239F40",
    "costa rica": "#002B7F",  "nigeria": "#008751",    "italy": "#0066CC",
    "ivory coast": "#FF8200", "cote d'ivoire": "#FF8200",
    "egypt": "#CE1126",       "scotland": "#0065BF",   "ireland": "#169B62",
    "sweden": "#006AA7",      "norway": "#BA0C2F",     "austria": "#ED2939",
}


# ---------------------------------------------------------------------------
# Looking a colour up from a team NAME
# ---------------------------------------------------------------------------
# TEAM_COLORS is keyed by abbreviation because that is what the score feeds
# return. The wall stores what somebody typed - "Yankees", "Cowboys" - so it
# needs a way in from the other end.

# Nickname to abbreviation, across every league in TEAM_COLORS.
_NAME_TO_ABBR = {
    # NFL
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "raiders": "LV", "chargers": "LAC", "rams": "LAR", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF",
    "niners": "SF", "seahawks": "SEA", "buccaneers": "TB", "bucs": "TB",
    "titans": "TEN", "commanders": "WAS",
    # MLB
    "diamondbacks": "ARI", "braves": "ATL", "orioles": "BAL", "red sox": "BOS",
    "white sox": "CWS", "cubs": "CHC", "reds": "CIN", "guardians": "CLE",
    "rockies": "COL", "tigers": "DET", "astros": "HOU", "royals": "KC",
    "angels": "LAA", "dodgers": "LAD", "marlins": "MIA", "brewers": "MIL",
    "twins": "MIN", "mets": "NYM", "yankees": "NYY", "athletics": "OAK",
    "phillies": "PHI", "pirates": "PIT", "padres": "SD", "mariners": "SEA",
    "rangers": "TEX", "blue jays": "TOR", "nationals": "WSH",
    # NBA
    "hawks": "ATL", "celtics": "BOS", "nets": "BKN", "hornets": "CHA",
    "bulls": "CHI", "cavaliers": "CLE", "mavericks": "DAL", "nuggets": "DEN",
    "pistons": "DET", "warriors": "GS", "rockets": "HOU", "pacers": "IND",
    "clippers": "LAC", "lakers": "LAL", "grizzlies": "MEM", "heat": "MIA",
    "bucks": "MIL", "timberwolves": "MIN", "pelicans": "NO", "knicks": "NYK",
    "thunder": "OKC", "magic": "ORL", "sixers": "PHI", "76ers": "PHI",
    "suns": "PHO", "trail blazers": "POR", "blazers": "POR", "kings": "SAC",
    "spurs": "SA", "raptors": "TOR", "jazz": "UTA", "wizards": "WSH",
}


def _flatten_colors():
    """TEAM_COLORS is nested by league; the wall does not know the league."""
    out = {}
    for v in TEAM_COLORS.values():
        if isinstance(v, dict):
            out.update(v)
    return out if out else dict(TEAM_COLORS)


def color_for_name(name):
    """
    A team's colour from its nickname, or None if unrecognised.

    Checks the name-keyed table first. The abbreviation route below is only a
    fallback for anything not listed, and is where the league collision lives
    - it is deliberately second.
    """
    if not name:
        return None
    key = str(name).strip().lower()

    direct = TEAM_NAME_COLORS.get(key)
    if direct:
        return direct
    # "New York Yankees" and the like.
    parts = key.split()
    for n in (2, 1):
        if len(parts) >= n:
            direct = TEAM_NAME_COLORS.get(" ".join(parts[-n:]))
            if direct:
                return direct

    abbr = _NAME_TO_ABBR.get(key)
    if not abbr:
        # "New York Yankees" and the like - try the last word or two.
        parts = key.split()
        for n in (2, 1):
            if len(parts) >= n:
                abbr = _NAME_TO_ABBR.get(" ".join(parts[-n:]))
                if abbr:
                    break
    if not abbr:
        return None
    return _flatten_colors().get(abbr)


def readable_color_for_name(name, on_dark=True):
    """
    The team's colour, lightened if it would disappear.

    Plenty of real team colours are nearly black - Chicago's navy is #0B162A,
    Cleveland's brown is #311D00 - and those are invisible on a dark card.
    Anything too dark is lifted until it can be read, keeping the hue so it
    is still recognisably the team.
    """
    hexv = color_for_name(name)
    if not hexv:
        return None
    try:
        h = hexv.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        # Perceived brightness, not a plain average - the eye weights green
        # far more heavily than blue.
        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        floor = 0.42 if on_dark else 0.0
        if lum <= 0:
            # Pure black (e.g. Germany, LA Kings) - no hue to preserve, so
            # lift to a readable neutral gray instead of staying invisible.
            return "#8A8A8A" if on_dark else hexv
        if lum < floor:
            scale = floor / lum
            r, g, b = (min(255, int(c * scale)) for c in (r, g, b))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hexv


# ---------------------------------------------------------------------------
# Conference / league grouping for the Smack Board
# ---------------------------------------------------------------------------
# DIVISIONS above is too fine for a scoreboard - eight NFL divisions means
# eight headings most of which hold one game. Rolling up to the two halves
# each sport actually splits into gives a heading with real games under it.

_CONFERENCE_OF = {
    "nfl":  lambda d: "AFC" if d.startswith("AFC") else "NFC",
    "mlb":  lambda d: "American League" if d.startswith("AL") else "National League",
    "nba":  lambda d: ("Eastern Conference"
                       if d in ("Atlantic", "Central", "Southeast")
                       else "Western Conference"),
    "nhl":  lambda d: ("Eastern Conference"
                       if d in ("Atlantic", "Metropolitan")
                       else "Western Conference"),
    "wnba": lambda d: ("Eastern Conference" if d == "Eastern"
                       else "Western Conference"),
}


def conference_for_abbr(league, abbr):
    """
    Which half of the sport a team belongs to, or None if unknown.

    Returns None rather than guessing for college and anything not mapped -
    the board leaves those ungrouped rather than inventing a heading.
    """
    lg = (league or "").lower()
    rule = _CONFERENCE_OF.get(lg)
    divs = DIVISIONS.get(lg)
    if not rule or not divs or not abbr:
        return None
    a = str(abbr).upper()
    for div_name, teams in divs.items():
        if a in teams:
            try:
                return rule(div_name)
            except Exception:
                return None
    return None
