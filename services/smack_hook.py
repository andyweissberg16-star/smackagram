"""
Pull the punchline from a smack for the feed hook.

The feed shows one sharp line above the player so a silent scroller
reads the joke and wants to tap. Rather than a second AI call per smack
(slow, and money adds up at volume), this picks the best line from the
script Smacky already wrote - which is text we already have.

Heuristic, tuned to how Smacky's scripts are built:
  * drop the greeting / opener (first sentence is usually "Well well,
    look who lost" throat-clearing, not the joke)
  * drop anything that's just the score or a bare fact
  * prefer a line with a comparison or a hard image ("couldn't find X
    with a Y") - that's where the punch lands
  * a roast almost always ends on its best beat, so the last real
    sentence is a strong default
  * keep it short enough to read at a glance
"""

import re

_MAXLEN = 200


def _sentences(text):
    if not text:
        return []
    # Split on sentence enders but keep it simple; smack scripts are
    # short and conversational.
    parts = re.split(r'(?<=[.!?])\s+', str(text).strip())
    return [p.strip() for p in parts if p.strip()]


def _is_weak(s):
    low = s.lower()
    # Bare score lines, pure setup, or too-short fragments make bad hooks.
    if len(s) < 18:
        return True
    if re.search(r'\b\d+\s*[-\u2013]\s*\d+\b', s) and len(s) < 40:
        return True  # mostly just a score
    if low.startswith(("well", "oh ", "so ", "hey", "look who",
                       "guess who", "knock knock")):
        return True
    return False


def _punch_score(s):
    """Higher = punchier. Rewards comparisons and vivid constructions."""
    low = s.lower()
    score = 0
    if " with a " in low or " like a " in low:
        score += 3          # "...clutch hit with a metal detector"
    if any(w in low for w in ("couldn't", "can't", "wouldn't",
                              "only thing", "somewhere", "at least")):
        score += 2
    if "?" in s or "!" in s:
        score += 1
    # Middle-length lines land best; very long ones ramble.
    if 30 <= len(s) <= 130:
        score += 2
    return score


def extract_hook(body):
    """Return the best single hook line from a smack body, or '' if none."""
    sents = _sentences(body)
    if not sents:
        return ""

    strong = [s for s in sents if not _is_weak(s)]
    pool = strong or sents

    # Rank by punch; on a tie prefer the later line (roasts end on the joke).
    best = None
    best_key = None
    for i, s in enumerate(pool):
        key = (_punch_score(s), i)
        if best_key is None or key > best_key:
            best_key = key
            best = s

    hook = (best or sents[-1]).strip().strip('"\u201c\u201d')
    if len(hook) > _MAXLEN:
        hook = hook[:_MAXLEN].rsplit(" ", 1)[0] + "\u2026"
    return hook
