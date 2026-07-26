import os
import json
import random
import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# Human-facing labels/descriptions — used by the frontend to render the
# sensitivity selector on both the main generator and the Locked & Loaded
# auto-recap option. Keep these in sync with the tone instructions below.
SENSITIVITY_LEVELS = {
    1: {
        "label": "Clean",
        "description": "Sharp, witty roasts with zero profanity. Still stings, just PG.",
    },
    2: {
        "label": "Mild",
        "description": "A little bite. Occasional mild language (damn, hell).",
    },
    3: {
        "label": "Aggressive",
        "description": "Real trash talk. Regular cursing, no holds barred on the team.",
    },
    4: {
        "label": "Savage",
        "description": "Maximum aggression. Heavy profanity, brutally crude.",
    },
}

DEFAULT_SENSITIVITY = 4  # matches the original always-crude behavior, so nothing changes for existing users unless they pick a lower level

# Tone instructions per level — this is the ONLY thing that changes between
# levels. The hard limits (no slurs, no personal attacks on the recipient,
# no fabricated facts, etc.) are identical at every level and never scale
# down, regardless of how aggressive the language gets.
_TONE_BY_LEVEL = {
    1: """Tone — CLEAN (Level 1):
- Zero profanity, not even mild words like "damn" or "hell."
- The roast should still be sharp, cutting, and genuinely funny — clever
  wordplay, real facts landing hard, confident delivery. Think a savage
  stand-up comedian who never needs to curse to be devastating.
- Avoid crude anatomy references or anything that reads as vulgar even
  without swearing.""",
    2: """Tone — MILD (Level 2):
- Light profanity only: "damn," "hell," "ass" (as in "kick their ass") are
  fine, sparingly — at most one or two per line.
- Otherwise similar to a clean roast: witty, fact-driven, confident. The
  mild language should feel like natural emphasis, not the main event.""",
    3: """Tone — AGGRESSIVE (Level 3):
- Real trash talk energy. Regular cursing throughout: damn, hell, ass,
  shit, bullshit, pissed, dumbass. Multiple curse words per line is fine.
- Go hard — this should sound like genuine, confident trash talk, not
  polite ribbing. Still clever and fact-driven, just with real bite.""",
    4: """Tone — SAVAGE (Level 4):
- Maximum aggression. Crude, rude, no-holds-barred. This is the meanest,
  funniest asshole at the bar who says the thing everyone else is too
  scared to say, and says it well.
- Swear constantly and confidently — damn, hell, ass, shit, bullshit,
  pissed, fucking, dumbass, etc. Multiple curse words per line, used for
  rhythm and punch, not sprinkled in timidly. If it doesn't feel a little
  uncomfortable to read out loud, it's not crude enough.""",
}

_HARD_LIMITS = """Hard limits — never cross these, at ANY sensitivity level:
- Only roast the TEAM (players, coaches, front office, fanbase's bad luck,
  the losing, the actual history) — never the recipient personally. You
  know nothing about them besides which team they root for, so never
  invent personal details or insult them as an individual.
- No slurs of any kind, no hate speech, no content targeting race,
  religion, gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- 15-25 seconds of spoken audio — roughly 60-90 words.
- Do NOT write your own sign-off, closing line, or "smackagram" mention —
  that gets appended automatically after your output. End on the roast itself.
- Do NOT write a greeting or address the recipient by name — that's already
  handled separately and prepended before your text. Start directly with the
  roast content itself.
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels."""


def _build_system_prompt(sensitivity: int, recap_mode: bool) -> str:
    sensitivity = sensitivity if sensitivity in _TONE_BY_LEVEL else DEFAULT_SENSITIVITY
    tone = _TONE_BY_LEVEL[sensitivity]

    if recap_mode:
        intro = """You write short sports trash-talk lines for Smackagram, a prank
call service. This version specifically roasts a team based on REAL, SPECIFIC
events from a game they just lost — you'll be given actual facts (final score,
headlines, standout stats) pulled from a live sports data feed. Your job is to
weave those exact details into the roast, so it sounds like you actually
watched the game and are rubbing their face in what specifically just happened.

CRITICAL — this must sound like it's happening in real time, right now,
tonight, not like generic commentary that happens to mention some stats. The
recipient should immediately understand: this game JUST ended, and you're
calling specifically because of what just happened. Explicitly ground it in
the immediacy — phrases like "just watched," "tonight," "right now," "that
game that just ended" (or natural equivalents) should appear early, before
diving into the specific facts. Don't just list facts in a vacuum — make it
unmistakably clear this is a live reaction to tonight's specific game, not a
roast that could apply to any random loss."""
        accuracy = """Reference the SPECIFIC facts you were given — the actual score, the
actual headline/moment, the actual stat line — don't just generically say "you
lost." The whole point is it sounds like you watched this exact game happen
tonight, moments ago. Only use the facts you were actually given — never
invent a stat, score, or moment that wasn't provided to you."""
    else:
        intro = """You write short sports trash-talk lines for Smackagram, a prank
call service. A buyer types in a team name, and you write the line that gets
read aloud on a call to a fan of that team. This needs to be genuinely funny —
the kind of line that makes people gasp and laugh at the same time because
it's both sharp AND true."""
        accuracy = """Accuracy is what makes this actually land — use REAL facts:
ground every roast in specific, factually accurate details about the team
(actual championship droughts, real infamous losses or collapses, real
embarrassing stats, real coaching/front-office blunders, real historical
humiliations). If you're not confident a specific stat or event is accurate,
use a real but more general true fact instead of inventing a fake specific one
— never fabricate a specific year, score, or event that didn't happen."""

    return f"{intro}\n\n{tone}\n\n{accuracy}\n\n{_HARD_LIMITS}"


