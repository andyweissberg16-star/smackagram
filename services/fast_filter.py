"""
The fast check, before anything else.
=====================================
content_moderation asks a model whether text is acceptable. That handles
CATEGORIES well - it understands intent, sarcasm, and a threat phrased as a
joke. But it costs a round trip, and it can time out.

This runs first, locally, instantly. It catches the obvious so the model
call is spent on the genuinely ambiguous.

TWO TIERS, AND THE DIFFERENCE MATTERS
-------------------------------------
STYLE swaps get rewritten quietly. "Idiot" becoming "clown" is a house-voice
decision and nobody needs to know.

BLOCKED categories are never rewritten. The temptation is to swap a threat
for something harmless and carry on - but that means a call goes out that
was ALMOST a threat, and the safety log never records it. You would lose the
one signal telling you a generator has started drifting somewhere bad.

So blocked means: refuse, regenerate, and record it.

WHAT THIS IS NOT
----------------
Not a substitute for the model check. A word list cannot understand "I'll
end him", which is a threat in one context and a normal thing to say about
a basketball matchup in another. Both layers run.
"""

import re

# ---------------------------------------------------------------------------
# BLOCKED. Refuse and regenerate - never rewrite.
# ---------------------------------------------------------------------------
#
# Deliberately short. A long list of individual words is impossible to
# maintain and misses anything phrased differently, which is what the model
# check is for. These are the ones where an instant, certain refusal is
# better than a probabilistic one.

_THREAT = [
    r"\bkill (?:you|him|her|them|yourself|himself|herself)\b",
    r"\bmurder(?:ing)? (?:you|him|her|them)\b",
    r"\b(?:shoot|stab|strangle|hang|torture) (?:you|him|her|them)\b",
    r"\bbeat (?:you|him|her|them) to death\b",
    r"\bburn (?:you|him|her|them|it) (?:alive|down)\b",
    r"\bhope (?:you|he|she|they) die\b",
    r"\bi(?:'| a)?m coming (?:for|after) you\b",
    r"\bi will find you\b",
    r"\bdestroy your life\b",
    r"\bbomb (?:the|his|her|their|your)\b",
]

_SELF_HARM = [
    r"\b(?:kill|hang|off) yourself\b",
    r"\bkys\b",
    r"\bcommit suicide\b",
    r"\bslit (?:your|his|her)\b",
    r"\bself[- ]harm\b",
    r"\boverdose\b",
]

# Traits rather than performance. The rule everywhere else on this product
# is that the roast lands on the game, and this is that rule made literal.
_TRAITS = [
    # ONLY WHEN IT DESCRIBES A PERSON.
    #
    # The first version matched any of these words within thirty characters
    # of "you", which blocked "that defence was disgusting and you know it"
    # and "an ugly night for you" - both completely normal sports talk. In
    # this vocabulary "disgusting" and "filthy" are COMPLIMENTS.
    #
    # Every generation attempt got blocked, all three retries failed, and
    # the site said "couldn't generate right now". A filter that fires on
    # ordinary output is worse than no filter, because it takes the product
    # down instead of a bad line.
    #
    # So: the word has to be attached to a PERSON - "you're fat", "he's
    # ugly", "your fat face". Describing a performance is fine.
    # Both apostrophes - the model produces the curly one as often as the
    # straight one, and "he's ugly" leaked straight through a pattern that
    # only knew about "he is".
    r"\b(?:you|he|she|they)\s*(?:'|\u2019)?(?:re|s)?\s*"
    r"(?:are|is)?\s*(?:so\s+)?(?:fat|obese|ugly|hideous)\b",
    r"\byour (?:fat|ugly|hideous)\b",
    r"\bretard(?:ed)?\b",
    r"\b(?:cripple|crippled|spastic)\b",
    r"\byour (?:mother|mom|wife|girlfriend|kids|children|family)\b",
    r"\bgo back to (?:your|his|her) country\b",
]

_CRIME = [
    r"\bhow to (?:make|build) (?:a )?(?:bomb|explosive|weapon)\b",
    r"\bcredit card (?:number|fraud)\b",
    r"\bsocial security number\b",
    r"\bidentity theft\b",
]

