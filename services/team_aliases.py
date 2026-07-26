# Maps each team's SportsDataIO abbreviation to a list of names/nicknames a
# person might actually type when searching — city, mascot, full name, and
# common short forms. Search matches against any of these, case-insensitive.
#
# Covers the four major leagues where fans reliably know team names by heart.
# For leagues without an explicit entry here (college sports, soccer, etc.),
# search falls back to matching directly against whatever the API returns.

TEAM_ALIASES = {
    "nfl": {
        "ARI": ["arizona", "cardinals", "arizona cardinals"],
        "ATL": ["atlanta", "falcons", "atlanta falcons"],
        "BAL": ["baltimore", "ravens", "baltimore ravens"],
        "BUF": ["buffalo", "bills", "buffalo bills"],
        "CAR": ["carolina", "panthers", "carolina panthers"],
        "CHI": ["chicago", "bears", "chicago bears"],
        "CIN": ["cincinnati", "bengals", "cincinnati bengals"],
        "CLE": ["cleveland", "browns", "cleveland browns"],
        "DAL": ["dallas", "cowboys", "dallas cowboys"],
        "DEN": ["denver", "broncos", "denver broncos"],
        "DET": ["detroit", "lions", "detroit lions"],
        "GB": ["green bay", "packers", "green bay packers"],
        "HOU": ["houston", "texans", "houston texans"],
        "IND": ["indianapolis", "colts", "indianapolis colts"],
        "JAX": ["jacksonville", "jaguars", "jacksonville jaguars"],
        "KC": ["kansas city", "chiefs", "kansas city chiefs"],
        "LAC": ["los angeles chargers", "la chargers", "chargers"],
        "LAR": ["los angeles rams", "la rams", "rams"],
        "LV": ["las vegas", "raiders", "las vegas raiders"],
        "MIA": ["miami", "dolphins", "miami dolphins"],
        "MIN": ["minnesota", "vikings", "minnesota vikings"],
        "NE": ["new england", "patriots", "new england patriots"],
        "NO": ["new orleans", "saints", "new orleans saints"],
        "NYG": ["new york giants", "ny giants", "giants"],
        "NYJ": ["new york jets", "ny jets", "jets"],
        "PHI": ["philadelphia", "eagles", "philadelphia eagles"],
        "PIT": ["pittsburgh", "steelers", "pittsburgh steelers"],
        "SEA": ["seattle", "seahawks", "seattle seahawks"],
        "SF": ["san francisco", "49ers", "niners", "san francisco 49ers"],
        "TB": ["tampa bay", "buccaneers", "bucs", "tampa bay buccaneers"],
        "TEN": ["tennessee", "titans", "tennessee titans"],
        "WAS": ["washington", "commanders", "washington commanders"],
    },
    "nba": {
        "ATL": ["atlanta", "hawks", "atlanta hawks"],
        "BOS": ["boston", "celtics", "boston celtics"],
        "BKN": ["brooklyn", "nets", "brooklyn nets"],
        "CHA": ["charlotte", "hornets", "charlotte hornets"],
        "CHI": ["chicago", "bulls", "chicago bulls"],
        "CLE": ["cleveland", "cavaliers", "cavs", "cleveland cavaliers"],
        "DAL": ["dallas", "mavericks", "mavs", "dallas mavericks"],
        "DEN": ["denver", "nuggets", "denver nuggets"],
        "DET": ["detroit", "pistons", "detroit pistons"],
        "GSW": ["golden state", "warriors", "golden state warriors"],
        "HOU": ["houston", "rockets", "houston rockets"],
        "IND": ["indiana", "pacers", "indiana pacers"],
        "LAC": ["los angeles clippers", "la clippers", "clippers"],
        "LAL": ["los angeles lakers", "la lakers", "lakers"],
        "MEM": ["memphis", "grizzlies", "memphis grizzlies"],
        "MIA": ["miami", "heat", "miami heat"],
        "MIL": ["milwaukee", "bucks", "milwaukee bucks"],
        "MIN": ["minnesota", "timberwolves", "wolves", "minnesota timberwolves"],
        "NOP": ["new orleans", "pelicans", "new orleans pelicans"],
        "NYK": ["new york", "knicks", "new york knicks"],
        "OKC": ["oklahoma city", "thunder", "oklahoma city thunder"],
        "ORL": ["orlando", "magic", "orlando magic"],
        "PHI": ["philadelphia", "76ers", "sixers", "philadelphia 76ers"],
        "PHX": ["phoenix", "suns", "phoenix suns"],
        "POR": ["portland", "trail blazers", "blazers", "portland trail blazers"],
        "SAC": ["sacramento", "kings", "sacramento kings"],
        "SAS": ["san antonio", "spurs", "san antonio spurs"],
        "TOR": ["toronto", "raptors", "toronto raptors"],
        "UTA": ["utah", "jazz", "utah jazz"],
        "WAS": ["washington", "wizards", "washington wizards"],
    },
    "mlb": {
        "ARI": ["arizona", "diamondbacks", "dbacks", "arizona diamondbacks"],
        "ATL": ["atlanta", "braves", "atlanta braves"],
        "BAL": ["baltimore", "orioles", "baltimore orioles"],
        "BOS": ["boston", "red sox", "boston red sox"],
        "CHC": ["chicago cubs", "cubs"],
        "CHW": ["chicago white sox", "white sox"],
        "CIN": ["cincinnati", "reds", "cincinnati reds"],
        "CLE": ["cleveland", "guardians", "cleveland guardians"],
        "COL": ["colorado", "rockies", "colorado rockies"],
        "DET": ["detroit", "tigers", "detroit tigers"],
        "HOU": ["houston", "astros", "houston astros"],
        "KC": ["kansas city", "royals", "kansas city royals"],
        "LAA": ["los angeles angels", "la angels", "angels"],
        "LAD": ["los angeles dodgers", "la dodgers", "dodgers"],
        "MIA": ["miami", "marlins", "miami marlins"],
        "MIL": ["milwaukee", "brewers", "milwaukee brewers"],
        "MIN": ["minnesota", "twins", "minnesota twins"],
        "NYM": ["new york mets", "ny mets", "mets"],
        "NYY": ["new york yankees", "ny yankees", "yankees"],
        "ATH": ["oakland", "athletics", "a's", "oakland athletics"],
        "PHI": ["philadelphia", "phillies", "philadelphia phillies"],
        "PIT": ["pittsburgh", "pirates", "pittsburgh pirates"],
        "SD": ["san diego", "padres", "san diego padres"],
        "SF": ["san francisco", "giants", "san francisco giants"],
        "SEA": ["seattle", "mariners", "seattle mariners"],
        "STL": ["st. louis", "st louis", "cardinals", "st. louis cardinals"],
        "TB": ["tampa bay", "rays", "tampa bay rays"],
        "TEX": ["texas", "rangers", "texas rangers"],
        "TOR": ["toronto", "blue jays", "toronto blue jays"],
        "WSH": ["washington", "nationals", "washington nationals"],
    },
    "nhl": {
        "ANA": ["anaheim", "ducks", "anaheim ducks"],
        "ARI": ["arizona", "coyotes", "arizona coyotes"],
        "BOS": ["boston", "bruins", "boston bruins"],
        "BUF": ["buffalo", "sabres", "buffalo sabres"],
        "CGY": ["calgary", "flames", "calgary flames"],
        "CAR": ["carolina", "hurricanes", "carolina hurricanes"],
        "CHI": ["chicago", "blackhawks", "chicago blackhawks"],
        "COL": ["colorado", "avalanche", "avs", "colorado avalanche"],
        "CBJ": ["columbus", "blue jackets", "columbus blue jackets"],
        "DAL": ["dallas", "stars", "dallas stars"],
        "DET": ["detroit", "red wings", "detroit red wings"],
        "EDM": ["edmonton", "oilers", "edmonton oilers"],
        "FLA": ["florida", "panthers", "florida panthers"],
        "LA": ["los angeles", "kings", "los angeles kings"],
        "MIN": ["minnesota", "wild", "minnesota wild"],
        "MTL": ["montreal", "canadiens", "habs", "montreal canadiens"],
        "NSH": ["nashville", "predators", "preds", "nashville predators"],
        "NJ": ["new jersey", "devils", "new jersey devils"],
        "NYI": ["new york islanders", "ny islanders", "islanders"],
        "NYR": ["new york rangers", "ny rangers", "rangers"],
        "OTT": ["ottawa", "senators", "sens", "ottawa senators"],
        "PHI": ["philadelphia", "flyers", "philadelphia flyers"],
        "PIT": ["pittsburgh", "penguins", "pens", "pittsburgh penguins"],
        "SJ": ["san jose", "sharks", "san jose sharks"],
        "SEA": ["seattle", "kraken", "seattle kraken"],
        "STL": ["st. louis", "st louis", "blues", "st. louis blues"],
        "TB": ["tampa bay", "lightning", "tampa bay lightning"],
        "TOR": ["toronto", "maple leafs", "leafs", "toronto maple leafs"],
        "VAN": ["vancouver", "canucks", "vancouver canucks"],
        "VGK": ["vegas", "golden knights", "vegas golden knights"],
        "WSH": ["washington", "capitals", "caps", "washington capitals"],
        "WPG": ["winnipeg", "jets", "winnipeg jets"],
    },
}