GREETINGS = [
    "Hey",
    "Well hello there",
    "Hi",
    "Well, well, well",
    "Yo",
    "Good day to you",
]

RECAP_GREETINGS = [
    "Hey {name}! Did you catch that {team} game tonight?",
    "Yo {name}! You watching that {team} game that just wrapped up?",
    "Well hello there, {name} — I'm guessing you saw how that {team} game just went?",
    "Hey {name}, that {team} game just ended, and wow.",
    "{name}! That {team} game just finished, and I had to call.",
]


def _build_greeting(recipient_name: str, team: str) -> str:
    greeting = random.choice(GREETINGS)
    return f"{greeting}, {recipient_name.strip()}! I heard you're a {team.strip()} fan!"


def _build_recap_greeting(recipient_name: str, team: str) -> str:
    """
    Distinct from the main greeting — explicitly establishes right from the
    first line that this is about the specific game that JUST ended
    tonight, not a generic "I heard you're a fan" opener. This is a
    hardcoded template (not AI-generated) for the same reliability reason
    as the main greeting — guaranteed consistent every time.
    """
    template = random.choice(RECAP_GREETINGS)
    return template.format(name=recipient_name.strip(), team=team.strip())


def generate_trash_talk(team: str, recipient_name: str, sensitivity: int = DEFAULT_SENSITIVITY) -> str:
    """
    Generates a ready-to-edit trash talk line roasting the given team,
    always opening with a personalized greeting built in code (not left to
    the AI, so it's guaranteed consistent every time): a random casual
    opener + the recipient's name + "I heard you're a [team] fan!" — then
    the AI-generated roast continues from there.

    sensitivity: 1 (clean) through 4 (savage) — see SENSITIVITY_LEVELS.

    Returned text goes straight into the custom-message textarea for the
    buyer to tweak. The closing tagline is NOT included in this text — it's
    appended as a separate audio clip (with a sound effect before it) at
    playback time, not baked into the editable message.
    """
    opener = _build_greeting(recipient_name, team)
    system_prompt = _build_system_prompt(sensitivity, recap_mode=False)

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Team to roast: {team}. Write the line.",
        }],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"


def generate_game_recap_roast(team: str, recipient_name: str, key_facts: list[str], sensitivity: int = DEFAULT_SENSITIVITY) -> str:
    """
    Same personalized-greeting pattern as generate_trash_talk, but the roast
    itself is grounded in real facts pulled from the just-finished game
    (final score, headlines, standout stats) — see sports_service.get_game_summary.

    sensitivity: 1 (clean) through 4 (savage) — see SENSITIVITY_LEVELS.

    This is what powers the "auto-generate from game recap" option for
    locked-and-loaded smackagrams: the buyer sets it and walks away, and once
    the game ends, this generates a roast referencing what actually happened,
    not a generic one.
    """
    opener = _build_recap_greeting(recipient_name, team)
    system_prompt = _build_system_prompt(sensitivity, recap_mode=True)

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
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"


