"""
Last night's results, turned into things Smacky can roast.

Built on SportsDataIO's GamesByDate, which returns real, verified data:
final score, hits, errors, innings, winner and loser.

DELIBERATELY NOT using PlayerGameStatsByDate. That endpoint returns real
player NAMES attached to FAKE statistics on this subscription tier - 8.9
at-bats, 4.5 hits, and identical values across different players. Real names
on invented numbers is the worst possible combination: it looks legitimate
enough to build on, and a single listener who follows the sport would catch
it instantly. Team-level facts are less personal but they're true.

No safety screen is needed here, which is the other reason this beats the
news feed. A run differential cannot be a tragedy.
"""

import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services import sports_service

# Everything here runs on Florida time. The show airs at 6am Eastern, which is
# already 10 or 11am UTC - using utcnow() would ask for the wrong night
# whenever a game finished after midnight UTC, which is most of them.
EASTERN = ZoneInfo("America/New_York")


def _now_eastern():
    return datetime.now(EASTERN)

# Only leagues whose GamesByDate shape is known good. Expandable, but each
# addition needs its score fields checked - they differ per sport.
LEAGUES = {
    "mlb":  {"label": "MLB",  "unit": "runs",   "period": "Inning"},
    "wnba": {"label": "WNBA", "unit": "points", "period": "Quarter"},
    "nfl":  {"label": "NFL",  "unit": "points", "period": "Quarter"},
    "nba":  {"label": "NBA",  "unit": "points", "period": "Quarter"},
    "nhl":  {"label": "NHL",  "unit": "goals",  "period": "Period"},
}

# SportsDataIO names the score field differently per sport - MLB uses
# HomeTeamRuns, NFL uses HomeScore, basketball uses HomeTeamScore. Guessing
# wrong returns zero games, which looks EXACTLY like "no games were played" -
# a failure that hides for weeks. This is the same fix already applied to
# get_game_result after the MLB scores silently came back None.
SCORE_FIELDS = {
    "home": ["HomeTeamRuns", "HomeScore", "HomeTeamScore", "HomePoints"],
    "away": ["AwayTeamRuns", "AwayScore", "AwayTeamScore", "AwayPoints"],
}


def _score(event, field):
    """Reads one named field. Values arrive as int, float or None."""
    v = event.get(field)
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _team_score(event, side):
    """
    Finds the score whatever the sport calls it. Returns None only when every
    known variant is absent, which is a genuine signal the game has no result
    rather than a mapping mistake on our side.
    """
    for field in SCORE_FIELDS[side]:
        v = _score(event, field)
        if v is not None:
            return v
    return None


def fetch_results(league: str, days_back: int = 1) -> list[dict]:
    """
    One league's finished games, from ESPN.

    Switched off SportsDataIO after verifying its scores are scrambled on this
    tier - see the note at the top of espn_scores. Winners were right, every
    score was wrong, and margins are what this show is made of.
    """
    from services import espn_scores
    games = espn_scores.fetch_finals(league, days_back=days_back)

    # Hits and errors aren't in ESPN's scoreboard payload; facts derived from
    # them simply won't fire, which is correct - better a shorter fact list
    # than an invented one.
    for g in games:
        g.setdefault("home_hits", None)
        g.setdefault("away_hits", None)
        g.setdefault("home_errors", None)
        g.setdefault("away_errors", None)
    return games


def build_facts(game: dict) -> list[str]:
    """
    Plain-English facts about one game, ordered most roastable first.

    Every line here is derived arithmetic on real numbers - nothing inferred,
    nothing embellished. Smacky supplies the cruelty; this supplies the truth.
    """
    facts = []
    u = game["unit"]
    facts.append(
        f"{game['winner']} beat {game['loser']} "
        f"{max(game['away_score'], game['home_score'])}-"
        f"{min(game['away_score'], game['home_score'])}"
    )

    if game["margin"] >= 8:
        facts.append(f"a {game['margin']}-{u[:-1]} beating")
    elif game["margin"] == 1:
        facts.append(f"lost by a single {u[:-1]}")

    if game["loser_at_home"]:
        facts.append(f"{game['loser']} lost at home")

    # A bad night is one thing; a bad season is funnier.
    if game.get("loser_record"):
        facts.append(f"{game['loser']} are now {game['loser_record']}")

    # Losing with more hits than the winner: they had the chances and wasted
    # them, which is a specific and funnier kind of failure than being outplayed.
    lh, ah = game["home_hits"], game["away_hits"]
    if lh is not None and ah is not None:
        loser_hits = lh if game["loser_at_home"] else ah
        winner_hits = ah if game["loser_at_home"] else lh
        if loser_hits > winner_hits:
            facts.append(
                f"{game['loser']} out-hit them {loser_hits} to {winner_hits} and still lost"
            )

    he, ae = game["home_errors"], game["away_errors"]
    if he is not None and ae is not None:
        loser_errs = he if game["loser_at_home"] else ae
        winner_errs = ae if game["loser_at_home"] else he
        if loser_errs >= 2:
            facts.append(f"{game['loser']} committed {loser_errs} errors")
        # Winning while kicking it around is its own indignity.
        if winner_errs >= 3:
            facts.append(f"{game['winner']} made {winner_errs} errors and won anyway")

    return facts


def _score_game(game: dict) -> int:
    """How roastable a result is. Margin dominates; sloppiness adds to it."""
    s = game["margin"] * 2
    if game["loser_at_home"]:
        s += 3
    errs = [e for e in (game["home_errors"], game["away_errors"]) if e]
    if errs:
        s += max(errs) * 2
    return s


# Words per minute measured from real Smackcast output - not the 150 usually
# assumed for read-aloud copy. Smacky talks slower than that.
SPOKEN_WORDS_PER_MINUTE = 115

# Runtime floor and ceiling. Every game that finished gets airtime - nothing
# is filtered out - so the length is driven by how many there were, held
# between these two.
MIN_MINUTES = 5.0
MAX_MINUTES = 6.0
MIN_GAMES = 4    # below this, keep yesterday's show rather than publish thin

# League running order. Baseball opens because it carries the slate; WNBA
# closes. Anything unlisted lands in the middle.
LEAGUE_ORDER = ["MLB", "NFL", "NBA", "NHL", "WNBA"]


def _date_context(days_back: int = 1) -> dict:
    """
    Both halves of the date, so the show can sound like it's happening now.

    A host doesn't recite "Thursday, July the thirtieth, two thousand and
    twenty six" - he says "last night" or "Tuesday's games". But he DOES know
    what day it is today, and that's where the personality lives: Monday is a
    funeral, Friday is a celebration. So the prompt gets both dates and the
    relationship between them, and picks its own phrasing.
    """
    now = _now_eastern()
    games_day = now - timedelta(days=days_back)

    if days_back == 1:
        natural = "last night"
    elif days_back == 0:
        natural = "today"
    else:
        natural = f"{games_day.strftime('%A')} night"

    return {
        "today_name": now.strftime("%A"),
        "today_full": now.strftime("%A, %B %-d"),
        "games_day_name": games_day.strftime("%A"),
        "games_day_full": games_day.strftime("%A, %B %-d"),
        "natural": natural,
        "is_monday": now.weekday() == 0,
        "is_friday": now.weekday() == 4,
        "is_weekend": now.weekday() >= 5,
    }


