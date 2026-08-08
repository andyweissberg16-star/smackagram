"""
Site analytics.
===============
What the admin page could not answer before: how many people came, what they
looked at, and where they stopped.

The money side was already tracked - revenue, signups, smacks sent. None of
that tells you whether a quiet day was a traffic problem or a conversion
problem, and those need opposite responses.

COUNTED, NOT LOGGED
-------------------
One row per path per day, incremented. Not one row per request - a busy day
would write tens of thousands of rows onto the same Postgres instance that is
serving the site, to answer a question a counter answers just as well.

WHAT IS DELIBERATELY NOT COLLECTED
----------------------------------
No IP addresses, no user agents, no cross-day identifiers. Visitors are
counted with a hash that includes the DATE, so the same person tomorrow is a
different number and nobody can be followed between days. This is a traffic
counter, not a surveillance record - and on a site whose whole promise is
that the recipient never finds out who sent the call, that distinction is
worth keeping.
"""

import datetime
import hashlib
import os

from models import db, PageStat

# Paths worth counting. Everything else is folded into "other" rather than
# creating a row per URL - share links alone would produce thousands.
TRACKED = {
    "/": "home",
    "/send-a-smack": "send a smackagram",
    "/auto-smack": "locked & loaded",
    "/smackcast": "smackcast",
    "/daily-smack": "the daily smack",
    "/smack-board": "smack board",
    "/did-you-get-smacked": "smack back",
    "/smack-lab": "smack lab",
    "/smack-battle": "smack battle",
    "/meet-smacky": "meet smacky",
    "/locker": "locker",
    "/profile": "profile",
    "/login": "login",
    "/register": "register",
    "/opt-out": "opt out",
    "/smacky-makes-the-call": "smacky makes the call",
}

# Seen-today keys, so a visitor is counted once per path per day without
# storing anything about them. Cleared when the date rolls over.
_seen = set()
_seen_day = None


def _visitor_key(request, day):
    """
    A number that identifies a browser FOR ONE DAY ONLY.

    The date is part of the hash, so tomorrow the same browser produces a
    different key and cannot be linked to today's. That is the point: it
    makes "how many people" answerable without making "who" answerable.
    """
    raw = "|".join([
        request.headers.get("X-Forwarded-For", "") or request.remote_addr or "",
        request.headers.get("User-Agent", "")[:80],
        str(day),
        os.environ.get("SECRET_KEY", "smackagram")[:16],
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def record(request, is_logged_in=False):
    """
    Count one page view. Never raises - analytics must not break a page.
    """
    global _seen, _seen_day
    try:
        path = (request.path or "/").rstrip("/") or "/"
        if path not in TRACKED:
            # Only the pages that matter. A row per share link would be
            # thousands of rows answering nothing.
            return

        day = datetime.date.today()
        if _seen_day != day:
            _seen, _seen_day = set(), day

        key = (path, _visitor_key(request, day))
        first_today = key not in _seen
        if first_today:
            _seen.add(key)

        row = PageStat.query.filter_by(day=day, path=path).first()
        if row is None:
            row = PageStat(day=day, path=path, views=0, visitors=0, logged_in=0)
            db.session.add(row)
        row.views = (row.views or 0) + 1
        if first_today:
            row.visitors = (row.visitors or 0) + 1
        if is_logged_in:
            row.logged_in = (row.logged_in or 0) + 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[analytics] not recorded: {e}", flush=True)


def _rows(days):
    since = datetime.date.today() - datetime.timedelta(days=days - 1)
    return PageStat.query.filter(PageStat.day >= since).all()


def summary(days=7):
    """
    Traffic for the last N days, plus the funnel.

    The funnel is the part that matters. Revenue alone cannot tell you
    whether a quiet day was fewer visitors or worse conversion, and those
    need opposite responses - one is a marketing problem, the other is a
    product problem.
    """
    from models import Order, User

    rows = _rows(days)
    by_path = {}
    for r in rows:
        e = by_path.setdefault(r.path, {"views": 0, "visitors": 0, "logged_in": 0})
        e["views"] += r.views or 0
        e["visitors"] += r.visitors or 0
        e["logged_in"] += r.logged_in or 0

    pages = sorted(
        ({"path": p, "name": TRACKED.get(p, p), **v} for p, v in by_path.items()),
        key=lambda x: -x["views"])

    # Day by day, for the shape rather than the total.
    by_day = {}
    for r in rows:
        d = str(r.day)
        e = by_day.setdefault(d, {"views": 0, "visitors": 0})
        e["views"] += r.views or 0
        e["visitors"] += r.visitors or 0
    daily = [{"day": d, **v} for d, v in sorted(by_day.items())]

    home = by_path.get("/", {}).get("visitors", 0)
    gens = sum(by_path.get(p, {}).get("visitors", 0)
               for p in ("/send-a-smack", "/auto-smack"))

    since_dt = datetime.datetime.combine(
        datetime.date.today() - datetime.timedelta(days=days - 1),
        datetime.time.min)
    orders = Order.query.filter(Order.created_at >= since_dt).count()
    signups = User.query.filter(User.created_at >= since_dt).count()

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "days": days,
        "pages": pages,
        "daily": daily,
        "totals": {
            "views": sum(p["views"] for p in pages),
            "visitors": sum(p["visitors"] for p in pages),
        },
        # Each step as a share of the one before it, which is where a drop
        # actually shows. Totals hide it.
        "funnel": {
            "home_visitors": home,
            "reached_a_generator": gens,
            "signed_up": signups,
            "ordered": orders,
            "home_to_generator_pct": pct(gens, home),
            "generator_to_order_pct": pct(orders, gens),
        },
        "note": ("Unique Visitors = distinct visitors PER DAY, summed across "
                 "this window - not the same as distinct people over the "
                 "whole period. Someone who visits on two different days in "
                 "this window counts twice, since visitors are counted by a "
                 "daily-rotating hash and nobody is tracked across days (no "
                 "IP or user agent stored). New-vs-returning visitor tracking "
                 "would need a longer-lived identifier and isn't built."),
    }