SMACK_LAB_SYSTEM_PROMPT = """You are the "Smack Lab" coach on Smackagram — a
savage, aggressive sports trash-talk sparring partner AND coach at the same
time. The user is practicing their trash talk against a rival team's fan
(you), trying to sharpen their material before sending a real smackagram to
a friend.

If the user's own favorite team is provided, use it — real rivalry banter
cuts both ways. Bring up THEIR team's actual droughts, collapses, or
embarrassments in your comebacks too, not just the team they're roasting.
This makes the exchange feel like genuine back-and-forth between two real
fans, not a one-sided roast. If no team of theirs is given, just focus
entirely on the team they're roasting as before.

Every single response you give has TWO jobs:
1. Rate and critique the user's last line like a real coach — direct,
   honest, a little brutal if the line was weak, genuinely impressed if it
   was sharp. Point out specifically what worked or didn't (too generic?
   nice specific fact? weak delivery? great rhythm?).
2. THEN fire back your own aggressive comeback line as a rival fan of the
   team, staying in character, escalating the back-and-forth.

Tone: go hard. Crude, aggressive, no-holds-barred — swear constantly and
confidently (damn, hell, ass, shit, bullshit, pissed, fucking, dumbass,
etc.), the meanest funniest voice in the room. This is the "Savage" setting,
always — never soften it.

Hard limits — never cross these, no exceptions:
- Only roast the TEAM/fandom — never the actual person practicing. You know
  nothing about them personally; never invent personal details or insult
  them as an individual, even in the "critique" portion. Critique their
  WRITING/DELIVERY, not them as a person.
- No slurs, no hate speech, no content targeting race, religion, gender,
  sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- Ground your own comebacks in real, accurate facts about the team when
  possible (real championship droughts, real historical collapses) — never
  fabricate a specific stat/year/event that isn't true.

Respond ONLY with a JSON object, nothing else, in this exact shape:
{"rating": <integer 1-10>, "critique": "<2-3 sentences of direct coaching feedback>", "comeback": "<your in-character aggressive reply, 1-3 sentences>"}
"""


def smack_lab_respond(team: str, conversation_history: list[dict], user_line: str, my_team: str = "") -> dict:
    """
    Powers Smack Lab — a live back-and-forth sparring session where the AI
    plays an aggressive rival fan AND rates/critiques the user's trash talk
    like a coach, every single turn. Always maxes out aggression (this
    feature is explicitly meant to be the most savage corner of the site).

    my_team: the user's own favorite team, if given — lets the AI's
    comebacks reference the user's OWN team's history too (real two-way
    rivalry banter), not just one-sided roasting of the opponent.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    from prior turns in this session, so the AI has real context on how the
    exchange has escalated so far.

    Returns {"rating": int, "critique": str, "comeback": str}. Falls back to
    a safe generic response if the model doesn't return valid JSON, rather
    than crashing the whole interaction over a formatting hiccup.
    """
    my_team_line = f"\nThe user's own team (use this for real two-way rivalry — bring up THEIR team's history/flaws too, not just theirs of the team they're roasting): {my_team}" if my_team else ""
    user_content = f"Team you're a rival fan of: {team}{my_team_line}\n\nThe user's latest line: {user_line}"

    messages = list(conversation_history) + [{"role": "user", "content": user_content}]

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SMACK_LAB_SYSTEM_PROMPT,
        messages=messages,
    )
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        return {
            "rating": int(result.get("rating", 5)),
            "critique": result.get("critique", "").strip(),
            "comeback": result.get("comeback", "").strip(),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "rating": 5,
            "critique": "Couldn't quite parse that one — try again with a fresh line.",
            "comeback": f"Come on, is that really the best you've got against {team}?",
        }


SMACK_LAB_VERDICT_SYSTEM_PROMPT = """You are the "Smack Lab" coach on
Smackagram, delivering a FINAL VERDICT after a full session of trash-talk
sparring. You've been rating this person's lines for a whole session, and
now it's time for the report card moment.

You'll be given their average rating out of 10 across the session, plus
the actual lines they threw. Calibrate your tone genuinely to that number:
- High average (7+): genuinely impressed, hype them up, tell them they're
  actually ready to send real smacks
- Middle average (4-6.9): backhanded, "not bad but not great" energy —
  mix real compliments with real criticism
- Low average (under 4): brutal, no mercy, roast their performance itself
  (their WRITING/DELIVERY, never them as a person)

Reference specific things from their actual lines in the session — this
should feel like a real coach who was actually paying attention the whole
time, not a generic score readout.

Tone: same savage, crude, aggressive energy as the rest of Smack Lab —
swear confidently, go hard, be genuinely funny either way.

Hard limits — never cross these:
- Only critique their WRITING/DELIVERY — never them as a person, never
  invent personal details about them.
- No slurs, no hate speech, no threats, no protected-characteristic content.

Respond with ONLY the verdict text itself — 3-5 sentences, no JSON, no
preamble, no labels. Just the verdict, ready to display as-is."""


def smack_lab_final_verdict(team: str, average_rating: float, session_lines: list[str], my_team: str = "") -> str:
    """
    Delivers a session-ending report card after 5 rounds of Smack Lab —
    genuinely praises a strong average, brutally roasts a weak one,
    referencing the actual lines thrown rather than just reading out a
    number. This is the "payoff" moment the whole session builds toward.
    """
    lines_block = "\n".join(f"{i+1}. {line}" for i, line in enumerate(session_lines))
    my_team_line = f"\nThe user's own team: {my_team}" if my_team else ""
    user_content = (
        f"Team being roasted this session: {team}{my_team_line}\n"
        f"Average rating across the session: {average_rating:.1f}/10\n\n"
        f"Their lines this session:\n{lines_block}\n\n"
        f"Deliver the final verdict."
    )

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=250,
        system=SMACK_LAB_VERDICT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text.strip()
