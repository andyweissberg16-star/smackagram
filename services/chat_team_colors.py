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
