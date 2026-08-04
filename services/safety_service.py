"""
Safety events: record them, and say so.
=======================================
Everything the moderation gate stopped used to be a print() to the Render
log. That log rolls off, and nobody reads it at two in the morning - so a
block would happen, the customer would be refunded, and nobody would learn
it had occurred.

WHY THIS MATTERS IN BOTH DIRECTIONS
-----------------------------------
If somebody is repeatedly probing the generators, you want to know tonight
rather than from a complaint later.

But if the gate is firing on HARMLESS messages, you want to know that just
as much: a false positive costs a paying customer the call they bought, and
they will not tell you - they will just leave.

WHAT IS AND IS NOT STORED
-------------------------
The offending excerpt only, never the whole message. Enough to judge whether
the block was right; not a transcript of everything anybody has typed into
the site.
"""

import os
from datetime import datetime, timedelta, timezone

from models import SafetyEvent, db

# Alert on the first block from a user, and on a burst from anyone.
#
# One block is usually somebody testing the edges and finding it - normal,
# and not worth waking up for on its own. THREE inside an hour is somebody
# working at it, and that is worth knowing immediately.
BURST_COUNT = 3
BURST_MINUTES = 60


def record(surface, stage, verdict, user_id=None, record_type=None,
           record_id=None, refunded=False):
    """
    Log a block, and alert if it looks like a pattern.

    Never raises. A failure here must not take down the thing that was
    already correctly refusing to send something.
    """
    try:
        ev = SafetyEvent(
            surface=surface,
            stage=stage,
            user_id=user_id,
            record_type=record_type,
            record_id=record_id,
            category=(verdict or {}).get("category"),
            reason=(verdict or {}).get("reason"),
            excerpt=((verdict or {}).get("excerpt") or "")[:400],
            refunded=bool(refunded),
        )
        db.session.add(ev)
        db.session.commit()

        print(f"[safety] {surface}/{stage} blocked "
              f"({ev.category}) user={user_id} id={ev.id}", flush=True)

        _maybe_alert(ev)
        return ev
    except Exception as e:
        db.session.rollback()
        print(f"[safety] could not record event: {e}", flush=True)
        return None


def _maybe_alert(ev):
    """Text the admin if this looks like more than a one-off."""
    try:
        since = datetime.now(timezone.utc) - timedelta(minutes=BURST_MINUTES)
        q = SafetyEvent.query.filter(SafetyEvent.created_at >= since)
        if ev.user_id:
            q = q.filter(SafetyEvent.user_id == ev.user_id)
        recent = q.count()

        # Generated-output blocks are rarer and more serious than input
        # blocks: it means OUR OWN writer produced something the gate
        # refused, which is a different problem from a user typing an
        # insult into a box.
        urgent = ev.stage in ("generated", "fire-time")

        if recent >= BURST_COUNT or urgent:
            who = f"user {ev.user_id}" if ev.user_id else "an anonymous visitor"
            body = (f"Smackagram safety: {ev.surface} / {ev.stage} blocked "
                    f"({ev.category}) from {who}. "
                    f"{recent} in the last hour. /admin to review.")
            _notify(body)
    except Exception as e:
        print(f"[safety] alert check failed: {e}", flush=True)


def _notify(body):
    """
    Text the admin.

    Uses the Twilio number the site already sends from. Silently skipped if
    ADMIN_ALERT_PHONE is not set, so this cannot break anything by being
    unconfigured - it simply does not alert until you want it to.
    """
    to = os.environ.get("ADMIN_ALERT_PHONE")
    if not to:
        print(f"[safety] ALERT (no ADMIN_ALERT_PHONE set): {body}", flush=True)
        return
    try:
        from services import twilio_service
        twilio_service.send_sms(to, body[:300])
        print("[safety] admin alerted by SMS", flush=True)
    except Exception as e:
        # SMS is blocked on A2P approval, so this will fail for now. The
        # event is still recorded and still visible in /admin - the alert is
        # the convenience, the record is the point.
        print(f"[safety] SMS alert failed ({e}). Event is still recorded.",
              flush=True)


def recent(limit=100, only_unreviewed=False):
    """For the admin panel."""
    q = SafetyEvent.query.order_by(SafetyEvent.id.desc())
    if only_unreviewed:
        q = q.filter(SafetyEvent.reviewed.is_(False))
    rows = q.limit(min(limit, 300)).all()
    return [{
        "id": r.id,
        "when": (utc_iso(r.created_at) or None),
        "surface": r.surface,
        "stage": r.stage,
        "user_id": r.user_id,
        "category": r.category,
        "reason": r.reason,
        "excerpt": r.excerpt,
        "refunded": bool(r.refunded),
        "reviewed": bool(r.reviewed),
    } for r in rows]


def summary(days=7):
    """Counts, so a rising trend is visible rather than a wall of rows."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = SafetyEvent.query.filter(SafetyEvent.created_at >= since).all()
    by_cat, by_surface, by_stage = {}, {}, {}
    for r in rows:
        by_cat[r.category or "?"] = by_cat.get(r.category or "?", 0) + 1
        by_surface[r.surface or "?"] = by_surface.get(r.surface or "?", 0) + 1
        by_stage[r.stage or "?"] = by_stage.get(r.stage or "?", 0) + 1
    return {
        "days": days,
        "total": len(rows),
        "unreviewed": sum(1 for r in rows if not r.reviewed),
        # The one to watch. An input block is a user testing the edges; a
        # generated block means our own writer produced something the gate
        # refused, which is a different and more serious thing.
        "our_own_output": by_stage.get("generated", 0) + by_stage.get("fire-time", 0),
        "by_category": by_cat,
        "by_surface": by_surface,
        "by_stage": by_stage,
    }

def utc_iso(dt):
    """
    A timestamp the browser will read correctly.

    Everything here stores UTC via datetime.utcnow(), which produces a
    NAIVE datetime - no timezone attached. isoformat() on that gives a
    string with no marker, and JavaScript reads a marker-less timestamp as
    LOCAL time.

    So a smack sent at 7:36pm in Florida was stored as 23:36 UTC and shown
    as 11:36pm. Four hours out, and out by a different amount per user.

    The Z says "this is UTC" and every browser converts it correctly.
    """
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.isoformat()
    except AttributeError:
        return None
