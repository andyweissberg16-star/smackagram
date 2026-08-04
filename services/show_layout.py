"""
The baseball layout.
====================
Which games get talked about, in which slot, and how many words each gets.

WHY THIS EXISTS
---------------
The writer used to be handed the whole slate and a word budget and left to
work it out. That produced two failures every night: the best game of the
evening got buried in a group with two forgettable ones, and the shape of the
show was different every day for no reason a listener could feel.

Worse, structure decided by the model is structure that cannot be relied on.
Three separate prompt-level rules have been ignored on this project. Slots
decided in CODE cannot be.

THE SHAPE
---------
Three real stories, one player section, one fast sweep, wrapped by a short
opening. Not six equal blocks - a night has a headline and the show should
know what it is.

WHAT SMACKY MUST NEVER SAY
--------------------------
There is no play-by-play in the feed. Walk-offs, blown saves, ninth-inning
rallies, who drove in the winning run, whether an error decided anything -
none of that is knowable, and inventing it turns a comedy bit into a false
statement about a named professional. The eligible facts are listed per slot
and nothing else is allowed in.
"""

import re


# Spoken words per minute, matching the rest of the show.
WPM = 115

# Words per game, and the ceiling.
#
# The budget scales with the slate: a four-game Monday should not be stretched
# to fill the same air as a fifteen-game Saturday. There is a floor so a tiny
# slate still gets a real show, and a cap so a huge one does not run long.
WORDS_PER_GAME = 37
MIN_WORDS = 150
MAX_WORDS = 600


def budget_for(game_count: int) -> int:
    """The baseball block's word budget for a slate this size."""
    return min(MAX_WORDS, max(MIN_WORDS, int(WORDS_PER_GAME * game_count)))


# ---------------------------------------------------------------------------
# Reading a game
# ---------------------------------------------------------------------------

def _facts_text(game):
    return " ".join(game.get("deep_facts") or []).lower()


def _num(pattern, text, default=0):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else default


def read_game(game: dict) -> dict:
    """
    Everything the layout needs to know, pulled out of the box score once.

    Derived rather than assumed. "one_run" is the margin, not a guess about
    how it finished; "extras" is the innings count, not a story about a
    dramatic tenth.
    """
    text = _facts_text(game)
    loser_runs = min(game.get("away_score") or 0, game.get("home_score") or 0)
    margin = game.get("margin") or 0
    periods = game.get("periods") or 9

    return {
        "game": game,
        "margin": margin,
        "loser_runs": loser_runs,
        "one_run": margin == 1,
        "extras": periods > 9,
        "shutout": loser_runs == 0,
        "at_home": bool(game.get("loser_at_home")),
        # Box score, absent if the deep fetch failed for this game.
        "stranded": _num(r"left (\d+) runners", text),
        "team_hits": _num(r"managed (\d+) hits? all night", text),
        "strikeouts": _num(r"struck out (\d+) times", text),
        "errors": _num(r"(\d+) errors in the field", text),
        "hitless_top": _num(r"(\d+) of the top \d+ hitters were held hitless", text),
        "starter_short": bool(re.search(r"went \d\.?\d? innings", text)),
        "quality_start": "quality start" in text,
        "big_hitter": bool(re.search(r"went [3-9] for", text)),
        "has_detail": bool(game.get("deep_facts")),
    }


# ---------------------------------------------------------------------------
# Which games are worth talking about
# ---------------------------------------------------------------------------

# What each thing is worth. Tuned for BASEBALL, where a 162-game season means
# a single result rarely matters on its own - so the score reflects how
# INTERESTING the game was, not how significant.
SCORES = {
    "extras": 4,
    "biggest_margin": 4,
    "one_run": 3,
    "shutout": 3,
    "starter_short": 3,
    "big_hitter": 3,
    "stranded_10": 2,
    "struck_out_12": 2,
    "errors_2": 2,
    "quality_start_wasted": 2,
    "at_home": 1,
}


