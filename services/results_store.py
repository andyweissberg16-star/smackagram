"""
Finished games, remembered.
===========================
A final score never changes. This stores each one the first time it is seen
and reads from the database ever after.

WHY
---
Every part of this site was re-asking a provider the same settled question.
When ESPN blocked this server on 4 August, the site lost access to games
that had finished the night before - games it had already fetched
successfully and simply thrown away.

That is the failure worth removing, and it is independent of which provider
is used. A stored result survives every outage, every rate limit, every
provider change and every billing lapse.

MATCHING ACROSS PROVIDERS
-------------------------
ESPN, Highlightly and SportsDataIO all use different game ids, so a game is
identified by LEAGUE + DATE + THE TWO TEAMS. Team names differ slightly
between providers ("New York Yankees" against "Yankees"), so only the LAST
WORD is compared - which is the nickname in every league that matters.

FIRST WRITER WINS
-----------------
If a second provider later disagrees, the stored result is NOT changed. The
disagreement is recorded and logged instead.

Silently rewriting a result is worse than being wrong consistently: Locked
& Loaded may already have called somebody and charged them based on the
first answer. Changing it afterwards means the database and the customer's
phone now tell different stories, and nothing anywhere would show why.
"""

from datetime import datetime

from models import db, GameResult


def _nick(name):
    """Last word of a team name - the bit providers agree on."""
    return (name or "").strip().split()[-1].lower() if name else ""


def _key(league, date_str, a, b):
    return (league.lower(), date_str, tuple(sorted([_nick(a), _nick(b)])))


def lookup(league, date_str, team_a, team_b):
    """A stored result for this pairing, or None."""
    want = _key(league, date_str, team_a, team_b)
    rows = GameResult.query.filter_by(league=league.lower(),
                                      game_date=date_str).all()
    for r in rows:
        if _key(r.league, r.game_date, r.winner, r.loser) == want:
            return r
    return None


def remember(league, date_str, result, source, ids=None):
    """
    Store a finished game, or note a disagreement with what is already there.

    result is {winner, loser, winner_score, loser_score, margin}.
    Returns the stored row - which may be the EXISTING one if it differs.
    """
    if not result or not result.get("winner") or not result.get("loser"):
        return None

    existing = lookup(league, date_str, result["winner"], result["loser"])
    if existing:
        same = (_nick(existing.loser) == _nick(result["loser"])
                and existing.winner_score == result.get("winner_score")
                and existing.loser_score == result.get("loser_score"))
        if not same and not existing.contested:
            # Record it, do not overwrite. See the module docstring.
            note = (f"{existing.source} said {existing.winner} "
                    f"{existing.winner_score}-{existing.loser_score} "
                    f"{existing.loser}; {source} said {result['winner']} "
                    f"{result.get('winner_score')}-"
                    f"{result.get('loser_score')} {result['loser']}")
            existing.contested = True
            existing.contested_note = note
            db.session.commit()
            wrong_loser = _nick(existing.loser) != _nick(result["loser"])
            print(f"[results] {'WRONG LOSER' if wrong_loser else 'score'} "
                  f"DISAGREEMENT: {note}", flush=True)
        return existing

    ids = ids or {}
    row = GameResult(
        league=league.lower(), game_date=date_str,
        winner=result["winner"], loser=result["loser"],
        winner_score=result.get("winner_score"),
        loser_score=result.get("loser_score"),
        margin=result.get("margin"),
        source=source,
        espn_event_id=ids.get("espn"),
        highlightly_id=ids.get("highlightly"),
        sportsdata_id=ids.get("sportsdata"),
    )
    db.session.add(row)
    db.session.commit()
    return row


def remember_many(league, date_str, results, source, id_field="highlightly"):
    """
    Store a whole night at once.

    results is {provider_id: {winner, loser, ...}} - the shape both
    league_results and highlightly.finals already return.
    """
    stored = contested = 0
    for pid, r in (results or {}).items():
        try:
            before = lookup(league, date_str, r.get("winner"), r.get("loser"))
            row = remember(league, date_str, r, source, {id_field: str(pid)})
            if row is None:
                continue
            if before is None:
                stored += 1
            elif row.contested:
                contested += 1
        except Exception as e:
            print(f"[results] could not store {pid}: {e}", flush=True)
            db.session.rollback()
    if stored or contested:
        print(f"[results] {league} {date_str}: {stored} new, "
              f"{contested} contested", flush=True)
    return stored


def known(league, date_str):
    """
    Everything already stored for a date, as {nickname_pair: result}.

    Callers use this BEFORE asking a provider - if the answer is already
    known, no request is made at all. That is what makes an outage cost
    nothing for games that already finished.
    """
    out = {}
    for r in GameResult.query.filter_by(league=league.lower(),
                                        game_date=date_str).all():
        out[_key(r.league, r.game_date, r.winner, r.loser)] = {
            "final": True,
            "winner": r.winner, "loser": r.loser,
            "winner_score": r.winner_score, "loser_score": r.loser_score,
            "margin": r.margin,
            "source": r.source, "stored": True,
        }
    return out
