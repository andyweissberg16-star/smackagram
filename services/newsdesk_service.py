"""
The Smacky Report - News Desk.
================================
Smacky, reporting on real games as they finish. One short article per
game, written entirely from box-score data already on hand - never
from a scraped headline or another outlet's article text.

NOT TO BE CONFUSED WITH services/news_service.py, which is a separate,
existing system: a two-pass safety screen over real sports HEADLINES
for the Daily Smack show, built specifically to keep tragic real-world
news (deaths, injuries, arrests) away from Smacky. That module already
exists and is doing important work - this one is deliberately named
differently to avoid colliding with it.

WHY THIS BUILDS FROM BOX SCORES, NOT SCRAPED HEADLINES: see the
research trail logged to memory on 8 Aug 2026. AP News is blocked
outright and aggressive about reuse. Publisher RSS (Fox Sports etc.)
is restricted to non-commercial use. Official league sites (NBA.com,
MLB.com) explicitly forbid reproducing ANY site content - including
stats - without written permission. A licensed commercial news API is
the only clean path to real outside headlines, and that's a real
recurring cost - deferred until this v1 (game recaps from data we
already have) proves itself.

THE SHAPE: one NewsArticle row per game. Written short - this is a
news-desk hit, not a Daily Smack segment - a headline and 2-4 short
paragraphs, Smacky's voice, grounded only in the real score and
whatever named box-score facts came back with the game.

LEAGUES: MLB first, since mlb_statsapi.py is the most reliable data
source in the whole pipeline (real local dates, finals within minutes,
season records on the schedule). Built so another league is a new
_articles_for_<league>() function plus a row in LEAGUE_FINALS, not a
rewrite.
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def _eastern_yesterday():
    return (datetime.now(EASTERN) - timedelta(days=1)).strftime("%Y-%m-%d")


# Same hard limits every other Smacky writer in this codebase is built
# under - see services/smackcast_service.py. Imported rather than
# copied so a future edit to the guardrail reaches every writer at once.
def _hard_limits():
    from services.smackcast_service import _HARD_LIMITS
    return _HARD_LIMITS


def _get_client():
    from services.smackcast_service import _get_client as _gc
    return _gc()


def _write_article(game, facts, league_label):
    """
    One Claude call, one article. Returns {"headline": ..., "body": ...}
    or None on any failure - a game that fails to write just doesn't
    appear, rather than showing a broken card.
    """
    home, away = game["home"], game["away"]
    hs, aws = game["home_score"], game["away_score"]
    winner, loser = game["winner"], game["loser"]

    facts_block = ("\n".join(f"- {f}" for f in facts) if facts
                   else "No box score detail available - work from the "
                        "final score alone.")

    system = (
        "You are Smacky, the sports-desk voice of Smackagram, writing a "
        "short news-style recap of a single real game that just finished. "
        "This is a NEWS ARTICLE, not a call script - written to be read, "
        "not spoken aloud. Still funny, still Smacky, but shaped like a "
        "short sports-desk item: a punchy headline, then 2-4 short "
        "paragraphs.\n\n"
        + _hard_limits() + "\n\n"
        "FORMAT: reply with JSON only, no markdown fences:\n"
        '{"headline": "...", "body": "..."}\n'
        "headline: under 12 words, no team-name-first wire-service "
        "phrasing like 'Yankees Defeat Red Sox' - make it a real hook.\n"
        "body: 2-4 short paragraphs (roughly 80-150 words total), plain "
        "text, no markdown, no headline repeated inside it."
    )
    user = (
        f"LEAGUE: {league_label}\n"
        f"FINAL: {away} {aws} @ {home} {hs}\n"
        f"WINNER: {winner}   LOSER: {loser}\n\n"
        f"BOX SCORE FACTS (only ones you may use - never invent a name, "
        f"a stat, or an injury not listed here):\n{facts_block}\n\n"
        "Write the article now."
    )

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        text = text.replace("```json", "").replace("```", "").strip()
        import json as _json
        try:
            out = _json.loads(text)
        except Exception:
            out, _end = _json.JSONDecoder().raw_decode(text)
        headline = (out.get("headline") or "").strip()
        body = (out.get("body") or "").strip()
        if not headline or not body:
            return None
        return {"headline": headline, "body": body}
    except Exception as e:
        print(f"[newsdesk] write failed for {away}@{home}: "
              f"{type(e).__name__}: {e}", flush=True)
        return None


def generate_mlb_articles(date_str=None, limit=None):
    """
    Write and store one article per finished MLB game on the given
    Eastern day (defaults to yesterday - the day a morning run is about).

    Idempotent per game: NewsArticle has a unique constraint on
    (league, source_game_id), so re-running a day that's already been
    written skips games that already have an article rather than
    duplicating or double-billing the API.

    Returns a summary dict for logging / the admin panel.
    """
    from services import mlb_statsapi
    from models import db, NewsArticle

    day = date_str or _eastern_yesterday()
    finals = mlb_statsapi.finals(day)
    if not finals:
        print(f"[newsdesk] mlb {day}: no finished games", flush=True)
        return {"league": "mlb", "date": day, "written": 0,
                "skipped": 0, "failed": 0, "total": 0}

    rows = list(finals.values())
    if limit:
        rows = rows[:limit]

    written = skipped = failed = 0
    for g in rows:
        gid = str(g.get("id") or "")
        if not gid:
            continue
        # Skip games already written up - the unique constraint would
        # catch this on insert too, but checking first avoids spending
        # a Claude call on a game we're about to throw away.
        exists = NewsArticle.query.filter_by(
            league="mlb", source_game_id=gid).first()
        if exists:
            skipped += 1
            continue

        facts = []
        try:
            pk = g.get("id")
            detail = mlb_statsapi.game_detail(
                pk, g.get("winner") or "", g.get("loser") or "")
            if detail:
                facts = mlb_statsapi.named_facts(detail) or []
        except Exception as e:
            print(f"[newsdesk] mlb detail failed for game {gid}: {e}",
                  flush=True)

        article = _write_article(g, facts, "MLB")
        if not article:
            failed += 1
            continue

        row = NewsArticle(
            league="mlb",
            game_date=day,
            home_team=g.get("home"),
            away_team=g.get("away"),
            home_score=g.get("home_score"),
            away_score=g.get("away_score"),
            winner=g.get("winner"),
            loser=g.get("loser"),
            headline=article["headline"],
            body=article["body"],
            source_game_id=gid,
        )
        db.session.add(row)
        try:
            db.session.commit()
            written += 1
        except Exception as e:
            db.session.rollback()
            # Unique-constraint race (two workers writing the same game
            # at once) lands here - not a real failure, just a skip.
            print(f"[newsdesk] mlb game {gid} not saved (likely already "
                  f"exists): {e}", flush=True)
            skipped += 1

    summary = {"league": "mlb", "date": day, "written": written,
               "skipped": skipped, "failed": failed, "total": len(rows)}
    print(f"[newsdesk] mlb {day}: {summary}", flush=True)
    return summary
