# Shared constants across all AI/text generators (trash talk, and any future
# generators — scenario writer, roast bot, etc.). Keeping this in one place
# means every generated line ends with the exact same brand sign-off.

CLOSING_TAGLINE = "You've just been smacked by Smackagram. Have a nice day."


def append_tagline(generated_text: str) -> str:
    """Appends the standard sign-off to any generated line."""
    return f"{generated_text.strip()} {CLOSING_TAGLINE}"
