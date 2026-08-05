"""
Who runs each team.
===================

WHY THIS IS A FILE AND NOT AN API CALL
--------------------------------------
Neither provider has coaches. Highlightly's support confirmed it by email
on 5 August - "we do not currently provide this data for any sport" - and
probing a full team record backs it up: abbreviation, displayName, id,
league, logo, name, and nothing else. Balldontlie does not carry them
either.

So it is a list. Andrew supplied it, which matters: several of these are
2026 moves that would not be in any model's training data.

WHY COACHES ARE WORTH HAVING AT ALL
-----------------------------------
A losing fanbase is usually angrier at the manager than at any player.
"Your season is Aaron Boone's fault" lands differently from a jab at a
shortstop, because it is the argument they are already having.

MAINTENANCE
-----------
Coaches change. A handful a season in the pro leagues, more in college
during the hiring cycle. This needs looking at once a year and after any
notable sacking - there is no way to automate it, and a wrong name is
worse than no name because it makes Smacky sound like he does not watch.

THE TITLE MATTERS
-----------------
Baseball says MANAGER. Everything else says HEAD COACH. Getting that
wrong undercuts the joke faster than almost anything else, because it is
the kind of mistake only somebody who does not follow the sport makes.
"""

# Baseball says manager, everything else says head coach.
TITLES = {
    "mlb": "manager",
    "nfl": "head coach",
    "nba": "head coach",
    "wnba": "head coach",
    "nhl": "head coach",
    "ncaaf": "head coach",
    "ncaab": "head coach",
}

COACHES = {
    "mlb": {
        "Diamondbacks": "Torey Lovullo",
        "Braves": "Walt Weiss",
        "Cubs": "Craig Counsell",
        "Reds": "Terry Francona",
        "Rockies": "Warren Schaeffer",
        "Dodgers": "Dave Roberts",
        "Marlins": "Clayton McCullough",
        "Brewers": "Pat Murphy",
        "Mets": "Andy Green",
        "Phillies": "Don Mattingly",
        "Pirates": "Don Kelly",
        "Padres": "Craig Stammen",
        "Giants": "Tony Vitello",
        "Cardinals": "Oliver Marmol",
        "Nationals": "Blake Butera",
        "Athletics": "Mark Kotsay",
        "Orioles": "Craig Albernaz",
        "Red Sox": "Chad Tracy",
        "White Sox": "Will Venable",
        "Guardians": "Stephen Vogt",
        "Tigers": "A. J. Hinch",
        "Astros": "Joe Espada",
        "Royals": "Matt Quatraro",
        "Angels": "Kurt Suzuki",
        "Twins": "Derek Shelton",
        "Yankees": "Aaron Boone",
        "Mariners": "Dan Wilson",
        "Rays": "Kevin Cash",
        "Rangers": "Skip Schumaker",
        "Blue Jays": "John Schneider",
    },
    "nfl": {
        "Cardinals": "Mike LaFleur",
        "Falcons": "Kevin Stefanski",
        "Ravens": "Jesse Minter",
        "Bills": "Joe Brady",
        "Panthers": "Dave Canales",
        "Bears": "Ben Johnson",
        "Bengals": "Zac Taylor",
        "Browns": "Todd Monken",
        "Cowboys": "Brian Schottenheimer",
        "Broncos": "Sean Payton",
        "Lions": "Dan Campbell",
        "Packers": "Matt LaFleur",
        "Texans": "DeMeco Ryans",
        "Colts": "Shane Steichen",
        "Jaguars": "Liam Coen",
        "Chiefs": "Andy Reid",
        "Raiders": "Klint Kubiak",
        "Chargers": "Jim Harbaugh",
        "Rams": "Sean McVay",
        "Dolphins": "Jeff Hafley",
        "Vikings": "Kevin O'Connell",
        "Patriots": "Mike Vrabel",
        "Saints": "Kellen Moore",
        "Giants": "John Harbaugh",
        "Jets": "Aaron Glenn",
        "Eagles": "Nick Sirianni",
        "Steelers": "Mike McCarthy",
        "49ers": "Kyle Shanahan",
        "Seahawks": "Mike Macdonald",
        "Buccaneers": "Todd Bowles",
        "Titans": "Robert Saleh",
        "Commanders": "Dan Quinn",
    },
    "nba": {
        "Hawks": "Quin Snyder",
        "Celtics": "Joe Mazzulla",
        "Nets": "Jordi Fernandez",
        "Hornets": "Charles Lee",
        "Bulls": "Tiago Splitter",
        "Cavaliers": "Kenny Atkinson",
        "Mavericks": "Dusty May",
        "Nuggets": "David Adelman",
        "Pistons": "J. B. Bickerstaff",
        "Warriors": "Steve Kerr",
        "Rockets": "Ime Udoka",
        "Pacers": "Rick Carlisle",
        "Clippers": "Tyronn Lue",
        "Lakers": "JJ Redick",
        "Grizzlies": "Tuomas Iisalo",
        "Heat": "Erik Spoelstra",
        "Bucks": "Taylor Jenkins",
        "Timberwolves": "Chris Finch",
        "Pelicans": "Jamahl Mosley",
        "Knicks": "Mike Brown",
        "Thunder": "Mark Daigneault",
        "Magic": "Sean Sweeney",
        "76ers": "Nick Nurse",
        "Suns": "Jordan Ott",
        "Trail Blazers": "Micah Nori",
        "Kings": "Doug Christie",
        "Spurs": "Mitch Johnson",
        "Raptors": "Darko Rajakovic",
        "Jazz": "Will Hardy",
        "Wizards": "Brian Keefe",
    },
    "wnba": {
        "Dream": "Karl Smesko",
        "Sky": "Tyler Marsh",
        "Sun": "Rachid Meziane",
        "Fever": "Stephanie White",
        "Liberty": "Chris DeMarco",
        "Tempo": "Sandy Brondello",
        "Mystics": "Sydney Johnson",
        "Wings": "Jose Fernandez",
        "Valkyries": "Natalie Nakase",
        "Aces": "Becky Hammon",
        "Sparks": "Lynne Roberts",
        "Lynx": "Cheryl Reeve",
        "Mercury": "Nate Tibbetts",
        "Fire": "Alex Sarama",
        "Storm": "Sonia Raman",
    },
    "nhl": {
        "Ducks": "Joel Quenneville",
        "Bruins": "Marco Sturm",
        "Sabres": "Lindy Ruff",
        "Flames": "Ryan Huska",
        "Hurricanes": "Rod Brind'Amour",
        "Blackhawks": "Jeff Blashill",
        "Avalanche": "Jared Bednar",
        "Blue Jackets": "Rick Bowness",
        "Stars": "Glen Gulutzan",
        "Red Wings": "Todd McLellan",
        "Oilers": "Mike Babcock",
        "Panthers": "Paul Maurice",
        "Kings": "Peter Laviolette",
        "Wild": "John Hynes",
        "Canadiens": "Martin St. Louis",
        "Predators": "Andrew Brunette",
        "Devils": "Sheldon Keefe",
        "Islanders": "Peter DeBoer",
        "Rangers": "Mike Sullivan",
        "Senators": "Travis Green",
        "Flyers": "Rick Tocchet",
        "Penguins": "Dan Muse",
        "Sharks": "Ryan Warsofsky",
        "Kraken": "Lane Lambert",
        "Blues": "Jim Montgomery",
        "Lightning": "Jon Cooper",
        "Maple Leafs": "Jim Hiller",
        "Mammoth": "Andre Tourigny",
        "Canucks": "Manny Malhotra",
        "Golden Knights": "Ryan Craig",
        "Capitals": "Spencer Carbery",
        "Jets": "Scott Arniel",
    },
}

