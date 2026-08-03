"""
Smacky's voice, shared by every generator.
==========================================
Smackagram, Locked & Loaded, the Daily Smack and Smackcast all pull from
here, so the character is the same everywhere. A different voice on each
page is how a character stops being a character.

WHY THIS IS DATA AND NOT A PROMPT STRING
----------------------------------------
Because the caps have to be enforced in code.

"Do not repeat the same catchphrase" and "use these sparingly" are exactly
the instructions that have been ignored twice on this project - once when a
twice-per-episode cap came out four times because the per-league writers each
thought they had their own budget. A model asked to ration itself will not.

So: this module PICKS the lines, tracks what has been used, and hands the
generator a fixed set with no room to reach for more.

WHY SITUATIONS AND NOT CATEGORIES
---------------------------------
The banks arrive sorted by what Smacky says. The generator needs them sorted
by WHEN he says it. A home-run line during a shutout is the single worst
thing an announcer can do, and it is only avoidable if eligibility is decided
before the model sees anything.
"""

import json
import os
import random

_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "smacky")

_cache = {}


def _load(name):
    if name not in _cache:
        with open(os.path.join(_DIR, name), encoding="utf-8") as fh:
            _cache[name] = json.load(fh)
    return _cache[name]


# ---------------------------------------------------------------------------
# Which situation is this?
# ---------------------------------------------------------------------------

def classify(game):
    """
    Work out what is actually happening, from real pulled data.

    Ordered by specificity: an injury outranks everything, a walk-off outranks
    a plain home run, a shutout outranks a general collapse. First match wins.

    `game` is a loose dict - anything absent is simply not tested, so this
    works with whatever a given generator happens to know.
    """
    g = game or {}

    if g.get("injury"):
        return "injury"
    if g.get("benches_cleared"):
        return "benches_clear"
    if g.get("position_player_pitching"):
        return "position_player_pitching"
    if g.get("walk_off"):
        return "walk_off"
    if g.get("blown_save"):
        return "blown_save"

    loser_runs = g.get("loser_score")
    margin = g.get("margin")
    final = g.get("final")

    # Nil is its own thing - the funniest scoreline available.
    if final and loser_runs == 0:
        return "shut_out"
    if g.get("led_and_lost"):
        return "collapse"
    if g.get("stranded", 0) >= 8:
        return "stranded"
    if g.get("errors", 0) >= 2:
        return "error"

    # Close and late is the quiet register, and it only applies while the
    # game is still live - a one-run FINAL is a result, not tension.
    if not final and g.get("late") and margin is not None and margin <= 1:
        return "tense_late"

    if g.get("home_runs", 0) >= 1 and not final:
        return "home_run"
    if g.get("loser_pitching_hit"):
        return "pitcher_shelled"

    # A final with runs on both sides. Margin decides the register:
    # a one-run loss is agonising, a rout is embarrassing, and the middle is
    # neither - it is just a loss, which is its own kind of quiet.
    m = margin or 0
    if final:
        if m <= 2:
            return "close_final"
        if m >= 7:
            return "collapse"
        return "routine_loss"
    return "routine_loss"


# ---------------------------------------------------------------------------
# Picking lines
# ---------------------------------------------------------------------------

def lines_for(situation, count=6, exclude=()):
    """
    A handful of eligible lines for this situation, none of them repeats.

    The generator is given a SHORTLIST rather than the whole bank. Handed 127
    lines a model gravitates to the same handful; handed six it uses what it
    has, and the variety comes from the pick rather than from the model's
    goodwill.
    """
    banks = _load("situations.json")
    bank = banks.get(situation) or banks["shut_out"]
    pool = [l for l in bank["lines"] if l not in exclude]
    if not pool:
        pool = bank["lines"]
    return random.sample(pool, min(count, len(pool)))


def closer(exclude=()):
    """One sign-off. Never more than one per segment."""
    return lines_for("closers", count=1, exclude=exclude)[0]


def belief(force=False):
    """
    An opinion, occasionally contradicted.

    A man who says "I hate intentional walks" every single time one happens is
    a bot. Saying it most times and once in a while grudgingly admitting one
    worked is what makes the opinion read as held rather than programmed.
    """
    v = _load("voice.json")["beliefs"]
    line = random.choice(v["lines"])
    if not force and random.random() < v.get("_contradict_odds", 0.15):
        return f"{line} ...though I'll admit, that one worked."
    return line


