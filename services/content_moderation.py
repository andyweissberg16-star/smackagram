import os
import json
import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# This is a SAFETY GATE, not a taste filter. It exists to catch the small
# number of genuinely dangerous submissions — real threats, sexual content
# involving minors, predatory/non-consensual sexual content, hate speech,
# harassment-style doxxing — in user-TYPED custom messages before they can
# be dialed out to a real phone number. It is deliberately narrow: ordinary
# crude trash talk about a sports team (even with heavy profanity) is not
# what this is for, and should pass through fine. AI-generated content
# already has its own guardrails baked into its system prompt; this check
# exists specifically for freeform user-typed text, which has none.
_MODERATION_SYSTEM_PROMPT = """You are a safety classifier for a prank-call
service. A user has typed a custom message that will be read aloud, via
text-to-speech, on a real phone call to a real person (the buyer confirms
they know the recipient, but content is not otherwise reviewed by a human).

Your ONLY job is to flag genuinely dangerous content — not to judge taste,
crudeness, or whether the joke is funny. Ordinary sports trash talk, even
aggressive or heavily profane, is NOT a violation and should pass.

Flag as UNSAFE only if the message contains any of:
- A genuine, credible threat of violence or physical harm against anyone
- Sexual content involving minors, in any form
- Non-consensual sexual content, sexual harassment, or predatory/grooming-style content directed at the recipient
- Hate speech or slurs targeting race, religion, gender, sexuality, disability, or other protected characteristics
- Doxxing-style content (real addresses, real financial/personal identifying info) used to harass
- Real-world tragedy exploitation used to torment someone

Do NOT flag: profanity, crude jokes, sports-related insults, mean-spirited
but non-threatening trash talk, or dark humor that isn't a genuine threat.

Respond with ONLY a JSON object, nothing else:
{"unsafe": true or false, "reason": "brief category if unsafe, otherwise null"}
"""


def check_message_safety(text: str) -> dict:
    """
    Returns {"safe": bool, "reason": str|None}. Fails safe (blocks) if the
    classifier call itself errors out — better to occasionally block a
    legitimate message and require a retry than to silently let a check
    failure allow something dangerous through.
    """
    if not text or not text.strip():
        return {"safe": True, "reason": None}

    try:
        message = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            system=_MODERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = message.content[0].text.strip()
        # strip potential markdown code fences before parsing
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        unsafe = bool(result.get("unsafe"))
        return {"safe": not unsafe, "reason": result.get("reason") if unsafe else None}
    except Exception as e:
        print(f"[content_moderation] check failed, blocking as a precaution: {e}")
        return {"safe": False, "reason": "moderation check unavailable — please try again"}
