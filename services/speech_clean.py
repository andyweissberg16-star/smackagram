"""
Cleaning text before it is spoken.
==================================
Anything that goes to ElevenLabs has to survive being read ALOUD, and that
is a different bar from looking right on a screen.

WHY THIS EXISTS
---------------
A real Smackagram about the Dodgers went out saying "ASTERISK" out loud. The
model had written the 2020-title joke as `title*`, or used markdown emphasis
somewhere, and the engine dutifully pronounced the character.

The Daily Smack has had a 157-line sanitiser for a while. THE CALL PATH HAD
NONE - whatever the model produced went straight to the voice. So the show
was protected and the flagship product was not.

This is the small, shared version: the things that break a spoken line
regardless of which generator wrote it. The show keeps its own longer one
for sports notation, which a phone call rarely contains.
"""

import re

# Characters the engine will happily read out by name, or that leave an
# audible stumble. Markdown is the usual source - a model asked for emphasis
# reaches for asterisks whether or not anybody wanted them.
_SPOKEN_SYMBOLS = {
    "*": "",
    "_": " ",
    "#": "",
    "~": "",
    "`": "",
    "|": " ",
    "^": "",
    "\\": " ",
    "<": " ",
    ">": " ",
    "{": " ",
    "}": " ",
    "[": " ",
    "]": " ",
}

# Typographic quotes and dashes. These are usually fine, but the em dash in
# particular gets read as a pause of unpredictable length, and smart quotes
# occasionally surface as "quote".
_TYPOGRAPHIC = {
    "\u2014": ", ",     # em dash
    "\u2013": ", ",     # en dash
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": "",
    "\u201d": "",
    "\u2026": "...",
    "\u00a0": " ",
}

# Written-out stage directions. A model told to sound casual sometimes
# produces "(laughs)" or "[sighs]", and the engine reads the words.
_STAGE = re.compile(
    r"[\(\[]\s*(laughs?|laughing|sighs?|pause|beat|chuckles?|scoffs?|"
    r"clears throat|coughs?|silence|music|sfx|sound effect)[^\)\]]*[\)\]]",
    re.I)


def clean_for_speech(text: str) -> str:
    """
    Make a line safe to read aloud.

    Conservative on purpose: it removes things that WILL be mispronounced
    and leaves everything else alone. A sanitiser that rewrites too much
    flattens the voice, and the voice is the product.
    """
    if not text:
        return ""

    out = str(text)

    # Stage directions first, before the brackets around them are stripped
    # and the words inside are left stranded in the sentence.
    out = _STAGE.sub(" ", out)

    for a, b in _TYPOGRAPHIC.items():
        out = out.replace(a, b)

    # A markdown-emphasised phrase should keep its words and lose its marks:
    # "*absolutely* nobody" must not become "absolutely nobody" with a
    # spoken asterisk on either side.
    out = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", out)
    out = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", out)

    for a, b in _SPOKEN_SYMBOLS.items():
        out = out.replace(a, b)

    # An asterisk used as a footnote marker - "champions*" - is a joke that
    # only works in writing. Spoken, it is either silence or the word
    # itself, and neither lands.
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)

    return out.strip()


def would_be_spoken(text: str) -> list:
    """
    What in this line would be read aloud wrongly.

    For the admin trace and for tests - it names the problem rather than
    silently fixing it, which is how you find out a generator has started
    producing something new.
    """
    found = []
    if not text:
        return found
    if "*" in text:
        found.append("asterisk")
    if _STAGE.search(text):
        found.append("stage direction in brackets")
    if re.search(r"[_#~`|^<>{}\[\]]", text):
        found.append("markdown or bracket characters")
    if "\u2014" in text or "\u2013" in text:
        found.append("em/en dash")
    return found
