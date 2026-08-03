"""
Smacky Makes the Call
=====================
Smacky calls the most famous moments in sports history.

WHAT THIS DOES NOT DO
---------------------
It never sees the original broadcast. The announcer's words are somebody
else's copyrighted work, and a transcript in the prompt would drag the model
straight to the phrases that ARE the moment - "do you believe in miracles"
surfaces because it is the most salient thing available, not because anyone
asked for it. A "make it your own" instruction is exactly the kind of
prompt-level cap that gets ignored.

So the pipeline is built the other way round: facts in, original call out.
Score, clock, who did what, what was at stake - none of which anyone owns -
plus a DESCRIPTION of how the broadcast felt. Smacky writes from that.
"""

import os
import random
import re
from datetime import datetime, timezone

import anthropic

from services import smackology

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# Openers
# ---------------------------------------------------------------------------
# Enforced in CODE, not requested in the prompt.
#
# Fifty calls sit on one page. Asked politely to vary the opening, a model
# will still start half of them with "OH MY" or "HERE WE GO" - the prompt cap
# has been ignored twice on this project already. Handing the model ONE
# assigned opener and requiring it to be used removes the choice.

_OPENERS = [
    "OH THAT'S TROUBLE", "HERE IT COMES", "LOOK OUT", "STAY WITH ME",
    "WATCH THIS", "DON'T BLINK", "HERE WE GO", "OH BOY", "AND THERE IT IS",
    "WAIT A SECOND", "HOLD EVERYTHING", "OH THIS IS SOMETHING",
    "YOU KIDDING ME", "GET IN HERE", "SIT DOWN FOR THIS",
    "SOMEBODY GRAB SOMETHING", "OH NO NO NO", "THIS IS IT",
    "EVERYBODY UP", "TURN IT UP", "RIGHT NOW", "HERE'S THE MOMENT",
    "OH THEY'RE IN BOTHER", "LISTEN TO THIS PLACE", "THAT'S THE ONE",
    "AND HE'S OFF", "OH MY DAYS", "STOP WHAT YOU'RE DOING",
    "IT'S HAPPENING", "GET READY",
]

# Closing beats, same reasoning.
_CLOSERS = [
    "WELCOME TO NUKE CITY", "PUT IT ON THE WALL", "FRAME THAT ONE",
    "THAT'S IN THE BOOKS FOREVER", "GOODNIGHT EVERYBODY",
    "SOMEBODY CALL A DOCTOR", "SEND THE TAPE TO THE HALL",
    "THAT IS ALL SHE WROTE", "GET THE TROPHY OUT",
    "NOBODY'S SLEEPING TONIGHT", "PRINT IT", "BOOK IT",
    "THAT'S THE BALLGAME", "SOMEBODY HOLD ME",
    "I NEED A MINUTE", "THAT'S GOING IN THE VAULT",
]


CALL_RULES = """
You are Smacky calling a famous moment in sports history, live, as it
happens. Smacky is a phone with a backwards hat and a jersey. He is not a
professional broadcaster and has never pretended to be one.

YOU HAVE NEVER HEARD THE ORIGINAL BROADCAST.
You are given facts and a description of the atmosphere. Write your OWN call
from those facts. Do not attempt to reconstruct, echo or approximate what any
real announcer said - you do not know, and guessing at it is the one thing
that will ruin this.

THE THREE BEATS. Always all three, always in this order:

1. THE CALL - the moment itself, live, escalating. All caps. This is the
   explosion. Six to nine sentences of it.
2. THE FOLLOW-UP - one or two sentences, normal case, the moment after the
   noise dies down. Drier. This is where the joke lands.
3. THE ROAST - one or two sentences aimed at the LOSING SIDE by name. Not a
   general observation about sport - a specific shot at the team that lost.

HOW SMACKY CALLS A GAME

- He gets more excited than the moment deserves and then says something
  no broadcaster would ever say.
- He is on the winner's side, always, and completely unfair about it.
- He never explains why a moment is historic. He reacts to it.
- Present tense during the call. It is happening now.
- Real names from the facts. Never invent a player, a score or a detail.
- Swearing is fine in the call - hell, damn - but not in every sentence.

THE ROAST IS THE POINT
The call is the setup. The roast is why anybody is listening. Go at the
losing team specifically: what they blew, what they had, how it felt. If the
facts name the pitcher who gave it up or the fielder who missed it, use them.
If there is no clean losing side, roast the situation instead - never invent
somebody to blame.

WHAT WILL RUIN IT

- Any phrase that sounds like a famous broadcast call. If a line feels
  familiar, it is not yours - write a different one.
- Explaining the significance. "This will be remembered forever" is what a
  documentary says, not what somebody watching it live says.
- Being nice about the losing team. That is not this product.
- Starting with anything other than the opener you were assigned.
""".strip()


