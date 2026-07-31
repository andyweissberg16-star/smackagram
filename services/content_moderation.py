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
{"unsafe": true or false,
 "category": "one of: threat, minors, sexual, hate, doxxing, tragedy — or null",
 "excerpt": "the exact words from the message that caused this, copied verbatim — or null",
 "reason": "one short plain sentence explaining what's wrong — or null"}

The excerpt must be copied EXACTLY from the user's message, word for word, so
it can be highlighted back to them. Quote only the offending part, not the
whole message.
"""


def check_message_safety(text: str) -> dict:
    """
    Returns a verdict about a user-typed message.

    Three outcomes, deliberately distinguished, because they need completely
    different handling and the previous version collapsed two of them:

      {"safe": True}
          Fine, send it.

      {"safe": False, "available": True, "category", "excerpt", "reason"}
          A genuine violation. The excerpt is the offending words copied out
          of their message, so the UI can show them exactly what to change
          instead of making them guess.

      {"safe": False, "available": False}
          The CHECK ITSELF failed - a timeout, a rate limit, an outage. There
          is nothing wrong with their message and nothing for them to edit.
          Previously this returned the same shape as a violation and told
          people to "edit that part", which is both wrong and impossible to
          act on.
    """
    if not text or not text.strip():
        return {"safe": True, "available": True}

    try:
        message = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_MODERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = message.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        if not bool(result.get("unsafe")):
            return {"safe": True, "available": True}

        category = (result.get("category") or "").strip().lower()
        excerpt = (result.get("excerpt") or "").strip()

        # Only trust an excerpt that genuinely appears in the message. A
        # paraphrase would highlight nothing and look broken.
        if excerpt and excerpt.lower() not in text.lower():
            excerpt = ""

        # For child-safety categories we name the problem but do NOT quote the
        # text back or coach a fix. Telling someone precisely which words
        # tripped this is a map for getting the next attempt through, and that
        # is not a trade worth making for a smoother error message.
        if category == "minors":
            return {
                "safe": False, "available": True, "category": category,
                "excerpt": "",
                "reason": "This can't be sent.",
            }

        return {
            "safe": False, "available": True,
            "category": category or "policy",
            "excerpt": excerpt,
            "reason": (result.get("reason") or "").strip() or "This breaks our content rules.",
        }

    except Exception as e:
        # Still fails closed - an unchecked message must not go out. But it is
        # reported honestly as OUR failure rather than the user's.
        print(f"[content_moderation] check failed, blocking as a precaution: {e}")
        return {"safe": False, "available": False,
                "reason": "We couldn't run the safety check just now."}
