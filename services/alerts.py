"""
System alerts.
==============
Something broke - who finds out, and how quickly.

THE PROBLEM THIS SOLVES
-----------------------
There are around thirty-five places in this codebase that detect a failure
and print it. A print goes to a log nobody is reading at three in the
morning, which means the first person to notice a broken product is a
customer.

THE PROBLEM THIS AVOIDS
-----------------------
Alert fatigue. If ESPN blocks the server and thirty requests fail in a
minute, that is ONE problem, not thirty texts. An alerting system that
cries wolf gets muted, and a muted alerting system is worse than none
because everybody believes they are covered.

So: every failure is RECORDED, and only the first of a kind in a window
is SENT. The count keeps rising in the record whether or not a message
goes out.

SEVERITY
--------
  critical  money or delivery is affected. Somebody paid and did not get
            what they paid for, or is about to be charged wrongly.
  error     a product is degraded. The show is thin, the board is empty.
  warning   something to look at, nothing is broken yet.

Only critical and error send a message. Warnings accumulate in the record
and are read when somebody looks.
"""

import os
import threading
import time
from datetime import datetime, timedelta

# How long the same kind of failure stays quiet after alerting once.
QUIET_SECONDS = {
    "critical": 900,    # 15 minutes - it matters, but ten texts do not help
    "error": 3600,      # an hour
    "warning": 0,       # never sent
}

_lock = threading.Lock()
_last_sent = {}


def _key(system, kind):
    return f"{system}:{kind}"


def record(system, kind, detail="", severity="error", send=True):
    """
    Note that something failed, and tell somebody if it is worth telling.

    system    which part - "espn", "twilio", "stripe", "email", "show"
    kind      what went wrong - "blocked", "call_failed", "send_failed"
    detail    the specifics, for the record rather than the message
    severity  critical | error | warning

    Never raises. An alerting system that can break the thing it is
    watching is worse than no alerting system.
    """
    line = f"[alert:{severity}] {system}/{kind}: {detail}"
    print(line, flush=True)

    try:
        from models import db, SystemAlert
        now = datetime.utcnow()
        # Roll up repeats rather than filling the table with the same row.
        existing = (SystemAlert.query
                    .filter_by(system=system, kind=kind, resolved=False)
                    .order_by(SystemAlert.last_seen.desc()).first())
        if existing:
            existing.count += 1
            existing.last_seen = now
            existing.detail = (detail or "")[:500]
        else:
            db.session.add(SystemAlert(
                system=system, kind=kind, severity=severity,
                detail=(detail or "")[:500], count=1,
                first_seen=now, last_seen=now))
        db.session.commit()
    except Exception as e:
        # Recording failed - carry on and still try to alert. Losing the
        # record is bad; losing the alert as well would be worse.
        print(f"[alert] could not record: {e}", flush=True)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass

    if not send:
        return
    quiet = QUIET_SECONDS.get(severity, 3600)
    if quiet <= 0:
        return

    k = _key(system, kind)
    now_t = time.time()
    with _lock:
        if now_t - _last_sent.get(k, 0) < quiet:
            return                      # already told them, recently
        _last_sent[k] = now_t

    line = f"{severity.upper()} {system}/{kind}: {(detail or '')[:200]}"
    sent_by = []

    # EMAIL FIRST, because it is the channel that actually works.
    #
    # SMS is blocked behind A2P approval, which has been rejected once
    # and is not yet resubmitted. An alerting system whose only channel
    # is blocked is not an alerting system - it is a log with ambition.
    try:
        from services import mail
        if mail.configured():
            ok, _ = mail.send(
                os.environ.get("SUPPORT_INBOX", "owners@smackagram.com"),
                f"[Smackagram {severity.upper()}] {system}/{kind}",
                f"{line}\n\n"
                f"Seen at {datetime.utcnow().isoformat()}Z\n\n"
                f"This is an automatic alert. Open the admin panel to see "
                f"what else is outstanding:\n"
                f"https://smackagram.com/admin\n")
            if ok:
                sent_by.append("email")
    except Exception as e:
        print(f"[alert] email failed: {e}", flush=True)

    # And SMS, for when A2P clears. Tried second because it is the one
    # that currently cannot deliver.
    try:
        from services import safety_service
        if safety_service._notify(line[:300]):
            sent_by.append("sms")
    except Exception as e:
        print(f"[alert] sms failed: {e}", flush=True)

    if not sent_by:
        print(f"[alert] NOBODY WAS TOLD about {system}/{kind} - no email "
              f"provider and no working SMS. It is in the admin panel "
              f"only.", flush=True)


def open_alerts(limit=50):
    """Everything currently unresolved, worst and most recent first."""
    from models import SystemAlert
    order = {"critical": 0, "error": 1, "warning": 2}
    rows = (SystemAlert.query.filter_by(resolved=False)
            .order_by(SystemAlert.last_seen.desc()).limit(limit).all())
    return sorted(rows, key=lambda r: (order.get(r.severity, 3),
                                       -(r.last_seen or datetime.min).timestamp()))


def resolve(alert_id, by=None):
    """Mark one as handled. Does not delete it - the history is the point."""
    from models import db, SystemAlert
    a = SystemAlert.query.get(alert_id)
    if not a:
        return False
    a.resolved = True
    a.resolved_at = datetime.utcnow()
    a.resolved_by = by
    db.session.commit()
    # Let it alert again if it comes back after being cleared.
    with _lock:
        _last_sent.pop(_key(a.system, a.kind), None)
    return True