def _facts_block(m):
    """Everything Smacky gets. Facts only - no transcript, ever."""
    lines = [
        f"MOMENT: {m.title}",
        f"DATE: {m.moment_date or 'unknown'}",
        f"GAME: {m.game or ''}",
        f"TEAMS: {m.teams or ''}",
    ]
    if m.hero:
        lines.append(f"WHO DID IT: {m.hero}")
    if m.goat:
        lines.append(f"WHO IT HAPPENED TO: {m.goat}")
    if m.losing_team:
        lines.append(f"LOSING SIDE (roast these): {m.losing_team}")
    if m.situation:
        lines.append("SITUATION:")
        for row in str(m.situation).splitlines():
            if row.strip():
                lines.append(f"  - {row.strip().lstrip('-').strip()}")
    if m.stakes:
        lines.append(f"WHAT WAS AT STAKE: {m.stakes}")
    if m.broadcast_style:
        # How it FELT, not what was said.
        lines.append(f"ATMOSPHERE: {m.broadcast_style}")
    return "\n".join(lines)


def generate_call(moment, seed=None):
    """
    Write one call. Returns (call, followup, roast).

    Raises on failure rather than returning half a call - a moment with a
    call and no roast is worse than one that has not generated yet, because
    the roast is the whole product.
    """
    rng = random.Random(seed)
    opener = rng.choice(_OPENERS)
    closer = rng.choice(_CLOSERS)

    # Tier 3: real teeth, short of the tier-4 profanity. These sit on a public
    # page anybody can reach without buying anything.
    vocab = smackology.render(level=3, context="call")

    prompt = f"""{_facts_block(moment)}

START THE CALL WITH: "{opener}"
END THE CALL WITH: "{closer}"
Both are assigned. Use them exactly, and build the rest around them.

Use at least two pieces of Smacky's own vocabulary from the list below, and
name the losing side in the roast.

Return EXACTLY this, nothing else:

CALL: <the live call, all caps>
FOLLOWUP: <one or two sentences, normal case>
ROAST: <one or two sentences at the losing side, normal case>
"""

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=CALL_RULES + "\n\n" + vocab,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def _grab(label, nxt):
        pat = rf"{label}:\s*(.*?)(?=\n{nxt}:|$)"
        m = re.search(pat, text, re.S | re.I)
        return (m.group(1).strip() if m else "")

    call = _grab("CALL", "FOLLOWUP")
    followup = _grab("FOLLOWUP", "ROAST")
    roast = _grab("ROAST", "ZZZZ")

    if not (call and followup and roast):
        raise ValueError(f"incomplete call for {moment.slug}: {text[:200]}")

    return call, followup, roast


def spoken_text(call, followup, roast):
    """
    The three beats as one piece of audio.

    Pauses between them, because the timing is the joke - the call explodes,
    a beat of silence, then the dry line. Run together it is just shouting.
    """
    return f"{call}\n\n...\n\n{followup}\n\n...\n\n{roast}"
