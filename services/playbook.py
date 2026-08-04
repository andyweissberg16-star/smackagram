"""
Smacky's roast playbook.
========================
Situational language - what to say about WHAT HAPPENED, not about who it
happened to.

THE POINT
---------
Insults describe a person. These describe a moment, which is what a real
sports host actually does. "You clown" works once; "they folded like cheap
lawn chairs" works because it is about the collapse rather than the man.

HOW IT IS USED, AND WHY THAT MATTERS
------------------------------------
The whole bank is NEVER handed over at once. The situation is worked out
first from the real game data, and only the ten or so phrases that fit go
into the prompt.

Given all thirteen situations, a writer picks whichever phrase it likes and
the result reads as a list being consulted. Given only the phrases for "they
blew a fourteen-point lead", it sounds like somebody who watched the game.

WHAT IS DELIBERATELY MISSING
----------------------------
There is no injury section, and there should not be. Smacky drops the act
completely when somebody is hurt - no slang, no phrases, no jokes. A
playbook entry for it would be an invitation to reach for one.
"""

# sport: None means anywhere. Otherwise the phrase is held back unless the
# call is about that sport - "the rim filed a restraining order" in a
# baseball call is a tell that nobody is watching.
PLAYBOOK = {

    "blowout": {
        "when": "the losing side was never in it",
        "phrases": [
            "they're getting absolutely smoked",
            "this game was over before it started",
            "somebody call the mercy rule",
            "they got run out of the building",
            "they got embarrassed on national television",
            "that scoreboard needs a parental warning",
            "somebody unplug the scoreboard",
            "they got folded",
            "they got cooked",
            "they got steamrolled",
            "that stopped being a game and became target practice",
            "they're wearing that loss like a backpack",
        ],
    },

    "collapse": {
        "when": "they led and lost it",
        "phrases": [
            "historic collapse",
            "complete meltdown",
            "they folded like cheap lawn chairs",
            "somebody hit the self-destruct button",
            "they snatched defeat from the jaws of victory",
            "they forgot how to play",
            "ice cold when it actually mattered",
            "the pressure cooked them",
            "they handed that game away",
            "they gift-wrapped it",
            "they found a brand new way to lose",
        ],
    },

    "bad_player": {
        "when": "a named player had a shocker",
        "phrases": [
            "couldn't hit water falling out of a boat",
            "couldn't throw a rock into the ocean",
            "looked completely lost out there",
            "playing like the controller disconnected",
            "running in quicksand",
            "forgot how the sport works",
            "playing scared",
            "completely invisible tonight",
            "should have stayed on the bench",
            "that was a certified cardio session",
            "just out there doing wind sprints",
            "that stat line needs witness protection",
        ],
    },

    "cold_shooting": {
        "when": "a shooter could not buy a basket",
        "sport": "basketball",
        "phrases": [
            "brick after brick after brick",
            "Mason of the Year",
            "Home Depot MVP",
            "opened a construction company tonight",
            "building affordable housing out there",
            "remodelling the arena one brick at a time",
            "the rim filed a restraining order",
            "the backboard is owed overtime pay",
            "every shot came with a building permit",
        ],
    },

    "always_bad": {
        "when": "the team is bad every year, not just tonight",
        "phrases": [
            "same movie, different ending",
            "annual disappointment",
            "professional rebuilders",
            "they're rebuilding the rebuild",
            "lottery legends",
            "permanent basement residents",
            "another season, same pain",
            "losing is part of the logo now",
            "collecting draft picks like Pokemon",
        ],
    },

    "upset": {
        "when": "the worse team won",
        "phrases": [
            "nobody saw that coming",
            "that's the upset of the night",
            "they shocked everybody",
            "they walked into enemy territory and stole one",
            "statement win",
            "that's how you silence a crowd",
            "they earned every second of that",
            "biggest surprise of the week",
        ],
    },

    "star_vanished": {
        "when": "their best player did nothing",
        "phrases": [
            "missing person report filed",
            "put his face on a milk carton",
            "invisible tonight",
            "ghosted the entire game",
            "nowhere to be found",
            "vanished when it mattered",
            "the lights got too bright",
            "superstar paycheck, role player performance",
            "hiding from the moment",
        ],
    },

    "opponent_dominant": {
        "when": "the WINNING side was excellent - credit before the roast",
        "phrases": [
            "they were firing on all cylinders",
            "an absolute clinic",
            "locked in from the first whistle",
            "clinical",
            "complete domination",
            "every possession looked easy",
            "they could not miss",
            "championship level execution",
        ],
    },

    "big_play": {
        "when": "somebody on the winning side did something absurd",
        "phrases": [
            "put that on a poster",
            "clip it",
            "somebody frame that",
            "play of the night",
            "that was filthy",
            "absolutely disgusting, in the good way",
            "that's going on every highlight show tomorrow",
            "somebody check his cheat codes",
        ],
    },

    "bad_coaching": {
        "when": "the decisions, not the players",
        "phrases": [
            "coaching malpractice",
            "a genuine galaxy brain decision",
            "somebody explain the game plan to me",
            "a coaching disasterclass",
            "that aged horribly",
            "the timeout came about ten minutes late",
            "outcoached from the first whistle",
            "that's getting questioned all week",
        ],
    },

    "excuses": {
        "when": "the FANBASE as a group, after a loss",
        "fans": True,
        "phrases": [
            "here come the excuses",
            "excuse season is officially open",
            "copium levels are critical",
            "somebody pass the tissues",
            "the excuse factory is open for business",
            "everybody suddenly became an officiating expert",
            "nobody wants to admit they just got beat",
            "that's premium grade copium",
            "keep moving those goalposts",
        ],
    },

    "smacky_gloats": {
        "when": "Smacky congratulating himself. Use sparingly.",
        "phrases": [
            "I tried to warn you",
            "I called it",
            "write that one down",
            "Smacky doesn't miss",
            "another certified Smacky prediction",
            "I saw this coming a mile off",
            "that's why they pay me absolutely nothing",
            "put me in the Hall of Smack",
            "I've got receipts",
        ],
    },
}

