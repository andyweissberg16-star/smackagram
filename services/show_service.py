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
# Roughly 90 seconds spoken. Enough for a real presence rather than a
# mention. Any league that played gets at least this, whatever its slate.
LEAGUE_FLOOR_WORDS = 225

# Words in a comfortable segment. Long enough to land a joke, short enough
# that the next one arrives before attention drifts.
WORDS_PER_SEGMENT = 75


def _target_segments(budget):
    """How many segments a budget should become. At least two, at most six."""
    return max(2, min(6, round(budget / WORDS_PER_SEGMENT)))


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
    # THE MANUAL DOOR (David, Aug 7): a HUMAN-VERIFIED game handed to
    # the show through a Setting row, for games no automated source
    # carries honestly - the Hall of Fame Game being the founding
    # case (ESPN blocks this host, Highlightly returned baseball
    # imposters, SDIO free tier scrambles scores). Rows are injected
    # via /api/admin/inject-game, live under the "manual_games" key,
    # and are consumed only for their own league.
    try:
        import json as _json
        from models import Setting as _Set
        _row = _Set.query.filter_by(key="manual_games").first()
        if _row and _row.value:
            for _m in _json.loads(_row.value):
                if (_m.get("league") or "").upper() == league.upper():
                    _m.setdefault("label", league.upper())
                    _m.setdefault("id", f"manual-{_m.get('winner','')}-"
                                        f"{_m.get('loser','')}")
                    games.append(_m)
                    print(f"[show] manual game included: "
                          f"{_m.get('winner')} over {_m.get('loser')} "
                          f"({league})", flush=True)
    except Exception as _e:
        print(f"[show] manual games unavailable: {_e}", flush=True)

    # Hits and errors aren't in ESPN's scoreboard payload; facts derived from
    # them simply won't fire, which is correct - better a shorter fact list
    # than an invented one.
    for g in games:
        g.setdefault("home_hits", None)
        g.setdefault("away_hits", None)
        g.setdefault("home_errors", None)
        g.setdefault("away_errors", None)
    return games


def _nick(name):
    """
    The last word of a team name, lowercased, or "" when there is none.

    "New York Yankees" -> "yankees". Written as a helper because the
    inline version was (name or "").split()[-1] - and "".split() is an
    EMPTY LIST, so [-1] raised IndexError on any blank name.
    """
    parts = (name or "").split()
    return parts[-1].lower() if parts else ""


def _attach_highlightly_ids(games, log=print, day=None):
    """
    Find each game's Highlightly match id, so its box score can be fetched.

    The providers use different ids, so games are matched on LEAGUE + THE
    TWO TEAMS. Only the last word of each name is compared - "New York
    Yankees" against "Yankees" - which is the nickname in every league that
    matters.

    One call per league, cached. Silent no-op when Highlightly is off.
    """

    # IF THE GAME CAME FROM HIGHLIGHTLY, IT ALREADY HAS ITS ID.
    #
    # This runs BEFORE the enabled() check below, on purpose: copying a
    # field that is already on the record needs no API and no key.
    #
    # The whole matching dance underneath was written when games came
    # from ESPN and the two providers had to be reconciled by team name.
    # Games from Highlightly carry highlightly_id in the shape already,
    # so re-fetching every league to rediscover it is a wasted round
    # trip - and it matched against a HARDCODED "yesterday", which may
    # not be the day the game is from.
    #
    # That is why the Smack Ball segment kept being skipped for want of
    # hitter data: the id never got attached, so the box score was never
    # fetched, so there was never any detail to work with.
    direct = 0
    for g in games:
        if not g.get("_hl_id") and g.get("highlightly_id"):
            g["_hl_id"] = str(g["highlightly_id"])
            direct += 1
    if direct:
        log(f"highlightly ids: {direct} already known, no lookup needed")

    unmatched = [g for g in games if not g.get("_hl_id")]
    if not unmatched:
        return games

    try:
        from services import highlightly
        if not highlightly.enabled():
            return games
    except Exception:
        return games

    # THE DAY MUST MATCH THE GAMES, NOT BE ASSUMED.
    #
    # This hardcoded "yesterday". If the show is run for any other day,
    # the lookup fetched the wrong day's results and matched them by team
    # name - so a box score could be attached to a DIFFERENT GAME
    # between the same two teams, and its stats read out as fact.
    #
    # Two teams meeting twice in a series makes that likely rather than
    # unlikely.
    from datetime import datetime as _dt, timedelta as _td
    if not day:
        day = (_dt.now(EASTERN) - _td(days=1)).strftime("%Y-%m-%d")

    by_league = {}
    for g in unmatched:
        lg = (g.get("league") or "").lower()
        if lg and lg not in by_league:
            try:
                by_league[lg] = highlightly.finals(lg, day)
            except Exception as e:
                log(f"highlightly ids unavailable for {lg}: {e}")
                by_league[lg] = {}

    matched = 0
    for g in unmatched:
        lg = (g.get("league") or "").lower()
        # "".split() IS AN EMPTY LIST, NOT [""].
        #
        # So [-1] on it raises IndexError, and the `if "" in want` guard
        # below never got the chance to help - it ran after the crash.
        # A team name arriving blank is rare and entirely possible.
        want = {_nick(g.get("winner")), _nick(g.get("loser"))}
        if "" in want or len(want) < 2:
            continue
        for hid, r in (by_league.get(lg) or {}).items():
            got = {_nick(r.get("winner")), _nick(r.get("loser"))}
            if got != want:
                continue

            # THE SCORE HAS TO AGREE TOO.
            #
            # Team names alone are not unique within a day - a
            # doubleheader is the same two teams twice, and this loop
            # takes the FIRST match. Attaching the wrong game's box score
            # means reading another game's stats out as fact.
            #
            # When either side gives no score we accept the name match,
            # because a name match is still better than nothing - but a
            # score that DISAGREES is a positive signal it is the wrong
            # game, and we skip it.
            ws, ls = g.get("winner_score"), g.get("loser_score")
            rws, rls = r.get("winner_score"), r.get("loser_score")
            if None not in (ws, ls, rws, rls) and (ws, ls) != (rws, rls):
                continue

            g["_hl_id"] = hid
            matched += 1
            break

    if matched:
        log(f"highlightly: matched {matched}/{len(games)} games")

    # HARVEST THE NAMES WHILE WE ARE HERE.
    #
    # The show already fetches a box score for every game. Those box scores
    # are full of player names, and throwing them away means the picker has
    # to fetch a squad live later for the same information.
    #
    # Fifteen games a night is thirty teams, so the database fills from
    # normal use rather than needing a job that somebody has to remember.
    try:
        from services import player_store, highlightly
        for g in games:
            if not g.get("_hl_id"):
                continue
            lg = (g.get("league") or "").lower()
            rows = highlightly.box_score(lg, g["_hl_id"])
            by_team = {}
            for p in rows:
                by_team.setdefault(p.get("team") or "", []).append(p)
            for team, ps in by_team.items():
                if team:
                    # Full name - see player_store.team_key. Last-word keys
                    # merged the two Sox teams into one.
                    player_store.remember(lg, team, ps)
    except Exception as e:
        log(f"player harvest skipped: {e}")

    return games


def _detail_day(g):
    """
    The Eastern day a game belongs to, for schedule matchup resolution.
    Games from fetch_finals carry "date" (YYYYMMDD); fall back to
    yesterday Eastern, which is the day every show is about.
    """
    raw = str(g.get("date") or "")
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    from datetime import datetime as _dt, timedelta as _td
    return (_dt.now(EASTERN) - _td(days=1)).strftime("%Y-%m-%d")


def enrich_with_detail(games, log=print, workers=6):
    """
    Pull the deep box score for every game and hang the roast facts on it.

    Without this a segment has only the scoreline, the margin, who lost at
    home and the loser's record - which is why segments lean so hard on the
    score. There is nothing else to say.

    With it a slot can carry the starting pitcher by name with his innings and
    season ERA, team hits, strikeouts, runners left on base, errors, how many
    of the top order were held hitless, and which opposing hitter did the
    damage. "The Cardinals got two hits, struck out fourteen times and left
    nine on base" is a joke. "The Cardinals lost 8-2" is a scoreline.

    Fetched in PARALLEL - nineteen games one after another would add close to
    a minute to a three-minute render.

    A failure costs that game its detail and nothing more. The show has always
    worked from the scoreline alone and still can.
    """
    from concurrent.futures import ThreadPoolExecutor

    from services import espn_scores

    def _one(g):
        """
        Attach whatever detail we can get, from whichever source has it.

        THIS USED TO BAIL OUT IF THERE WAS NO ESPN ID:

            eid = g.get("espn_id")
            if not eid:
                return g

        And no game has an ESPN id any more. The Highlightly box-score
        path sat INSIDE this function, after that early return, so it was
        never reached - not once, all day.

        That is why every episode has been thin: "deep detail on 0/6
        games", and the Smack Ball skipped for want of hitter data on
        every single run.

        Highlightly first now, because it is the source that answers.
        """
        facts, detail = [], None

        # MLB: THE LEAGUE'S OWN BOX SCORE FIRST.
        #
        # statsapi has the box within minutes of the final; Highlightly
        # lags a day, which is why the player awards never fired at
        # 5:55am. The gamePk rides on statsapi-sourced games directly;
        # anything that arrived from another source is resolved by
        # matchup through the day's schedule. Emitted in the ESPN shape
        # the layout already parses, so the awards work unchanged.
        if (g.get("league") or "").lower() == "mlb":
            # LOUD ON PURPOSE, one line per game. Two consecutive runs
            # said "deep detail on 0/19" with NOTHING else in the log -
            # no fetch, no refusal, no exception. A silent zero cannot
            # be debugged; this names the exact step each game dies at.
            try:
                from services import mlb_statsapi
                _pk = (g.get("id") if g.get("source") == "mlb_statsapi"
                       else mlb_statsapi.game_pk_for(
                           _detail_day(g), g.get("home") or "",
                           g.get("away") or ""))
                if not _pk:
                    print(f"[detail] {g.get('away')}@{g.get('home')}: "
                          f"NO gamePk (day={_detail_day(g)}, "
                          f"source={g.get('source')})", flush=True)
                else:
                    detail = mlb_statsapi.game_detail(
                        _pk, g.get("winner") or "", g.get("loser") or "")
                    if detail is None:
                        print(f"[detail] {g.get('away')}@{g.get('home')}: "
                              f"pk={_pk} but game_detail returned None "
                              f"(fetch refused or empty)", flush=True)
                    else:
                        _nh = sum(len(b["statistics"][0]["athletes"])
                                  for b in detail["boxscore"]["players"])
                        print(f"[detail] {g.get('away')}@{g.get('home')}: "
                              f"pk={_pk} box OK, {_nh} hitters", flush=True)
                        # NAMES INTO THE PROMPT. The detail attached
                        # but only award slots ever read it - ordinary
                        # segments got a bare scoreline, so the writer
                        # said "their pitcher" for want of a name.
                        _nf = mlb_statsapi.named_facts(detail)
                        if _nf:
                            facts = facts + [f for f in _nf
                                             if f not in facts]
            except Exception as e:
                import traceback as _tb
                print(f"[detail] {g.get('away')}@{g.get('home')}: "
                      f"EXCEPTION {type(e).__name__}: {e}", flush=True)
                _tb.print_exc()

        try:
            from services import highlightly
            if detail is None and highlightly.enabled() and g.get("_hl_id"):
                hl = highlightly.roast_facts(
                    (g.get("league") or "").lower(), g["_hl_id"],
                    g.get("loser") or "")
                if hl:
                    facts = list(hl)
        except Exception as e:
            print(f"[show] highlightly facts unavailable: {e}", flush=True)

        # ESPN after, for as long as it is there at all. Costs nothing
        # when there is no id, and fails fast while the gate is cooling.
        eid = g.get("espn_id")
        if eid:
            try:
                detail = espn_scores.fetch_game_detail(
                    g.get("league", ""), eid)
                espn_facts = espn_scores.roast_facts(detail) if detail else []
                facts = facts + [f for f in espn_facts if f not in facts]
            except Exception as e:
                print(f"[show] no ESPN detail for {eid}: {e}", flush=True)

        if facts:
            g["deep_facts"] = facts
        if detail:
            g["_detail"] = detail
        return g

    with ThreadPoolExecutor(max_workers=workers) as pool:
        games = list(pool.map(_one, games))

    # Count ATTACHED DETAIL too - statsapi attaches a full box score
    # without the old-style fact strings, and this counter reported
    # "0/19" over fifteen perfect box scores, sending the debugging
    # hunt in the wrong direction for an hour.
    got = sum(1 for g in games
              if g.get("deep_facts") or g.get("_detail"))
    log(f"deep detail on {got}/{len(games)} games")
    return games


def loser_runs_of(game):
    """
    What the losing side scored, or None when the feed did not say.

    NOT min(a or 0, b or 0). That is the shape of a bug that has now
    appeared four times: two missing scores become 0, zero means
    shutout, and a postponed game gets called the funniest result of
    the night AND put top of the running order.

    Unknown is None. Callers must decide what to do with that, which is
    the point - it forces the question rather than quietly answering it
    wrong.
    """
    ls = game.get("loser_score")
    if ls is not None:
        return ls
    known = [v for v in (game.get("away_score"), game.get("home_score"))
             if v is not None]
    return min(known) if len(known) == 2 else None


