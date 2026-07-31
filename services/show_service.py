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

def write_script(material: dict) -> dict:
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

    blocks = []
    for lg in LEAGUE_ORDER:
        if lg not in by_league:
            continue
        rows = []
        for g in by_league[lg]:
            mark = "BIG" if g.get("tier") == "headline" else "quick"
            rows.append(f"  [{mark}] " + "; ".join(g["facts"]))
        blocks.append(f"{lg}:\n" + "\n".join(rows))

    streaks = "\n".join(
        f"  {s['team']} have lost {s['losses']} straight ({s['league']})"
        for s in material.get("streaks", [])
    )

    d = material["date"] if isinstance(material.get("date"), dict) else _date_context(1)

    system = smackology.render(level=4, context="recap")

    user = (
        f"You are Smacky, hosting THE DAILY SMACK - a daily sports radio "
        f"segment. It is {d['today_full']} in Florida right now, and you are "
        f"talking about the games played on {d['games_day_full']}.\n\n"

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
        "straight is a condition, and you should treat it like a diagnosis.\n\n"

        "RUNNING ORDER: work through the leagues in the order given above. "
        "Baseball opens the show. Do not reorder them.\n\n"

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


        "COVER EVERY GAME LISTED. None get skipped - the short ones get short "
        "treatment, not silence.\n\n"

        f"TOTAL LENGTH: about {plan['word_budget']} words. This is a timed "
        "segment, so that's a target, not a suggestion.\n\n"

        "THE OPENING - three beats, in this order, before a single result.\n\n"

        "  1. A GREETING that varies day to day. Rotate or coin your own in "
        "the same register: What's up, degenerates. / Rise and shine, losers. "
        "/ Well, well, well. Look who crawled back. / Smackalicious, "
        "everybody. / Morning, you beautiful disasters. / Top of the morning, "
        "bottom of the standings. / Oh good, you're all still here. "
        "Unfortunate. It just can't be the same one every day.\n\n"

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
        'roasted. I\'m Smacky, and you\'ve been smacked.\"\n'
        "     Same rule as the opening: it only works as branding if it is "
        "identical every single day.\n\n"

        "HOW HARD TO GO: all the way. This is a late-night sports radio show "
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

        "Reply with JSON only:\n"
        '{"intro": "...", "segments": [{"text": "...", "reaction": "burn"}], '
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


def produce_daily_show(days_back: int = 1) -> dict:
    """
    The whole job, end to end: pull the night, decide the runtime, write it,
    render it, store it.

    Called by the cron endpoint. Returns a dict describing what happened, so
    a failure is visible in the logs rather than silent.
    """
    from services.smackcast_service import assemble_recap_audio, sanitize_for_speech

    material = get_show_material(days_back=days_back)
    plan = material["plan"]

    if not plan["publish"]:
        # Deliberately does NOT publish something thin. Yesterday's show stays
        # up, which is a better outcome than four minutes of padding.
        print(f"[show] holding: {plan['reason']}")
        return {"published": False, "reason": plan["reason"],
                "game_count": material["game_count"]}

    script = write_script(material)
    if not script.get("publish"):
        return {"published": False, "reason": script.get("reason", "no script")}

    # Same speech sanitiser the Smackcast uses - strips punctuation names,
    # em dashes and emoji that TTS would otherwise read aloud.
    intro = sanitize_for_speech(script.get("intro") or script.get("opening") or "")
    outro = sanitize_for_speech(script.get("outro") or script.get("closing") or "")
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
        segments.append({"text": sanitize_for_speech(body), "reaction": reaction})

    if not segments:
        print(f"[show] script had no usable segments. Keys returned: "
              f"{[list(x.keys()) if isinstance(x, dict) else type(x).__name__ for x in script.get('segments', [])][:3]}")
        return {"published": False, "reason": "script returned no usable segments"}

    audio_url = _assemble_with_music(intro, segments, outro)
    print(f"[show] published {plan['minutes']:g} min from {material['game_count']} games")

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
FADE_OUT_MS = 2600        # fades out under the first line


# NOTE: an earlier version mixed the bed with pydub, which decoded the whole
# finished episode into memory - roughly 250MB of raw PCM for five minutes,
# several times over during the mix. Render's instance is 512MB and killed it
# every run. Removed rather than left in the file: it worked correctly and
# would be tempting to reuse.


def _assemble_with_music(intro: str, segments: list, outro: str) -> str:
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

    url = smackcast_service.assemble_recap_audio(intro, segments, outro)

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
        fade_start = solo
        fade_dur = FADE_OUT_MS / 1000.0
        duck = 10 ** (DUCK_DB / 20.0)      # dB to linear gain

        # The bed: full level until the voice arrives, then ducked and faded.
        # The speech is delayed by the solo period so it starts on the peak.
        filters = (
            f"[0:a]volume=enable='gte(t,{fade_start})':volume={duck:.4f},"
            f"afade=t=out:st={fade_start}:d={fade_dur}[bed];"
            f"[1:a]adelay={MUSIC_SOLO_MS}|{MUSIC_SOLO_MS}[voice];"
            f"[bed][voice]amix=inputs=2:duration=longest:dropout_transition=0,"
            f"volume=2.0[out]"
        )

        subprocess.run(
            ["ffmpeg", "-y", "-i", INTRO_MUSIC_PATH, "-i", speech,
             "-filter_complex", filters, "-map", "[out]",
             "-c:a", "libmp3lame", "-b:a", "192k", out],
            check=True, capture_output=True, timeout=300,
        )

        bucket = os.environ["AUDIO_S3_BUCKET"]
        region = os.environ.get("AWS_REGION", "us-east-1")
        key = f"tts/{uuid.uuid4()}.mp3"
        with open(out, "rb") as f:
            boto3.client("s3", region_name=region).put_object(
                Bucket=bucket, Key=key, Body=f, ContentType="audio/mpeg")

        print(f"[show] intro bed mixed via ffmpeg, voice in at {MUSIC_SOLO_MS}ms")
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