# INTERIM COACHES ARE WORTH KNOWING ABOUT.
#
# "Your interim manager" is a better line than the name alone - it says
# the season went wrong enough that somebody already got sacked.
INTERIM = {
    ("mlb", "Mets"), ("mlb", "Phillies"), ("mlb", "Red Sox"),
}

# TEAMS SHARING A NICKNAME ACROSS LEAGUES.
#
# Rangers are an NHL team and an MLB team. Panthers are NHL and NFL.
# Kings are NHL and NBA. Giants are MLB and NFL. Jets are NHL and NFL.
# So a lookup MUST know the sport - guessing from the nickname alone
# would have Smacky name a hockey coach in a baseball smack.
AMBIGUOUS = {"rangers", "panthers", "kings", "giants", "jets", "cardinals"}


def _key(name):
    return (name or "").strip().lower()


def for_team(sport, team_name):
    """
    Who runs this team, or None.

    Returns {name, title, interim} so a caller can say "manager Aaron
    Boone" or "interim manager Andy Green" without knowing the sport's
    conventions.
    """
    sport = (sport or "").lower()
    table = COACHES.get(sport)
    if not table or not team_name:
        return None

    want = _key(team_name)
    if not want:
        return None

    # Exact nickname first, then a contains match - the board gives
    # "Yankees" but a user might type "New York Yankees".
    for nick, coach in table.items():
        if _key(nick) == want:
            return _result(sport, nick, coach)
    for nick, coach in table.items():
        k = _key(nick)
        if k and (k in want or want in k):
            return _result(sport, nick, coach)
    return None


def _result(sport, nick, coach):
    return {
        "name": coach,
        "title": TITLES.get(sport, "head coach"),
        "interim": (sport, nick) in INTERIM,
        "team": nick,
    }


def describe(sport, team_name):
    """
    A phrase ready to drop into a prompt: "manager Aaron Boone", or
    "interim manager Andy Green". None when we do not know.
    """
    c = for_team(sport, team_name)
    if not c:
        return None
    title = ("interim " + c["title"]) if c["interim"] else c["title"]
    return f"{title} {c['name']}"


def known(sport=None):
    """How many we hold, for the admin panel."""
    if sport:
        return len(COACHES.get(sport.lower(), {}))
    return {k: len(v) for k, v in COACHES.items()}