def build_facts(game: dict) -> list[str]:
    """
    Plain-English facts about one game, ordered most roastable first.

    Every line here is derived arithmetic on real numbers - nothing inferred,
    nothing embellished. Smacky supplies the cruelty; this supplies the truth.
    """
    facts = []
    u = game["unit"]
    # SCORES CAN BE None, AND max(None, None) CRASHES.
    #
    # A provider that returns a game without a scoreline is not a fault -
    # it happens on postponed games, and on anything where the feed is
    # thin. But max() on two Nones raises "'>' not supported between
    # instances of NoneType and NoneType", which killed a whole episode.
    #
    # Better: use the winner and loser scores this shape already
    # computes, and fall back to nothing rather than inventing a 0-0.
    _ws, _ls = game.get("winner_score"), game.get("loser_score")
    if _ws is None or _ls is None:
        _a, _h = game.get("away_score"), game.get("home_score")
        _known = [v for v in (_a, _h) if v is not None]
        _ws = max(_known) if _known else None
        _ls = min(_known) if _known else None
    if _ws is not None and _ls is not None:
        facts.append(f"{game['winner']} beat {game['loser']} {_ws}-{_ls}")
    else:
        # No scoreline at all. Naming the result is still worth saying.
        facts.append(f"{game['winner']} beat {game['loser']}")

    if game["margin"] >= 8:
        facts.append(f"a {game['margin']}-{u[:-1]} beating")
    elif game["margin"] == 1:
        facts.append(f"lost by a single {u[:-1]}")

    if game["loser_at_home"]:
        facts.append(f"{game['loser']} lost at home")

    # A bad night is one thing; a bad season is funnier.
    if game.get("loser_record"):
        facts.append(f"{game['loser']} are now {game['loser_record']}")

    # The box score, if it came back.
    #
    # These go LAST so the scoreline and the record still lead - they are what
    # a segment is about. But this is the material that makes a segment
    # specific: a named pitcher who went four innings, fourteen strikeouts,
    # nine left on base. Without them the writer only has the score, which is
    # why segments used to lean on it so hard.
    for f in (game.get("deep_facts") or [])[:6]:
        if f and f not in facts:
            facts.append(f)

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


def _voice_block_for_show(material):
    """
    One voice block for the night, built from the real games.

    Taken from the MOST DRAMATIC game rather than averaged across all of them
    - an episode has one emotional register, and it should be set by the game
    people will actually talk about.
    """
    from services import smacky_voice

    games = []
    by_league = material.get("by_league") or {}
    for league_games in by_league.values():
        games.extend(league_games or [])
    if not games:
        games = material.get("games") or []
    if not games:
        return smacky_voice.render(situation="shut_out")

    def drama(g):
        # Nil beats a blowout beats a one-run game. A shutout is the funniest
        # scoreline available and should set the tone when there is one.
        # A game with NO scoreline is not a shutout - it is unknown, and
        # it must not outrank a real result. Score it on margin alone.
        loser_runs = loser_runs_of(g)
        if loser_runs is None:
            return 0
        return 100 if loser_runs == 0 else (g.get("margin") or 0)

    top = max(games, key=drama)
    loser_runs = loser_runs_of(top)
    errs = (top.get("home_errors") or 0) + (top.get("away_errors") or 0)

    # Read the box score for what actually happened, so the register comes
    # from the game rather than only the margin. A 3-2 loss with nine men
    # left on base is a different feeling from a 3-2 loss that was never
    # close, and until now both looked identical.
    deep = " ".join(top.get("deep_facts") or []).lower()
    stranded = 0
    _m = re.search(r"left (\d+) runners", deep)
    if _m:
        stranded = int(_m.group(1))
    if "errors in the field" in deep:
        _e = re.search(r"(\d+) errors in the field", deep)
        if _e:
            errs = max(errs, int(_e.group(1)))

    return smacky_voice.render(game={
        "final": True,
        "loser_score": loser_runs,
        "margin": top.get("margin") or 0,
        "errors": errs,
        "stranded": stranded,
    })


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
# No floor worth the name.
#
# A five-minute minimum meant a four-game Monday was PADDED to fill the same
# air as a fifteen-game Saturday, and padding is more noticeable than
# brevity. The per-league budgets now scale with the slate, so a light night
# simply produces a shorter show - which is the honest outcome.
MIN_MINUTES = 2.0
# Eight, not six. Baseball at ~5:00 and the WNBA at ~1:30 do not fit under
# six once the intro, the ad and the close are counted. The cap is a
# CEILING rather than a target - most nights land well under it.
MAX_MINUTES = 8.0
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
    # THIS NUMBER IS THE EPISODE LENGTH. At 26 words per non-headline
    # game a full card planned 4.7 minutes; the episodes David and Andy
    # were happy with ran seven to nine. 45 words per game restores that
    # once the per-league blocks and the bits are on top.
    wanted = 60 + (3 * 55) + (max(0, game_count - 3) * 45)
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
    # EVERY GAME ONCE, NOT ONCE PER OFFSET IT APPEARS IN.
    #
    # fetch_results now returns TWO UTC days per call, because an Eastern
    # day spans two of them. So consecutive offsets OVERLAP - offset 1
    # returns Aug 4 and Aug 5, offset 2 returns Aug 3 and Aug 4 - and
    # every game was counted twice.
    #
    # That is how the show announced an ELEVEN GAME LOSING STREAK, which
    # is not possible from a seven-day lookback. An honest five or six
    # became eleven.
    #
    # A wrong stat said with confidence is worse than no stat, because
    # anybody who follows that team knows immediately.
    seen_games = set()
    for offset in range(days_back, days_back + lookback):
        for lg in active:
            for g in fetch_results(lg, days_back=offset):
                gid = str(g.get("id") or g.get("highlightly_id") or
                          f"{g.get('winner')}|{g.get('loser')}|"
                          f"{g.get('winner_score')}|{g.get('loser_score')}")
                if gid in seen_games:
                    continue
                seen_games.add(gid)
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

    # THREE PER LEAGUE, not three in total.
    #
    # The flat top-three was written when one writer handled every league.
    # Now that each writer only sees its own league's streaks, a flat cap
    # means three baseball runs leave the WNBA with none - even when a WNBA
    # team is on five straight, which is exactly the material that block
    # needs.
    per_league = {}
    out = []
    for st in streaks:
        lg = (st.get("league") or "").upper()
        if per_league.get(lg, 0) >= 3:
            continue
        per_league[lg] = per_league.get(lg, 0) + 1
        out.append(st)
    return out


# ---------------------------------------------------------------------------
# The writer and the daily job
# ---------------------------------------------------------------------------

AUDIENCE_NAMES = [
    "Smackheads", "Smackers", "Smackaholics", "the Smackerdome",
    "Smacknation", "the Smack Pack", "Smackadelics", "Smackerinos",
    "the Smack Faithful", "Smacktators", "Smackateers", "Smackaneers",
    "the Smack Squad", "Smack City", "Smackamaniacs", "the Smack Mob",
]


def pick_audience_name(day=None):
    """
    Tonight's name for the audience - chosen in CODE, not by the model.

    "Rotate, never the same two days running" was an INSTRUCTION in the
    prompt, and the model cannot remember yesterday - so it settled on
    "Smackateers" and opened every single episode with it. The signature
    move became a catchphrase by accident.

    Same mechanism as the WNBA award title: the order is shuffled ONCE
    from a fixed seed, then walked by date. Every name is used before
    any repeats, consecutive nights always differ, and a re-render of
    the same day keeps the same name.
    """
    import datetime
    import random as _r
    d = day or datetime.date.today()
    rng = _r.Random(20260806)          # fixed seed - the cycle, not the day
    order = AUDIENCE_NAMES[:]
    rng.shuffle(order)
    return order[d.toordinal() % len(order)]


_TIMELESS_EXITS = [
    "We'll be right back.", "Back shortly.", "Don't go anywhere.",
    "Sit tight.", "Stay right there.", "Be right back.",
    "One second.", "Hold that thought.", "Right back at it in a moment.",
    "Don't touch that dial.",
]


def _strip_time_promises(text):
    """
    A ~30-second break must never be introduced with 'back in sixty'.
    IN CODE, not just the prompt, because prompt caps have been ignored
    before (the that's-not-a cap, twice). Any duration promise in the
    break line is replaced with a timeless exit from the pool.
    """
    import re as _re, random as _rand
    pat = _re.compile(
        r"(?:i(?:'| a)?m |we(?:'| a)?re |be |right )?back in "
        r"(?:about |like |under )?"
        r"(?:a few|a couple(?: of)?|forty[- ]five|thirty|sixty|ninety|"
        r"twenty|\d+|one |a )"
        r"\s*(?:seconds?|secs?|minutes?|mins?)?",
        _re.IGNORECASE)
    if not text or not pat.search(text):
        return text
    out = pat.sub("", text)
    out = _re.sub(r"\s{2,}", " ", out)
    out = _re.sub(r"\s+([,.!?])", r"\1", out)      # ' , unfortunately' -> ', unfortunately'
    out = _re.sub(r"(?:^|(?<=[.!?]))\s*[,;]\s*", " ", out)  # orphan leading commas
    out = out.strip(" .,-")
    exit_line = _rand.choice(_TIMELESS_EXITS)
    out = (out + ". " if out else "") + exit_line
    print(f"[show] break line promised a duration - scrubbed to "
          f"'{exit_line}'", flush=True)
    return out


