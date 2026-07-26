# Team lists for Smack Chat rooms. Independent of team_aliases.py on
# purpose — that file's codes have to exactly match SportsDataIO's API for
# live game lookups; these are just room labels for a chat feature, so
# they don't need that same precision. Codes here just need to be unique
# and URL-safe.
#
# NFL/NBA/MLB/NHL are complete (every team in the league). NCAAF/NCAAB/
# NCAAWB cover major, widely-recognized programs across all the Power
# conferences rather than every D1 school — full FBS is 130+ teams and
# full D1 basketball is 350+, which isn't practical to hand-list here.
# WNBA is complete (only ~13 teams).

CHAT_LEAGUES = {
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
        "DET": "Pistons", "GS": "Warriors", "HOU": "Rockets", "IND": "Pacers",
        "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat",
        "MIL": "Bucks", "MIN": "Timberwolves", "NO": "Pelicans", "NY": "Knicks",
        "OKC": "Thunder", "ORL": "Magic", "PHI": "76ers", "PHO": "Suns",
        "POR": "Trail Blazers", "SAC": "Kings", "SA": "Spurs", "TOR": "Raptors",
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
        "ANA": "Ducks", "UTA": "Mammoth", "BOS": "Bruins", "BUF": "Sabres",
        "CGY": "Flames", "CAR": "Hurricanes", "CHI": "Blackhawks", "COL": "Avalanche",
        "CBJ": "Blue Jackets", "DAL": "Stars", "DET": "Red Wings", "EDM": "Oilers",
        "FLA": "Panthers", "LA": "Kings", "MIN": "Wild", "MON": "Canadiens",
        "NAS": "Predators", "NJ": "Devils", "NYI": "Islanders", "NYR": "Rangers",
        "OTT": "Senators", "PHI": "Flyers", "PIT": "Penguins", "SJ": "Sharks",
        "SEA": "Kraken", "STL": "Blues", "TB": "Lightning", "TOR": "Maple Leafs",
        "VAN": "Canucks", "VEG": "Golden Knights", "WAS": "Capitals", "WPG": "Jets",
    },
    "wnba": {
        "ATL": "Dream", "CHI": "Sky", "CON": "Sun", "DAL": "Wings",
        "GS": "Valkyries", "IND": "Fever", "LA": "Sparks", "LV": "Aces",
        "MIN": "Lynx", "NY": "Liberty", "PHO": "Mercury", "SEA": "Storm",
        "WAS": "Mystics",
    },
    "ncaaf": {
        "ALA": "Alabama", "AUB": "Auburn", "ARK": "Arkansas", "AGGIES": "Texas A&M",
        "FLA": "Florida", "UGA": "Georgia", "KY": "Kentucky", "LSU": "LSU",
        "MISS": "Ole Miss", "MSST": "Mississippi State", "MIZ": "Missouri",
        "OU": "Oklahoma", "SC": "South Carolina", "TENN": "Tennessee", "TEX": "Texas",
        "VAN": "Vanderbilt",
        "ILL": "Illinois", "IND": "Indiana", "IOWA": "Iowa", "MD": "Maryland",
        "MICH": "Michigan", "MSU": "Michigan State", "MINN": "Minnesota",
        "NEB": "Nebraska", "NW": "Northwestern", "OSU": "Ohio State",
        "ORE": "Oregon", "PSU": "Penn State", "PUR": "Purdue", "RUT": "Rutgers",
        "UCLA": "UCLA", "USC": "USC", "UW": "Washington", "WISC": "Wisconsin",
        "BAY": "Baylor", "BYU": "BYU", "CIN": "Cincinnati", "COLO": "Colorado",
        "HOU": "Houston", "ISU": "Iowa State", "KU": "Kansas", "KSU": "Kansas State",
        "OKST": "Oklahoma State", "TCU": "TCU", "TTU": "Texas Tech",
        "UCF": "UCF", "WVU": "West Virginia", "ARIZ": "Arizona", "ASU": "Arizona State",
        "BC": "Boston College", "CLEM": "Clemson", "DUKE": "Duke", "FSU": "Florida State",
        "GT": "Georgia Tech", "LOU": "Louisville", "MIAFL": "Miami",
        "NCST": "NC State", "UNC": "North Carolina", "PITT": "Pittsburgh",
        "SMU": "SMU", "STAN": "Stanford", "SYR": "Syracuse", "UVA": "Virginia",
        "VT": "Virginia Tech", "WAKE": "Wake Forest", "CAL": "California",
        "ND": "Notre Dame",
    },
    "ncaab": {
        "ALA": "Alabama", "ARIZ": "Arizona", "AUB": "Auburn", "BAY": "Baylor",
        "BYU": "BYU", "UCONN": "UConn", "DUKE": "Duke", "FLA": "Florida",
        "GONZ": "Gonzaga", "UGA": "Georgia", "HOU": "Houston", "ILL": "Illinois",
        "IND": "Indiana", "IOWA": "Iowa", "ISU": "Iowa State", "KU": "Kansas",
        "KSU": "Kansas State", "KY": "Kentucky", "LOU": "Louisville", "MICH": "Michigan",
        "MSU": "Michigan State", "MIZ": "Missouri", "UNC": "North Carolina",
        "OSU": "Ohio State", "OU": "Oklahoma", "ORE": "Oregon", "PUR": "Purdue",
        "SDSU": "San Diego State", "TENN": "Tennessee", "TEX": "Texas",
        "TAMU": "Texas A&M", "UCLA": "UCLA", "USC": "USC", "VILL": "Villanova",
        "UVA": "Virginia", "WISC": "Wisconsin", "MARQ": "Marquette", "CREI": "Creighton",
        "MSST": "Mississippi State", "MISS": "Ole Miss", "SC": "South Carolina",
        "TCU": "TCU", "TTU": "Texas Tech", "XAV": "Xavier", "SLU": "Saint Louis",
    },
    "ncaawb": {
        "SC": "South Carolina", "UCONN": "UConn", "IOWA": "Iowa", "LSU": "LSU",
        "STAN": "Stanford", "UCLA": "UCLA", "USC": "USC", "TENN": "Tennessee",
        "NOTRE": "Notre Dame", "OSU": "Ohio State", "TEX": "Texas", "UNC": "North Carolina",
        "DUKE": "Duke", "BAY": "Baylor", "OU": "Oklahoma", "KY": "Kentucky",
        "UGA": "Georgia", "IND": "Indiana", "VT": "Virginia Tech", "MD": "Maryland",
        "NCST": "NC State", "COLO": "Colorado", "UTAH": "Utah", "MISS": "Ole Miss",
    },
    "soccer": {
        # Major clubs across the Premier League, La Liga, Serie A,
        # Bundesliga, Ligue 1, and MLS — same leagues referenced in the
        # site's sports data integration elsewhere.
        "ARS": "Arsenal", "AVL": "Aston Villa", "CHE": "Chelsea", "EVE": "Everton",
        "LIV": "Liverpool", "MCI": "Manchester City", "MUN": "Manchester United",
        "NEW": "Newcastle United", "TOT": "Tottenham Hotspur", "WHU": "West Ham United",
        "RMA": "Real Madrid", "BAR": "Barcelona", "ATM": "Atletico Madrid",
        "SEV": "Sevilla", "VAL": "Valencia", "BIL": "Athletic Bilbao",
        "JUV": "Juventus", "INT": "Inter Milan", "ACM": "AC Milan", "NAP": "Napoli",
        "ROM": "AS Roma", "LAZ": "Lazio",
        "BAY_M": "Bayern Munich", "BVB": "Borussia Dortmund", "RBL": "RB Leipzig",
        "B04": "Bayer Leverkusen", "SGE": "Eintracht Frankfurt",
        "PSG": "Paris Saint-Germain", "OM": "Marseille", "OL": "Lyon", "MON": "Monaco",
        "LAFC": "LAFC", "LAG": "LA Galaxy", "NYC": "New York City FC", "NYRB": "New York Red Bulls",
        "ATL": "Atlanta United", "SEA": "Seattle Sounders", "MIA": "Inter Miami",
    },
}