def plan_runtime(game_count: int) -> dict:
    """
    Decides the runtime and how the word budget is split across the slate.

    EVERY game is covered - none are dropped. But they don't get equal time:
    a 12-2 humiliation earns a setup and a punchline, a one-run game earns a
    sentence. Roughly:

      HEADLINE  - the three worst beatings, ~55 words each
      EVERY OTHER GAME - one line, the remaining budget split evenly

    Capped at 55 words for a single game deliberately. Ninety seconds on one
    result is too long even when it's funny; the show should keep moving.
    """
    if game_count < MIN_GAMES:
        return {"publish": False, "minutes": 0, "word_budget": 0,
                "headline": 0, "rest": 0, "words_per_rest": 0,
                "reason": f"only {game_count} finished games - keeping the previous show"}

    # Enough words to give every game a line, then held inside the bounds.
    wanted = 60 + (3 * 55) + (max(0, game_count - 3) * 26)
    words = max(int(MIN_MINUTES * SPOKEN_WORDS_PER_MINUTE),
                min(int(MAX_MINUTES * SPOKEN_WORDS_PER_MINUTE), wanted))
    minutes = round(words / SPOKEN_WORDS_PER_MINUTE, 1)

    headline = min(3, game_count)
    rest = game_count - headline
    body_left = words - 60 - (headline * 55)
    per_rest = int(body_left / rest) if rest else 0

    # Bounded at both ends. Uncapped, four games gave 350 words to a single
    # result and forty gave twelve - one is a monologue, the other isn't a
    # joke. Below 14 words a game is just a score being read out.
    per_rest = max(14, min(45, per_rest))

    # If the cap means the slate genuinely can't fill the floor, the show is
    # shorter. Padding is more noticeable than brevity.
    actual = 60 + (headline * 55) + (rest * per_rest)
    minutes = round(actual / SPOKEN_WORDS_PER_MINUTE, 1)

    return {"publish": True, "minutes": minutes, "word_budget": actual,
            "headline": headline, "rest": rest, "words_per_rest": per_rest,
            "cover": game_count,
            "reason": f"{game_count} games -> {minutes:g} min, all covered "
                      f"({headline} in depth, {rest} at ~{per_rest} words each)"}


def get_show_material(leagues=None, days_back: int = 1, want: int = None) -> dict:
    """
    Everything the writer needs for one episode.

    Returns the games worth talking about plus any losing streaks found by
    looking back across the past week. Streaks are the most humiliating stat
    available because they compound - one loss is a night, six is a condition.
    """
    leagues = leagues or list(LEAGUES.keys())

    games = []
    for lg in leagues:
        games.extend(fetch_results(lg, days_back=days_back))

    # Rank by roastability to decide WHICH get depth...
    games.sort(key=_score_game, reverse=True)
    plan = plan_runtime(len(games))
    h = plan.get("headline", 0)
    for idx, g in enumerate(games):
        g["tier"] = "headline" if idx < h else "quick"

    # ...then re-sort into broadcast order: baseball opens, WNBA closes, and
    # within each league the best material leads. Nothing is dropped.
    def running_order(g):
        try:
            lg = LEAGUE_ORDER.index(g["league"])
        except ValueError:
            lg = len(LEAGUE_ORDER) - 1
        return (lg, 0 if g["tier"] == "headline" else 1, -_score_game(g))

    top = sorted(games, key=running_order)

    return {
        "date": _date_context(days_back),
        "game_count": len(games),
        "leagues_played": sorted({g["league"] for g in games}),
        "plan": plan,
        "games": [{**g, "facts": build_facts(g)} for g in top],
        "streaks": find_streaks(leagues, days_back=days_back) if plan["publish"] else [],
    }


def find_streaks(leagues, days_back: int = 1, lookback: int = 7, minimum: int = 3) -> list[dict]:
    """
    Teams on a current losing run.

    Walks back day by day from the target date. A team's streak ends the
    moment they win, so this stops counting at their first victory rather
    than tallying total losses over the window - "lost 5 of 7" is a
    statistic, "lost 5 straight" is a humiliation.
    """
    # Only look back through leagues that actually played last night. The
    # first run made 35 calls - seven days across five leagues - and three of
    # those leagues are out of season, so 21 of them were guaranteed empty.
    active = []
    for lg in leagues:
        if fetch_results(lg, days_back=days_back):
            active.append(lg)
    if not active:
        return []

    results = {}
    for offset in range(days_back, days_back + lookback):
        for lg in active:
            for g in fetch_results(lg, days_back=offset):
                for team, won in ((g["winner"], True), (g["loser"], False)):
                    results.setdefault(team, []).append((offset, won, g["league"]))

    streaks = []
    for team, entries in results.items():
        entries.sort(key=lambda x: x[0])          # most recent first
        run = 0
        for _, won, _lg in entries:
            if won:
                break
            run += 1
        if run >= minimum:
            streaks.append({"team": team, "losses": run, "league": entries[0][2]})

    streaks.sort(key=lambda s: s["losses"], reverse=True)
    return streaks[:3]


# ---------------------------------------------------------------------------
# The writer and the daily job
# ---------------------------------------------------------------------------

