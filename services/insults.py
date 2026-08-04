"""
Smacky's insult dictionary.
===========================
A small, deliberate vocabulary where every word does a different job.

WHY A SHORT LIST BEATS A LONG ONE
---------------------------------
Given twenty-five words that all mean "idiot", a writer uses them
interchangeably and the result reads as a thesaurus rather than a voice.
Twenty-five words that each mean something SPECIFIC produce writing that
sounds chosen. "Bricklayer" is not a synonym for "clown" - one is a
basketball player missing shots, the other is somebody embarrassing
themselves in public, and using the wrong one is a small tell that nobody
is really watching.

WHY THIS LIVES IN CODE
----------------------
Every rule asked of the model in a prompt on this project has been ignored
at least once - the construction cap, the cross-league teases, the grouping
instruction, the segment targets. A vocabulary handed over as data, filtered
by level before the model ever sees it, cannot be exceeded. It can only be
used or not used.

THE FAN PROBLEM
---------------
Four of these - bandwagoner, couch coach, crybaby, delusional - are aimed at
FANS. But the person receiving the call IS a fan, and the rule everywhere
else on this product is that the roast lands on the TEAM, never the person
listening.

So they are kept, because they are good words, but marked. They may describe
the fanbase as a group, or be posed as a question, and never be stated flat
at the listener. "Their fans are delusional" is fine. "You're delusional" is
the line this product does not cross.
"""

# level: the lowest sensitivity at which a word may appear.
#   1 Clean · 2 Mild · 3 Aggressive · 4 Savage
#
# about: who it can be pointed at.
#   any    - anybody
#   player - a named player only
#   team   - the club, front office, coaching
#   fans   - the fanbase AS A GROUP, never the listener directly
INSULTS = [
    # --- light. Fine even at Clean. ---
    {"word": "knucklehead", "level": 1, "about": "any",
     "means": "a harmless, goofy fool", "use": "lighthearted teasing"},
    {"word": "doofus", "level": 1, "about": "any",
     "means": "awkward or clueless",
     "use": "funny mistakes rather than serious failures"},
    {"word": "bonehead", "level": 1, "about": "any",
     "means": "somebody who just made an avoidable mistake",
     "use": "missed plays, mental errors, coaching blunders"},
    {"word": "benchwarmer", "level": 1, "about": "player",
     "means": "a player who rarely contributes", "use": "reserve players"},
    {"word": "has-been", "level": 1, "about": "player",
     "means": "somebody whose best days are behind them",
     "use": "ageing stars"},
    {"word": "wannabe", "level": 1, "about": "any",
     "means": "pretending to be elite without earning it",
     "use": "overhyped players or fans"},

    # --- medium. Mild and up. ---
    {"word": "clown", "level": 2, "about": "any",
     "means": "making a complete fool of themselves in public",
     "use": "a bad take or an awful performance"},
    {"word": "bozo", "level": 2, "about": "any",
     "means": "a goofy, laughable person nobody takes seriously",
     "use": "players or fans doing something ridiculous"},
    {"word": "chump", "level": 2, "about": "any",
     "means": "somebody outplayed or embarrassed easily",
     "use": "rival fans and beaten opponents"},
    {"word": "meathead", "level": 2, "about": "any",
     "means": "relying on emotion instead of thinking",
     "use": "angry fans or reckless players"},
    {"word": "buffoon", "level": 2, "about": "any",
     "means": "acting dramatically while looking ridiculous",
     "use": "coaches, commentators, or anybody making unnecessary drama"},
    {"word": "loser", "level": 2, "about": "any",
     "means": "somebody who constantly comes up short",
     "use": "after repeated failures"},
    {"word": "bust", "level": 2, "about": "player",
     "means": "a player who never lived up to expectations",
     "use": "draft picks and disappointing signings"},
    {"word": "liability", "level": 2, "about": "player",
     "means": "actively hurting their own team",
     "use": "poor defenders, bad quarterbacks, terrible coaches"},
    {"word": "bricklayer", "level": 2, "about": "player",
     "means": "constantly missing shots", "use": "BASKETBALL ONLY"},
    {"word": "choke artist", "level": 2, "about": "any",
     "means": "falls apart in the big moments",
     "use": "playoffs, clutch situations, pressure"},
    {"word": "schmuck", "level": 2, "about": "any",
     "means": "foolish while thinking they are clever",
     "use": "cocky people getting humbled"},

    # --- fan-directed. Handle with the rule below. ---
    {"word": "bandwagoner", "level": 2, "about": "fans",
     "means": "only supports a team while it wins",
     "use": "the fanbase as a group"},
    {"word": "couch coach", "level": 2, "about": "fans",
     "means": "thinks they know better than professionals",
     "use": "fans second-guessing every decision"},
    {"word": "crybaby", "level": 2, "about": "fans",
     "means": "constantly whining or blaming others",
     "use": "losing fans, players complaining to officials"},
    {"word": "delusional", "level": 2, "about": "fans",
     "means": "believing things that clearly are not true",
     "use": "unrealistic predictions, defending a terrible team"},

    # --- heavy. Aggressive and up. ---
    {"word": "idiot", "level": 3, "about": "any",
     "means": "a general insult for a bad decision",
     "use": "fits almost anywhere"},
    {"word": "moron", "level": 3, "about": "any",
     "means": "lacking basic common sense",
     "use": "terrible sports opinions"},
    {"word": "dumbass", "level": 4, "about": "any",
     "means": "making an incredibly stupid decision",
     "use": "after obvious mistakes"},
    {"word": "jackass", "level": 4, "about": "any",
     "means": "loud, arrogant and foolish",
     "use": "somebody confidently saying something absurd"},
]

# Said flat at the listener, these four break the rule the rest of the
# product runs on. Kept because they are good words, but framed.
FAN_RULE = (
    "The four fan words - bandwagoner, couch coach, crybaby, delusional - "
    "describe the FANBASE AS A GROUP or get posed as a question. Never "
    "stated flat at the person listening.\n"
    "  YES  \"their fans are delusional about this team\"\n"
    "  YES  \"are you a bandwagoner or have you actually suffered through it\"\n"
    "  NO   \"you're delusional\"\n"
    "  NO   \"you're a crybaby\"\n"
    "The person on the phone is a fan. The roast lands on the team."
)


def for_level(level, sport=None):
    """The words permitted at this sensitivity."""
    try:
        lv = int(level)
    except (TypeError, ValueError):
        lv = 2
    out = [w for w in INSULTS if w["level"] <= lv]
    # Bricklayer in a baseball call is a tell that nobody is watching.
    if sport and str(sport).lower() not in ("nba", "wnba", "ncaab", "ncaaw",
                                            "basketball"):
        out = [w for w in out if w["word"] != "bricklayer"]
    return out


def block(level, sport=None):
    """
    The vocabulary as a prompt section.

    Includes what each word MEANS, because a list of bare words gets used
    interchangeably - which is the exact failure a short list exists to
    avoid.
    """
    words = for_level(level, sport)
    if not words:
        return ""

    lines = [f"  {w['word']} - {w['means']}; {w['use']}" for w in words]
    return (
        "SMACKY'S INSULT VOCABULARY. Use these and no others.\n"
        "Each one means something DIFFERENT - they are not "
        "interchangeable, and reaching for the wrong one is a small tell "
        "that nobody is really watching the sport.\n\n"
        + "\n".join(lines)
        + "\n\nRotate them. Repeating the same insult twice in one call is "
          "worse than using a plainer word the second time.\n"
          "Two or three across a whole call is plenty - a line that is "
          "nothing but insults stops being funny about eight words in.\n\n"
        + FAN_RULE
    )
