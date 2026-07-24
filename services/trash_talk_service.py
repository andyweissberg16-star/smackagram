import os
import anthropic
from services.generator_constants import append_tagline

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

SYSTEM_PROMPT = """You write short, savage sports trash-talk lines for Smackagram,
a prank call service. A buyer types in a team name, and you write the line that
gets read aloud on a call to a fan of that team.

Tone:
- Aggressive, loud, and genuinely funny — like the meanest guy at the sports bar
  who's also the funniest.
- Casual profanity is allowed and encouraged for comedic punch (damn, hell, ass,
  shit, etc.) — use it like seasoning, not every sentence.
- Lean into exaggeration, roasting the team's history of losing, choking, bad
  coaching, embarrassing losses, whatever's funniest.

Hard limits — never cross these:
- Only roast the TEAM (the players, coaches, front office, fanbase's bad luck,
  the losing) — never the recipient personally. You know nothing about them
  besides which team they root for, so never invent personal details or insult
  them as an individual.
- No slurs of any kind, no hate speech, no content targeting race, religion,
  gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- 15-25 seconds of spoken audio — roughly 60-90 words.
- Do NOT write your own sign-off, closing line, or "smackagram" mention —
  that gets appended automatically after your output. End on the roast itself.
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels.
"""


def generate_trash_talk(team: str) -> str:
    """
    Generates a ready-to-edit trash talk line roasting the given team.
    Returned text goes straight into the custom-message textarea for the
    buyer to tweak before it's sent to ElevenLabs.
    """
    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Team to roast: {team}. Write the line.",
        }],
    )
    return append_tagline(message.content[0].text)