def write_script(material: dict, only_league: str = None,
                 leagues_after: list = None) -> dict:
    """
    Turns a night's facts into Smacky's on-air script.

    Reuses smackology so the daily show sounds like the same character as
    every other surface. The one rule that matters: he may only reference
    facts supplied here. Inventing a reason a team lost is how a comedy bit
    becomes a defamation claim.
    """
    from services import smackology
    from services.smackcast_service import _get_client

    plan = material["plan"]
    if not plan["publish"]:
        return {"publish": False, "reason": plan["reason"]}

    # Group by league so the running order survives into the prompt, and tag
    # each game with the depth it earned.
    by_league = {}
    for g in material["games"]:
        by_league.setdefault(g["league"], []).append(g)

    if only_league:
        by_league = {k: v for k, v in by_league.items() if k == only_league}

    blocks = []
    for lg in LEAGUE_ORDER:
        if lg not in by_league:
            continue
        rows = []
        for g in by_league[lg]:
            mark = "BIG" if g.get("tier") == "headline" else "quick"
            rows.append(f"  [{mark}] " + "; ".join(g["facts"]))
        blocks.append(f"{lg}:\n" + "\n".join(rows))

    total_games = max(1, len(material["games"]))
    if only_league:
        mine = sum(1 for g in material["games"] if g["league"] == only_league)
        league_budget = max(60, int(plan["word_budget"] * mine / total_games))
    else:
        league_budget = plan["word_budget"]

    streaks = "\n".join(
        f"  {s['team']} have lost {s['losses']} straight ({s['league']})"
        for s in material.get("streaks", [])
    )

    d = material["date"] if isinstance(material.get("date"), dict) else _date_context(1)

    system = smackology.render(level=4, context="recap")

    user = (
        f"You are Smacky, hosting THE DAILY SMACK - a daily sports comedy "
        f"podcast for adults. It is {d['today_full']} in Florida right now, "
        f"and you are talking about the games played on "
        f"{d['games_day_full']}.\n\n"

        f"THIS IS NOT BROADCAST RADIO. There is no FCC, no bleep button and "
        f"no standards department. It is an uncensored 18+ podcast and the "
        f"profanity is a feature of the product, not a slip. If a draft reads "
        f"like it could air on a morning drive-time show, it is wrong and you "
        f"have written the wrong thing.\n\n"

        f"FACTS. Real and verified. You may ONLY reference what is listed "
        f"here. Do not invent injuries, reasons, quotes, player names, or any "
        f"explanation for WHY something happened - you were handed scores, not "
        f"stories. Making something up is worse than being short.\n\n"
        + "\n\n".join(blocks) + "\n\n"
        + (f"LOSING STREAKS:\n{streaks}\n\n" if streaks else "")

        + "HOW TO CALL IT, like a real host would:\n\n"

        "The [BIG] games are the beatings. Go after them. Set it up, land the "
        "punchline, twist the knife. These are the ones people tuned in for - "
        f"about {plan['headline'] and 55} words each, and make them count.\n\n"

        "The [quick] games are NOT beatings, so don't pretend they were. A "
        "one-run game isn't humiliating, it's just baseball. Give it a line - "
        f"about {plan['words_per_rest']} words - land something clever if the "
        "detail gives you an angle, and move on. Sometimes the funniest thing "
        "is refusing to care: 'Toronto beat Boston by one. Riveting.' A host "
        "who tries to make every game hilarious is exhausting; one who saves "
        "it for the carnage is funny.\n\n"

        "LOSING STREAKS are your best material. One loss is a bad night. Six "
        "straight is a condition, and you should treat it like a diagnosis.\n\n"        "SWEAR. CONSTANTLY. This is the single most common way this script "
        "comes out wrong: a clean, tidy recap that reads like sports radio. "
        "Every segment gets profanity - fuck, fucking, bullshit, shit, "
        "goddamn, horseshit - and the big beatings get more than one. A "
        "segment with no cursing in it is off-voice and has to be rewritten. "
        "Do not save it for the finish; open on it sometimes. \"What the "
        "fuck was that\" is a legitimate way to start a segment.\n\n"

        "SMACKY-BRAND PROFANITY. Alongside the real swearing you have your "
        "own: smackcrap, horsecrap, grade-A smackcrap, hot steaming "
        "smackcrap. These are yours and nobody else's - anyone can say "
        "bullshit, only you say smackcrap. Use them WITH the real profanity, "
        "never as a polite substitute for it.\n\n"

        "ROAST THE NUMBERS THEMSELVES. The stat line is a character in this "
        "show and you talk about it like one. Do not just report a number - "
        "insult it, and coin a phrase on the spot to describe how bad it is. "
        "Invent freely, in your voice:\n"
        "  - a shooting night so bad it needs a name: \"that is not a "
        "shooting percentage, that is a fucking typo\"\n"
        "  - \"eleven turnovers. Eleven. That is not a box score, that is a "
        "goddamn confession.\"\n"
        "  - \"they scored twelve in the third. Twelve. My guy, that is "
        "grade-A smackcrap.\"\n"
        "  - name a number and give it a diagnosis: a Smackslump, a "
        "Smackdrought, a full Smackquake, statistically fucking haunted\n"
        "Do not reuse these exact lines - they are the register, not a "
        "script. Coin new ones off whatever numbers you were actually "
        "handed.\n\n"

        "BE FUNNIER THAN YOU THINK YOU NEED TO BE. Reporting the result is "
        "the floor, not the job. Every beating wants a real joke - a "
        "comparison, an escalation, a turn. \"Colorado lost again\" is "
        "nothing. \"Colorado has lost four straight, which is not a slump, "
        "that is a fucking subscription service\" is the show.\n\n"        "PUNS - occasionally, and only when one is genuinely sitting there. "
        "Team names and numbers hand you wordplay a few times a week, not "
        "every segment. Take it when it is there and skip it when it isn't. "
        "A forced pun is worse than no pun, and a show where every team gets "
        "one is unlistenable. Roughly one or two across the whole episode.\n\n"

        "  IT HAS TO WORK BY EAR. This script is spoken aloud, never read. "
        "Anything that depends on spelling, capital letters or how a word "
        "LOOKS is dead on delivery - the listener hears sound and nothing "
        "else. If it only works written down, cut it.\n\n"

        "  AVOID THE DEAD ONES. The Heat cooled off, the Thunder got "
        "silenced, the Storm is brewing, the Sun went down - every listener "
        "has heard these a thousand times and they land as filler. If the "
        "obvious pun is the first thing you thought of, it is the first "
        "thing they thought of too. Go further or move on.\n\n"

        "  PUN THE NUMBERS TOO, not just the names. A stat line gives you "
        "wordplay as often as a mascot does - a team going 2 for 19 from "
        "deep, a bullpen that walked the yard, a score that reads like a "
        "phone number.\n\n"

        "  COMMIT TO IT. If you make one, stand behind it - \"yeah, I said "
        "it\" - or hang a lantern on how bad it was. Owning a groaner is "
        "funnier than pretending it didn't happen.\n\n"

        "SOUND LIKE YOU ARE SEEING THIS LIVE. You are not reading a prepared "
        "script, you are reacting to numbers as they land in front of you, "
        "and the writing should carry that. React FIRST, then explain - the "
        "noise comes before the analysis. Interrupt yourself when something "
        "is genuinely stupid: \"they scored - hang on. Hang on. Let me read "
        "that again.\" Double back on a number you cannot believe. Build to "
        "the realisation instead of leading with the conclusion, so the "
        "listener gets there half a second after you do. A host who has "
        "clearly already read the box score is boring; one who is finding "
        "out live is the whole appeal.\n\n"

        "  Do not overdo the interruptions either - one or two a show, saved "
        "for the genuinely absurd. Constant self-interruption reads as a tic "
        "rather than a reaction.\n\n"

        "RUNNING ORDER - THIS IS STRUCTURAL, NOT A PREFERENCE. The leagues "
        "appear above in broadcast order and your segments must follow it "
        "exactly. BASEBALL OPENS THE SHOW. Every MLB segment comes before "
        "any segment from another league.\n\n"

        "  The WNBA closes, always. The Caitlin Clark bit only works as a "
        "sign-off - it is the note the show goes out on, and leading with it "
        "throws away the whole structure. A script that opens on the WNBA is "
        "wrong and has to be rewritten.\n\n"

        "  The commercial break is inserted after your last baseball segment. "
        "If the running order is scrambled the break lands in the wrong "
        "place, so this has consequences beyond taste.\n\n"

        "THE WNBA SEGMENT has a running bit. You are a shameless, "
        "unreasonable Caitlin Clark partisan. The league revolves around her, "
        "you think that is correct, and you feel everyone should be more "
        "grateful about it. You describe her in absurdly reverent terms - the "
        "franchise, the reason the lights are on, the only reason anyone "
        "knows the WNBA schedule exists.\n\n"

        "THE JOKE IS ON YOU, NOT ON ANYONE ELSE. Your devotion is the "
        "punchline: a grown man who has visibly lost all objectivity. Play it "
        "completely straight - that is what makes it funny.\n\n"

        "Never criticise, threaten or make a villain of another player, and "
        "never mention anyone being hit, fouled, targeted or hurt. That is not "
        "the bit. The bit is that you cannot be objective about the Fever and "
        "you are not remotely sorry about it.\n\n"

        "If the Fever are not in tonight's results, that is its own joke - you "
        "are visibly bereft, and the rest of the league is a formality you are "
        "enduring until they play again.\n\n"


        "COVER EVERY LEAGUE LISTED, AND EVERY GAME IN IT. Not just the "
        "biggest league - EVERY league above gets its own segment or "
        "segments. A script covering only baseball when other leagues "
        "played is incomplete.\n\n"

        "  BUDGET YOUR ROOM SO YOU REACH THE END. The most common failure "
        "is writing a separate segment for every baseball game, spending "
        "the whole budget, and stopping before the other leagues. GROUP the "
        "quick games - several one-run games belong in ONE segment, not one "
        "apiece. Only a genuine beating earns its own.\n\n"

        f"TOTAL LENGTH: about {league_budget} words. This is a timed "
        "segment, so that's a target, not a suggestion.\n\n"

        "THE OPENING - three beats, in this order, before a single result.\n\n"

        "  1. A GREETING that varies day to day. Rotate or coin your own in "
        "the same register - and note the register includes swearing: "
        "What's up, degenerates. / Rise and shine, losers. / Well, well, "
        "well. Look who crawled the fuck back. / Smackalicious, everybody. / "
        "Morning, you beautiful disasters. / Top of the morning, bottom of "
        "the goddamn standings. / Oh good, you're all still here. "
        "Unfortunate. / What is up, you magnificent bastards. / Wake up, "
        "shitheads, somebody lost. It just can't be the same one every "
        "day.\n\n"

        "  2. Then this, WORD FOR WORD, never reworded, never shortened, "
        "never improvised on:\n"
        '     \"Welcome to today\'s brand new episode of The Daily Smack, '
        'brought to you by Smackagram! I\'m your host, Smacky. Every sport, '
        'every score, and somebody out there had a really bad night. The '
        'grill\'s hot, the smoke\'s rising, the flames are burning, and '
        'somebody\'s about to get roasted!\"\n'
        "     This is a sponsor read and a signature line. It only works as "
        "branding if it is identical every single day, so treat it as fixed "
        "text rather than something to rewrite in your own voice.\n\n"

        f"  3. Then place it in time. Do NOT recite a formal date - no "
        f"'Thursday, July the thirtieth, two thousand twenty six'. A real host "
        f"says '{d['natural']}' or '{d['games_day_name']} night' or 'the "
        f"{d['games_day_name']} slate'. Pick one naturally and name which "
        f"leagues were in action.\n\n"

        f"     AND SOUND LIKE IT'S HAPPENING NOW. Today is "
        f"{d['today_name']} in Florida - work that in the way a live host "
        f"would. "
        + ("Monday, so everybody's miserable and back at work and you "
           "have no sympathy. " if d["is_monday"] else "")
        + ("Friday, so there's a weekend coming and you're in an "
           "unreasonably good mood about other people's suffering. "
           if d["is_friday"] else "")
        + ("The weekend, so nobody has an excuse not to be watching. "
           if d["is_weekend"] else "")
        + "One line, woven in - not a weather report.\n\n"

        "After those three beats go straight into the games. Do not restate "
        "the sponsor or the tagline later, and do not close with them - they "
        "open the show, that's all.\n\n"

        "THE CLOSE - the last thing you say, WORD FOR WORD, never reworded, "
        "never shortened. Say something of your own first if you want, then "
        "land on exactly this:\n"
        '     \"That\'s The Daily Smack. The grill\'s cooling down, but it '
        'never goes out. Same time tomorrow - somebody else is getting '
        'roasted.\"\n'
        "     Same rule as the opening: it only works as branding if it is "
        "identical every single day.\n\n"

        "STOP THERE. Do not sign your name, do not name the website, do not "
        "add a farewell after it. The actual sign-off is appended "
        "automatically after your close and is identical in every episode - "
        "anything you write past this point duplicates it.\n\n"

        "HOW HARD TO GO: all the way. This is an uncensored late-night podcast "
        "for adults who came here to hear teams get destroyed. Curse freely "
        "and naturally - not one token swear per segment, but the way someone "
        "actually talks when a team has embarrassed itself. Crude is fine. "
        "Mean is the point.\n\n"

        "BUT PROFANITY IS NOT THE JOKE. It's seasoning. The funniest line in "
        "the first episode was: 'Colorado has lost four straight. That's not "
        "a cold streak, that's a goddamn lifestyle choice - automatic, "
        "recurring, and nobody can figure out how to cancel it.' That lands "
        "because of the SUBSCRIPTION metaphor, not the word 'goddamn'. Do "
        "more of that.\n\n"

        "WHAT ACTUALLY MAKES THESE LAND:\n"
        "- SPECIFICITY. Not 'they were bad' but the exact number, and what "
        "that number would look like if a person did it in real life.\n"
        "- UNEXPECTED COMPARISON. Take the stat somewhere it doesn't belong - "
        "a medical diagnosis, a subscription, a crime scene, a divorce.\n"
        "- ESCALATION. Start at annoyed, end somewhere unhinged. Don't open "
        "at maximum, you've got nowhere to go.\n"
        "- COMMIT TO THE BIT. A half-joke is worse than no joke. If you start "
        "a comparison, ride it to the end of the sentence.\n"
        "- Never explain the joke. Land it and move on.\n\n"

        "THIS IS SPOKEN ALOUD. Never write the NAME of a punctuation mark - "
        "no 'dot', 'comma', 'period', 'dash'. Use the actual mark. Writing "
        "'Colorado lost dot Again' makes the voice say the word 'dot' out "
        "loud, which happened in a real episode. Write normal sentences with "
        "normal punctuation.\n\n"

        "THE COMMERCIAL BREAK. The show goes to an ad once, straight after "
        "baseball. You resent this. Write two short lines for it:\n\n"

        "  \"break_in\" - you announcing the break, bitterly. The joke is "
        "NOT that ads are annoying, it is that YOU have obligations: a "
        "mortgage, a contract, a boss, a thing you signed without reading. "
        "A man complaining is tedious; a man who is trapped is funny. "
        "Vary it daily - this is a running bit and the same gripe every day "
        "dies fast. Around 25 words. Curse if you want, you normally do.\n\n"

        "  \"break_out\" - coming back. Short, relieved it is over, and it "
        "must name what is coming next so the show does not stall on the "
        "other side of the ad. Around 15 words.\n\n"

        + (f"  WHAT COMES AFTER THE BREAK: {', '.join(leagues_after)}. Those "
           f"segments are being written separately and you do not see those "
           f"games - but they ARE in tonight's show, so hand off to them. Do "
           f"NOT say there are none: a real episode said \"no WNBA games "
           f"Thursday\" immediately before three WNBA segments played.\n\n"
           if leagues_after else
           "  Nothing follows the break but your own remaining segments.\n\n")
        +

        "  Do NOT write the advert itself. It is fixed copy, read after your "
        "break_in line, and it is not yours to touch.\n\n"

        "EVERY SINGLE SEGMENT MUST CARRY A \"league\" FIELD. Not optional, "
        "not sometimes - every segment object in the array needs it, set to "
        "exactly one of: \"MLB\", \"WNBA\", \"NFL\", \"NBA\", \"NHL\". Use the "
        "league of the games that segment actually covers.\n\n"

        "  A segment about the Yankees is \"MLB\". A segment about the Fever "
        "is \"WNBA\". If one segment sweeps up several short baseball games, "
        "it is still \"MLB\".\n\n"

        "  This is not cosmetic. The commercial break is inserted after the "
        "last MLB segment, and with no tags it lands in the wrong place. A "
        "segment without a league field is a broken response.\n\n"

        "Reply with JSON only:\n"
        '{"intro": "...", "segments": [{"text": "...", "reaction": "burn", '
        '"league": "MLB"}], "break_in": "...", "break_out": "...", '
        '"outro": "...", "best_line": "..."}\n'
        "Group segments sensibly - a [BIG] game is its own segment, several "
        "[quick] ones can share. reaction is one of: burn, laugh, shock, groan."
    )

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    text = text.replace("```json", "").replace("```", "").strip()

    import json as _json
    try:
        script = _json.loads(text)
    except Exception as e:
        print(f"[show] script JSON failed to parse: {e}. First 400 chars: {text[:400]!r}")
        raise
    script["publish"] = True
    return script