def write_script(material: dict, only_league: str = None,
                 leagues_after: list = None, mood: tuple = None,
                 opens_show: bool = None) -> dict:
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
        # KEY NORMALIZED TO UPPER (Aug 7, David's second dry run): keys
        # here were the feeds' raw labels while the blocks loop below
        # checks LEAGUE_ORDER's uppercase - a lowercase "nfl" key meant
        # the NFL writer's prompt carried ZERO games, and a writer with
        # an empty slate improvised baseball from surrounding material.
        by_league.setdefault((g.get("league") or "").upper(), []).append(g)

    if only_league:
        # Case-insensitive - an exact compare left this EMPTY: a league
        # writer with no games in its prompt.
        by_league = {k: v for k, v in by_league.items()
                     if k.upper() == only_league.upper()}
        if not any(by_league.values()):
            # NO GAMES, NO WRITER. An empty prompt is an invitation to
            # invent - the exact failure of the fake-NFL segments.
            print(f"[show] {only_league}: zero games after filtering - "
                  f"writer skipped entirely", flush=True)
            return {"segments": []}

    # THE LAYOUT decides which games go where, in code, before the writer
    # sees anything. Structure decided by the model is structure that cannot
    # be relied on.
    # STREAKS FOR THIS LEAGUE ONLY.
    #
    # They were handed to every writer unfiltered, so the WNBA writer received
    # "Rockies have lost 8 straight (MLB)" as material and duly wrote about
    # it - producing baseball content inside the WNBA block, after the ad
    # break, which is exactly what a listener heard.
    #
    # Each writer only ever sees streaks from its own league now. If that
    # leaves none, it simply has none, which is correct.
    _streak_rows = [x for x in material.get("streaks", [])
                    if not only_league
                    or (x.get("league") or "").upper() == only_league.upper()]

    # ONE LAYOUT PER LEAGUE, and they share nothing.
    #
    # Every cross-league fault on this show came from something shared that
    # should not have been - a grouping rule written for a fifteen-game
    # baseball slate collapsed a four-game WNBA night into a single segment,
    # and a streak list compiled across all leagues put the Rockies inside
    # the WNBA block.
    #
    # So the layouts are separate modules with separate slots, separate
    # thresholds and separate awards. Basketball has no innings, no pitchers
    # and no runners left on base; baseball has no turnovers and no shooting
    # percentage. Sharing a layout between them was never going to work.
    LAYOUTS = {"MLB": "show_layout", "WNBA": "wnba_layout"}
    layout_block = ""
    _lg = (only_league or "").upper()
    if _lg in LAYOUTS:
        try:
            import importlib
            mod = importlib.import_module(f"services.{LAYOUTS[_lg]}")
            _mine = [g for g in material["games"]
                     if (g.get("league") or "").upper() == _lg]
            # The league is passed in so the streak segment can NAME it -
            # every block has one, and without the name a listener hears
            # "Winners & Whiners" twice and assumes the show repeated itself.
            layout_block = mod.prompt_block(_mine, streaks=_streak_rows,
                                            league=_lg)
            # Record what the layout actually allocated, so the length check
            # measures against the briefs the writer was given rather than the
            # planner's independent estimate.
            _lay = mod.build(_mine, log=lambda m: None,
                             streaks=_streak_rows, league=_lg)
            material.setdefault("_layout_budgets", {})[_lg] = sum(
                x["words"] for x in _lay["slots"])
            # And WHICH slots, so the checklist can tell "allocated but
            # the writer dropped it" (a failure) from "not allocated
            # tonight" (correct - e.g. Winners and Whiners only exists
            # when a losing streak qualifies, and the stats awards only
            # when a box score arrived).
            material.setdefault("_layout_slots", {})[_lg] = [
                x.get("slot") for x in _lay["slots"]]
        except Exception as e:
            print(f"[show] {_lg} layout unavailable, writer decides: {e}",
                  flush=True)

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
        # Case-insensitive - an exact compare counted ZERO games here,
        # which is a zero word budget.
        mine = sum(1 for g in material["games"]
                   if (g.get("league") or "").upper() == only_league.upper())
        # EACH LEAGUE EARNS ITS OWN TIME FROM ITS OWN SLATE - the game
        # plan David and Andy actually ran with. A share of one pot
        # meant a busy WNBA night would DILUTE baseball's block.
        #
        #   BASEBALL: up to ~7 minutes from its own game count.
        #   WNBA: rarely more than six games, so naturally shorter -
        #   no cap needed, and baseball cannot squeeze it.
        _heads = min(3, mine)
        share = (_heads * 55) + (max(0, mine - _heads) * 45)
        share = min(share, int(7.0 * SPOKEN_WORDS_PER_MINUTE))
        # A FLOOR, not pure proportion.
        #
        # Nobody listens to this for results - they listen for Smacky. In that
        # frame 45 seconds is not a fair share, it is too little to be worth
        # showing up for if the WNBA is why you came.
        #
        # The asymmetry is the argument: MLB losing twenty seconds off a
        # three-minute block is unnoticeable, while a small league going from
        # 45 seconds to 90 doubles the reason to listen. Same words, very
        # different effect.
        #
        # And baseball's slate will always crush everything else - fifteen
        # games a night against four - so pure proportion permanently
        # relegates every other league. Come October football does the same
        # thing in reverse.
        league_budget = max(LEAGUE_FLOOR_WORDS, share)
    else:
        league_budget = plan["word_budget"]

    # Leagues that were scanned and had no games - the off-season ones.
    # Smacky gets a joke out of the silence before handing to whatever did
    # play.
    _played = {(g.get("league") or "").upper() for g in material.get("games", [])}
    _dark = [lg for lg in LEAGUE_ORDER if lg not in _played and lg != "WNBA"]

    streaks = "\n".join(
        f"  {s['team']} have lost {s['losses']} straight ({s['league']})"
        for s in _streak_rows
    )

    d = material["date"] if isinstance(material.get("date"), dict) else _date_context(1)

    system = smackology.render(level=4, context="recap")

    # The situation-aware voice layer on top.
    #
    # smackology supplies the vocabulary; this supplies the JUDGEMENT - which
    # register tonight's games call for, which lines are eligible, and which
    # running bits still have budget.
    #
    # A home-run line during a shutout is the worst thing an announcer can do,
    # and the only way to prevent it is deciding eligibility from the real
    # numbers BEFORE the model sees anything.
    try:
        system = system + "\n\n" + _voice_block_for_show(material)
    except Exception as e:
        # Never let the voice layer take down an episode.
        print(f"[show] voice layer unavailable: {e}", flush=True)

    # The mood is passed IN rather than chosen here, because each league is
    # written in a separate call - choosing per call would give you a manic
    # baseball segment and a melancholy basketball one in the same episode.
    if mood:
        _name, _desc = mood
        system += (
            f"\n\nYOUR MOOD TODAY: {_name.upper()}\n\n  {_desc}\n\n"
            "  This colours HOW you say things, never WHAT you say. The "
            "scores are the scores and the roasting is still the roasting - "
            "a bad mood does not mean going easy on anybody. If anything the "
            "low moods cut deeper, because you cannot be bothered to dress "
            "it up.\n\n"
            "  Do not announce it. Nobody says 'I am in a strange mood "
            "today'. It shows in the rhythm, the sentence length and what "
            "you choose to linger on.\n"
        )

    # An episode is not flat. Nobody sustains one energy for five minutes,
    # and a host who does sounds like a recording rather than a person in a
    # room at five in the morning.
    system += (
        "\n\nTHE SHAPE OF THE HOUR. Your energy moves across the episode "
        "and it is not the same at the end as at the start.\n\n"
        "  EARLY - you are warming up. Slightly too much energy, a bit "
        "unfocused, still finding the rhythm. This is where you are most "
        "likely to go off on something irrelevant.\n\n"
        "  MIDDLE - you have settled. This is your best work: sharpest "
        "lines, tightest delivery, most confident. If a segment is going to "
        "land properly it is one of these.\n\n"
        "  LATE - still full energy, but you are more willing to DISMISS a "
        "game rather than work at it. 'Toronto beat Boston. Fine.' That is "
        "not tiredness, it is judgement - you have decided that game does "
        "not deserve your time, and saying so is funnier than forcing a "
        "joke onto a one-run game.\n\n"
        "  THE CLOSE - the biggest energy of the whole show. Send them "
        "out on the highest point.\n\n"
        "  Do not label these or announce them. It shows in sentence length "
        "and how hard you are trying.\n"
    )

    # HOW OFTEN to swear, not just permission to. The vocabulary above is
    # properly profane and the level is set to savage, but nothing said
    # anything about frequency - so the model reached for the tame end of a
    # list that contains both, and a real episode came out with a couple of
    # "crap"s and nothing else.
    system += (
        "\n\nSWEARING. This is an uncensored show for adults and you are "
        "not being careful. This is NOT optional and NOT a good-days "
        "thing: EVERY episode runs at full savage, tonight included. "
        "If you notice the script reading clean, that is a fault - fix "
        "it before you hand it in. Most segments MUST contain real profanity - "
        "fuck, shit, goddamn, bullshit - used naturally, the way somebody "
        "talks when nobody is stopping them.\n\n"
        "  It is PUNCTUATION, not decoration. 'They fucking collapsed' lands; "
        "'they fucking collapsed in a fucking disaster of a fucking game' is "
        "a man trying to prove something. One or two per segment, placed "
        "where the emphasis actually belongs.\n\n"
        "  And do NOT keep reaching for the soft options. The vocabulary "
        "includes 'smackcrap' and 'horsecrap' - those are seasoning, used "
        "occasionally because they sound like HIS words. They are not a "
        "substitute for swearing and a whole episode built on them sounds "
        "like a man who has been told off.\n"
    )

    # The sport's own vocabulary, for whichever league this script covers.
    # The show writes per-league in parallel, so each call gets exactly the
    # right words and nothing bleeds across - baseball terms in a basketball
    # segment is the fastest way to tell a fan nobody here watches the game.
    #
    # This is the SHOW version, which is fuller than the one Auto-Smack
    # uses. A roast call only ever covers a loss, so it skips the
    # celebratory material - the dunk words, the home run catchphrases, the
    # great-player terms. The show covers winners too and wants all of it.
    system += _show_vocabulary(only_league)

    # THE OPENING BELONGS TO THE LEAD LEAGUE ONLY.
    #
    # In per-league mode every league writer receives this same prompt.
    # The parallel path never fired until the case fix - the first
    # morning it runs, the WNBA block would greet the audience and
    # re-introduce the whole show mid-episode.
    #
    # The lead is the call that receives leagues_after (a list, even an
    # empty one); every other league gets None and opens cold. The
    # single-call path has only_league=None and stays the lead.
    # WHO OPENS AND WHO CLOSES.
    #
    # opens_show is explicit from the per-league caller; the single-call
    # path leaves it None and does both. leagues_after is now every
    # block's TRUE after-list, so "nothing after me" - an empty list -
    # means this block ends the show and owns the sign-off. With three
    # leagues in autumn, the middle block neither opens nor closes.
    _lead = opens_show if opens_show is not None else (only_league is None)
    _closes = not leagues_after

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

        # The streaks handed over are now filtered to this writer's own
        # league. Saying so, because the previous unfiltered list is how
        # baseball ended up being discussed inside the WNBA block.
        "  Every streak listed above is from YOUR league. There are no others "
        "to mention and no other league's teams to bring in.\n\n"

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
        "is genuinely stupid. Build to "
        "the realisation instead of leading with the conclusion, so the "
        "listener gets there half a second after you do. A host who has "
        "clearly already read the box score is boring; one who is finding "
        "out live is the whole appeal.\n\n"

        "  BUT VARY HOW YOU DO IT. The \"hang on - hang on, let me read that "
        "again\" double-take is ONE way and you lean on it far too hard. "
        "ONCE per episode at the absolute most, and some days not at all. "
        "It reads fine on the page and lands flat out loud when the delivery "
        "does not sell the pause - which is most of the time.\n\n"
        "  Other ways to sound like you are finding out live:\n"
        "  - say the number, then stop, then carry on as if nothing happened\n"
        "  - question it rather than repeating it: \"is that right?\"\n"
        "  - address the scoreboard directly, or somebody off-mic\n"
        "  - start the sentence, abandon it, start a different one\n"
        "  - state it completely flatly, as if it is beneath comment\n"
        "  - react to the wrong part of it entirely\n"
        "  - accept it immediately and move on, which is funnier than shock\n\n"

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

        # The Caitlin Clark bit belongs to the WNBA WRITER ONLY.
        #
        # It was in the shared prompt, so a baseball writer with no basketball
        # games was being told to be visibly bereft about the Fever - nineteen
        # lines of instruction about a league it is not covering. That is how
        # a WNBA reference ends up inside a baseball segment.
        + ((
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
        ) if (only_league or "").upper() in ("", "WNBA") else "")


        + ((f"  DEAD LEAGUES. These scanned and had nothing: "
            f"{', '.join(_dark)}. Before the WNBA block, note it and get a "
            f"joke out of it - lean on the NFL and the NBA, they are the ones "
            f"people miss. One or two lines, not a monologue.\n\n"
            if _dark else "")

           + "  AND THEN THE HANDOFF. The bit is that SMACKY is out of his "
           "depth here, not that the league is beneath him. He is "
           "contractually obligated, he does not follow it closely, he knows "
           "one name and it is Caitlin Clark, and he is aware that somebody "
           "listening cares about this far more than he does and is already "
           "annoyed with him. THAT is the joke - he is the idiot in this "
           "exchange, not the sport.\n\n"
           "  Play it as a man doing his job badly and knowing it. Do NOT "
           "call the league boring, bad, or the worst thing in sports - "
           "cheap, and much less funny than admitting he cannot name a "
           "second player.\n\n"
           "  Vary the angle daily. Some days he is faking expertise, some "
           "days he is openly reading off a card, some days he is "
           "apologising to the one person who cares.\n\n"

           if only_league == "WNBA" else "")

        + ("  OPENING THE WNBA BLOCK. Before any WNBA score, open with a "
           "line about the Caitlin Clark circus - the ratings, the media "
           "obsession, the fact that a whole league's attention rides on one "
           "player's schedule. This is the running bit and it opens the "
           "block every time.\n\n"
           "  Aim it at the PHENOMENON, not the woman. The league leaning on "
           "her, the networks, the discourse, the fanbases arguing about her "
           "- all fair. Her as a person is not: nothing about her looks, her "
           "character, her personal life, and never invent something she "
           "said or did. Same rule you follow everywhere else - the target "
           "is the situation, not the human.\n\n"
           "  Vary it daily. Same target, new joke.\n\n"

           "  AND KEEP PULLING IT BACK. Once or twice more inside the block, "
           "drag an unrelated game back to the Fever or the Clark circus. "
           "Two teams she has nothing to do with lost, and you still find a "
           "way to make it about the ratings draw. That is the joke - the "
           "obsession is inescapable, even yours. Do not do it on every "
           "score or it stops landing.\n\n"
           if only_league == "WNBA" else "")

        + "VARY THE JOKE SHAPE. The \"that's not a score, that's a war "
        "crime\" construction - naming a thing, denying it, then replacing it "
        "with something worse - is a good beat and you lean on it far too "
        "hard.\n\n"

        "  YOU MAY USE IT ONCE. Not once per segment - ONCE, in everything "
        "you write here, and preferably not at all.\n\n"

        # Naming what to do INSTEAD, rather than only what not to do.
        # "Vary the joke shape" is abstract and has been ignored three times;
        # a list of concrete shapes gives the model somewhere to go.
        # An episode covered the same game twice, in different words, either
        # side of a hand-off. Saying it plainly, because the writer does not
        # otherwise know it is a risk.
        "  ONE GAME, ONE SEGMENT. Do not come back to a game you have already "
        "covered. An episode described the same shutout twice in different "
        "words and it sounded like a mistake, because it was one. If a game "
        "deserves more, give it more THE FIRST TIME.\n\n"

        "  REACH FOR THESE INSTEAD - eight shapes, all of which land as hard "
        "and none of which is that one:\n"
        "    1. Comparison to something mundane: \"I've seen folding chairs "
        "put up more resistance.\"\n"
        "    2. Absurd consequence: \"That baseball is applying for "
        "citizenship in the parking lot.\"\n"
        "    3. Understatement: \"They had a rough one.\" (after describing "
        "a nine-run beating)\n"
        "    4. Direct address: \"Buddy. Buddy, look at me.\"\n"
        "    5. Bureaucratic language for chaos: \"Somebody file the "
        "paperwork on that inning.\"\n"
        "    6. A number doing the work alone: \"Six pitchers. Six.\"\n"
        "    7. Mock sympathy: \"Bless them. They tried.\"\n"
        "    8. Escalating list: \"Cooked. Seasoned. Plated. Served.\"\n\n"

        "  This is stricter than it sounds because YOU ARE NOT WRITING THE "
        "WHOLE SHOW. Each league is written separately and at the same time, "
        "and the other writer cannot see what you are doing. A real episode "
        "used this construction FOUR times because two leagues each thought "
        "they were allowed two. Assume somebody else has already used it and "
        "write as though your one is the last one available.\n\n"

        "  FIFTY OTHER WAYS TO LAND THE SAME BEAT. Work through these - a "
        "different one every segment, and across the episode you should use "
        "a dozen different shapes, not one shape a dozen times.\n\n"

        "  REACTING TO A NUMBER\n"
        "   1. Say it flatly and move on. No comment. The silence does it.\n"
        "   2. Say it, pause, say a completely unrelated thing.\n"
        "   3. Question whether it is correct, then accept it sadly.\n"
        "   4. Do the maths out loud badly and give up.\n"
        "   5. Compare it to something domestic and small.\n"
        "   6. Say the number twice with nothing after it.\n"
        "   7. Refuse to say the number at all and describe it instead.\n"
        "   8. Round it up in their favour and note it does not help.\n\n"

        "  TALKING TO PEOPLE\n"
        "   9. Address the losing fanbase directly. Second person.\n"
        "  10. Address one specific fan you have invented.\n"
        "  11. Address the team as if they are in the room.\n"
        "  12. Address the winning team and thank them.\n"
        "  13. Ask the audience a question and answer it yourself, wrongly.\n"
        "  14. Apologise to somebody uninvolved.\n"
        "  15. Speak to the city rather than the team.\n\n"

        "  FALSE SYMPATHY\n"
        "  16. Sympathise sincerely, then withdraw it mid-sentence.\n"
        "  17. Offer practical advice nobody asked for.\n"
        "  18. Suggest they take the rest of the week off.\n"
        "  19. Say it could be worse, then fail to think of how.\n"
        "  20. Find one genuine positive and undersell it enormously.\n"
        "  21. Congratulate them on something irrelevant.\n"
        "  22. Pretend to defend them and give up halfway.\n\n"

        "  STRUCTURE TRICKS\n"
        "  23. Start the sentence, abandon it, start a better one.\n"
        "  24. Interrupt yourself with something petty and unrelated.\n"
        "  25. Call back to a team you buried earlier in the episode.\n"
        "  26. Set up an expectation and undercut it immediately.\n"
        "  27. Tell it in the wrong order - punchline first.\n"
        "  28. Build a list and stop at two.\n"
        "  29. Ask a rhetorical question and leave it hanging.\n"
        "  30. Repeat one word from the score three times.\n\n"

        "  THE SPECIFIC DETAIL\n"
        "  31. Pick one absurd stat and stay on it for the whole segment.\n"
        "  32. Name the one player who did nothing and dwell on him.\n"
        "  33. Mention how long the game took.\n"
        "  34. Mention how many people paid to watch it in person.\n"
        "  35. Note what inning or quarter it was already over.\n"
        "  36. Compare their night to their own previous night.\n\n"

        "  TONE SHIFTS\n"
        "  37. Say something genuinely kind, then move on quickly.\n"
        "  38. Get quiet about it rather than loud.\n"
        "  39. Sound tired rather than delighted.\n"
        "  40. Sound personally betrayed by the result.\n"
        "  41. Treat it as a medical matter.\n"
        "  42. Treat it as a legal matter.\n"
        "  43. Treat it as a weather event.\n"
        "  44. Treat it as entirely expected and barely worth mentioning.\n\n"

        "  COMPARISONS\n"
        "  45. Compare the team to a business that is failing.\n"
        "  46. Compare them to a household appliance.\n"
        "  47. Compare them to their own fans.\n"
        "  48. Compare tonight to a specific past humiliation.\n"
        "  49. Compare them favourably to something worse, barely.\n"
        "  50. Refuse to compare it to anything because nothing fits.\n\n"

        "NAMING PEOPLE. First mention of anyone gets their full name. "
        "Only after that do you use she, he or they. A real episode opened "
        "on 'her' with no idea who 'her' was.\n\n"

        "COVER EVERY LEAGUE LISTED, AND EVERY GAME IN IT. Not just the "
        "biggest league - EVERY league above gets its own segment or "
        "segments. A script covering only baseball when other leagues "
        "played is incomplete.\n\n"

        "  BUDGET YOUR ROOM SO YOU REACH THE END.\n\n"

        # This used to say "GROUP the quick games - several one-run games
        # belong in ONE segment". Written when a single writer handled every
        # league and baseball routinely ate the whole budget before reaching
        # the rest.
        #
        # Each league is now written SEPARATELY with its own budget, so that
        # failure cannot happen any more - and the instruction had started
        # causing harm instead. A four-game league read "group them" and
        # produced one long block, which is exactly why the WNBA kept
        # arriving as a single segment however much budget it was given.
        "  Your budget is YOURS and is not shared with any other league, so "
        "you cannot starve anybody by using it. Spend it across the number of "
        "segments asked for above.\n\n"

        "  Grouping is still right WITHIN a segment - two forgettable one-run "
        "games belong together, and only a genuine beating earns a segment to "
        "itself. But do not collapse everything into one block to play safe: "
        "several short segments are a show, one long one is a lecture.\n\n"

        f"TOTAL LENGTH: about {league_budget} words. This is a timed "
        "segment, so that's a target, not a suggestion.\n\n"

        # A SEGMENT count as well as a word count.
        #
        # Budget alone is not enough: given 225 words the writer produced ONE
        # segment of 225 rather than three of 75, and one long block covering
        # four games is markedly less listenable than three tight ones at the
        # same duration. The floor raised the time and the structure got
        # worse.
        + layout_block
        +
        f"HOW MANY SEGMENTS: aim for about {_target_segments(league_budget)}. "
        "Spread the budget across them rather than writing one long block - "
        "a single segment covering four games is a lecture, and several short "
        "ones are a show. Short segments may cover more than one quick game; "
        "that is the intended way to fit them.\n\n"

        + ((
        "THE OPENING - three beats, in this order, before a single result.\n\n"

        "  1. A GREETING.\n\n"

        # TONIGHT'S NAME IS CHOSEN IN CODE, NOT BY THE MODEL - see
        # pick_audience_name(). The old wording asked the model to
        # rotate through the set, and a model cannot remember
        # yesterday, so it settled on "Smackateers" every episode.
        f"  Address the audience as \"{pick_audience_name()}\" - "
        "tonight's name, exactly as written. Do not swap it for another "
        "smack-word name; the rotation is handled for you and this is "
        "tonight's turn in it.\n\n"

        "  Tone: affectionate needling, not abuse. He is pleased to see "
        "them and about to ruin their morning. Mild profanity is fine in "
        "the rest of the greeting. Do NOT call them shitheads or losers - "
        "too blunt, and it is not the joke.\n\n"

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

        f"Every time Florida gets named, land a QUICK joke about it - the "
        f"heat, the humidity, the hurricanes, the lizards, the sinkholes, "
        f"the drivers, the six-week winter, a Florida Man headline. ONE "
        f"clause, not a bit. It is a throwaway on the way to the scores, "
        f"and it must be different every day. "
        f"Shape: 'six in the morning in Florida, already ninety degrees' / "
        f"'Saturday in Florida, which is just Tuesday with worse traffic' / "
        f"'morning in Florida, the air is a liquid'. "
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

        ) if _lead else (
        "YOUR BLOCK STARTS MID-SHOW. The audience has already been "
        "greeted and the show introduced by an earlier block. NO "
        "greeting, NO welcome, NO introducing yourself or the show, NO "
        "signing off as if the show is starting. Your first words land "
        "straight on your first result.\n\n"
        ))
        # The opening gate above and the close gate below sit adjacent
        # in the chain - ONE operator joins them. A "+" from each made
        # "+ +", and the second one parsed as UNARY plus on a string:
        # syntactically legal, so it compiled, and it failed only at
        # runtime, on the first morning the parallel path ever ran.
        + ((
        "THE CLOSE - the last thing you say, WORD FOR WORD, never reworded, "
        "never shortened. Say something of your own first if you want, then "
        "land on exactly this. But the phrase \"That's The Daily Smack\" "
        "appears ONCE, in this close, and nowhere else - a real episode said "
        "it, carried on talking, and said it again, which sounded like the "
        "show ending twice. Your own preamble must not use it:\n"
        '     \"That\'s The Daily Smack. The grill\'s cooling down, but it '
        'never goes out. Same time tomorrow - somebody else is getting '
        'roasted.\"\n'
        "     Same rule as the opening: it only works as branding if it is "
        "identical every single day.\n\n"

        "     AND IT COMES LAST. Nothing follows it. If you want a final "
        "thought, it goes BEFORE the close, not after - the close is the "
        "door shutting.\n\n"

        "STOP THERE. Do not sign your name, do not name the website, do not "
        "add a farewell after it. The actual sign-off is appended "
        "automatically after your close and is identical in every episode - "
        "anything you write past this point duplicates it.\n\n"
        ) if _closes else (
        "YOUR BLOCK DOES NOT END THE SHOW - another league's block "
        "follows yours. NO sign-off of any kind: never say \"That's The "
        "Daily Smack\", no farewell, no wrapping up. Your last segment "
        "ends on your league's last result and simply stops.\n\n"
        )) +

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

        "  \"break_in\" - you announcing the break, bitterly. NEVER "
        "PROMISE A DURATION - no 'back in thirty', no 'back in sixty', "
        "no seconds or minutes of any kind: the break is shorter than "
        "any number you would say and the lie is audible. End on a "
        "TIMELESS exit instead - 'we'll be right back', 'back shortly', "
        "'don't go anywhere', 'sit tight', 'stay right there', 'one "
        "second' style - vary which one daily. The joke is "
        "NOT that ads are annoying, it is that YOU have obligations: a "
        "mortgage, a contract, a boss, a thing you signed without reading. "
        "A man complaining is tedious; a man who is trapped is funny. "
        "Vary it daily - this is a running bit and the same gripe every day "
        "dies fast. Around 25 words. Curse if you want, you normally do.\n\n"

        "  \"break_out\" - coming back. Short, relieved it is over, and it "
        "must name what is coming next so the show does not stall on the "
        "other side of the ad. Around 15 words.\n\n"

        + (f"  WHAT COMES AFTER THE BREAK: {', '.join(leagues_after)}. Those "
           f"segments are written separately and you do not see those games, "
           f"but they ARE in tonight's show.\n\n"

           f"  ONLY \"break_out\" MAY MENTION THEM. This is a hard rule, not "
           f"a preference. Your own segments must never announce, tease or "
           f"hand off to {', '.join(leagues_after)} - no \"now to the \", no "
           f"\"coming up\", no \"let's get to\". Your last segment ends on "
           f"YOUR league and stops there.\n\n"

           f"  Why: your segments run BEFORE the advert and break_out runs "
           f"AFTER it. A real episode announced the WNBA at the end of a "
           f"baseball segment, then played more baseball, then the ad, then "
           f"announced the WNBA again. It sounded broken.\n\n"

           f"  And do NOT say there are none: another episode said \"no WNBA "
           f"games Thursday\" seconds before three WNBA segments played.\n\n"
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
        "SOUND EFFECTS. Each segment can carry a reaction, played after it:\n"
        "  boo       a bad result, a team letting people down\n"
        "  laugh     something genuinely absurd\n"
        "  cheer     used IRONICALLY - one competent thing all night\n"
        "  gasp      a number nobody expected\n"
        "  trombone  the classic sad wah-wah, for a collapse\n"
        "  flourish  a moment worth celebrating, or mock-celebrating\n"
        "  aww       mock sympathy\n"
        "  crickets  NOTHING happened - a shutout, a team with two hits\n"
        "  boom      BLOWOUTS ONLY. A genuinely absurd scoreline, the sort\n"
        "            where a team got run out of their own building. Once an\n"
        "            episode at the very most, and most days not at all - it\n"
        "            is a big loud sound and it stops meaning anything the\n"
        "            second time.\n"
        "  ring      a phone ringing in a room. Use it when you have just\n"
        "            described somebody who deserves a call - it is the\n"
        "            product, so it lands as a threat rather than a noise.\n"
        "            Sparingly: once an episode, and not every episode.\n"
        "  none      say nothing after it\n\n"
        "  MOST SEGMENTS SHOULD BE \"none\". A sound after every segment turns "
        "a comedy show into a soundboard. Roughly a third is right, and the "
        "silence after a brutal line does more work than any effect.\n\n"

        '{"intro": "...", "segments": [{"text": "...", "reaction": "boo", '
        '"league": "MLB"}], "break_in": "...", "break_out": "...", '
        '"outro": "...", "best_line": "..."}\n'
        "Group segments sensibly - a [BIG] game is its own segment, several "
        "[quick] ones can share. reaction is one of: burn, laugh, shock, groan."
    )

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        # Raised from 2500. The prompt has grown a lot - fifty joke shapes,
        # per-league vocabulary, sound effect guidance - and two consecutive
        # runs logged "leagues played but NOT covered", with the WNBA getting
        # a single segment that never named either team. Each league is
        # written in its own call, so this is a per-league budget rather than
        # one shared across the show.
        # 2500 originally, raised to 4000 to fix a WNBA coverage warning, and
        # that produced an ELEVEN MINUTE episode against a six minute cap -
        # max_tokens was quietly the only thing limiting length, because the
        # word budget below it is advisory. 3000 is a compromise: room for
        # every league, not room to write a second show.
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    text = text.replace("```json", "").replace("```", "").strip()

    import json as _json
    try:
        script = _json.loads(text)
    except Exception as e:
        # "Extra data" means the JSON itself was fine and the model appended
        # something after the closing brace - a sign-off, a note, whatever.
        # Rejecting the whole response over trailing chatter loses a good
        # script and silently leaves yesterday's episode published, which is
        # exactly what happened on 1 Aug. raw_decode reads the first complete
        # object and ignores whatever follows it.
        try:
            script, end = _json.JSONDecoder().raw_decode(text)
            trailing = text[end:].strip()
            if trailing:
                print(f"[show] ignored {len(trailing)} chars of trailing text "
                      f"after the JSON: {trailing[:120]!r}", flush=True)
        except Exception:
            print(f"[show] script JSON failed to parse: {e}. "
                  f"First 400 chars: {text[:400]!r}", flush=True)
            raise
    script["publish"] = True
    return script


