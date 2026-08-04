"""
Player names, kept.
===================
The picker reads from here rather than fetching a squad live on every use.

WHAT THIS FIXES
---------------
Speed: a database read instead of two or three HTTP requests.

Resilience: it works when every provider is unreachable, which was most of
4 August.

AND AARON JUDGE. A player on the injured list appears in no recent roster,
and Highlightly's baseball feed carries no injuries block at all - so
somebody out for six weeks is invisible in live data. But he was in a
roster before he got hurt. Storing names as they are seen means the picker
keeps offering him long after he stops appearing, which is exactly what
somebody typing his name wants.

HOW IT FILLS UP
---------------
Every time a squad is fetched for any reason - the picker, the show, the
roast facts - the names go in. No separate job to run and no backfill to
remember: it accumulates from ordinary use.

A name is never deleted, only stamped with when it was last seen.
"""

from datetime import datetime, timedelta

from models import db, Player


def _clean(s):
    return (s or "").strip()


def remember(league, team, players, source="highlightly"):
    """
    Store or refresh a squad. Returns how many names were new.

    Safe to call constantly - an existing name is a timestamp update, not
    an insert.
    """
    league = (league or "").lower()
    team = _clean(team)
    if not league or not team or not players:
        return 0

    existing = {p.name.lower(): p for p in
                Player.query.filter_by(league=league, team=team).all()}
    now = datetime.utcnow()
    added = 0

    for p in players:
        nm = _clean(p.get("name"))
        if not nm:
            continue
        got = existing.get(nm.lower())
        if got:
            got.last_seen = now
            # Fill in details we did not have before - a box score gives a
            # name with no position, a team sheet gives both.
            if p.get("position") and not got.position:
                got.position = str(p["position"])[:40]
            if p.get("number") and not got.jersey:
                got.jersey = str(p["number"])[:8]
            continue
        db.session.add(Player(
            name=nm, team=team, league=league,
            position=(str(p["position"])[:40] if p.get("position") else None),
            jersey=(str(p["number"])[:8] if p.get("number") else None),
            source=source, last_seen=now, first_seen=now,
        ))
        added += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[players] could not store {team}: {e}", flush=True)
        return 0

    if added:
        print(f"[players] {team} ({league}): {added} new, "
              f"{len(players) - added} refreshed", flush=True)
    return added


def squad(league, team, stale_days=400):
    """
    Everyone we know plays for this team.

    Returns the shape the picker already renders, with "away" set on
    anybody who has not appeared in a fortnight - which is the honest
    version of "injured" from data that never says so directly.

    Sorted by who was seen most recently, so the people actually playing
    come first and somebody long gone sits at the bottom.
    """
    league = (league or "").lower()
    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    rows = (Player.query
            .filter(Player.league == league,
                    Player.team == _clean(team),
                    Player.last_seen >= cutoff)
            .order_by(Player.last_seen.desc())
            .all())

    fortnight = datetime.utcnow() - timedelta(days=14)
    out = []
    for r in rows:
        out.append({
            "name": r.name,
            "position": r.position,
            "number": r.jersey,
            # NOT called "injured". No feed tells us that, and saying it
            # would be inventing a fact about somebody's health. "Has not
            # played recently" is what the data actually supports - and
            # "he has not been seen in a month" is the better line anyway.
            "away": r.last_seen < fortnight,
            "last_seen": r.last_seen.strftime("%Y-%m-%d"),
        })
    return out


def count(league=None):
    q = Player.query
    if league:
        q = q.filter(Player.league == league.lower())
    return q.count()


def teams_known(league=None):
    q = db.session.query(Player.team, Player.league).distinct()
    if league:
        q = q.filter(Player.league == league.lower())
    return [{"team": t, "league": l} for t, l in q.all()]
