"""
Sports headlines for The Smacky Report — the daily on-air show.

The important part of this module is not fetching news. It's REFUSING news.

Sports headlines routinely include deaths, serious injuries, cancer
diagnoses, domestic violence arrests, overdoses, suicides and CTE. On those
days "Smacky's take" is not edgy, it is the screenshot that ends the brand.
Since the show publishes unreviewed, the safeguard cannot be checking the
output after the fact — it has to be refusing the input before anything is
written.

So: every headline is screened twice. A fast keyword pass drops the obvious
cases for free, then a model pass catches what wording alone misses ("placed
on the non-football injury list", "away from the team for personal reasons").
Anything that fails either check never reaches the writer.

The bar is deliberately paranoid. Skipping a usable story costs nothing —
there are always more. Publishing one roast about a dead athlete costs
everything.
"""

import os
import json
import anthropic
import requests

from services import sports_service
from datetime import datetime, timedelta

_client = None


def _get_client():
    """Lazy, matching the other services - no client is built unless news
    actually runs."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

BASE = "https://api.sportsdata.io/v3"

# Same key and league paths the scores already use — news is on the same
# subscription, so this adds no cost and no new vendor.
SPORT_PATHS = {
    "nfl": "nfl",
    "nba": "nba",
    "mlb": "mlb",
    "nhl": "nhl",
    "ncaaf": "cfb",
    "ncaab": "cbb",
    "wnba": "wnba",
}

# Fast reject pass. Cheap, runs on every headline, catches the obvious cases
# before spending a model call. Substring matching on a lowered string, so
# fragments are deliberate: "arrest" catches "arrested", "arrests".
# Fast reject pass. Deliberately PHRASE-based rather than word-based: the
# first version used bare words like "shot", "cut", "crash" and "loss" and
# rejected 75% of an ordinary news day - "cut from the roster", "shot 4-for-19",
# "crash the boards" are all normal sports language. A filter that blocks
# everything isn't safe, it's just broken.
#
# So these are terms that are almost never innocent in a sports headline.
# Ambiguous ones are left to the model pass, which can read context.
BANNED_TERMS = [
    # death and grief
    "died", "dies", "death", "passed away", "obituary", "funeral", "memorial",
    "fatally", "killed", "mourns", "mourning", "condolence", "tragic death",
    "remembering", "in memory of", "laid to rest",
    # self-harm and mental health
    "suicide", "took his own life", "took her own life", "mental health",
    "depression", "rehab", "overdose", "addiction", "substance abuse",
    "checked into", "treatment facility",
    # serious medical
    "cancer", "tumor", "tumour", "chemotherapy", "diagnosed with",
    "hospitalized", "hospitalised", "intensive care", "life support", "coma",
    "stroke", "heart attack", "cardiac", "collapsed on", "seizure",
    "paralyzed", "paralysed", "cte", "brain injury", "als", "life-threatening",
    "critical condition", "medical emergency",
    # crime and abuse
    "arrested", "arrest warrant", "charged with", "indicted", "convicted",
    "sentenced", "pleads guilty", "assault", "domestic violence",
    "sexual", "abuse", "misconduct", "harassment", "trafficking",
    "dui", "dwi", "shooting", "stabbed", "gunshot", "homicide",
    "criminal", "felony", "restraining order", "allegations of",
    # discrimination
    "racist", "racism", "slur", "homophobic", "antisemit", "discrimination",
    "hate speech",
    # serious accidents
    "car accident", "car crash", "plane crash", "hospital",
    # career-ending / long-term injury framing
    "career-ending", "season-ending", "torn acl", "achilles tear",
    "ruptured", "surgery", "non-football injury", "personal reasons",
    "away from the team", "stepping away", "leave of absence",
]

# What the show IS about. Not used to filter — used to rank, so the most
# roastable stories float to the top once the unsafe ones are gone.
JUICY_TERMS = [
    "blowout", "collapse", "choke", "benched", "cut", "released", "traded",
    "fired", "ejected", "meltdown", "blown lead", "loss", "lost", "slump",
    "streak", "contract", "holdout", "feud", "called out", "criticized",
    "criticised", "rant", "referee", "officiating", "controversy", "upset",
    "shutout", "swept", "eliminated", "record low", "worst",
]


def _api_key() -> str:
    """
    Deliberately delegates to sports_service rather than reading the
    environment directly. The variable is SPORTSDATA_API_KEY (no "IO"), and
    duplicating that string here is exactly how this module shipped broken -
    it read SPORTSDATAIO_API_KEY and every fetch failed. One accessor, one
    name, one place to get it wrong.
    """
    return sports_service._api_key()


def fetch_headlines(sport: str, days_back: int = 1) -> list[dict]:
    """
    Pulls one league's news for a given day. Yesterday by default, since the
    show covers what happened rather than what's happening.
    """
    path = SPORT_PATHS.get(sport)
    if not path:
        return []

    # Uses /News rather than /NewsByDate. NewsByDate returned nothing on this
    # subscription; /News is confirmed working and returns the recent feed,
    # which we date-filter below. One endpoint that works beats a tidier one
    # that doesn't.
    url = f"{BASE}/{path}/scores/json/News"
    try:
        resp = requests.get(url, params={"key": _api_key()}, timeout=15)
        if resp.status_code != 200:
            print(f"[news] {sport} -> HTTP {resp.status_code}: {resp.text[:160]}")
            return []
        items = resp.json() or []
    except Exception as e:
        print(f"[news] {sport} fetch failed: {e}")
        return []

    print(f"[news] {sport}: {len(items)} items returned by /News")

    # Keep a window rather than a single day. The feed's density varies by
    # league and season - a strict one-day match can legitimately return
    # nothing, which reads as a broken pull rather than a quiet day.
    # Wide by design. Late July is the quietest week in sport - NBA and NHL
    # fully out of season, NFL barely into camp - and a narrow window there
    # returns almost nothing. A story from a few days ago still roasts fine.
    cutoff = datetime.utcnow() - timedelta(days=max(days_back + 1, 5))
    windowed = []
    for i in items:
        stamp = (i.get("Updated") or "")[:19]
        if not stamp:
            windowed.append(i)
            continue
        try:
            if datetime.fromisoformat(stamp) >= cutoff:
                windowed.append(i)
        except ValueError:
            windowed.append(i)

    print(f"[news] {sport}: {len(windowed)} within the last {days_back + 1} day(s)")
    items = windowed

    return [
        {
            "sport": sport,
            "title": (i.get("Title") or "").strip(),
            "content": (i.get("Content") or "").strip(),
            "source": i.get("Source") or "",
            "updated": i.get("Updated") or "",
            "team": i.get("Team") or "",
            "player": i.get("PlayerID"),
        }
        for i in items
        if (i.get("Title") or "").strip()
    ]


def keyword_hit(item: dict) -> str | None:
    """
    Returns the banned term that rejected this story, or None if it passed.
    Naming the term matters: the admin view exists so the FILTER can be
    judged, and "rejected" without a reason can't be argued with.
    """
    haystack = f"{item.get('title','')} {item.get('content','')}".lower()
    for term in BANNED_TERMS:
        if term in haystack:
            return term
    return None


def keyword_safe(item: dict) -> bool:
    """
    First pass. Free, instant, and catches the majority. Checks the body as
    well as the headline — a harmless-looking title often sits on top of an
    article about an arrest.
    """
    haystack = f"{item.get('title','')} {item.get('content','')}".lower()
    return not any(term in haystack for term in BANNED_TERMS)


def _juice_score(item: dict) -> int:
    """How roastable a story is. Ranking only — never used to reject."""
    haystack = f"{item.get('title','')} {item.get('content','')}".lower()
    return sum(1 for t in JUICY_TERMS if t in haystack)


def model_safe(items: list[dict]) -> list[dict]:
    """
    Second pass. Wording alone misses plenty — "placed on the non-football
    injury list", "away from the team for personal reasons", "stepping back
    to focus on family" — all of which can sit on top of something serious.
    A model reads each headline and decides whether it is safe to be funny
    about.

    Fails CLOSED. If this call errors, every story is dropped rather than
    waved through, because the whole point is that nobody reviews the output.
    """
    if not items:
        return []

    numbered = "\n".join(f"{n+1}. {i['title']}" for n, i in enumerate(items))
    prompt = (
        "You screen sports headlines for a comedy show that mocks teams and "
        "players. Decide which headlines are SAFE to make jokes about.\n\n"
        "UNSAFE — anything touching death, grief, serious injury or illness, "
        "mental health, addiction, crime, arrests, lawsuits, abuse, "
        "discrimination, accidents, or a person's family misfortune. Also "
        "unsafe if the story is really about any of those even when the "
        "wording is neutral (e.g. 'away from the team for personal reasons', "
        "'non-football injury list', 'stepping away').\n\n"
        "SAFE — losses, blowouts, chokes, benchings, trades, contract "
        "disputes, feuds, bad officiating, slumps, poor performance, "
        "front-office decisions, fan reactions.\n\n"
        "When uncertain, mark it UNSAFE.\n\n"
        f"Headlines:\n{numbered}\n\n"
        'Reply with JSON only: {"safe": [1, 4, 7]} listing the numbers of the '
        "safe headlines. No other text."
    )

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        text = text.replace("```json", "").replace("```", "").strip()
        keep = set(json.loads(text).get("safe", []))
    except Exception as e:
        # Fail closed. An unreviewed show built on an unscreened list is the
        # exact failure this module exists to prevent.
        print(f"[news] safety screen failed, dropping everything: {e}")
        return []

    return [item for n, item in enumerate(items, start=1) if n in keep]


def get_show_stories(sports=None, want=6) -> list[dict]:
    """
    The full pipeline: pull, screen twice, rank, return.

    Returns fewer than `want` — possibly zero — when not enough stories
    survive. The caller is expected to keep yesterday's show up rather than
    publish something thin.
    """
    sports = sports or list(SPORT_PATHS.keys())

    raw = []
    for sport in sports:
        raw.extend(fetch_headlines(sport))

    # Same story often appears across outlets; keep one per headline.
    seen, deduped = set(), []
    for item in raw:
        key = item["title"].lower()[:70]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    passed_keywords = [i for i in deduped if keyword_safe(i)]
    print(f"[news] {len(deduped)} headlines -> {len(passed_keywords)} past keyword screen")

    passed_model = model_safe(passed_keywords)
    print(f"[news] {len(passed_model)} past model screen")

    passed_model.sort(key=_juice_score, reverse=True)
    return passed_model[:want]