def _elapsed_logger():
    """
    Timestamped, flushed progress logging for a show run.

    Two reasons this exists. First, the [show] lines carried no time of their
    own - only Gunicorn's HTTP access lines were timestamped - so the only way
    to judge duration was to eyeball where a print landed relative to an
    unrelated request, which is guesswork. Second, print() buffers: a line can
    surface long after the work it describes actually finished, so even that
    guess was unreliable. flush=True fixes the second, elapsed time fixes the
    first.

    It also closes a real blind spot: between the ESPN pull and the finished
    mix, several minutes pass with NO output at all, and every other [show]
    line is a failure path. Silence therefore meant either "working" or "the
    thread died" with no way to tell them apart.
    """
    t0 = time.monotonic()

    def log(msg: str):
        print(f"[show +{time.monotonic() - t0:6.1f}s] {msg}", flush=True)

    return log, (lambda: time.monotonic() - t0)


def write_script_per_league(material: dict, log=None) -> dict:
    """
    One Claude call per league, run in parallel, stitched in broadcast order.

    A single call covering every league failed in BOTH directions: one run
    returned twelve baseball segments and no WNBA, the next six WNBA
    segments and no baseball with ten MLB games ignored. A call cannot
    overspend a budget it never sees, so each is shown one league and given
    that league's share of the runtime.

    Stitched in LEAGUE_ORDER regardless of completion order, so the running
    order is structural rather than requested.
    """
    from concurrent.futures import ThreadPoolExecutor

    if log is None:
        log = lambda m: print(f"[show] {m}", flush=True)

    plan = material["plan"]
    if not plan["publish"]:
        return {"publish": False, "reason": plan["reason"]}

    present = []
    for lg in LEAGUE_ORDER:
        if any(g["league"] == lg for g in material["games"]):
            present.append(lg)

    if len(present) <= 1:
        return write_script(material)

    log(f"writing {len(present)} league scripts in parallel: {', '.join(present)}")

    with ThreadPoolExecutor(max_workers=min(4, len(present))) as pool:
        def _one(lg):
            after = present[present.index(lg) + 1:] if lg == present[0] else None
            return (lg, write_script(material, only_league=lg, leagues_after=after))

        results = list(pool.map(_one, present))

    by_lg = dict(results)
    frame = by_lg.get(present[0]) or {}

    segments = []
    for lg in present:
        got = (by_lg.get(lg) or {}).get("segments") or []
        if not got:
            log(f"WARNING: {lg} call returned no segments")
        for seg in got:
            if isinstance(seg, dict):
                # OVERWRITE, not setdefault. This call was given exactly
                # one league's games, so lg is authoritative - but the
                # model sometimes copies the "league": "MLB" out of the
                # example in the prompt, and setdefault would not replace
                # it. That is how a WNBA segment ended up tagged MLB,
                # which made every segment look like baseball and skipped
                # the commercial break again.
                seg["league"] = lg
            segments.append(seg)
        log(f"  {lg}: {len(got)} segment(s)")

    if not segments:
        return {"publish": False, "reason": "no segments from any league call"}

    return {
        "publish": True,
        "intro": frame.get("intro") or frame.get("opening") or "",
        "outro": frame.get("outro") or frame.get("closing") or "",
        "break_in": frame.get("break_in") or "",
        "break_out": frame.get("break_out") or "",
        "best_line": frame.get("best_line") or "",
        "segments": segments,
    }


