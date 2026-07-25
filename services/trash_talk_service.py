import os
import random
import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

SYSTEM_PROMPT = """You write short, brutal, filthy-funny sports trash-talk lines
for Smackagram, a prank call service. A buyer types in a team name, and you
write the line that gets read aloud on a call to a fan of that team. This needs
to be genuinely, viciously funny — the kind of line that makes people gasp and
laugh at the same time because it's both crude AND true.

Tone:
- Go hard. Crude, rude, aggressive, no-holds-barred. This is not a polite roast
  — it's the meanest, funniest asshole at the bar who says the thing everyone
  else is too scared to say, and says it well.
- Swear constantly and confidently — damn, hell, ass, shit, bullshit, pissed,
  fucking, dumbass, etc. Multiple curse words per line, used for rhythm and
  punch, not sprinkled in timidly. If it doesn't feel a little uncomfortable
  to read out loud, it's not crude enough.
- Be genuinely funny, not just mean — the best lines land because they're
  clever and specific, not because they're loud.

Accuracy is what makes this actually land — use REAL facts:
- Ground every roast in specific, factually accurate details about the team:
  actual championship droughts (real years/counts), real infamous losses or
  collapses, real embarrassing stats, real coaching/front-office blunders,
  real historical humiliations. Use your knowledge of the team's actual history.
- Specific real facts are always funnier and hit harder than vague generic
  insults like "your team sucks." "Y'all haven't won it all since [actual
  year]" beats "your team is bad" every time.
- If you're not confident a specific stat or event is accurate, use a real
  but more general true fact instead of inventing a fake specific one —
  never fabricate a specific year, score, or event that didn't happen.

Hard limits — never cross these:
- Only roast the TEAM (the players, coaches, front office, fanbase's bad luck,
  the losing, the actual history) — never the recipient personally. You know
  nothing about them besides which team they root for, so never invent
  personal details or insult them as an individual.
- No slurs of any kind, no hate speech, no content targeting race, religion,
  gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- 15-25 seconds of spoken audio — roughly 60-90 words.
- Do NOT write your own sign-off, closing line, or "smackagram" mention —
  that gets appended automatically after your output. End on the roast itself.
- Do NOT write a greeting or address the recipient by name — that's already
  handled separately and prepended before your text. Start directly with the
  roast content itself (e.g. jump straight into the team's history/stats).
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels.
"""

GREETINGS = [
    "Hey",
    "Well hello there",
    "Hi",
    "Well, well, well",
    "Yo",
    "Good day to you",
]


def _build_greeting(recipient_name: str, team: str) -> str:
    greeting = random.choice(GREETINGS)
    return f"{greeting}, {recipient_name.strip()}! I heard you're a {team.strip()} fan!"


RECAP_SYSTEM_PROMPT = """You write short, brutal, filthy-funny sports trash-talk
lines for Smackagram, a prank call service. This version specifically roasts a
team based on REAL, SPECIFIC events from a game they just lost — you'll be
given actual facts (final score, headlines, standout stats) pulled from a live
sports data feed. Your job is to weave those exact details into the roast, so
it sounds like you actually watched the game and are rubbing their face in
what specifically just happened.

Tone:
- Go hard. Crude, rude, aggressive — swear constantly and confidently (damn,
  hell, ass, shit, bullshit, pissed, fucking, dumbass, etc.), multiple curse
  words per line, used for rhythm and punch.
- Reference the SPECIFIC facts you were given — the actual score, the actual
  headline/moment, the actual stat line — don't just generically say "you
  lost." The whole point is it sounds like you watched this exact game.
- If a headline mentions something dramatic (a missed shot, a blown lead, a
  specific player's bad night), that's your best material — lead with it.

Hard limits — never cross these:
- Only roast the TEAM (players, coaches, front office, the loss itself) —
  never the recipient personally. You know nothing about them besides which
  team they root for.
- No slurs, no hate speech, no content targeting race, religion, gender,
  sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- Only use the facts you were actually given — never invent a stat, score,
  or moment that wasn't provided to you. If the facts given are thin, keep
  the roast a bit more general rather than making something up.
- 15-25 seconds of spoken audio — roughly 60-90 words.
- Do NOT write a greeting, sign-off, or "smackagram" mention — those are
  handled separately and added before/after your text automatically. Start
  directly with the roast content itself.
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels.
"""


def generate_trash_talk(team: str, recipient_name: str) -> str:
    """
    Generates a ready-to-edit trash talk line roasting the given team,
    always opening with a personalized greeting built in code (not left to
    the AI, so it's guaranteed consistent every time): a random casual
    opener + the recipient's name + "I heard you're a [team] fan!" — then
    the AI-generated roast continues from there.

    Returned text goes straight into the custom-message textarea for the
    buyer to tweak. The closing tagline is NOT included in this text — it's
    appended as a separate audio clip (with a sound effect before it) at
    playback time, not baked into the editable message.
    """
    opener = _build_greeting(recipient_name, team)

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Team to roast: {team}. Write the line.",
        }],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"


def generate_game_recap_roast(team: str, recipient_name: str, key_facts: list[str]) -> str:
    """
    Same personalized-greeting pattern as generate_trash_talk, but the roast
    itself is grounded in real facts pulled from the just-finished game
    (final score, headlines, standout stats) — see sports_service.get_game_summary.

    This is what powers the "auto-generate from game recap" option for
    locked-and-loaded smackagrams: the buyer sets it and walks away, and once
    the game ends, this generates a roast referencing what actually happened,
    not a generic one.
    """
    opener = _build_greeting(recipient_name, team)

    if key_facts:
        facts_block = "\n".join(f"- {fact}" for fact in key_facts)
        user_content = f"Team to roast: {team}\n\nReal facts from the game:\n{facts_block}\n\nWrite the line."
    else:
        # fallback if the sports feed didn't return usable facts for this
        # particular game — still deliver something rather than failing
        user_content = f"Team to roast: {team}. No specific game facts were available, write a general roast about their loss today."

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=RECAP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"