# There is no "referees" section, though it was on the list.
#
# On a Locked & Loaded call we work from a box score, and a box score does
# not contain a single officiating decision - so every ref line would be
# invented, about a real named official, in a call somebody paid to have
# delivered. That is the one category of made-up detail with a person on the
# other end of it.
#
# On a core Smackagram with no game attached, "the whistles are working
# overtime" is a general gripe and harmless, but the same phrases would then
# need to be blocked for Locked & Loaded, and a bank that is safe in one
# generator and not the other is a bank somebody eventually wires into the
# wrong one.

_SPORT_FAMILY = {
    "nba": "basketball", "wnba": "basketball", "ncaab": "basketball",
    "ncaaw": "basketball", "basketball": "basketball",
    "nfl": "football", "ncaaf": "football", "football": "football",
    "mlb": "baseball", "ncaabb": "baseball", "baseball": "baseball",
    "nhl": "hockey", "hockey": "hockey",
}


def situations_for(game=None, sport=None):
    """
    Which situations actually apply, from the real game data.

    Returns a short list of keys. With no game data - a plain Smackagram
    with no fixture attached - it returns the ones that always work.
    """
    fam = _SPORT_FAMILY.get(str(sport or "").lower())
    out = []

    if not game:
        # No fixture. Only the timeless ones make sense.
        out = ["always_bad", "bad_player", "excuses"]
    else:
        margin = game.get("margin") or 0
        blowout_at = {"basketball": 18, "football": 17,
                      "baseball": 6, "hockey": 4}.get(fam, 12)

        if margin >= blowout_at:
            out.append("blowout")
        if game.get("blown_lead") or game.get("collapse"):
            out.append("collapse")
        if game.get("upset"):
            out.append("upset")
        if game.get("bad_player") or game.get("worst"):
            out.append("bad_player")
        if game.get("star_quiet"):
            out.append("star_vanished")
        if game.get("cold_shooting") and fam == "basketball":
            out.append("cold_shooting")
        if game.get("big_play"):
            out.append("big_play")
        if game.get("coaching"):
            out.append("bad_coaching")
        if game.get("winner_dominant") or margin >= blowout_at:
            out.append("opponent_dominant")
        if not out:
            out = ["bad_player", "always_bad"]

    # Sport-restricted sections are dropped rather than translated.
    return [k for k in out
            if not PLAYBOOK.get(k, {}).get("sport")
            or PLAYBOOK[k]["sport"] == fam]


def block(game=None, sport=None, limit=3):
    """
    The playbook as a prompt section - ONLY the situations that apply.

    The whole bank is never handed over. Given all thirteen, a writer picks
    whichever phrase it likes and the result reads as a list being
    consulted. Given only the phrases for "they blew a fourteen point lead",
    it sounds like somebody who watched the game.
    """
    keys = situations_for(game, sport)[:limit]
    if not keys:
        return ""

    chunks = []
    has_fans = False
    for k in keys:
        sec = PLAYBOOK[k]
        if sec.get("fans"):
            has_fans = True
        chunks.append(
            f"  {k.upper()} - {sec['when']}\n"
            + "\n".join(f"    {p}" for p in sec["phrases"]))

    out = ("WHAT ACTUALLY HAPPENED. Language for tonight's situation, not for\n"
           "the person - a real host roasts the MOMENT.\n\n"
           + "\n\n".join(chunks)
           + "\n\nThese are the SHAPE of what to say, not lines to read out. "
             "Rework them in your own words, use at most two across the whole "
             "call, and never the same one twice.\n"
             "If the winning side played well, say so BEFORE the roast. A "
             "balanced call lands harder than relentless negativity, and it "
             "is what somebody who actually watched would say.")

    if has_fans:
        out += ("\n\nThe excuse lines are about the FANBASE as a group. Never "
                "aimed at the person listening - they are a fan, and the "
                "roast lands on the team.")
    return out