def story_score(r: dict, biggest_margin: bool = False) -> int:
    """How much of a story this game is."""
    s = 0
    if r["extras"]:            s += SCORES["extras"]
    if biggest_margin:         s += SCORES["biggest_margin"]
    if r["one_run"]:           s += SCORES["one_run"]
    if r["shutout"]:           s += SCORES["shutout"]
    if r["starter_short"]:     s += SCORES["starter_short"]
    if r["big_hitter"]:        s += SCORES["big_hitter"]
    if r["stranded"] >= 10:    s += SCORES["stranded_10"]
    if r["strikeouts"] >= 12:  s += SCORES["struck_out_12"]
    if r["errors"] >= 2:       s += SCORES["errors_2"]
    if r["quality_start"]:     s += SCORES["quality_start_wasted"]
    if r["at_home"]:           s += SCORES["at_home"]
    return s


# ---------------------------------------------------------------------------
# Player of the night, and the other one
# ---------------------------------------------------------------------------

def _hitters(detail, side):
    """Every hitter on one side of one game, with their line."""
    out = []
    box = (detail.get("boxscore") or {})
    winner = ((detail.get("winner") or {}).get("team") or "").lower()
    loser = ((detail.get("loser") or {}).get("team") or "").lower()
    want = winner if side == "winning" else loser

    for block in (box.get("players") or []):
        nick = ((block.get("team") or {}).get("name")
                or (block.get("team") or {}).get("shortDisplayName") or "")
        if nick.lower() != want:
            continue
        for group in (block.get("statistics") or []):
            keys = [k.upper() for k in (group.get("keys") or [])]
            if "H" not in keys or "AB" not in keys:
                continue
            for ath in (group.get("athletes") or []):
                stats = ath.get("stats") or []
                row = dict(zip(keys, stats))
                name = ((ath.get("athlete") or {}).get("displayName") or "")
                try:
                    hits = int(row.get("H", 0))
                    abs_ = int(row.get("AB", 0))
                except (TypeError, ValueError):
                    continue
                if not name or abs_ == 0:
                    continue
                out.append({
                    "name": name, "team": nick, "hits": hits, "at_bats": abs_,
                    "rbi": _int(row.get("RBI")), "hr": _int(row.get("HR")),
                    "runs": _int(row.get("R")),
                    "season_avg": row.get("AVG"),
                    "order": len(out) + 1,   # batting order position
                })
    return out


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _avg(v):
    try:
        return float(str(v).lstrip("0") or 0)
    except (TypeError, ValueError):
        return 0.0


# How an award is handed over. Varied HERE rather than asked for in the
# prompt, because a prompt-level "vary this" has been ignored three times on
# this project. Same reason the caps live in code.
AWARD_VERBS = [
    "goes to", "is awarded to", "belongs to", "has to go to",
    "is going straight to", "lands on the desk of", "gets handed to",
    "we are giving to", "there is only one name for tonight, and it is",
    "is not even close tonight, it is",
]


def award_line(title, who, rng=None):
    """One presentation line, never the same two nights running by chance."""
    import random as _r
    verb = (rng or _r).choice(AWARD_VERBS)
    return f"Smackagram's {title} {verb} {who}"


def _pitchers(detail, side):
    """Pitchers on one side of one game."""
    out = []
    box = detail.get("boxscore") or {}
    winner = ((detail.get("winner") or {}).get("team") or "").lower()
    loser = ((detail.get("loser") or {}).get("team") or "").lower()
    want = winner if side == "winning" else loser

    for block in (box.get("players") or []):
        nick = ((block.get("team") or {}).get("name")
                or (block.get("team") or {}).get("shortDisplayName") or "")
        if nick.lower() != want:
            continue
        for group in (block.get("statistics") or []):
            keys = [k.upper() for k in (group.get("keys") or [])]
            if "IP" not in keys:
                continue
            for i, ath in enumerate(group.get("athletes") or []):
                row = dict(zip(keys, ath.get("stats") or []))
                name = ((ath.get("athlete") or {}).get("displayName") or "")
                if not name:
                    continue
                try:
                    ip = float(row.get("IP", 0))
                except (TypeError, ValueError):
                    continue
                out.append({
                    "name": name, "team": nick, "starter": i == 0,
                    "innings": row.get("IP"), "innings_num": ip,
                    "earned": _int(row.get("ER")),
                    "strikeouts": _int(row.get("K") or row.get("SO")),
                    "hits": _int(row.get("H")),
                    "season_era": row.get("ERA"),
                })
    return out


