"""
The WNBA layout.
================
Deliberately SEPARATE from baseball, sharing no slot definitions and no
selection logic.

WHY IT IS ITS OWN FILE
----------------------
Every cross-league fault on this show came from something shared that should
not have been. A grouping rule written for a fifteen-game baseball slate
collapsed a four-game WNBA night into one segment. A streak list compiled
across all leagues put the Rockies inside the WNBA block. A hand-off written
by the baseball writer announced a league it could not see.

So: no shared slots, no shared thresholds, no shared material. The only thing
the two leagues have in common is Smacky himself.

WHAT MAKES BASKETBALL DIFFERENT
-------------------------------
Baseball's whole vocabulary is meaningless here - no innings, no pitchers, no
runners left on base, no quality starts. A basketball night is decided by
shooting, turnovers and whether the fourth quarter held.

And the slate is SMALL. Four games, not fifteen. Every game can be covered
properly, so there is no sweep - a sweep exists to dispose of games there is
no room for, and that problem does not arise here.
"""

import re


WPM = 115

# Basketball gets more per game because there are so few of them - four games
# at 55 words is under two minutes, which is not a block, it is a mention.
# Quick, deliberately. The WNBA block is a visit, not a second show - and a
# tight two minutes that leaves people wanting more beats four that do not.
WORDS_PER_GAME = 42
MIN_WORDS = 120
MAX_WORDS = 260


def budget_for(game_count: int) -> int:
    return min(MAX_WORDS, max(MIN_WORDS, int(WORDS_PER_GAME * game_count)))


def _facts_text(game):
    return " ".join(game.get("deep_facts") or []).lower()


def _num(pattern, text, default=0):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else default


def read_game(game: dict) -> dict:
    """
    What happened, in basketball terms.

    "one possession" rather than "one run"; cold shooting rather than a
    pitcher getting shelled. None of baseball's tests apply.
    """
    text = _facts_text(game)
    margin = game.get("margin") or 0
    periods = game.get("periods") or 4

    return {
        "game": game,
        "margin": margin,
        "one_possession": margin <= 3,
        "overtime": periods > 4,
        "blowout": margin >= 20,
        "at_home": bool(game.get("loser_at_home")),
        "cold": _num(r"shot (\d+) percent as a team", text),
        "three_pct": _num(r"(\d+) percent from three", text),
        "turnovers": _num(r"(\d+) turnovers", text),
        "star_wasted": "and it still was" in text,
        "has_detail": bool(game.get("deep_facts")),
    }


def story_score(r: dict, widest: bool = False) -> int:
    """Basketball's own hierarchy. Tension first, then collapse."""
    s = 0
    if r["overtime"]:        s += 5
    if r["one_possession"]:  s += 4
    if widest:               s += 3
    if r["blowout"]:         s += 3
    if r["star_wasted"]:     s += 3      # 30 points in a loss is its own story
    if r["turnovers"] >= 18: s += 2
    if r["cold"] and r["cold"] <= 38: s += 2
    if r["at_home"]:         s += 1
    return s


# A new award name every episode. The bit is the invention, not the trophy.
#
# Deliberately NOT named after Clark. An award named for an active player is
# a hostage to her career - an injury, a trade or a bad season makes the name
# awkward nightly, and any controversy would force a rebrand of a signature
# segment under pressure. She is the STANDARD, not the trophy.
AWARD_TITLES = [
    "Walking Bucket Award",
    "Bucket Getter of the Night",
    "Queen of the Night Award",
    "Certified Bucket Award",
    "Problem of the Night Award",
    "Bucket Boss Award",
    "Ice Queen Award",
    "Cooker of the Night Award",
    "Heat Check Award",
    "Human Highlight Award",
    "Main Character Award",
    "Smack Queen Award",
    "Hoop Boss Award",
    "Bucket Factory Award",
    "Spotlight Award",
    "Smoke Dealer Award",
    "Built Different Award",
    "Too Easy Award",
    "Good Luck Guarding That Award",
    "Video Game Numbers Award",
    "She Was Different Award",
    "Couldn't Miss Award",
    "Grill Master Award",
    "Crown of the Night",
]


def pick_award_title(day=None):
    """
    Tonight's award name.

    Seeded on the DATE rather than random, so two runs of the same episode
    produce the same title - a re-render after a failure should not quietly
    rename the award - while consecutive nights never repeat.
    """
    import datetime
    import random as _r
    d = day or datetime.date.today()

    # A CYCLE, not a daily shuffle.
    #
    # Reshuffling every day and indexing into the result gave "Smack Queen"
    # twice inside five days - random picks repeat, which is exactly what a
    # nightly bit cannot do.
    #
    # The order is shuffled ONCE from a fixed seed, then walked in sequence.
    # Every title is used before any repeats, and the order is scrambled
    # rather than alphabetical so it does not sound like a list being read
    # down.
    order = list(AWARD_TITLES)
    _r.Random(20260803).shuffle(order)
    return order[d.toordinal() % len(order)]