# Inventing a crime about a real person. Not a joke - a false statement of
# fact about somebody who could be named on the call.
_DEFAMATION = [
    r"\b(?:he|she|they)(?:'s| is| are)? (?:a )?(?:criminal|drug dealer|"
    r"rapist|paedophile|pedophile)\b",
    # "They threw the game" is what every fan says about a bad night. Only
    # an explicit accusation of CORRUPTION belongs here.
    r"\b(?:fixing|fixed) (?:the )?(?:game|match|series) for money\b",
    r"\bpaid to (?:lose|throw)\b",
    r"\bbetting against (?:his|her|their) own team\b",
    r"\bon (?:steroids|peds)\b",
    r"\bbetting on (?:his|her|their) own\b",
]

# CELEBRATING AN INJURY.
#
# Injured players are now offered in the name picker, because the best
# player on a team is often the one who is out - and "you are losing without
# him" is a fair joke. "I am glad he got hurt" is not, and the prompt rule
# alone is not enough now that those names are being handed over
# deliberately.
#
# The ABSENCE is fair game. The injury never is.
_INJURY_GLEE = [
    # "glad he tore..." - the verb can come after the sentiment.
    r"\b(?:glad|happy|pleased|delighted)\b[^.!?]{0,40}"
    r"\b(?:hurt|injur\w*|tore|torn|broke|broken|snapped|blew out)\b",
    r"\b(?:hurt|injur\w+|tore|torn|broke)\b[^.!?]{0,30}\b(?:and|so)\b"
    r"[^.!?]{0,20}\b(?:glad|happy|deserved|good)\b",
    # "hope he stays hurt", "hope he never plays again"
    r"\bhope\b[^.!?]{0,40}\b(?:gets? hurt|stays? (?:hurt|injured|out)|"
    r"tears?|breaks?|never plays?)\b",
    r"\bdeserved (?:that|the|it)\b[^.!?]{0,20}\b(?:injury|tear|break)?\b"
    r"(?=[^.!?]{0,20}\b(?:injur|hurt|tore|torn)\b)|"
    r"\bdeserved (?:that|the) (?:injury|tear|break)\b",
    r"\bstays? (?:hurt|injured|on the (?:il|shelf))\b",
    # "career-ending" about a PERSON only. A career-ending decision by a
    # general manager is ordinary sports talk.
    r"\bcareer[- ]ending\b(?![^.!?]{0,30}\b(?:mistake|decision|trade|"
    r"signing|move|contract)\b)",
]

BLOCKED = [
    ("injury_glee", _INJURY_GLEE),
    ("threat", _THREAT),
    ("self_harm", _SELF_HARM),
    ("personal_traits", _TRAITS),
    ("dangerous_instructions", _CRIME),
    ("defamation", _DEFAMATION),
]

# ---------------------------------------------------------------------------
# STYLE. Rewritten quietly - these are voice decisions, not safety ones.
# ---------------------------------------------------------------------------
#
# Every replacement is something Smacky would actually say, so the swap is an
# improvement rather than a euphemism. A filter that made the writing blander
# would not survive contact with the product.
STYLE_SWAPS = [
    (r"\bidiots?\b", "clown"),
    (r"\bmorons?\b", "bozo"),
    (r"\bstupid\b", "brainless"),
    (r"\bterrible\b", "a certified disaster"),
    (r"\bawful\b", "a dumpster fire"),
    (r"\boverrated\b", "a fraud"),
    (r"\bpathetic\b", "embarrassing"),
    (r"\btrash\b", "a walking L"),
    (r"\bgarbage\b", "a dumpster fire"),
]


def _hits(text, patterns):
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return None


def check(text):
    """
    Fast local verdict.

    {"ok": True, "text": ...}                       fine, possibly restyled
    {"ok": False, "category": ..., "excerpt": ...}   refuse and regenerate
    """
    if not text:
        return {"ok": True, "text": ""}

    raw = str(text)

    for category, patterns in BLOCKED:
        hit = _hits(raw, patterns)
        if hit:
            return {"ok": False, "category": category, "excerpt": hit[:120]}

    out = raw
    swapped = []
    for pattern, replacement in STYLE_SWAPS:
        if re.search(pattern, out, re.I):
            out = re.sub(pattern, replacement, out, flags=re.I)
            swapped.append(replacement)

    return {"ok": True, "text": out, "restyled": swapped}


def is_blocked(text):
    """Just the verdict, for anywhere that only needs a yes or no."""
    return not check(text).get("ok", True)