def pick_cooker(games: list):
    """
    The pitcher who did the cooking.

    Separated from the Smack Ball on purpose. Best hitter and most dominant
    player are USUALLY THE SAME MAN - a 4-for-4 with two home runs is the
    domination - so two awards would go to one player and the second would
    read as padding. Split by discipline and they are always different
    people, and the pitching half of the box score finally gets used: a
    seven-inning shutout currently earns no recognition at all while the man
    who took a bad pitcher deep gets everything.
    """
    best = None
    for g in games:
        d = g.get("_detail") or {}
        if not d:
            continue
        for p in _pitchers(d, "winning"):
            if not p["starter"] or p["innings_num"] < 5:
                continue
            score = (p["strikeouts"] * 2
                     + int(p["innings_num"]) * 2
                     - p["earned"] * 4)
            if p["earned"] == 0:
                score += 6                  # nothing at all is the story
            if p["strikeouts"] >= 10:
                score += 4
            if best is None or score > best["score"]:
                best = {**p, "score": score, "game": g,
                        "against": g.get("loser")}
    return best


def pick_players(games: list) -> dict:
    """
    The best and worst individual nights, across every game.

    PLAYER OF THE NIGHT is chosen on production, then used to roast the
    PITCHING STAFF that allowed it - which is the joke. The hitter is
    congratulated; the team that let him do it is not.

    THE OTHER ONE is the worst individual night, and there are three ways to
    earn it, taken in order of how bad they are:
      1. a pitcher who was genuinely shelled
      2. a fielder with multiple errors
      3. a top-of-the-order hitter who went 0-for-4 or worse

    Both are about the PERFORMANCE. Never the person.
    """
    best = None
    worst = None

    for g in games:
        d = g.get("_detail") or {}
        if not d:
            continue

        # Best: production first, with the season average as the twist -
        # a man hitting .190 who picks tonight to remember how is far
        # funnier than a star doing what stars do.
        for h in _hitters(d, "winning"):
            score = h["hits"] * 2 + h["hr"] * 3 + h["rbi"]
            if h["hits"] >= 3 or h["hr"] >= 2:
                score += 2
            avg = _avg(h.get("season_avg"))
            if avg and avg < 0.240 and h["hits"] >= 2:
                score += 3          # the contrast IS the joke
            if best is None or score > best["score"]:
                best = {**h, "score": score, "game": g,
                        "against": g.get("loser"),
                        "surprise": bool(avg and avg < 0.240)}

        # Worst, in order of severity.
        text = _facts_text(g)
        er = _num(r"gave up (\d+) earned", text) or _num(r"and gave up (\d+)", text)
        innings = re.search(r"went (\d+\.?\d?) innings", text)
        if er >= 5:
            cand = {"kind": "pitcher", "score": er * 3,
                    "detail": f"gave up {er} earned"
                              + (f" in {innings.group(1)} innings" if innings else ""),
                    "team": g.get("loser"), "game": g}
            if worst is None or cand["score"] > worst["score"]:
                worst = cand

        errs = _num(r"(\d+) errors in the field", text)
        if errs >= 2:
            cand = {"kind": "fielding", "score": errs * 4,
                    "detail": f"{errs} errors in the field",
                    "team": g.get("loser"), "game": g}
            if worst is None or cand["score"] > worst["score"]:
                worst = cand

        for h in _hitters(d, "losing")[:5]:      # top five in the order only
            if h["hits"] == 0 and h["at_bats"] >= 4:
                cand = {"kind": "hitter", "score": h["at_bats"] * 2,
                        "name": h["name"], "team": h["team"],
                        "detail": f"0 for {h['at_bats']} batting "
                                  f"{h['order']} in the order",
                        "game": g}
                if worst is None or cand["score"] > worst["score"]:
                    worst = cand

    return {"best": best, "worst": worst}


# ---------------------------------------------------------------------------
# The layout
# ---------------------------------------------------------------------------