def matches_search(sport: str, team_code: str, query: str) -> bool:
    """
    True if the search query matches this team — checks the raw code itself
    plus every known alias (city, nickname, full name) for that sport.
    Falls back to a plain substring match against the code for leagues
    without an alias table (college sports, soccer, etc.).

    Tolerant of missing spaces (e.g. "whitesox" still matches the "white
    sox" alias) since that's a very natural way for someone to type it.
    """
    query = query.strip().lower()
    if not query:
        return True

    if query in team_code.lower():
        return True

    aliases = TEAM_ALIASES.get(sport, {}).get(team_code, [])
    if any(query in alias for alias in aliases):
        return True

    # space-insensitive fallback — catches "whitesox" against "white sox"
    query_no_spaces = query.replace(" ", "")
    return any(query_no_spaces in alias.replace(" ", "") for alias in aliases)


# Properly-capitalized nickname for display purposes — SportsDataIO's raw
# feed only gives abbreviations ("SF", "LAA"), not friendly names, so this
# is what actually shows up anywhere a team name is displayed on-screen
# (search results, "who has to lose" cards, the scoreboard, etc).
DISPLAY_NAMES = {
    "nfl": {
        "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
        "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
        "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
        "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs",
        "LAC": "Chargers", "LAR": "Rams", "LV": "Raiders", "MIA": "Dolphins",
        "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
        "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
        "SF": "49ers", "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
    },
    "nba": {
        "ATL": "Hawks", "BOS": "Celtics", "BKN": "Nets", "CHA": "Hornets",
        "CHI": "Bulls", "CLE": "Cavaliers", "DAL": "Mavericks", "DEN": "Nuggets",
        "DET": "Pistons", "GSW": "Warriors", "HOU": "Rockets", "IND": "Pacers",
        "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat",
        "MIL": "Bucks", "MIN": "Timberwolves", "NOP": "Pelicans", "NYK": "Knicks",
        "OKC": "Thunder", "ORL": "Magic", "PHI": "76ers", "PHX": "Suns",
        "POR": "Trail Blazers", "SAC": "Kings", "SAS": "Spurs", "TOR": "Raptors",
        "UTA": "Jazz", "WAS": "Wizards",
    },
    "mlb": {
        "ARI": "Diamondbacks", "ATL": "Braves", "BAL": "Orioles", "BOS": "Red Sox",
        "CHC": "Cubs", "CHW": "White Sox", "CIN": "Reds", "CLE": "Guardians",
        "COL": "Rockies", "DET": "Tigers", "HOU": "Astros", "KC": "Royals",
        "LAA": "Angels", "LAD": "Dodgers", "MIA": "Marlins", "MIL": "Brewers",
        "MIN": "Twins", "NYM": "Mets", "NYY": "Yankees", "ATH": "Athletics",
        "PHI": "Phillies", "PIT": "Pirates", "SD": "Padres", "SF": "Giants",
        "SEA": "Mariners", "STL": "Cardinals", "TB": "Rays", "TEX": "Rangers",
        "TOR": "Blue Jays", "WSH": "Nationals",
    },
    "nhl": {
        "ANA": "Ducks", "ARI": "Coyotes", "BOS": "Bruins", "BUF": "Sabres",
        "CGY": "Flames", "CAR": "Hurricanes", "CHI": "Blackhawks", "COL": "Avalanche",
        "CBJ": "Blue Jackets", "DAL": "Stars", "DET": "Red Wings", "EDM": "Oilers",
        "FLA": "Panthers", "LA": "Kings", "MIN": "Wild", "MTL": "Canadiens",
        "NSH": "Predators", "NJ": "Devils", "NYI": "Islanders", "NYR": "Rangers",
        "OTT": "Senators", "PHI": "Flyers", "PIT": "Penguins", "SJ": "Sharks",
        "SEA": "Kraken", "STL": "Blues", "TB": "Lightning", "TOR": "Maple Leafs",
        "VAN": "Canucks", "VGK": "Golden Knights", "WSH": "Capitals", "WPG": "Jets",
    },
}


def get_display_name(sport: str, team_code: str) -> str:
    """
    Returns the friendly team name (e.g. "Giants") for display anywhere on
    screen. Falls back to the raw code if this sport/team isn't in the
    table (college sports, soccer, etc. — those show the code as-is).
    """
    return DISPLAY_NAMES.get(sport, {}).get(team_code, team_code)