def bits_for(situation, used_this_segment=(), used_this_week=()):
    """
    Running bits whose budget still allows them.

    Meatball Alert is a REACTION and fires every time by design. The rest are
    JOKES - a joke that appears every episode stops being a bit and becomes a
    tic, so each carries a real budget checked here rather than requested in
    the prompt.
    """
    trigger_map = {
        "pitcher_shelled": ["Meatball Alert", "The ERA Funeral"],
        "home_run": ["Grandpa in Left Field", "The Baseball Police"],
        "walk_off": ["The Bullpen Accountant"],
        "collapse": ["Smack Insurance", "Dugout Therapist"],
        "blown_save": ["Smack Insurance"],
        "shut_out": ["Dugout Therapist"],
    }
    wanted = trigger_map.get(situation, [])
    out = []
    for b in _load("voice.json")["running_bits"]["bits"]:
        if b["name"] not in wanted:
            continue
        per_seg = b.get("max_per_segment")
        if per_seg is not None and used_this_segment.count(b["name"]) >= per_seg:
            continue
        per_week = b.get("max_per_week")
        if per_week is not None and used_this_week.count(b["name"]) >= per_week:
            continue
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# The prompt block
# ---------------------------------------------------------------------------

def render(situation=None, game=None, level=3, include_rejects=True,
           exclude=(), used_this_segment=(), used_this_week=()):
    """
    Everything the model needs for ONE generation, and nothing more.

    Deliberately not the whole library. Sending all 127 lines and 30 rejects
    on every call would cost real money across a Daily Show's worth of
    generations, and would produce worse output - a model handed everything
    reaches for the same few things.
    """
    if situation is None:
        situation = classify(game)

    banks = _load("situations.json")
    bank = banks.get(situation, {})
    parts = []

    parts.append(
        "WHO YOU ARE\n"
        "Smacky: a fan with a microphone, not a coach with a clipboard.\n"
        "A phone in a backwards hat who loves baseball, loves chaos, and loves\n"
        "roasting bad baseball. Never malicious. The listener should laugh and\n"
        "think \"that's brutal - but he's right.\""
    )

    parts.append(
        "THE EDGE\n"
        "Roast: the pitch, the swing, the strategy, the bullpen, the defence,\n"
        "the collapse, the scoreboard, the moment.\n"
        "NEVER: injuries, appearance, identity, somebody's career or\n"
        "livelihood, or the fans. The fans laugh WITH you.\n"
        "If anybody is hurt, drop the act completely - no slang, no jokes."
    )

    if situation == "injury":
        # Nothing else applies. Say the human thing and stop.
        parts.append(
            "SOMEBODY IS HURT.\n"
            "This overrides everything above. No vocabulary, no exaggeration,\n"
            "no roast, no closer. One short sincere line and nothing else."
        )
        return "\n\n".join(parts)

    parts.append(
        "YOUR OWN WORDS - use at least one\n"
        "SMACKIFIED, COOKAGEDDON, SMACKASTROPHE, L CITY, SMACKVILLE,\n"
        "SMACK DETENTION, TANK JOB, MOON MISSILE"
    )

    if bank:
        picked = lines_for(situation, count=6, exclude=exclude)
        parts.append(
            f"THE SITUATION: {bank.get('when','')}\n"
            f"Intensity: {bank.get('intensity', 80)} out of 120.\n"
            "Lines in this register - use them as a GUIDE to the voice, do not\n"
            "quote them all:\n" + "\n".join(f"  - {l}" for l in picked)
        )

    parts.append(
        "INTENSITY SHAPES THE WRITING, NOT JUST THE WORDS\n"
        "Below 40: short sentences, full stops, room to breathe. Quiet is a\n"
        "register, not a volume - do not say quiet words loudly.\n"
        "Above 100: fragments, exclamations, no commas where a full stop will\n"
        "do.\n"
        "This matters because the text is spoken aloud: punctuation drives the\n"
        "delivery. Capitals do not."
    )

    bits = bits_for(situation, used_this_segment, used_this_week)
    if bits:
        parts.append(
            "RUNNING BITS available right now (at most one):\n" +
            "\n".join(f"  - {b['name']}: {b['line']}" for b in bits)
        )

    if level >= 3 and random.random() < 0.35:
        parts.append("AN OPINION you can drop in:\n  " + belief())

    if include_rejects:
        # Four bland, one over-the-line. The second kind matters more: bland
        # output is a disappointment, a line that crosses is a problem.
        rj = _load("rejects.json")
        bland = random.sample([r for r in rj if r["kind"] == "bland"], 4)
        edge = random.choice([r for r in rj if r["kind"] == "over_the_line"])
        parts.append(
            "NEVER WRITE LIKE THIS\n" +
            "\n".join(f"  NO:  {r['reject']}\n  YES: {r['instead']}"
                      for r in bland + [edge])
        )

    parts.append("END WITH ONE SIGN-OFF:\n  " + closer(exclude=exclude))

    return "\n\n".join(parts)