def build(games: list, log=print, streaks=None, league="MLB") -> dict:
    """
    Assign every game to exactly one slot, and hand each slot its words.

    A game can qualify for several labels. It appears ONCE - hearing the same
    result twice in an episode is the fault that made this necessary.
    """
    if not games:
        return {"slots": [], "budget": 0}

    reads = [read_game(g) for g in games]
    widest = max(r["margin"] for r in reads)

    for r in reads:
        r["score"] = story_score(r, biggest_margin=(r["margin"] == widest
                                                    and widest >= 5))

    taken = set()

    def claim(candidates, why):
        """Take the best unclaimed game matching a filter."""
        pool = [r for r in candidates if id(r["game"]) not in taken]
        if not pool:
            return None
        pick = max(pool, key=lambda r: r["score"])
        taken.add(id(pick["game"]))
        pick["why"] = why
        return pick

    # THE BLOWOUT goes first, and is reserved.
    #
    # Claimed before the headline because it is usually also the highest
    # scoring game - and if the headline takes it, the show ends up with two
    # slots fighting over one result and a blowout slot filled by something
    # that was not a blowout.
    blowout = claim([r for r in reads if r["margin"] >= 5], "biggest margin")

    # THE HEADLINE - the most interesting game left.
    #
    # Extra innings and one-run games first, because tension is the thing a
    # scoreline cannot convey and a recap most often loses.
    headline = (claim([r for r in reads if r["extras"] or r["one_run"]],
                      "closest game")
                or claim(reads, "best story left"))

    # THE CLOSE ONE.
    #
    # Falls back to the most FRUSTRATING loss when no genuine one-run game is
    # left, because some nights simply do not have one - and a slot that can
    # be empty is a slot that breaks the show. Stranded runners and a wasted
    # quality start define frustration perfectly well without a close margin.
    close = (claim([r for r in reads if r["one_run"] or r["extras"]],
                   "one-run game")
             or claim([r for r in reads
                       if r["stranded"] >= 8 or r["quality_start"]],
                      "most frustrating loss")
             or claim(reads, "next best"))

    rest = [r for r in reads if id(r["game"]) not in taken]

    # WORDS.
    #
    # Proportions first, then the sweep takes whatever is left - so the three
    # stories keep their shape on a light night and the sweep absorbs the
    # variation instead of every slot shrinking together.
    total = budget_for(len(games))

    # The SWEEP is reserved first, not left over.
    #
    # Taking fixed floors off the top and giving the sweep the remainder gave
    # it NOTHING on a six-game night - the floors alone exceeded the budget
    # and three real games were left with no words to be covered in. Whatever
    # is not featured still has to be reported.
    #
    # So: reserve enough for the games in the sweep, then share what is left
    # among the stories, which shrink gracefully. A short night means shorter
    # stories, not missing games.
    n_rest = max(0, len(games) - (1 if headline else 0)
                    - (1 if blowout else 0)
                    - (1 if (close and close is not headline) else 0))
    sweep = min(int(total * 0.42), n_rest * 22) if n_rest else 0

    body = total - sweep
    n_stories = ((1 if headline else 0) + (1 if blowout else 0)
                 + (1 if (close and close is not headline) else 0))
    # Opening and the player section are a fixed proportion of the body; the
    # stories divide the rest.
    opening = max(30, int(body * 0.14))
    # The awards are the show's signature segments and get real room.
    #
    # At 0.18 they came out at forty words each, which is a stat read aloud
    # rather than a presentation - and a three-beat award needs about thirty
    # seconds, so roughly 55 words. Raised to 0.30 of the body and floored
    # high enough that a light night still gets a proper ceremony.
    # Three awards need a quarter of the block. At 0.30 each came out at
    # 38 words - twenty seconds for a wind-up, a stat line and a joke, which
    # is a stat read aloud rather than a presentation. 0.42 gives each about
    # 45, and the sweep absorbs the difference by shortening its lines rather
    # than dropping games.
    player_w = max(120, int(body * 0.42))
    story_pool = max(0, body - opening - player_w)
    story_w = max(30, story_pool // n_stories) if n_stories else 0

    slots = [
        {"slot": "opening", "words": opening, "games": [],
         "brief": "The shape of the night before a single score. How many "
                  "games, how many one-run finishes, how many went to extras, "
                  "the widest margin, any streak of three or more. Tease the "
                  "biggest collapse without naming the score."},
    ]

    if headline:
        slots.append({"slot": "headline", "words": story_w, "games": [headline],
                      "brief": "The game of the night. Score, whether it went "
                               "to extras, the losing pitcher, who did the "
                               "damage, and ONE reason they lost."})
    if blowout:
        slots.append({"slot": "blowout", "words": story_w, "games": [blowout],
                      "brief": "The heaviest defeat. Go hardest here. Score, "
                               "margin, whether it was at home, the starter's "
                               "line, hits, strikeouts, errors, the record "
                               "after it."})
    if close and close is not headline:
        slots.append({"slot": "close", "words": story_w, "games": [close],
                      "brief": "The painful one. LOWER volume, more tension. "
                               "Stranded runners, strikeouts, whether a "
                               "quality start was wasted. No blowout jokes "
                               "here - it is a different kind of loss."})

    # TWO player slots, not one.
    #
    # The best night and the worst night are opposite jokes and do not belong
    # in the same breath. Split, they also let the show change gear - a
    # celebration then a demolition.
    pl = pick_players([r["game"] for r in reads])

    # SECOND ROUTE TO EVERY AWARD.
    #
    # The awards must be there EVERY DAY. A show that has them on Tuesday
    # and not Wednesday has no signature - and this morning they vanished
    # entirely, because the pickers read a raw box score that
    # fetch_game_detail was not keeping. Nobody would have known why.
    #
    # So there are now two routes to each one. The box score is the good
    # route, with real numbers. These are the fallback, built from data
    # fetch_game_detail ALREADY extracts and has extracted all along:
    # losing_pitcher, pitchers, bad_nights.
    #
    # A named player with a thinner line beats no award at all.
    def _fallback_players(gs):
        best = worst = None
        cook = None
        for g in gs:
            d = g.get("_detail") or {}
            # Worst: the pitcher who wore the defeat.
            lp = d.get("losing_pitcher") or {}
            if lp.get("name") and lp.get("earned") is not None:
                score = (lp.get("earned") or 0)
                if worst is None or score > worst.get("_score", -1):
                    worst = {"name": lp["name"],
                             "team": (d.get("loser") or {}).get("team"),
                             "detail": f"gave up {lp['earned']} earned in "
                                       f"{lp.get('innings') or 'his outing'}",
                             "_score": score}
            # Cooker: the winning starter.
            pit = (d.get("pitchers") or {}).get("winning_side") or []
            for p in pit:
                if not p.get("starter") or not p.get("name"):
                    continue
                sc = (p.get("strikeouts") or 0) * 2 - (p.get("earned") or 0) * 3
                if cook is None or sc > cook.get("_score", -99):
                    cook = {**p, "_score": sc, "game": g,
                            "against": g.get("loser"),
                            "team": (d.get("winner") or {}).get("team")}
            # Best: nothing in the extracted data names a hitter, so the
            # Smack Ball has no fallback. Flagged rather than faked - an
            # award given to nobody is worse than one that did not run.
        return best, cook, worst

    # THE THREE AWARDS - the podium.
    #
    # Every one is branded: "Smackagram's [title] goes to..." That puts the
    # product name in the show nightly without it being an advert.
    #
    # The presentation VERB is varied here in code, not requested in the
    # prompt. A prompt-level "vary this" has been ignored three times on this
    # project; the same lesson as the caps.
    _gs = [r["game"] for r in reads]
    pl = pick_players(_gs)
    cooker = pick_cooker(_gs)

    # If the good route found nobody, try the other one before giving up.
    if not (pl.get("best") and pl.get("worst") and cooker):
        _fb, _fc, _fw = _fallback_players(_gs)
        if not pl.get("worst") and _fw:
            pl["worst"] = _fw
            log("clown show: box score empty, used the losing pitcher")
        if not cooker and _fc:
            cooker = _fc
            log("certified cooker: box score empty, used the winning starter")
        if not pl.get("best"):
            # No hitter data exists outside the box score, so this one
            # genuinely cannot run. Say so loudly rather than quietly
            # producing an eight-slot show and leaving it a mystery.
            log("SMACK BALL SKIPPED - no hitter data. Check that "
                "fetch_game_detail is returning a boxscore.")
    award_w = max(38, int(player_w * 0.34))

    if pl.get("best"):
        b = pl["best"]
        line = f"went {b['hits']} for {b['at_bats']}"
        if b.get("hr"):
            line += f" with {b['hr']} home run" + ("s" if b["hr"] > 1 else "")
        if b.get("rbi"):
            line += f", {b['rbi']} driven in"
        if b.get("season_avg"):
            line += f", hitting {b['season_avg']} on the season"
        slots.append({
            "slot": "smack_ball", "words": award_w, "games": [], "player": b,
            "brief": "SMACKAGRAM'S SMACK BALL OF THE NIGHT AWARD - the best "
                     "night with a bat.\n"
                     f"    OPEN WITH: \"{award_line('Smack Ball of the Night Award', b['name'])}\"\n"
                     f"    WHY: {b['team']}, {line}. He did it to "
                     f"{b.get('against') or 'them'}.\n"
                     "    Then the roast - at the PITCHING STAFF that let him "
                     "do it, not at him. He is the one being congratulated."
                     + (" His season average makes tonight look absurd, and "
                        "that contrast is the line."
                        if b.get("surprise") else "")})

    if cooker:
        c = cooker
        line = f"went {c['innings']} innings"
        if c.get("strikeouts"):
            line += f", {c['strikeouts']} strikeouts"
        line += (", nothing earned" if c["earned"] == 0
                 else f", {c['earned']} earned")
        if c.get("season_era"):
            line += f", {c['season_era']} ERA on the season"
        slots.append({
            "slot": "certified_cooker", "words": award_w, "games": [],
            "player": c,
            "brief": "SMACKAGRAM'S CERTIFIED COOKER OF THE NIGHT AWARD - the "
                     "pitcher who did the cooking rather than getting cooked.\n"
                     f"    OPEN WITH: \"{award_line('Certified Cooker of the Night Award', c['name'])}\"\n"
                     f"    WHY: {c['team']}, {line}, against "
                     f"{c.get('against') or 'them'}.\n"
                     "    Then the roast - at the LINEUP that could not touch "
                     "him. He is being congratulated; they are the joke."})

    if pl.get("worst"):
        w = pl["worst"]
        who = w.get("name") or f"the {w.get('team')} staff"
        slots.append({
            "slot": "clown_show", "words": award_w, "games": [], "player": w,
            "brief": "SMACKAGRAM'S CLOWN SHOW OF THE NIGHT AWARD - the one "
                     "nobody wants.\n"
                     f"    OPEN WITH: \"{award_line('Clown Show of the Night Award', who)}\"\n"
                     f"    WHY: {w['detail']}. One short reason, no more.\n"
                     "    Then the roast joke, and STOP. Do not explain it "
                     "twice or add a second example.\n"
                     "    Roast the PERFORMANCE only - not his career, not "
                     "his future, not his worth. One bad night is one bad "
                     "night."})

    if not pl.get("best") and not pl.get("worst"):
        slots.append({"slot": "players", "words": player_w, "games": [],
                      "brief": "One hero, one hard-luck story from the games "
                               "above. Roast the performance, never the "
                               "person."})
    # WINNERS & WHINERS - the streaks, and nothing else.
    #
    # Fifteen seconds. Deliberately the shortest slot in the show: a streak is
    # a one-line fact, and stretching it means explaining a losing run, which
    # explains the joke away. Read them and move on.
    #
    # It has its own slot at last. Folded into whatever segment the writer
    # fancied, a baseball streak once ended up inside the WNBA block.
    if streaks:
        rows = "; ".join(f"{x['team']} have lost {x['losses']} straight"
                         for x in streaks[:3])
        slots.append({
            "slot": "winners_and_whiners", "words": 29, "games": [],
            # NAME THE LEAGUE OUT LOUD.
            #
            # Every league block carries its own streak slot, so a real show
            # introduced "Winners & Whiners" twice - once in baseball, again
            # when the WNBA started. Different streaks, same segment name,
            # and it sounded like the show had forgotten it already did it.
            #
            # Saying "the MLB Winners and Whiners" makes the second one a
            # different segment rather than a repeat, and a listener knows
            # instantly which league they are hearing about.
            "brief": f"THE {league.upper()} WINNERS & WHINERS - fifteen "
                     "seconds, no more.\n"
                     f"    SAY THE LEAGUE IN THE TITLE: \"the "
                     f"{league.upper()} Winners and Whiners\". Every league "
                     "has its own, so the name is what tells a listener "
                     "which one this is.\n"
                     f"    {rows}.\n"
                     "    Rattle them off. One line each at most, one shared "
                     "joke at the end if there is room. Do NOT explain a "
                     "losing run - the number is the joke and explaining it "
                     "kills it."})

    if rest:
        slots.append({"slot": "sweep", "words": sweep, "games": rest,
                          "brief": f"Every remaining game, {len(rest)} of them, "
                                   f"about {max(12, sweep // max(1, len(rest)))} "
                                   "words each. Winner, loser, score, ONE "
                                   "statistic, one short line. Do not force a joke "
                                   "where the box score gives you nothing."})

    log(f"layout: {total}w across {len(slots)} slots, "
        f"{len(rest)} games in the sweep")
    return {"slots": slots, "budget": total, "reads": reads}


# ---------------------------------------------------------------------------
# What may and may not be said
# ---------------------------------------------------------------------------

FORBIDDEN = """NEVER SAY THESE. The feed has no play-by-play, so none of it is
knowable, and inventing it makes a false statement about a named professional:
  - a walk-off, or anything about how the final run scored
  - a blown save, a closer melting down, a bullpen collapse
  - a ninth-inning rally or a comeback from any deficit
  - who drove in the winning run
  - that an error or a decision cost them the game
  - a manager leaving a pitcher in too long
  - benches clearing, ejections, injuries
  - anything about a specific pitch or at-bat you were not given

SAFE, because the box score supports them:
  - they wasted a quality start
  - they stranded N runners
  - their starter went N innings and gave up N
  - they were held to N hits
  - N of the top order went hitless
  - they lost at home
  - they lost by one, or it went to extra innings
  - they are on a losing streak of N"""


def prompt_block(games: list, log=print, streaks=None,
                 league="MLB") -> str:
    """The whole running order, ready to drop into the writer's prompt."""
    lay = build(games, log=log, streaks=streaks, league=league)
    rows = []
    for sl in lay["slots"]:
        names = "; ".join(
            f"{r['game'].get('winner')} beat {r['game'].get('loser')} "
            f"{max(r['game'].get('home_score', 0), r['game'].get('away_score', 0))}-"
            f"{min(r['game'].get('home_score', 0), r['game'].get('away_score', 0))}"
            for r in sl["games"])
        rows.append(f"  [{sl['slot'].upper()}] about {sl['words']} words\n"
                    f"    {sl['brief']}\n"
                    + (f"    THE GAME: {names}\n" if names else ""))

    total = sum(sl["words"] for sl in lay["slots"])
    n = len(lay["slots"])
    return (f"YOUR RUNNING ORDER - {n} SEGMENTS, ABOUT {total} WORDS IN "
            "TOTAL.\n\n"
            "ONE SEGMENT PER SLOT. Not five segments covering seven slots - "
            f"{n} slots means {n} segments. A real episode merged two of "
            "these and the show lost a beat nobody could point at.\n\n"
            "THE WORD COUNTS ARE THE BUDGET, not a suggestion. A real "
            "episode came in 68% over and had to be trimmed after the fact, "
            "which cuts from the END - so the last segment written is the "
            "one that disappears.\n\n"
            "Every game appears in exactly ONE slot. Write them in this "
            "order. Do not add, merge, reorder or skip a slot, and do not "
            "announce the slot names out loud - they are structure, not "
            "headings.\n\n"
            + "\n".join(rows) + "\n" + FORBIDDEN + "\n\n")