def build(games: list, log=print, streaks=None, league="WNBA") -> dict:
    """
    Assign every game to a slot. No sweep - the slate is small enough that
    everything gets covered properly.
    """
    if not games:
        return {"slots": [], "budget": 0}

    reads = [read_game(g) for g in games]
    widest = max(r["margin"] for r in reads)
    for r in reads:
        r["score"] = story_score(r, widest=(r["margin"] == widest and widest >= 15))

    taken = set()

    def claim(pool, why):
        cand = [r for r in pool if id(r["game"]) not in taken]
        if not cand:
            return None
        pick = max(cand, key=lambda r: r["score"])
        taken.add(id(pick["game"]))
        pick["why"] = why
        return pick

    headline = (claim([r for r in reads if r["overtime"] or r["one_possession"]],
                      "closest game")
                or claim(reads, "best story"))
    beating = claim([r for r in reads if r["margin"] >= 15], "widest margin")
    rest = [r for r in reads if id(r["game"]) not in taken]

    total = budget_for(len(games))
    opening = max(30, int(total * 0.12))
    award_w = max(38, int(total * 0.13))
    story_w = max(40, int(total * 0.15))
    streak_w = 25 if streaks else 0

    used = opening + award_w + streak_w + (story_w if headline else 0) \
        + (story_w if beating else 0)
    per_rest = max(20, (total - used) // len(rest)) if rest else 0

    slots = [{
        "slot": "opening", "words": opening, "games": [],
        "brief": "The shape of the night. How many games, how many were "
                 "close, the widest margin. No scores yet."}]

    if headline:
        slots.append({
            "slot": "headline", "words": story_w, "games": [headline],
            "brief": "The game of the night. Score, whether it went to "
                     "overtime, who carried it, and ONE reason the other side "
                     "lost - shooting, turnovers, or a fourth quarter that "
                     "got away."})

    # No separate blowout slot. Baseball has fifteen games and can afford one;
    # four games cannot carry five slots without each becoming a fragment.
    # The heaviest defeat lands in the rest, where it still gets its roast.

    # THE PLAYER AWARD - a different name every episode.
    #
    # Baseball's awards are fixed, because they are the show's signature and a
    # signature has to be recognisable. This one is the opposite: the joke IS
    # that Smacky invents a new title for her every night, so the segment
    # never sounds like yesterday's.
    #
    # Chosen in code from a pool, because "vary this" asked of the model has
    # been ignored three times on this project.
    title = pick_award_title()
    slots.append({
        "slot": "player_award", "words": award_w, "games": [],
        "brief": f"SMACKAGRAM'S {title.upper()} - tonight's name for the best "
                 "individual performance. Smacky invents a new title every "
                 "episode and this is tonight's; use it exactly as written "
                 "and do not explain the joke.\n"
                 f"    OPEN WITH: \"Smackagram's {title} goes to...\" then "
                 "her name and her line, then the roast - aimed at the "
                 "DEFENCE that allowed it. She is being congratulated; they "
                 "are the joke.\n"
                 "    THE CAITLIN STANDARD: Clark is the bar Smacky measures "
                 "against - \"would this have made Caitlin nod?\" He is "
                 "STINGY with it and most nights nobody clears it, but when "
                 "somebody genuinely does he hands it over without "
                 "qualification. A standard nobody ever meets is not a "
                 "standard, it is a way of dismissing the league.\n"
                 "    Mention her only when the performance earns it. Every "
                 "night is a tic, not a bit."})

    if streaks:
        rows = "; ".join(f"{x['team']} have lost {x['losses']} straight"
                         for x in streaks[:3])
        slots.append({
            "slot": "winners_and_whiners", "words": streak_w, "games": [],
            # The league is named out loud because every block has one of
            # these - a real show introduced "Winners & Whiners" twice and
            # it sounded like it had forgotten the first.
            "brief": f"THE {league.upper()} WINNERS & WHINERS - fifteen "
                     "seconds.\n"
                     f"    SAY THE LEAGUE IN THE TITLE: \"the "
                     f"{league.upper()} Winners and Whiners\".\n"
                     f"    {rows}.\n"
                     "    Rattle them off and move on. Do not explain a "
                     "losing run."})

    if rest:
        slots.append({
            "slot": "the_rest", "words": per_rest * len(rest), "games": rest,
            "brief": f"The other {len(rest)} game(s), about {per_rest} words "
                     "each. Score, one statistic, one line. These get REAL "
                     "coverage rather than a scoreline - the slate is small "
                     "enough that every game can be a segment."})

    log(f"wnba layout: {total}w across {len(slots)} slots")
    return {"slots": slots, "budget": total, "reads": reads}


FORBIDDEN = """NEVER SAY THESE. There is no play-by-play in the feed:
  - a buzzer-beater, or how the final basket came about
  - a specific run ("they went on a 12-0 run")
  - who hit the shot that decided it
  - that a turnover or a foul cost them the game
  - an injury, an ejection, or anything about officiating
  - a comeback from any specific deficit

SAFE, because the box score supports them:
  - the final score and the margin
  - team shooting percentage, three-point percentage
  - turnovers
  - a player's points, and whether she was a minus in a loss
  - who led the winning side
  - they lost at home, or in front of a stated attendance
  - a losing streak of N"""


def prompt_block(games: list, log=print, streaks=None, league="WNBA") -> str:
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
            f"ONE SEGMENT PER SLOT. {n} slots means {n} segments - a real "
            "episode wrote three for five and the block felt thin.\n\n"
            "THE WORD COUNTS ARE THE BUDGET. A real episode came in 60% over "
            "and got trimmed afterwards, and trimming cuts from the END.\n\n"
            "Every game appears in exactly ONE slot. Write them in this "
            "order. Do not add, merge, reorder or skip a slot, and do not "
            "say the slot names aloud.\n\n"
            + "\n".join(rows) + "\n" + FORBIDDEN + "\n\n")