def _rss_mb():
    """
    Resident memory in MB, or None if it cannot be read.

    Render gives this service 512 MB and a production run was killed for
    exceeding it. Without a reading at each stage the only information is
    "it died", which is not enough to fix anything - three plausible causes
    were investigated and disproved by guesswork alone.
    """
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return None


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
        # Memory on every line. A run was killed for exceeding 512 MB and
        # there was nothing in the log to say where it happened - this turns
        # the next one from a guess into an answer.
        rss = _rss_mb()
        mem = f" {rss:5.0f}MB" if rss is not None else ""
        print(f"[show +{time.monotonic() - t0:6.1f}s{mem}] {msg}", flush=True)

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

    # CASE-INSENSITIVE: LEAGUE_ORDER says "MLB", games carry "mlb". The
    # exact compare matched NOTHING, so this fell through to the single
    # shared call every run - the per-league system never fired once.
    # The proof: "writing N league scripts in parallel" has never
    # appeared in a log.
    # THE CROSS-SPORT GATE (David's review, Aug 7): the NFL feed came
    # back carrying MLB GAMES mislabeled as NFL - so the NFL writer ran
    # and honestly wrote "Thursday night baseball" under a football
    # header, and the show teased a league it never had. A game only
    # counts for a league if its teams actually BELONG to that league
    # (checked against the alias tables); imposters are dropped loudly
    # and, if that empties a league, its writer never runs.
    def _belongs(team, lg_key):
        try:
            from services.team_aliases import TEAM_ALIASES
            table = TEAM_ALIASES.get(lg_key.lower())
            if not table:
                return True          # no table for this league: trust it
            t = (team or "").lower().strip()
            last = t.split()[-1] if t else ""
            # FULL NAME or NICKNAME equality only - substring matching
            # let "Baltimore Orioles" pass as NFL because "baltimore"
            # is a Ravens alias. Cities collide across leagues;
            # nicknames almost never do.
            return any(t == a or last == a
                       for names in table.values() for a in names)
        except Exception:
            return True
    _kept = []
    for g in material["games"]:
        _lg = (g.get("league") or "").lower()
        if _lg in ("mlb", "nfl", "nba", "nhl", "wnba") and not (
                _belongs(g.get("winner"), _lg)
                and _belongs(g.get("loser"), _lg)):
            print(f"[show] DROPPED cross-sport imposter: "
                  f"{g.get('winner')} vs {g.get('loser')} arrived "
                  f"labeled {_lg.upper()} but those are not "
                  f"{_lg.upper()} teams", flush=True)
            continue
        _kept.append(g)
    material["games"] = _kept

    present = []
    for lg in LEAGUE_ORDER:
        if any((g.get("league") or "").upper() == lg.upper()
               for g in material["games"]):
            present.append(lg)

    # One mood for the whole episode. Chosen HERE rather than inside each
    # call, so both league writers get the same one - otherwise a single
    # show could be manic about baseball and melancholy about basketball.
    _mood = pick_mood()
    log(f"mood today: {_mood[0]}")

    if len(present) <= 1:
        return write_script(material, mood=_mood)

    log(f"writing {len(present)} league scripts in parallel: {', '.join(present)}")


    # max_workers=0 RAISES, and present[0] below would too.

    #

    # present should never be empty here - the publish gate requires

    # games, and present is derived from them. But "should never" is

    # how four separate things broke today, and this costs one line.

    if not present:

        log("no leagues with games - nothing to write")

        # "publish", not "published" - that is the key this function's
        # other early returns use, and the caller checks.
        return {"publish": False, "reason": "no leagues with games"}


    with ThreadPoolExecutor(max_workers=min(4, len(present))) as pool:
        def _one(lg):
            # EVERY block gets its true after-list - the last one's is
            # empty, which is how it knows the sign-off is its job.
            _idx = present.index(lg)
            after = present[_idx + 1:]
            return (lg, write_script(material, only_league=lg,
                                     leagues_after=after, mood=_mood,
                                     opens_show=(_idx == 0)))

        results = list(pool.map(_one, present))

    by_lg = dict(results)

    # STRIP cross-league hand-offs, rather than asking for them not to happen.
    #
    # The prompt already forbids this in detail and even cites the episode it
    # broke. It was ignored anyway - the third prompt-level rule on this
    # project to be. Parallel writers cannot see each other, so a writer
    # announcing what follows is guessing, and the guess lands in the wrong
    # segment.
    #
    # Only break_out is allowed to mention another league. Everything else
    # gets the hand-off cut out of it.
    _strip_cross_league(by_lg, present, material.get("games"))

    # Did each league actually spread its budget?
    #
    # The segment target is a PROMPT instruction, and prompt instructions have
    # been ignored three times on this project - so this logs the miss rather
    # than assuming it held. Not corrected in code: splitting prose on
    # sentence boundaries would produce two halves of a joke, which is worse
    # than one long segment.
    #
    # If this warns repeatedly the answer is a second writing pass for that
    # league, not a mechanical split.
    for _lg in present:
        _segs = (by_lg.get(_lg) or {}).get("segments") or []
        _words = sum(len((x.get("text") or "").split()) for x in _segs)
        _want = _target_segments(_words) if _words else 0
        # Always log the shape, warn on any shortfall.
        #
        # The threshold was "< want - 1", which meant one segment against a
        # target of two never fired - so an episode where the WNBA wrote a
        # single block looked clean in the log.
        log(f"{_lg}: {len(_segs)} segment(s), {_words} words "
            f"(target ~{_want})")
        if _segs and len(_segs) < _want:
            log(f"WARNING: {_lg} under-spread - {len(_segs)} segment(s) for "
                f"{_words} words, asked for about {_want}. One long block "
                f"reads as a lecture.")
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
    from services.smackcast_service import (assemble_recap_audio,
                                            sanitize_for_speech,
                                            sanitize_for_display)

    log, elapsed = _elapsed_logger()
    log("started - fetching results")

    material = get_show_material(days_back=days_back)
    plan = material["plan"]
    log(f"results in: {material['game_count']} games, planning {plan['minutes']:g} min")
    # Box scores before writing, not after - the writer needs them.
    try:
        # The day the show is ABOUT, not an assumed yesterday. Matching
        # against the wrong day can attach another game's box score.
        from datetime import datetime as _d2, timedelta as _t2
        _show_day = (_d2.now(EASTERN) - _t2(days=days_back)).strftime("%Y-%m-%d")
        material["games"] = _attach_highlightly_ids(
            material["games"], log, day=_show_day)
        material["games"] = enrich_with_detail(material["games"], log)
    except Exception as e:
        log(f"deep detail unavailable, using scorelines only: {e}")

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
        # "burn" was the default and is not a valid reaction type - it is not
        # in _REACTION_TYPES, so nothing ever played for it. Any segment the
        # model did not explicitly tag silently got no sound at all.
        if isinstance(seg, str):
            body = seg
            reaction = "none"
        else:
            body = (seg.get("text") or seg.get("line") or seg.get("content")
                    or seg.get("body") or seg.get("script") or "")
            reaction = seg.get("reaction") or "none"
        body = (body or "").strip()
        if not body:
            continue
        league = (seg.get("league") or "").strip().upper() if isinstance(seg, dict) else ""
        # Two versions of every segment. The engine gets the respelled one -
        # "double you N B A", ".500" as "five hundred". The transcript keeps
        # what was actually written, because a real episode stored "double
        # you N B A" in its text and it looked broken to anyone reading it.
        segments.append({"text": sanitize_for_speech(body),
                         "display_text": sanitize_for_display(body),
                         "reaction": reaction, "league": league})

    # AWARD DEDUPE (David's review, Aug 7): the dry run carried TWO
    # "Crown of the Night" segments back to back, both about the same
    # team. One award name appears once per episode - the second
    # instance is dropped loudly, keeping whichever came first.
    try:
        import re as _re2
        _seen_awards = set()
        _deduped = []
        for _seg in segments:
            _m = _re2.search(r"(Smackagram's [A-Z][\w' ]{2,40}?) (?:goes|gets|we are giving)",
                             _seg.get("text") or "")
            if _m:
                _aw = _m.group(1).lower().strip()
                if _aw in _seen_awards:
                    print(f"[show] DROPPED duplicate award segment: "
                          f"{_m.group(1)}", flush=True)
                    continue
                _seen_awards.add(_aw)
            _deduped.append(_seg)
        segments = _deduped
    except Exception as _e:
        print(f"[show] award dedupe failed: {_e}", flush=True)

    # THE SAVAGE METER (Andy, Aug 7): the profanity level drifted soft
    # after the API switch and nobody could see it happening. Now it is
    # a NUMBER in every render log - counted in code, because prompt
    # mandates have been ignored before. Floor: one real swear per two
    # segments. Below floor logs a warning; the episode still ships
    # (a warning beats a blocked show at 5:55am with nobody awake).
    try:
        import re as _re
        _swears = _re.compile(
            r"\b(fuck\w*|shit\w*|goddamn\w*|damn\w*|bullshit|ass(?:hole)?s?\b"
            r"|bastard\w*|hell\b)", _re.IGNORECASE)
        _n = sum(len(_swears.findall(x.get("text") or "")) for x in segments)
        _floor = max(1, len(segments) // 2)
        print(f"[show] savage meter: {_n} swears across {len(segments)} "
              f"segments (floor {_floor})", flush=True)
        if _n < _floor:
            print(f"[show] SAVAGE WARNING: below floor - the script came "
                  f"back too clean, the mandate is being ignored again",
                  flush=True)
    except Exception as _e:
        print(f"[show] savage meter failed: {_e}", flush=True)

    if not segments:
        print(f"[show] script had no usable segments. Keys returned: "
              f"{[list(x.keys()) if isinstance(x, dict) else type(x).__name__ for x in script.get('segments', [])][:3]}")
        return {"published": False, "reason": "script returned no usable segments"}

    # Insert the commercial break after the LAST baseball segment, found by
    # the league tags rather than a fixed index - the number of MLB segments
    # changes nightly with the slate, so any hardcoded position would land
    # mid-baseball the first time the schedule was light.
    break_in = _strip_time_promises(
        sanitize_for_speech((script.get("break_in") or "").strip()))
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
        # The TAG first, and the prose only as a fallback.
        #
        # This warned that the WNBA was missing from an episode it was
        # actually in - three segments, correctly tagged, present in the
        # audio. Coverage was being decided purely by hunting for nicknames
        # in the prose, and that fails in two ways at once: nicknames under
        # four characters are deliberately dropped (Sky and Sun both are), and
        # a segment can legitimately talk about a game without naming either
        # club.
        #
        # The segments already carry a league tag - the same one the break
        # placement uses successfully. It is authoritative. Prose matching is
        # only needed for segments that arrive untagged.
        covered = set()
        for seg in segments:
            tag = (seg.get("league") or "").strip().upper()
            if tag and tag not in ("BREAK",):
                covered.add(tag)
                continue
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

        # DID THE BRANDED SEGMENTS ACTUALLY GET WRITTEN?
        #
        # The layouts allocate named slots - Smack Ball, Certified
        # Cooker, Clown Show, Winners and Whiners, the WNBA's rotating
        # award - but segments come back tagged by LEAGUE only, so
        # nothing confirmed a named bit survived into the script. A
        # dropped award was invisible until somebody listened for it.
        #
        # Matched PER LEAGUE (both leagues have a Winners and Whiners,
        # so a whole-script match cannot tell whose landed); untagged
        # segments count toward every league to err away from crying
        # wolf. One log line per run: what landed, what went missing.
        try:
            _by = {}
            _untagged = []
            for sg in segments:
                _t = (sg.get("text") or "").lower()
                _lgt = (sg.get("league") or "").strip().upper()
                if _lgt and _lgt not in ("BREAK", "ELSEWHERE"):
                    _by.setdefault(_lgt, []).append(_t)
                else:
                    _untagged.append(_t)

            def _league_text(lg):
                return " ".join(_by.get(lg, []) + _untagged)

            # (name, phrase to find, the layout slot that allocates it)
            _expected = []
            if any((g.get("league") or "").upper() == "MLB"
                   for g in material.get("games", [])):
                _expected += [
                    ("MLB Smack Ball", "smack ball", "smack_ball"),
                    ("MLB Certified Cooker", "certified cooker",
                     "certified_cooker"),
                    ("MLB Clown Show", "clown show", "clown_show"),
                    ("MLB Winners and Whiners", "winners and whiners",
                     "winners_and_whiners")]
            if any((g.get("league") or "").upper() == "WNBA"
                   for g in material.get("games", [])):
                try:
                    from services.wnba_layout import pick_award_title
                    _title = pick_award_title()
                    _expected.append((f"WNBA award '{_title}'",
                                      _title.lower(), "player_award"))
                except Exception:
                    pass
                _expected.append(("WNBA Winners and Whiners",
                                  "winners and whiners",
                                  "winners_and_whiners"))

            # ALLOCATED-BUT-ABSENT IS A FAILURE. NOT-ALLOCATED IS NOT.
            #
            # Winners and Whiners only exists when a losing streak
            # qualifies; the stats awards only when a box score arrived.
            # The first version of this check listed those as MISSING on
            # a night the layout had correctly not scheduled them - a
            # checklist that cries wolf on a correct night teaches
            # nobody to trust it on a bad one.
            _slots = material.get("_layout_slots") or {}
            _landed, _dropped, _unalloc = [], [], []
            _report_rows = []
            for _name, _phrase, _slot in _expected:
                _lg = _name.split()[0].upper()
                _lg_slots = _slots.get(_lg)
                _allocated = (_slot in _lg_slots) if _lg_slots else None
                if _allocated is False:
                    _unalloc.append(_name)
                    _report_rows.append({"name": _name, "hit": False,
                                         "allocated": False})
                    continue
                _hit = _phrase in _league_text(_lg)
                (_landed if _hit else _dropped).append(_name)
                _report_rows.append({"name": _name, "hit": _hit,
                                     "allocated": True})
            if _landed:
                log(f"branded segments in the script: {', '.join(_landed)}")
            if _unalloc:
                log(f"not scheduled tonight (layout had no material for "
                    f"them): {', '.join(_unalloc)}")
            if _dropped:
                log(f"WARNING: branded segments the layout ALLOCATED but "
                    f"the writer DROPPED: {', '.join(_dropped)}")

            # STRUCTURED, so the admin panel can render it as a
            # checklist rather than anybody hunting the log line.
            material["_segment_report"] = {
                "checked_at": __import__("datetime").datetime.utcnow()
                              .isoformat() + "Z",
                "greeting": pick_audience_name(),
                # More than one league in the material means the
                # parallel per-league writers ran.
                "parallel": len({(g.get("league") or "").upper()
                                 for g in material.get("games", [])}) > 1,
                "segments": _report_rows,
            }
        except Exception as _e:
            log(f"segment coverage check unavailable: {_e}")

        # The break goes after the LEAD league's block, whichever league that
        # is - not after MLB specifically. Hardcoding baseball fell apart the
        # moment the show was pointed at a football Sunday: no MLB meant the
        # midpoint fallback, which split the NBA in half.
        # The lead league's segments must not announce what follows - that is
        # break_out's job, and break_out runs AFTER the advert. The prompt now
        # forbids it, but a prompt is a request; this makes the failure
        # visible in the logs instead of only in the audio.
        # Same case trap as above.
        _later = [lg for lg in LEAGUE_ORDER
                  if any((g.get("league") or "").upper() == lg.upper()
                         for g in material.get("games", []))]
        if len(_later) > 1:
            _lead, _rest = _later[0], _later[1:]
            _tease = re.compile(
                r"\b(now|next|coming up|up next|let's get to|over to|moving on to)\b[^.!?]{0,40}\b("
                + "|".join(re.escape(lg) for lg in _rest) + r")\b",
                re.IGNORECASE)
            for i, seg in enumerate(segments):
                if seg.get("league") != _lead:
                    continue
                hit = _tease.search(seg.get("text") or "")
                if hit:
                    log(f"WARNING: {_lead} segment {i} hands off to "
                        f"{'/'.join(_rest)} before the break - that belongs in "
                        f"break_out. Text: {hit.group(0)[:70]!r}")

        lead_league = None
        for seg in segments:
            if seg.get("league"):
                lead_league = seg["league"]
                break

        last_mlb = -1
        first_non_mlb = -1
        tagged = False
        for i, seg in enumerate(segments):
            if seg.get("league"):
                tagged = True
                is_lead = seg["league"] == lead_league
            else:
                verdict = _looks_mlb(seg.get("text"))
                if verdict is None:
                    continue
                is_lead = verdict

            if is_lead:
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
                   {"text": ad_copy_for_today(), "reaction": "none", "league": "BREAK",
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

    # ELSEWHERE - about a minute on everything else that happened.
    #
    # Placed AFTER the break, and its position ROTATES: some days it sits
    # between baseball and the WNBA, other days it closes the show. A
    # segment that is always in the same place is one a regular listener
    # starts skipping.
    #
    # Rotated on the DATE rather than at random, so a re-render of the same
    # episode does not move it - and consecutive days always differ.
    try:
        # IMPORTED LOCALLY, like the other two call sites in this file.
        #
        # This one was missed, so the whole around-the-grounds segment
        # died with "name 'espn_scores' is not defined" - caught by the
        # try, logged, and silently dropped from every episode.
        from services import espn_scores
        _else = espn_scores.fetch_elsewhere()
        if _else:
            _rows = []
            for r in _else:
                if r.get("drawn"):
                    _rows.append(f"{r['league']}: {r['a']} and {r['b']} drew "
                                 f"{r['score']}")
                else:
                    _rows.append(f"{r['league']}: {r['winner']} beat "
                                 f"{r['loser']} {r['score']}")

            _text = (
                "AROUND THE GROUNDS - about a minute, no more.\n"
                + "\n".join(f"  {x}" for x in _rows) +
                "\n\nRattle these off. ONE LINE EACH, a joke on two or three "
                "of them at most - this is a quick lap, not a block.\n"
                "Say what sport each one is, because a listener who has just "
                "heard baseball needs telling that this is football now.\n"
                "Only what is listed above is true. Invent no scores, no "
                "scorers, no detail."
            )

            # WRITTEN, not pasted.
            #
            # Everything else at this point is finished prose. Inserting the
            # brief itself would put "AROUND THE GROUNDS - about a minute,
            # no more" straight down the microphone.
            #
            # Its own small call rather than adding it to a league writer:
            # this is not a league, and the two league writers run in
            # parallel and would either both include it or both leave it
            # out.
            from services.smackcast_service import _get_client as _cl
            _r = _cl().messages.create(
                model="claude-sonnet-4-6",
                max_tokens=350,
                # Smacky's real voice, not a thin one-off description -
                # otherwise this segment sounds like a different presenter
                # walked in for a minute.
                system=_elsewhere_system(),
                messages=[{"role": "user", "content": _text}],
            )
            _written = (_r.content[0].text or "").strip()
            if not _written:
                raise ValueError("empty around-the-grounds copy")

            _seg = {"text": _written, "display_text": _written,
                    "reaction": "none", "league": "ELSEWHERE"}

            import datetime as _dt
            _after_wnba = _dt.date.today().toordinal() % 2 == 0

            _brk_end = -1
            for _i, _sg in enumerate(segments):
                if (_sg.get("league") or "").upper() == "BREAK":
                    _brk_end = _i
            if _after_wnba or _brk_end == -1:
                segments.append(_seg)
                log(f"around the grounds: {len(_rows)} results, closing the show")
            else:
                segments.insert(_brk_end + 1, _seg)
                log(f"around the grounds: {len(_rows)} results, straight "
                    f"after the break")
    except Exception as e:
        log(f"around the grounds unavailable: {e}")

    # A phone bit, sometimes. Inserted after the break is placed so it never
    # lands next to the advert, and before audio so it is treated as a normal
    # segment everywhere downstream.
    # Hold it to the budget BEFORE the interruption goes in, so the bit is
    # never the thing that gets cut.
    # Count the overused construction. It is capped in the prompt, but the
    # cap has been ignored twice now - once because each league is written
    # in parallel and neither writer could see the other's usage. Logging it
    # is how we find out whether the tighter wording actually holds, rather
    # than waiting for someone to notice while listening.
    try:
        _tnt = sum(len(re.findall(
            r"(?:that|this|it)(?:'s| is| was)\s+not\s+a\b", (x.get("text") or ""),
            flags=re.IGNORECASE)) for x in segments)
        if _tnt:
            log(f"\"that's not a...\" construction used {_tnt} time(s)")
        _flag_repeats(segments, log)

        # THE SAFETY FILTER, on the show too.
        #
        # This is the one thing from the call generators worth adding here,
        # and it cannot disrupt the writing because it only acts when
        # something is actually wrong.
        #
        # The show arguably needs it MORE than a call does: a Smackagram
        # goes to one person who chose to receive it, while the Daily Smack
        # is published to everybody and nobody reviews it before it airs.
        #
        # The PLAYBOOK is deliberately NOT added - the show already has its
        # own seventeen-situation bank, richer for baseball than the
        # playbook is, and two systems answering "what do I say about a
        # collapse" would fight each other.
        try:
            from services import fast_filter
            for _seg in segments:
                _v = fast_filter.check(_seg.get("text") or "")
                if not _v["ok"]:
                    log(f"SAFETY: a segment was blocked ({_v['category']}) - "
                        f"cutting it rather than airing it")
                    _seg["text"] = ""
                    _seg["display_text"] = ""
                elif _v.get("restyled"):
                    _seg["text"] = _v["text"]
            # A blocked segment leaves an empty one behind, which would be
            # silence in the middle of the show.
            segments[:] = [x for x in segments if (x.get("text") or "").strip()]
        except Exception as e:
            log(f"safety filter unavailable: {e}")
        if _tnt > TNT_MAX_PER_EPISODE:
            _capped = _cap_construction(segments, TNT_MAX_PER_EPISODE)
            log(f"capped it to {TNT_MAX_PER_EPISODE} - rewrote {_capped}")
    except Exception:
        pass

    # Hand the length check the layouts' own total, so it measures against
    # what the writers were told rather than the planner's separate estimate.
    _lb = sum((material.get("_layout_budgets") or {}).values())
    if _lb:
        plan = {**plan, "layout_budget": _lb}
        segments = enforce_length(segments, plan, log)

    segments = maybe_interruption(segments)

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
            # Preview the DISPLAY text. The speech version is respelled for
            # the engine - "double you N B A" - which is right out loud and
            # unreadable in a log.
            preview = seg.get("display_text") or seg.get("text") or ""
            log(f"  [{i}] {preview[:70]}")
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
        # The checklist the panel renders - which branded segments made
        # the script, tonight's greeting, and whether the parallel
        # writers ran.
        "segment_report": material.get("_segment_report"),
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
# Occasionally the read goes wrong. The ad is currently a hard block that
# listeners will learn to skip, and the single best defence against that is
# making it sound live - a man reading copy badly is worth listening to, a
# clean recording is not.
#
# Never so wrong that the message is lost. The domain, the dollar and the
# promise all survive every variant; what breaks is his composure.
AD_FUMBLES = [
    # loses his place
    ("Smackagram. The world leader in sports trash tal- sorry. Sorry. "
     "Let me start that again. ", ""),

    # reads it too fast, then apologises
    ("", " ...that was too fast. Nobody got any of that. It's on the website."),

    # gets the domain wrong and corrects himself
    ("", " Smackagram dot org. Dot com. It's dot com. It's always been dot com."),

    # editorialises mid-read
    ("", " I've read that four hundred times and I still don't know who wrote it."),

    # can't believe the price
    ("", " Less than a dollar a call. A whole phone call for POCKET "
      "CHANGE. We are being robbed."),

    # sincerely means it
    ("", " And that one's actually true, by the way. All of it."),

    # loses interest halfway
    ("", " ...and so on. You've heard it. You know what it says."),
]

# How often the read goes wrong. Roughly one episode in five - often enough
# to be worth staying for, rare enough that a clean read is still the norm.
AD_FUMBLE_CHANCE = 0.20


def _elsewhere_system():
    """
    Smacky's voice for the Around the Grounds minute.

    Built from the same vocabulary the rest of the show uses, so it does not
    sound like a different presenter walked in for sixty seconds. But the
    PLAYBOOK is left out - a one-line result has no box score behind it, and
    "somebody call the mercy rule" needs a margin nobody fetched.
    """
    parts = ["You are Smacky, a loud sports host reading a quick lap of "
             "everything else that happened. Spoken radio copy only - no "
             "headings, no stage directions, no asterisks, nothing that a "
             "text-to-speech engine would read out as a symbol."]
    try:
        from services import smackology
        blk = smackology.smacky_block(3)
        if blk:
            parts.append(blk)
    except Exception:
        pass
    try:
        from services import insults
        blk = insults.block(3)
        if blk:
            parts.append(blk)
    except Exception:
        pass
    parts.append(
        "AROUND THE GROUNDS - ITS OWN RULES.\n"
        "This is a sixty-second lap, not a block. It sits inside a show that "
        "already has full segments on baseball and basketball, and every "
        "rule below exists so it does not collide with them.\n\n"

        "ONE LINE PER RESULT. Four or five results, one sentence each. A "
        "joke on two or three of them at most - a lap where every result "
        "gets a punchline is not a lap, it is another block.\n\n"

        "NAME THE SPORT EVERY TIME. Somebody has just heard nine minutes of "
        "baseball. 'Arsenal beat Chelsea' means nothing to them until you "
        "say it is football.\n\n"

        "NO STREAKS, NO RECORDS, NO SEASON TALK. Each league already has a "
        "Winners and Whiners for that, and doing it here is the same "
        "segment twice.\n\n"

        "NO AWARDS. No player of the night, no worst performer. Those belong "
        "to the leagues that have box scores behind them.\n\n"

        "DO NOT SIGN OFF. Some days this closes the show and the real "
        "outro follows immediately - 'that's all from me' here means the "
        "listener hears goodbye twice. Just stop.\n\n"

        "DO NOT TEASE WHAT IS COMING. You do not know what follows.\n\n"

        "AT MOST ONE INVENTED WORD in the whole minute, and only if it "
        "fits. The league blocks have already used theirs; a second "
        "Clownburger in the same episode is the joke wearing out in real "
        "time.\n\n"

        "Roast the RESULT, never the person listening and never anybody's "
        "appearance, career or private life.\n"
        "INVENT NOTHING. No score, no scorer, no red card, no knockdown, no "
        "detail beyond exactly what you are given. You have the result and "
        "nothing else, and a made-up detail about a named professional is "
        "not a joke.")
    return "\n\n".join(parts)


def ad_copy_for_today():
    """The advert, occasionally delivered badly."""
    import random
    if random.random() > AD_FUMBLE_CHANCE:
        return AD_COPY
    pre, post = random.choice(AD_FUMBLES)
    print("[show] ad read fumbled", flush=True)
    return (pre + AD_COPY + post).strip()


AD_COPY = (
    "Smackagram. The world leader in sports trash talk. Any sport. Any team. "
    "You write the smack. We make the call. A real phone, ringing in their "
    "pocket, saying everything you could never say to their face. And they "
    "never find out it was you. "
    "You watch the games. We talk the talk. Less than a dollar a call. "
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

        # A NAME YOU CAN READ.
        #
        # Every file in the bucket was tts/<random-uuid>.mp3 - a wall of
        # meaningless names with no way to tell a daily show from a single
        # call from a Smackcast. Twenty-three episodes are in there and none
        # of them can be identified without opening it.
        #
        # Its own folder, dated, so the bucket sorts itself and any file can
        # be recognised at a glance. The short random tail keeps two runs on
        # the same day from overwriting each other - a re-render should not
        # silently replace the episode somebody is already listening to.
        # STAYS UNDER tts/. The bucket's public-read policy is scoped to
        # that path, so a file in daily-smack/ uploads perfectly and then
        # returns AccessDenied when a browser asks for it - the show goes
        # silent with nothing in any log.
        #
        # This already happened once on this project with the meme images,
        # and there is a comment in smackcast_service saying so. I moved
        # these anyway.
        #
        # The name still does the work - readable and dated - it just lives
        # where the policy can see it.
        _day = datetime.now(EASTERN).strftime("%Y-%m-%d")
        key = f"tts/daily-smack-{_day}-{uuid.uuid4().hex[:6]}.mp3"

        with open(out, "rb") as f:
            boto3.client("s3", region_name=region).put_object(
                Bucket=bucket, Key=key, Body=f, ContentType="audio/mpeg",
                # Downloads land as "2026-08-04-daily-smack.mp3" rather than
                # a uuid, which matters the moment anybody saves one to clip
                # it or send it on.
                ContentDisposition=(
                    f'inline; filename="{_day}-daily-smack.mp3"'),
                Metadata={"show": "daily-smack", "date": _day})

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


def _show_vocabulary(league: str) -> str:
    """
    Smacky's vocabulary for the league being written about.

    Kept separate from the Auto-Smack blocks in trash_talk_service
    because the show has different needs: it covers winners as well as
    losers, so the celebratory half of every list is in play here and is
    dead weight in a roast call.
    """
    from services import trash_talk_service as tt

    lg = (league or "").lower()
    lookup = {
        "mlb": tt.MLB_SLANG, "ncaabb": tt.MLB_SLANG,
        "nfl": tt.NFL_SLANG, "ncaaf": tt.NFL_SLANG,
        "nba": tt.NBA_SLANG, "ncaab": tt.NBA_SLANG,
        "wnba": tt.WNBA_SLANG, "ncaaw": tt.WNBA_SLANG,
    }
    block = lookup.get(lg)
    if not block:
        return ""

    out = "\n\n" + block

    out += (
        "\n\nUSE THAT VOCABULARY. It is not a reference list you may "
        "consult - it is how this character talks, and a real episode came "
        "out without a single one of those words in it.\n\n"
        "  AT LEAST ONE per segment. Most segments should carry one; some "
        "will carry two. A segment with none is a segment written by "
        "somebody who does not watch this sport.\n\n"
        "  The INVENTED words matter most. Anyone can say 'they lost badly'. "
        "Only Smacky says Batastrophe, Sackediculous, Clankageddon, "
        "Bucketress, Touchdonkey. Those are the ones people repeat, and they "
        "are the reason the show sounds like him instead of like a "
        "broadcast.\n\n"
        "  Do not stack them. One well-placed invented word beats three in "
        "a row, which reads as a man showing off a glossary.\n\n"
        "  And you are covering WINNERS as well as losers here, unlike a "
        "roast call - so the celebratory half of that vocabulary is live "
        "too. The home run words, the dunk words, the catchphrases about "
        "somebody going off. A show that only insults people is exhausting; "
        "the joy is what makes the cruelty land.\n"
    )

    # NOT the Clark block from trash_talk_service. The show already carries
    # its own Clark instruction, tuned to the show's shape - it OPENS the
    # WNBA segment rather than being dropped in wherever. Two sets of
    # instructions about the same running joke would fight each other.
    if lg == "ncaaw":
        out += "\n" + tt.NCAAW_CLARK

    if lg.startswith("ncaa"):
        out += "\n" + tt.COLLEGE_ANGLES

    return out


# ---------------------------------------------------------------------------
# Interruptions
# ---------------------------------------------------------------------------
# Short bits where something pulls Smacky off the show. They exist to give
# him a life outside the box score - a voice reading scores is a format, a
# man whose phone keeps going is a character.
#
# Written rather than generated, deliberately. A bad improvised interruption
# lands in the middle of a published episode and there is no taking it back.
#
# Two rules hold the whole thing together:
#
#   ONE PER EPISODE AT MOST, and not every episode. The danger is Smacky's
#   kitchen becoming more interesting than the sport.
#
#   HE ALWAYS COMES OFF WORSE. He is aggressive with the entire sporting
#   world for five minutes and folds instantly the moment his wife rings.
#   That contrast is the joke. The moment his cruelty points at somebody in
#   his own life he stops being fun and starts being someone you would
#   avoid.

PHONE_INTERRUPTIONS = [
    # The mother
    "Hang on. Hang on. ... Hello? ... Ma. Ma, I'm working. I am literally working "
    "right now. No. No, I told you Tuesday. Tuesday, Ma. I have to go. I "
    "have to - okay. Okay. Bye. ... Where was I.",

    # The wife, and he folds instantly
    "Hang on. (sigh) Hi. Yes. No, I'm at work. This is work. No, I - okay. "
    "Okay, I'll get it on the way home. ... I know I said that yesterday. "
    "Bye. ... Right.",

    # Defending the job
    "Hello? ... I can't, I'm live. I'm live right now, people are listening. ... No, "
    "dozens of people. ... That's not the point.",

    # The list
    "Hello? ... No, that was on the list, I got the - ... I got most of the "
    "list.",

    # Explaining what he does for a living. Names the sport, so it is tagged
    # - dropped into a basketball segment it would be simply wrong.
    ("Hello? ... I'm going to have to call you back. ... Because I'm describing a "
     "baseball game to strangers. ... Yes. Yes, that's what I do now.", "MLB"),

    # Screening it
    "Sorry. One second. ... Hello? ... Nope. Nope, not doing this. Goodbye.",

    # The same number all week
    "Hello? ... Oh, you have got to be kidding me. ... It's the same number. It's been "
    "the same number all week. If you're the extended warranty people, I "
    "don't own a car.",

    # Wrong number entirely
    "Hello? ... This isn't the mortgage people. ... No, sir. ... No, I don't "
    "own the house either.",

    # The mother of a player he just roasted
    "Hello? ... Ma'am, I'm sure he's a lovely boy. ... Ma'am. ... Ma'am, he "
    "went oh for four.",

    # His agent, at five in the morning
    "Hello? ... It's five in the morning. ... No, I haven't read it. ... Send it again "
    "and I'll not read it again.",

    # Somebody who heard the show
    "Hello? ... Yes, that was me. ... Well, yes, I did say that about your "
    "team. ... I stand by it. ... Hello?",

    # The one that will not stop
    "I'm not - I'm going to let that go to voicemail. We're all going to "
    "pretend that isn't happening.",

    # --- home ---
    "Hello? ... No, I don't know where it is. ... Because I didn't move it. "
    "... Because I've been here, doing this.",

    "Hang on. ... Hello? ... I'm not having this conversation again. ... It's a "
    "chair. ... It's a perfectly good chair.",

    "Hello? ... What do you mean it's leaking. ... Since when. ... Okay. "
    "Okay, I'm coming. Not now. ... Fine.",

    "No - no, I said I'd think about it. ... Thinking about it is a thing "
    "you can do. ... Okay. Bye.",

    "Hello? ... I did feed him. ... I fed him at four. ... Well, he's lying "
    "to you.",

    # --- family ---
    "Ma. Ma. Ma. ... No, that was your other son. ... Yes, I know. Yes. "
    "Bye, Ma.",

    "Hello? ... No, I'm not coming Sunday. ... Because last Sunday took "
    "eleven hours. ... It did, Ma. I timed it.",

    "Hello? ... You're breaking up. You're - I can hear you perfectly, "
    "actually. I'm lying.",

    "Yes? ... He said what about me. ... At Christmas? He's been saving "
    "that since Christmas?",

    # --- work and admin ---
    "Hello? ... No, I've not filled that in. ... Because it's a form, and "
    "I'm a grown man.",

    "Hello? ... It's five in the morning. ... Yes, I'm aware what time zone you're in. "
    "... That's not my problem.",

    "Hello? ... The invoice went out. ... It went out. ... I'll check. I'm "
    "not going to check.",

    "Yes? ... No, that's not what I said. ... That's what you heard. ... I "
    "have to go.",

    # --- strangers ---
    "Hello? ... Is this about the car? ... I don't have a car. ... I've "
    "never had a car.",

    "Hello? ... No, this is Smacky. ... No. Smacky. ... You know what, yes. "
    "Yes, speaking.",

    "Hello? ... How did you get this number. ... How did you get this "
    "number.",

    "Hello? ... Hello? ... Somebody's breathing. Somebody is just breathing "
    "at me.",

    "Hello? ... Sir, it's five in the morning. ... Sir, I'm going to hang "
    "up. ... Sir.",

    # --- the baby ---
    # He never tells anyone to deal with it. A man shouting at his wife
    # about a crying child is not funny, it is just a man you would avoid -
    # the joke is that his life is happening loudly and he has no authority
    # over any of it.
    ("Okay, he's up. He's up, we're all up. Nobody in this house is asleep "
     "now.", None, "baby"),

    ("That's not going to stop, is it. ... No. No, that's the rest of the "
     "show, then.", None, "baby"),

    ("I'm going to keep going. I'm going to keep going, and we're all going "
     "to have a difficult five minutes together.", None, "baby"),

    ("That is the sound of a man's career. Right there. That noise.",
     None, "baby"),

    ("Can somebody - ... anyone? ... No. Okay. It's me. It's always me.",
     None, "baby"),

    # --- the neighbour ---
    # Never named, never seen, referenced as though the audience already
    # knows him - because after three weeks they do. A running joke costs
    # nothing and builds equity: people start waiting for it.
    ("He's out there again. Five in the morning. He's out there.",
     None, "mower"),

    ("That's him. That's the man. I'm not going to say his name.",
     None, "mower"),

    ("Somebody is cutting grass. In the dark. I want that on the record.",
     None, "mower"),

    ("He knows I'm doing this. That's the part that gets me. He knows.",
     None, "mower"),

    ("Twenty past five and the man is landscaping.", None, "mower"),

    ("I've seen the lawn. It did not need doing. It has never needed "
     "doing.", None, "mower"),

    ("One day I'm going to go out there. Not today. But one day.",
     None, "mower"),

    ("That's the third time this week. I'm keeping count now.",
     None, "mower"),
]


# The neighbour with the lawnmower. Never named, never seen, referenced as
# though the audience already knows him - because after three weeks they do.
# A running joke costs nothing and builds equity: people start waiting for
# it, and something people wait for is worth more than something that lands
# once.
#
# These fire alongside the ambient mower bed, so the sound and the complaint
# arrive together.
# Every bit has to CLOSE ITSELF. The interruption is inserted after the
# script is written, so the segment that follows has no idea it happened and
# will simply carry on with a baseball score - which leaves the bit hanging
# in the air with nobody acknowledging it.
#
# A return line does the work: he gathers himself, says something, and the
# show resumes. Varied so it is not the same recovery every time.
# He has to NOTICE the phone. A ring followed instantly by "Hello?" sounds
# like a cue rather than an interruption - a real person hears it, reacts,
# apologises, and only then answers. This is what turns a sound effect into
# a moment.
# And he has to END the call. Most scripts simply stop, which leaves the
# other person hanging and the listener wondering whether the line is dead.
# A real call closes, even badly.
SIGNOFF_LINES = [
    "Okay. Bye. Bye. Bye.",
    "Right - I have to go. Bye.",
    "Yep. Okay. Bye.",
    "I'm hanging up now. Goodbye.",
    "Okay, love you, bye.",
    "Right. Bye then.",
    "I'll call you back. I won't, but I'll say it. Bye.",
    "Okay. Okay. Goodbye.",
    "Alright, bye. Bye. BYE.",
    "That's me gone. Bye.",
    "Yeah. Bye.",
    "Goodbye. Goodbye.",
]

# Smacky is in FULL GEAR, every single episode.
#
# A mood system was built here - eight states, one picked per morning, so
# some days he turned up flat or melancholy. Good idea for a show that runs
# several times a day; wrong for this one. There is ONE episode every
# morning, and a listener who gets the tired version has got the only
# version. Every episode has to be his best.
#
# So the variation lives in WHAT he says, not in how much he can be bothered.
FULL_GEAR = (
    "wired",
    "You are in full gear and you stay there. Loud, fast, delighted, "
    "completely on. This is the version of you that is having the best time "
    "of anybody involved in professional sport this morning.\n\n"
    "  You are not tired. You are not going through the motions. You are not "
    "above this - you LOVE this, and the joy is exactly what makes the "
    "cruelty land. A host who sounds bored makes the audience bored.\n\n"
    "  Big reactions. Real delight at other people's disasters. The energy "
    "of a man who cannot believe he gets paid for this."
)


def pick_mood():
    """
    Always full gear.

    Kept as a function rather than inlined so the seam is obvious if this
    ever becomes variable again - and so the log line still reports what he
    is doing.
    """
    return FULL_GEAR


PICKUP_LINES = [
    "Sorry - hang on, let me just grab this.",
    "Oh - sorry. Sorry, I thought that was on silent.",
    "Hang on, hang on. I should get this.",
    "Sorry, one second, I have to take this.",
    "Oh, come on. ... Sorry. One moment.",
    "That's - sorry. That's mine. Give me a second.",
    "Hang on. I've got to answer that, it might be important. It won't be.",
    "Sorry, I'll be honest, I thought I turned that off.",
    "Oh, for - sorry. Let me deal with this.",
    "Hold on. Hold on. Sorry about this.",
    "That's been going all morning. Sorry. Let me just...",
    "Sorry - I'm going to get that. I know. I know.",
    "One second. I promise this is quick.",
    "Oh, brilliant. Perfect timing. Sorry, hang on.",
    "Sorry. Right. Let me just see who this is.",
]

RETURN_LINES = [
    "Anyway.",
    "Right. Where was I.",
    "Sorry. Sorry about that.",
    "Okay. Moving on.",
    "That's my life. That's what that is.",
    "Let's pretend that didn't happen.",
    "Back to it.",
    "Right. Baseball.",
    "So. Yes.",
    "We're going to move past that.",
    "Anyway, none of you needed to hear any of that.",
    "Where were we. Doesn't matter.",
    "That's going to be dealt with later. Not now. Later.",
    "Okay. Focus.",
    "I apologise to everyone listening.",
    "That's the last we'll speak of it.",
]

# EXACTLY ONE PER EPISODE, ALWAYS. Not a chance roll - the bit is part of
# the show now rather than an accident that sometimes happens.
#
# Which is why the pool needs to be big. At thirty scripts a daily listener
# gets a month before hearing a repeat; at twelve they would notice inside a
# fortnight, and a joke you can see coming is not one.


def enforce_length(segments, plan, log=None):
    """
    Hold the script to its word budget.

    The budget was only ever a line in the prompt, which meant the real
    limit was max_tokens - and raising that to cover a missing league
    produced an eleven minute episode against a six minute cap. A number
    the model is asked to respect is not a limit; this is.

    Whole segments are dropped from the END rather than sentences trimmed
    from the middle, because a segment cut mid-thought sounds broken and a
    missing one sounds like editing. The advert and anything before it are
    never touched - the break has to stay where it was placed.
    """
    budget = int(plan.get("word_budget") or 0)
    if not budget or not segments:
        return segments

    # A SAFETY NET, not a pair of scissors.
    #
    # The eleven minute episode that prompted this turned out to be mostly a
    # playback fault - pieces written at the wrong sample rate played back
    # slowed down, stretching the runtime - rather than the model writing
    # too much. Trimming at a tight tolerance would have cut a script that
    # was fine.
    #
    # So this only fires on genuine runaway: sixty percent over budget is
    # far outside normal variation and means something has actually gone
    # wrong. Below that the script is left exactly as written.
    # The budget the LAYOUTS actually handed out, not the planner's estimate.
    #
    # Two systems were disagreeing. plan_runtime allocated 641 words for the
    # whole show while the layouts allocated 555 for baseball and 168 for the
    # WNBA - so a script that fitted its own briefs perfectly still read as
    # 80% over, and the trim cut two segments that were never surplus. On a
    # night when an award falls at the end, that trim removes the award.
    #
    # The layouts are authoritative: they are what the writer was actually
    # told to write to.
    laid_out = plan.get("layout_budget") or 0
    if laid_out:
        budget = max(budget, laid_out)

    ceiling = int(budget * 1.6)

    def words(seg):
        return len((seg.get("text") or "").split())

    total = sum(words(x) for x in segments)
    if total <= ceiling:
        return segments

    # CUT FROM WHICHEVER LEAGUE IS FATTEST, not from the end.
    #
    # The old rule protected everything before the ad break and dropped
    # whatever followed. But the break sits after the LAST BASEBALL segment,
    # so baseball was fully protected and the WNBA took every cut.
    #
    # A real episode ran 86% over and lost two segments - both from the WNBA
    # block. That is how one league loses its closing beat while the league
    # before it keeps every one of its own.
    #
    # Now: take from whoever has the most, one at a time, until it fits. A
    # long baseball block gives up a segment rather than a short basketball
    # block losing its ending.
    #
    # The BREAK is never dropped - the ad is the thing that was paid for -
    # and no league is ever emptied completely.
    kept = list(segments)

    def _lg(seg):
        return (seg.get("league") or "").upper()

    def _total(segs):
        return sum(words(x) for x in segs)

    guard = 0
    while _total(kept) > ceiling and guard < 40:
        guard += 1
        by_lg = {}
        for idx, seg in enumerate(kept):
            lg = _lg(seg)
            # BREAK is the advert - the thing that was paid for.
            # ELSEWHERE is a single sixty-second segment, so dropping it
            # does not shorten the show by a segment, it removes a whole
            # feature. It is currently safe only because the rule below
            # never touches a league with one segment - which is luck, not
            # design, and luck stops working the day it gets a second one.
            if lg in ("BREAK", "ELSEWHERE", ""):
                continue
            by_lg.setdefault(lg, []).append(idx)
        spare = {lg: ix for lg, ix in by_lg.items() if len(ix) > 1}
        if not spare:
            break
        fattest = max(spare, key=lambda lg: sum(words(kept[i])
                                                for i in spare[lg]))
        kept.pop(spare[fattest][-1])
        if log:
            log(f"over budget - dropped a {fattest} segment")

    if log and len(kept) < len(segments):
        log(f"trimmed {len(segments) - len(kept)} segment(s): script was "
            f"{total} words against a {budget} budget")
    return kept


# One per episode, at most. It is a good construction the first time and a
# tic by the third - and with parallel league writers each believing it has
# its own budget, "twice per episode" has come out four times.
TNT_MAX_PER_EPISODE = 1


def _flag_repeats(segments, log):
    """
    Find segments that say the same thing twice.

    An episode repeated a baseball line after the WNBA hand-off. Nothing in
    assembly duplicated it - the segment counts add up exactly - so the writer
    said it twice, which is the failure mode a phrase bank makes MORE likely,
    not less.

    Compared on CONTENT WORDS rather than whole strings. A model repeating
    itself rarely repeats verbatim; it rewords the same observation about the
    same game, and an exact-match check would miss every real case.

    Flagged, not deleted. Cutting the second occurrence can remove the better
    version, and can leave the segment before it pointing at something that no
    longer follows.
    """
    import re as _re

    STOP = {"the","a","an","and","but","that","this","it","was","were","is",
            "are","to","of","in","on","for","with","they","them","their",
            "you","your","he","his","just","not","got","had","have","been",
            "one","two","all","out","up","off","at","by","from","so","as"}

    def bag(text):
        words = _re.findall(r"[a-z']{3,}", (text or "").lower())
        return {w for w in words if w not in STOP}

    bags = [(i, bag(s.get("text"))) for i, s in enumerate(segments)]
    for a_i, a_b in bags:
        if len(a_b) < 8:
            continue
        for b_i, b_b in bags:
            if b_i <= a_i or len(b_b) < 8:
                continue
            shared = a_b & b_b
            overlap = len(shared) / min(len(a_b), len(b_b))
            if overlap >= 0.55:
                log(f"WARNING: segments {a_i} and {b_i} are {overlap:.0%} the "
                    f"same - the writer repeated itself. Shared: "
                    f"{', '.join(sorted(shared)[:8])}")


def _cap_construction(segments, keep=1):
    """
    Rewrite the surplus "that's not a X, that's a Y" lines.

    The negation is the disposable half. "That's not a loss, that's an
    eviction notice" becomes "That's an eviction notice" - which is shorter,
    hits sooner, and loses nothing except the formula.

    Rewritten rather than deleted: the second half usually carries the actual
    joke, and cutting the sentence would throw the joke away with the tic.

    In code because the prompt cap has been ignored twice.
    """
    import re as _re

    # "That's not a loss, that's an eviction notice."
    # "This isn't football - it's community service."
    # Two shapes of the same tic:
    #   "that's NOT a loss, that's an eviction notice"
    #   "this ISN'T football - it's community service"
    # The second hides its negation inside the contraction, so a pattern
    # looking for a following "not" misses it entirely.
    PAT = _re.compile(
        r"\b(?:that|this|it)"
        r"(?:(?:'s|s| is| was)\s+not|(?:\s*isn'?t|\s*ain'?t|\s*wasn'?t))\s+"
        r"(?:a |an |the )?[^,.;!?-]{1,40}[,.;:\u2014-]+\s*"
        r"(?:that|this|it)(?:'s| is| was)\s+",
        _re.IGNORECASE)

    seen = 0
    rewritten = 0
    for seg in segments:
        text = seg.get("text") or ""
        if not text:
            continue
        out = text
        for m in list(PAT.finditer(text)):
            seen += 1
            if seen <= keep:
                continue          # the first one earns its place
            # Keep the payoff, drop the set-up.
            out = out.replace(m.group(0), "That's ", 1)
            rewritten += 1
        if out != text:
            seg["text"] = out
            # display_text is what the transcript shows; keep them in step.
            if seg.get("display_text"):
                seg["display_text"] = out
    return rewritten


def _strip_cross_league(by_lg, present, _material_games=None):
    """
    Remove any sentence in which one league's writer announces another's.

    Cuts whole SENTENCES, not phrases. Removing "now to the WNBA" from the
    middle of a line leaves a fragment that reads worse than the fault did;
    the sentence is the smallest unit that can be taken out cleanly.

    break_out is left alone - that segment exists precisely to hand over.
    """
    import re as _re

    others = {lg.upper() for lg in present}
    if len(others) < 2:
        return

    # TEAM NAMES TOO, not just league names.
    #
    # The first version only looked for "WNBA" and "MLB", so a tease naming
    # the CLUBS walked straight through - "now over to the Fever and the
    # Aces" contains no league name at all. That is how a WNBA hand-off
    # survived into an episode after this function was supposedly stopping
    # them.
    by_team = {}
    for lg in present:
        names = set()
        for g in (_material_games or []):
            if (g.get("league") or "").upper() != lg.upper():
                continue
            for key in ("home_nick", "away_nick"):
                nm = (g.get(key) or "").strip().lower()
                if len(nm) >= 4:           # short ones hit ordinary words
                    names.add(nm)
        by_team[lg.upper()] = names

    # "now to the WNBA", "coming up, the NBA", "let's get to some hockey"
    TEASE = _re.compile(
        r"(now (?:to|for)|coming up|next up|let'?s get to|over to|stay (?:tuned|with)"
        r"|after (?:the break|this)|when we come back|later on|we'?ll get to)",
        _re.IGNORECASE)

    for lg, res in by_lg.items():
        for seg in (res or {}).get("segments") or []:
            if (seg.get("league") or "").upper() == "BREAK":
                continue
            if seg.get("kind") in ("break_in", "break_out"):
                continue
            # AROUND THE GROUNDS IS EXEMPT.
            #
            # This strip exists to stop a baseball segment wandering into
            # basketball. But Around the Grounds names five different sports
            # ON PURPOSE - that IS the segment - so running the strip over it
            # would cut every line it has.
            if (seg.get("league") or "").upper() == "ELSEWHERE":
                continue
            text = seg.get("text") or ""
            if not text:
                continue

            kept = []
            for sentence in _re.split(r"(?<=[.!?])\s+", text):
                low = sentence.lower()
                toks = {w.upper() for w in _re.findall(r"\b[A-Za-z]{3,5}\b", sentence)}
                mentions_other = bool((toks & others) - {lg.upper()})
                if not mentions_other:
                    for other_lg, team_names in by_team.items():
                        if other_lg == lg.upper():
                            continue
                        if any(_re.search(r"\b" + _re.escape(t) + r"\b", low)
                               for t in team_names):
                            mentions_other = True
                            break
                if mentions_other and TEASE.search(sentence):
                    print(f"[show] stripped cross-league tease from {lg}: "
                          f"{sentence[:70]!r}", flush=True)
                    continue
                kept.append(sentence)

            if kept and len(kept) != len(_re.split(r"(?<=[.!?])\s+", text)):
                seg["text"] = " ".join(kept).strip()


# The ambient bed behind each kind of distraction.
#
# The written bits have always carried a category - "mower", "baby", "phone" -
# but nothing ever turned that into a sound, so a neighbour with a lawnmower
# was complained about in total silence. The joke was landing without the
# thing it was about.
#
# Several names per category so a new file can be dropped in without touching
# code, and so the same recording is not heard every time. A category with no
# file on disk simply plays dry, exactly as it has been.
AMBIENT_BEDS = {
    "mower": ["static/sfx/lawnmower.mp3", "static/sfx/mower.mp3",
              "static/sfx/lawnmower.wav", "static/audio/lawnmower.mp3"],
    "baby":  ["static/sfx/baby.mp3", "static/sfx/baby-crying.mp3",
              "static/sfx/baby.wav"],
    "traffic": ["static/sfx/traffic.mp3", "static/sfx/traffic.wav",
                "static/sfx/street.mp3"],
    "siren": ["static/sfx/siren.mp3", "static/sfx/sirens.mp3",
              "static/sfx/siren.wav"],
    "dog": ["static/sfx/dog.mp3", "static/sfx/dog-barking.mp3"],
    # phone already has its own ring and hangup handling
    "phone": [],
}


def ambient_bed_for(kind):
    """The first file that exists for this category, or None."""
    import os
    for path in AMBIENT_BEDS.get(kind or "", []):
        if os.path.exists(path):
            return path
    if kind and kind not in ("phone", "") and AMBIENT_BEDS.get(kind):
        print(f"[show] no audio for '{kind}' bit - playing dry. Expected one "
              f"of: {', '.join(AMBIENT_BEDS[kind])}", flush=True)
    return None


def maybe_interruption(segments):
    """
    Insert at most one interruption, in a gap between segments.

    Placed BETWEEN segments rather than inside one, because a bit dropped
    into the middle of a game recap buries the score it was reporting.
    Never first and never last - the show opens and closes on its own terms.
    """
    import random

    # One every episode. The only reason to skip is a show too short to have
    # anywhere sensible to put it.
    if len(segments) < 4:
        return segments

    # Anywhere in the FIRST FOUR MINUTES.
    #
    # Measured in spoken words rather than segment index, because segments
    # vary wildly in length - a 19-word sweep line and a 73-word headline are
    # both "one segment", so counting positions tells you nothing about where
    # you actually are in the episode.
    #
    # Not first, because the show has to establish itself before anything can
    # interrupt it. Otherwise free: the point of a phone bit is that it
    # arrives when nobody expects it, and a fixed position is a position a
    # regular listener learns.
    CUTOFF_WORDS = 4 * SPOKEN_WORDS_PER_MINUTE      # four minutes in
    running = 0
    hi = 1
    for idx, seg in enumerate(segments):
        running += len((seg.get("text") or "").split())
        if running > CUTOFF_WORDS:
            break
        hi = idx + 1
    # max(lo + 1, ...) FORCES hi TO AT LEAST 2, EVEN WITH ONE SEGMENT.
    #
    # With a single segment, len(segments) - 1 is 0, min(hi, 0) is 0, and
    # max(2, 0) is 2 - so the range yields index 1 and segments[1] does
    # not exist. IndexError, whole episode lost.
    #
    # A thin night with one game is exactly when that happens, which is
    # exactly when the show can least afford to fall over.
    #
    # An interruption needs somewhere to go: at least two segments, so it
    # can land between them.
    if len(segments) < 2:
        return segments

    lo = 1
    hi = min(hi, len(segments) - 1)
    if hi <= lo:
        return segments
    spots = [i for i in range(lo, hi)
             if (segments[i].get("league") or "") not in ("BREAK",)
             and (segments[i - 1].get("league") or "") not in ("BREAK",)]
    if not spots:
        return segments

    at = random.choice(spots)

    # Which league is he in the middle of? Most bits work anywhere, but any
    # that NAME a sport - "describing a baseball game to strangers" - are
    # tagged, and dropping one of those into a basketball segment would just
    # be wrong.
    here = (segments[at - 1].get("league") or "").upper()

    def entry(e):
        """
        Normalise to (text, league, sound).

        Most entries are a bare string - anywhere, phone. Some name a sport
        and are tagged to it. Some are not phone calls at all: the baby ones
        need a crying baby underneath, and playing a phone ring over "he's
        up, we're all up" would be nonsense.
        """
        if isinstance(e, tuple):
            return (e + (None, None))[:3] if len(e) < 3 else e
        return (e, None, "phone")

    rows = [entry(e) for e in PHONE_INTERRUPTIONS]
    rows = [(t, lg, snd or "phone") for t, lg, snd in rows]

    usable = [r for r in rows if r[1] is None or r[1].upper() == here]
    if not usable:
        usable = [r for r in rows if r[1] is None]
    if not usable:
        return segments

    text, _lg, sound = random.choice(usable)

    # Build the bit in explicit parts rather than by appending strings, which
    # produced a call that said goodbye twice and another that hung up after
    # announcing it would not answer.
    if sound == "phone":
        low = text.lower()

        # Some scripts REFUSE the call - "not answering that", "let that go
        # to voicemail". Those get noticed but never answered, so no hello
        # and certainly no goodbye.
        declines = any(k in low for k in
                       ("not answering", "voicemail", "not doing this"))

        parts = [random.choice(PICKUP_LINES), text]

        if not declines:
            # Only add a farewell if the script does not already end on one.
            # Checked across the last stretch rather than the exact ending,
            # because several close with "Bye. ... Where was I." and an exact
            # match misses it.
            tail = low[-60:]
            if not any(k in tail for k in
                       ("bye", "goodbye", "hang up", "hanging up")):
                parts.append(random.choice(SIGNOFF_LINES))

        text = " ... ".join(parts)

    # Close it. Some scripts already end on a recovery - "Where was I",
    # "Right." - so a second one would be doubled up.
    if not any(text.rstrip().endswith(e) for e in
               ("Where was I.", "Right.", "It's always me.")):
        text = text.rstrip() + " ... " + random.choice(RETURN_LINES)

    bit = {"text": text, "display_text": text, "reaction": "none",
           "league": "", "interruption": True, "interrupt_sound": sound}

    # The ambient bed, at last.
    #
    # music_bed is the field the assembler already loops and fades under a
    # segment - the ad read uses it. Reusing it means the mower runs under the
    # complaint about the mower, which is the entire joke and has been missing
    # since the bits were written.
    bed = ambient_bed_for(sound)
    if bed:
        bit["music_bed"] = bed
        print(f"[show] {sound} bed: {bed}", flush=True)

    segments.insert(at, bit)
    print(f"[show] interruption inserted at segment {at} ({sound})", flush=True)
    return segments