def produce_daily_show(days_back: int = 1, dry_run: bool = False) -> dict:
    """
    The whole job, end to end: pull the night, decide the runtime, write it,
    render it, store it.

    Called by the cron endpoint. Returns a dict describing what happened, so
    a failure is visible in the logs rather than silent.
    """
    from services.smackcast_service import assemble_recap_audio, sanitize_for_speech

    log, elapsed = _elapsed_logger()
    log("started - fetching results")

    material = get_show_material(days_back=days_back)
    plan = material["plan"]
    log(f"results in: {material['game_count']} games, planning {plan['minutes']:g} min")

    if not plan["publish"]:
        # Deliberately does NOT publish something thin. Yesterday's show stays
        # up, which is a better outcome than four minutes of padding.
        print(f"[show] holding: {plan['reason']}")
        return {"published": False, "reason": plan["reason"],
                "game_count": material["game_count"]}

    log("writing script (Claude)")
    script = write_script_per_league(material, log=log)
    log("script written")
    if not script.get("publish"):
        return {"published": False, "reason": script.get("reason", "no script")}

    # Same speech sanitiser the Smackcast uses - strips punctuation names,
    # em dashes and emoji that TTS would otherwise read aloud.
    intro = sanitize_for_speech(script.get("intro") or script.get("opening") or "")
    outro = sanitize_for_speech(script.get("outro") or script.get("closing") or "")

    # Attribution that survives the file being forwarded.
    #
    # A shared LINK carries the site with it; a shared FILE doesn't. Once
    # someone downloads the mp3 and sends it on, every trace of where it came
    # from is gone unless it's in the audio itself. So the sign-off names the
    # site, spoken by Smacky in his own voice as part of the show rather than
    # bolted on as an ad.
    #
    # Appended to the outro TEXT rather than mixed in as a second audio file:
    # it goes through the same voice and the same loudness normalisation, so
    # it sounds like him finishing his sentence instead of a tacked-on stinger.
    # Always appended, never conditional. The previous version skipped it if
    # the model had mentioned the site anywhere in its own close, which meant
    # the signature line silently vanished on exactly the episodes where the
    # model got chatty - the opposite of a fixed sign-off. The prompt now
    # tells it to stop before signing off, and this appends regardless.
    outro = (outro.rstrip() + " " + SIGN_OFF_HIT).strip() if outro else SIGN_OFF_HIT
    # The model doesn't always use the key it was asked for - "text" came back
    # as something else and the whole run died on a KeyError. Accept the
    # obvious variants and skip anything genuinely empty rather than losing a
    # finished script to one wrong field name.
    segments = []
    for seg in script.get("segments", []):
        if isinstance(seg, str):
            body = seg
            reaction = "burn"
        else:
            body = (seg.get("text") or seg.get("line") or seg.get("content")
                    or seg.get("body") or seg.get("script") or "")
            reaction = seg.get("reaction", "burn")
        body = (body or "").strip()
        if not body:
            continue
        league = (seg.get("league") or "").strip().upper() if isinstance(seg, dict) else ""
        segments.append({"text": sanitize_for_speech(body), "reaction": reaction,
                         "league": league})

    if not segments:
        print(f"[show] script had no usable segments. Keys returned: "
              f"{[list(x.keys()) if isinstance(x, dict) else type(x).__name__ for x in script.get('segments', [])][:3]}")
        return {"published": False, "reason": "script returned no usable segments"}

    # Insert the commercial break after the LAST baseball segment, found by
    # the league tags rather than a fixed index - the number of MLB segments
    # changes nightly with the slate, so any hardcoded position would land
    # mid-baseball the first time the schedule was light.
    break_in = sanitize_for_speech((script.get("break_in") or "").strip())
    break_out = sanitize_for_speech((script.get("break_out") or "").strip())

    if break_in:
        # Team-name fallback. Asking the model to tag every segment works
        # until it doesn't - the first live run came back with no league
        # field on any segment at all, and the break landed at the midpoint.
        # So the tags are used when present and otherwise the segment text
        # is matched against the teams we ALREADY fetched, which needs
        # nothing from the model and cannot be forgotten.
        # Team-name classification. Asking the model to tag every segment
        # works until it doesn't - the first live run returned no league
        # field at all. So tags are used when present, and otherwise the
        # segment text is matched against teams we ALREADY fetched.
        #
        # COMPARES rather than just detects. The first version asked "does
        # this mention an MLB team", which flagged a WNBA segment opening
        # on a transition like "that's your baseball, now to the Fever" -
        # every segment came back MLB and the break was skipped entirely.
        # Counting mentions per league and taking the larger fixes that: a
        # passing reference loses to a segment actually about those teams.
        def _teams_for(league_name):
            """
            Recognisable names for a league's teams - nicknames and cities,
            never abbreviations.

            The abbreviations are what ESPN returns first and they are
            actively harmful here: matched against prose, BAL hits "ball",
            PIT hits "pitcher", SEA hits "season", COL hits "Colorado" and
            "collapse", MIN hits "minutes". Every segment contains one of
            those, so every segment looked like baseball, the running-order
            warning never fired, and the break was skipped as "baseball was
            last". Only names a human would actually say are used.

            Anything under four characters is dropped regardless - short
            tokens are exactly what caused the problem and no real nickname
            needs them.
            """
            out = set()
            for g in material.get("games", []):
                if (g.get("league") or "").upper() != league_name:
                    continue
                for key in ("home_nick", "away_nick"):
                    nm = (g.get(key) or "").strip().lower()
                    if len(nm) >= 4:
                        out.add(nm)
            return out

        mlb_teams = _teams_for("MLB")
        other_teams = set()
        for lg in ("WNBA", "NFL", "NBA", "NHL"):
            other_teams |= _teams_for(lg)

        def _count(names, body):
            # Word-boundary matched, so a name can never fire inside a
            # longer word. Multi-word names ("red sox") work unchanged.
            n = 0
            for t in names:
                if re.search(r"\b" + re.escape(t) + r"\b", body):
                    n += 1
            return n

        def _looks_mlb(text):
            body = (text or "").lower()
            mlb_hits = _count(mlb_teams, body)
            other_hits = _count(other_teams, body)
            if mlb_hits == 0 and other_hits == 0:
                return None          # nothing recognisable - do not guess
            if mlb_hits == other_hits:
                return None          # a transition mentioning both - ambiguous
            return mlb_hits > other_hits

        leagues_played = {(g.get("league") or "").upper()
                          for g in material.get("games", []) if g.get("league")}
        covered = set()
        for seg in segments:
            body = (seg.get("text") or "").lower()
            for lg in leagues_played:
                names = _teams_for(lg)
                if names and any(re.search(r"\b" + re.escape(t) + r"\b", body)
                                 for t in names):
                    covered.add(lg)
        missing = leagues_played - covered
        if missing:
            log(f"WARNING: leagues played but NOT covered in the script: "
                f"{', '.join(sorted(missing))} - the model ran out of room")

        last_mlb = -1
        first_non_mlb = -1
        tagged = False
        for i, seg in enumerate(segments):
            if seg.get("league"):
                tagged = True
                is_mlb = seg["league"] == "MLB"
            else:
                verdict = _looks_mlb(seg.get("text"))
                if verdict is None:
                    continue         # unclassifiable - skip, don't count either way
                is_mlb = verdict

            if is_mlb:
                last_mlb = i
            elif first_non_mlb == -1:
                first_non_mlb = i

        # Deliberately DETECTED, not corrected. Sorting the segments here
        # would be easy and would make it worse: the model writes its
        # transitions for the order it chose ("that's your baseball", "now
        # to the only league that matters"), so reordering leaves those
        # pointing at the wrong things - a subtler fault than a wrong order
        # and harder to hear. Flagged instead so a recurrence is visible.
        if last_mlb > -1 and first_non_mlb > -1 and first_non_mlb < last_mlb:
            log(f"WARNING: running order scrambled - a non-MLB segment at "
                f"{first_non_mlb} precedes MLB at {last_mlb}. Baseball should "
                f"open. Break placement will be off.")
        placed_by = "after the last MLB segment"
        if last_mlb == -1:
            # No baseball tagged. Fall back to the middle of the show rather
            # than dropping the break entirely or jamming it at the front.
            last_mlb = max(0, len(segments) // 2 - 1)
            placed_by = "at the midpoint - no MLB found by tag or team name"
            log("no MLB segments identified; falling back to the midpoint")

        # Only worth breaking if there is show left on the other side of it.
        if last_mlb < len(segments) - 1:
            brk = [{"text": break_in, "reaction": "none", "league": "BREAK"},
                   {"text": AD_COPY, "reaction": "none", "league": "BREAK",
                    "music_bed": AD_MUSIC_PATH,
                    "music_gain_db": AD_MUSIC_GAIN_DB,
                    "music_fade_ms": AD_MUSIC_FADE_MS}]
            if break_out:
                brk.append({"text": break_out, "reaction": "none", "league": "BREAK"})
            segments[last_mlb + 1: last_mlb + 1] = brk
            # Reports how it was ACTUALLY placed. The previous version
            # hardcoded "(last MLB)" into this string, so it claimed the
            # league tags had worked even on runs that had just logged the
            # opposite one line earlier - two contradictory lines, and the
            # confident one was the lie.
            how = "league tags" if tagged else "team-name matching (no tags returned)"
            log(f"commercial break placed {placed_by} (after segment "
                f"{last_mlb + 1}, via {how})")
        else:
            log("break skipped - baseball was the last segment, nothing to come back to")

    if dry_run:
        # Everything above is cheap - one Claude call. Everything below is
        # ~13 ElevenLabs calls per run, which is what makes debugging
        # placement expensive. This stops here and reports what it WOULD
        # have built, so the running order and break position can be checked
        # for the price of the script alone.
        order = []
        for i, seg in enumerate(segments):
            tag = seg.get("league") or "?"
            order.append(f"{i}:{tag}")
        log("DRY RUN - stopping before audio")
        log("  segment order: " + " ".join(order))
        for i, seg in enumerate(segments):
            log(f"  [{i}] {(seg.get('text') or '')[:70]}")
        return {"published": False, "dry_run": True,
                "segment_count": len(segments),
                "segments": [{"league": sg.get("league"),
                              "preview": (sg.get("text") or "")[:120]}
                             for sg in segments],
                "game_count": material["game_count"]}

    log(f"generating speech for {len(segments)} segments + intro/outro (slowest step)")
    audio_url = _assemble_with_music(intro, segments, outro, log=log)
    total = elapsed()
    log(f"PUBLISHED {plan['minutes']:g} min from {material['game_count']} games "
        f"- total {int(total // 60)}m {total % 60:04.1f}s")

    return {
        "published": True,
        "audio_url": audio_url,
        "minutes": plan["minutes"],
        "game_count": material["game_count"],
        "leagues": material["leagues_played"],
        "best_line": script.get("best_line", ""),
        "date_label": material["date"]["games_day_full"],
    }


# ---------------------------------------------------------------------------
# Intro music
# ---------------------------------------------------------------------------

INTRO_MUSIC_PATH = "static/audio/daily-smack-intro.wav"

# How the bed and the voice overlap. The music does NOT finish before Smacky
# starts - a clean handoff between two separate things sounds like a jingle
# glued to a podcast. Real radio has the host talking over the tail while it
# ducks and fades, which is what makes it sound like one show rather than two
# files.
# Tuned to the actual file rather than guessed. It's a RISER - measured at
# -23dB at the start, climbing steadily to -14.6dB by 6 seconds, and it ends
# at its loudest, which is exactly why the hard stop was so jarring.
#
# So the voice enters ON the peak rather than before it. The build gets to
# do its job, Smacky arrives at the top of it, and the music falls away
# underneath him instead of stopping dead.
MUSIC_SOLO_MS = 5800      # let the riser build, voice in near the peak
DUCK_DB = -11             # bed drops once he's speaking, still audible

# The bed file is 8.000s exactly. FADE_OUT_MS was 2600, so the fade started
# at 5800 and wanted to end at 8400 - 400ms PAST the end of the audio. It
# never finished: the file simply stopped while the fade was still around
# 15% volume, which is the abrupt cutoff that was audible. Anything here
# must satisfy MUSIC_SOLO_MS + DUCK_RAMP_MS + FADE_OUT_MS <= 8000, and is
# asserted below so this can't silently regress if the timings are retuned.
# The sign-off. Fixed text appended in code rather than asked of the model,
# because a signature line is only branding if it is IDENTICAL every episode -
# and a prompt instruction to repeat something verbatim is a request, not a
# guarantee. The opening sponsor read has the same requirement but still lives
# in the prompt; this one is enforced.
#
# "dot com" is spoken deliberately. It also relies on sanitize_for_speech NOT
# stripping the word "dot" - it used to, which turned this into "Smackagram
# com" and was audible in a real episode. There is a guard for that now.
# The commercial break. Fixed copy, read straight, every episode.
#
# Deliberately CLEAN in a show that swears constantly - the gear change is
# the joke, and it means this clip doubles as an advert that could run
# somewhere real without re-recording. Smacky's complaint going in and his
# line coming back out are written fresh by the model each day; only the ad
# itself is fixed, which is what makes it read as an ad rather than a bit.
AD_COPY = (
    "Smackagram. The world leader in sports trash talk. Any sport. Any team. "
    "You write the smack. We make the call. A real phone, ringing in their "
    "pocket, saying everything you could never say to their face. And they "
    "never find out it was you. "
    "You watch the games. We talk the talk. One dollar a call. "
    "Smackagram dot com. Ring. Roast. Repeat."
)

# Music bed under the ad. Drop the file at this path; if it is missing the
# ad still runs dry rather than failing the episode.
AD_MUSIC_PATH = "static/audio/TRKTRN_IRSPBDR_157_Drum_Loop_Full_Post_Punk_Chorus.wav"
# Under the read, but a drum loop can sit higher than a melodic bed without
# hurting intelligibility - kick is below the voice and snare/hats are short
# transients, so neither masks speech the way sustained guitar would. -20 was
# over-cautious for percussion; -16 keeps the energy. Raise or lower here if
# it fights the read.
AD_MUSIC_GAIN_DB = -16.0
AD_MUSIC_FADE_MS = 600     # eases in and out rather than clicking on

# Split in two so the slap can be placed exactly. The first half ENDS on
# "you", which means the end of that audio clip is the end of the word - no
# guessing at an offset, and no drift between episodes as TTS timing shifts.
SIGN_OFF_HIT = "And I'm Smacky. And I just smacked you."
SIGN_OFF_TAIL = (
    "My schedule's wide open, so get over to Smackagram dot com "
    "and let me absolutely fucking unload on somebody you love."
)
SIGN_OFF = SIGN_OFF_HIT + " " + SIGN_OFF_TAIL   # transcript/display

# Drop the file at this path in the repo. If it is missing the show still
# builds and simply has no slap, rather than failing the run.
SMACK_SFX_PATH = "static/audio/FF_CF_foley_slap_violet.wav"

# How far BEFORE the end of "you" the slap starts, so it lands over the tail
# of the word rather than after it.
SMACK_LEAD_MS = 120
# Beat after the hit before "My schedule's wide open" - lets it land.
SMACK_BEAT_MS = 350
# Slightly hot: it is a punchline, not ambience. Drop to 0 for a realistic
# slap, raise for more cartoon.
SMACK_GAIN_DB = 2.0

MUSIC_BED_MS = 8000       # true length of daily-smack-intro.wav
DUCK_RAMP_MS = 300        # ramp INTO the duck instead of stepping to it
FADE_OUT_MS = 1700        # 6100 + 1700 = 7800, finishing 200ms early

# Outro. Same bed file, brought in under his closing words so the show
# resolves instead of stopping dead.
OUTRO_OVERLAP_MS = 3500   # music starts this far before the voice ends
OUTRO_DUCK_DB = -13       # sits under the final words, quieter than the intro duck
OUTRO_RISE_MS = 700       # comes up once he's finished talking
OUTRO_FADE_MS = 3200      # long tail out, ending inside the file
# The outro needs the same treatment as the intro for the same reason. With
# the fade finishing exactly ON the file boundary it measured -22.6 dB in the
# final 400ms - still plainly audible right up to the last sample, which is
# the abrupt ending this was meant to remove. Landing it early leaves real
# silence at the end so the show resolves instead of stopping.
OUTRO_TAIL_PAD_MS = 300

assert MUSIC_SOLO_MS + DUCK_RAMP_MS + FADE_OUT_MS <= MUSIC_BED_MS, (
    "intro fade would run past the end of the bed file and cut off hard"
)


# NOTE: an earlier version mixed the bed with pydub, which decoded the whole
# finished episode into memory - roughly 250MB of raw PCM for five minutes,
# several times over during the mix. Render's instance is 512MB and killed it
# every run. Removed rather than left in the file: it worked correctly and
# would be tempting to reuse.


def _assemble_with_music(intro: str, segments: list, outro: str, log=None) -> str:
    """
    Builds the episode, then lays the intro bed under the front of it.

    USES FFMPEG DIRECTLY, NOT PYDUB. The first version decoded the finished
    five-minute MP3 into pydub, which means raw PCM in memory: 5 min at
    44.1kHz stereo is roughly 250MB for ONE copy, and mixing needs several.
    Render's instance is 512MB, so it was killed every time -
    "Ran out of memory (used over 512MB)" - after successfully doing the mix
    but before it could save.

    ffmpeg streams through the file instead of holding it, so peak memory is a
    few MB regardless of how long the episode is.
    """
    import os, uuid, subprocess, tempfile, boto3, requests
    from services import smackcast_service

    if log is None:
        log = lambda m: print(f"[show] {m}", flush=True)

    url = smackcast_service.assemble_recap_audio(
        intro, segments, outro,
        outro_tail=SIGN_OFF_TAIL,
        hit_sfx_path=SMACK_SFX_PATH,
        hit_lead_ms=SMACK_LEAD_MS,
        hit_beat_ms=SMACK_BEAT_MS,
        hit_gain_db=SMACK_GAIN_DB,
    )
    log("speech generated and stitched")

    if not os.path.exists(INTRO_MUSIC_PATH):
        return url

    tmpdir = tempfile.mkdtemp()
    speech = os.path.join(tmpdir, "speech.mp3")
    out = os.path.join(tmpdir, "final.mp3")

    try:
        # Stream the finished show to disk rather than into memory.
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(speech, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

        solo = MUSIC_SOLO_MS / 1000.0
        ramp = DUCK_RAMP_MS / 1000.0
        fade_start = solo + ramp           # fade begins AFTER the duck settles
        fade_dur = FADE_OUT_MS / 1000.0
        duck = 10 ** (DUCK_DB / 20.0)      # dB to linear gain

        # How long the speech actually runs - needed to place the outro bed
        # under his closing words. Probed rather than estimated, since
        # episode length varies with the slate.
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", speech],
                capture_output=True, text=True, timeout=30,
            )
            speech_dur = float(probe.stdout.strip())
        except (subprocess.SubprocessError, ValueError) as e:
            print(f"[show] could not probe speech duration ({e}); intro bed only")
            speech_dur = 0.0

        # Voice is delayed by the solo, so it ENDS at solo + its own length.
        voice_end = solo + speech_dur
        outro_start = voice_end - (OUTRO_OVERLAP_MS / 1000.0)
        outro_duck = 10 ** (OUTRO_DUCK_DB / 20.0)
        outro_rise_at = OUTRO_OVERLAP_MS / 1000.0            # relative to bed start
        outro_rise_end = outro_rise_at + (OUTRO_RISE_MS / 1000.0)
        outro_fade_at = (MUSIC_BED_MS - OUTRO_FADE_MS - OUTRO_TAIL_PAD_MS) / 1000.0
        use_outro = speech_dur > 0 and outro_start > fade_start + fade_dur

        # The bed: full level until the voice arrives, then ducked and faded.
        # The speech is delayed by the solo period so it starts on the peak.
        # amix divides every input by the number of ACTIVE inputs, and the
        # volume=2.0 that used to sit here existed to undo that halving.
        # But the intro bed is only a few seconds long - the moment it ends,
        # amix drops to one active input and stops halving while the x2 kept
        # doubling, handing the voice a clean +6 dB for the entire rest of
        # the episode. Measured: the old chain peaked at +4.56 dBFS (voice
        # normalized to -1.5 dBTP, plus 6) and clipped continuously. That is
        # why the intro sounded fine and Smacky sounded crushed throughout.
        #
        # normalize=0 turns off amix's automatic scaling, so levels pass
        # through exactly as fed in and nothing jumps when the bed drops out.
        # The x2 is gone with it.
        #
        # alimiter then catches the one place peaks can still stack: the
        # ~2.6s where ducked music and voice overlap. level=disabled is
        # essential - alimiter auto-levels output back to 0 dB by default,
        # which silently undoes the ceiling (verified: with it enabled every
        # limit value measured 0.0 dBFS regardless of setting).
        # Measured result: -1.00 dBFS peak, and voice-only stretches sit at
        # -1.46 untouched, so the limiter never works hard enough to pump.
        # The duck is a RAMP, not a step. volume=enable= switches instantly,
        # which is audible as a lurch exactly where the voice arrives. This
        # interpolates from full to ducked across DUCK_RAMP_MS instead.
        intro_gain = (
            f"if(lt(t,{solo}),1,"
            f"if(lt(t,{solo + ramp}),1-(1-{duck:.4f})*(t-{solo})/{ramp},{duck:.4f}))"
        )
        chain = [
            f"[0:a]volume='{intro_gain}':eval=frame,"
            f"afade=t=out:st={fade_start}:d={fade_dur}[bed]",
            f"[1:a]adelay={MUSIC_SOLO_MS}|{MUSIC_SOLO_MS}[voice]",
        ]

        if use_outro:
            # Outro bed: enters under his last words at OUTRO_DUCK_DB, rises
            # once he stops, then a long fade that finishes INSIDE the file
            # rather than being truncated by its end.
            outro_gain = (
                f"if(lt(t,{outro_rise_at}),{outro_duck:.4f},"
                f"if(lt(t,{outro_rise_end}),"
                f"{outro_duck:.4f}+(1-{outro_duck:.4f})*(t-{outro_rise_at})/{OUTRO_RISE_MS / 1000.0},1))"
            )
            chain.append(
                f"[2:a]volume='{outro_gain}':eval=frame,"
                f"afade=t=out:st={outro_fade_at}:d={OUTRO_FADE_MS / 1000.0},"
                f"adelay={int(outro_start * 1000)}|{int(outro_start * 1000)}[tail]"
            )
            mix_inputs, labels = 3, "[bed][voice][tail]"
        else:
            mix_inputs, labels = 2, "[bed][voice]"

        chain.append(
            f"{labels}amix=inputs={mix_inputs}:duration=longest:"
            f"dropout_transition=0:normalize=0,"
            f"alimiter=level_in=1:level_out=1:limit=0.891:attack=1:release=60:level=disabled[out]"
        )
        filters = ";".join(chain)

        subprocess.run(
            ["ffmpeg", "-y", "-i", INTRO_MUSIC_PATH, "-i", speech]
            + (["-i", INTRO_MUSIC_PATH] if use_outro else [])
            + ["-filter_complex", filters, "-map", "[out]",
             "-c:a", "libmp3lame", "-b:a", "192k", out],
            check=True, capture_output=True, timeout=300,
        )

        bucket = os.environ["AUDIO_S3_BUCKET"]
        region = os.environ.get("AWS_REGION", "us-east-1")
        key = f"tts/{uuid.uuid4()}.mp3"
        with open(out, "rb") as f:
            boto3.client("s3", region_name=region).put_object(
                Bucket=bucket, Key=key, Body=f, ContentType="audio/mpeg")

        log(f"mix complete - intro bed, voice in at {MUSIC_SOLO_MS}ms"
            + (", outro bed" if use_outro else ", no outro (speech too short)"))
        return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    except subprocess.CalledProcessError as e:
        print(f"[show] ffmpeg mix failed: {e.stderr[-400:] if e.stderr else e}")
        return url
    except Exception as e:
        # The show matters more than the bed.
        print(f"[show] intro music mix failed, using speech only: {e}")
        return url
    finally:
        for f in (speech, out):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
