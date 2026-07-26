import os
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
