"""
Data behind the admin panel.

Money here is reconstructed from the LEDGER (WalletTransaction) rather than
read off balance_cents, and revenue comes from actual Stripe-confirmed rows
rather than intent. The distinction matters: a wallet balance is a cached
number, and "what did we take" is a question you want answered from the
append-only record, not from a mutable field that could have drifted.

Free credits granted by an admin are deliberately EXCLUDED from revenue.
They're a cost, not income, and folding them in would inflate the only number
on the page that has to be trustworthy.
"""

from datetime import datetime, timedelta

from sqlalchemy import func

from models import (
    db, User, Order, Smackagram, WalletTransaction,
    SmackcastPurchase, SmackcastSubscription,
)

# Ledger reasons that represent an admin giveaway rather than money taken.
# Kept as a tuple so revenue queries can exclude them in one place.
# WalletTransaction records transaction_type, not "reason". These are the
# types that represent an admin giveaway rather than money taken.
COMP_TYPES = ("admin_grant", "comp", "promo")


def _cents(v):
    return int(v or 0)


def accounting_summary() -> dict:
    """
    The numbers that actually matter, over a few windows.

    Wallet top-ups and Smackcast purchases are counted separately because
    they're different products with different economics - lumping them into
    one "revenue" figure hides which one is working.
    """
    now = datetime.utcnow()
    windows = {
        "today": now - timedelta(days=1),
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
        "all": datetime(2000, 1, 1),
    }

    out = {}
    for label, since in windows.items():
        # Real money in: positive ledger entries that AREN'T admin comps.
        topups = db.session.query(
            func.coalesce(func.sum(WalletTransaction.amount_cents), 0)
        ).filter(
            WalletTransaction.amount_cents > 0,
            WalletTransaction.created_at >= since,
            ~WalletTransaction.transaction_type.in_(COMP_TYPES),
        ).scalar()

        smackcast = db.session.query(
            func.coalesce(func.sum(SmackcastPurchase.amount_cents), 0)
        ).filter(
            SmackcastPurchase.status == "paid",
            SmackcastPurchase.created_at >= since,
        ).scalar()

        # Comped separately - a cost to track, never revenue.
        comped = db.session.query(
            func.coalesce(func.sum(WalletTransaction.amount_cents), 0)
        ).filter(
            WalletTransaction.amount_cents > 0,
            WalletTransaction.created_at >= since,
            WalletTransaction.transaction_type.in_(COMP_TYPES),
        ).scalar()

        out[label] = {
            "topups_cents": _cents(topups),
            "smackcast_cents": _cents(smackcast),
            "total_cents": _cents(topups) + _cents(smackcast),
            "comped_cents": _cents(comped),
            "new_users": User.query.filter(User.created_at >= since).count(),
            "smacks_sent": Order.query.filter(Order.created_at >= since).count(),
        }

    # Outstanding liability: credits sold but not yet spent. This is money
    # already taken that still owes a service, which is worth seeing next to
    # revenue rather than buried.
    out["outstanding_balance_cents"] = _cents(
        db.session.query(func.coalesce(func.sum(User.balance_cents), 0)).scalar()
    )
    out["total_users"] = User.query.count()
    out["total_orders"] = Order.query.count()
    out["armed_pending"] = Smackagram.query.filter_by(status="armed").count()
    return out


def customer_list(search: str = "", limit: int = 50) -> list[dict]:
    """Customers, newest first, optionally filtered by name, email or number."""
    q = User.query
    if search:
        term = f"%{search.strip()}%"
        conditions = [
            User.email.ilike(term),
            User.screen_name.ilike(term),
            User.first_name.ilike(term),
            User.last_name.ilike(term),
            User.phone.ilike(term),
        ]
        if search.strip().isdigit():
            conditions.append(User.customer_number == int(search.strip()))
        q = q.filter(db.or_(*conditions))

    users = q.order_by(User.id.desc()).limit(limit).all()

    out = []
    for u in users:
        spent = db.session.query(
            func.coalesce(func.sum(WalletTransaction.amount_cents), 0)
        ).filter(
            WalletTransaction.user_id == u.id,
            WalletTransaction.amount_cents > 0,
            ~WalletTransaction.transaction_type.in_(COMP_TYPES),
        ).scalar()

        out.append({
            "id": u.id,
            "customer_number": u.customer_number,
            "name": f"{u.first_name} {u.last_name}".strip(),
            "screen_name": u.screen_name,
            "email": u.email,
            "phone": u.phone,
            "balance_cents": u.balance_cents,
            "balance_smacks": u.balance_cents // 100,
            "lifetime_spend_cents": _cents(spent),
            "orders": Order.query.filter_by(user_id=u.id).count(),
            "is_admin": bool(u.is_admin),
            "created_at": (utc_iso(u.created_at) or ""),
        })
    return out


def customer_detail(user_id: int) -> dict | None:
    """Everything about one customer: ledger, orders, smackcast, locker."""
    u = User.query.get(user_id)
    if not u:
        return None

    ledger = WalletTransaction.query.filter_by(user_id=u.id) \
        .order_by(WalletTransaction.id.desc()).limit(60).all()

    orders = Order.query.filter_by(user_id=u.id) \
        .order_by(Order.id.desc()).limit(40).all()

    armed = Smackagram.query.filter_by(user_id=u.id) \
        .order_by(Smackagram.id.desc()).limit(40).all() \
        if hasattr(Smackagram, "user_id") else []

    purchases = SmackcastPurchase.query.filter_by(user_id=u.id) \
        .order_by(SmackcastPurchase.id.desc()).all()

    spent = db.session.query(
        func.coalesce(func.sum(WalletTransaction.amount_cents), 0)
    ).filter(
        WalletTransaction.user_id == u.id,
        WalletTransaction.amount_cents > 0,
        ~WalletTransaction.transaction_type.in_(COMP_TYPES),
    ).scalar()

    comped = db.session.query(
        func.coalesce(func.sum(WalletTransaction.amount_cents), 0)
    ).filter(
        WalletTransaction.user_id == u.id,
        WalletTransaction.transaction_type.in_(COMP_TYPES),
    ).scalar()

    return {
        "id": u.id,
        "customer_number": u.customer_number,
        "name": f"{u.first_name} {u.last_name}".strip(),
        "screen_name": u.screen_name,
        "email": u.email,
        "phone": u.phone,
        "is_admin": bool(u.is_admin),
        "created_at": (utc_iso(u.created_at) or ""),
        "balance_cents": u.balance_cents,
        "balance_smacks": u.balance_cents // 100,
        "lifetime_spend_cents": _cents(spent),
        "comped_cents": _cents(comped),

        "ledger": [{
            "id": t.id,
            "amount_cents": t.amount_cents,
            "type": t.transaction_type,
            "description": getattr(t, "description", "") or "",
            "balance_after_cents": t.balance_after_cents,
            "created_at": (utc_iso(t.created_at) or ""),
        } for t in ledger],

        "orders": [{
            "id": o.id,
            "recipient_name": getattr(o, "recipient_name", "") or "",
                        "price_cents": o.price_cents,
            "payment_status": o.payment_status,
            "call_status": o.call_status,
            "recording_url": getattr(o, "recording_url", None),
            "audio_url": getattr(o, "audio_url", None),
            "created_at": (utc_iso(o.created_at) or ""),
        } for o in orders],

        "armed": [{
            "id": s.id,
            "recipient_name": getattr(s, "recipient_name", "") or "",
                        "status": s.status,
            "created_at": (utc_iso(s.created_at) or ""),
        } for s in armed],

        "smackcast": [{
            "id": p.id,
            "amount_cents": p.amount_cents,
            "status": p.status,
            "league_slots": p.league_slots,
            "slots_used": getattr(p, "slots_used", 0),
            "created_at": (utc_iso(p.created_at) or ""),
        } for p in purchases],
    }


def grant_smacks(user_id: int, smacks: int, note: str, by_admin: str) -> dict:
    """
    Adds free smacks to a wallet.

    Goes through wallet_service so a WalletTransaction row is written exactly
    as a paid top-up would be - the balance stays reconstructable from the
    ledger. The reason is tagged 'admin_grant' so accounting can exclude it
    from revenue rather than counting a giveaway as income.
    """
    from services import wallet_service

    u = User.query.get(user_id)
    if not u:
        return {"error": "No such customer."}
    if smacks < 1 or smacks > 500:
        return {"error": "Between 1 and 500 smacks."}

    cents = smacks * wallet_service.SMACK_COST_CENTS
    wallet_service.credit_wallet(
        u, cents,
        transaction_type="admin_grant",
        description=(f"{smacks} free smacks by {by_admin}"
                     + (f" - {note[:120]}" if note else "")),
    )
    db.session.commit()

    print(f"[admin] {by_admin} granted {smacks} smacks to user {u.id} ({u.email})")
    return {
        "ok": True,
        "balance_cents": u.balance_cents,
        "balance_smacks": u.balance_cents // 100,
    }


def grant_smackcast(user_id: int, slots: int, note: str, by_admin: str) -> dict:
    """
    Gives free Smackcast league slots.

    Creates a PAID purchase row with amount_cents=0 rather than a special
    'comp' type, so every entitlement check downstream works unchanged - the
    zero amount is what marks it as free, and accounting reads amount rather
    than counting rows.
    """
    u = User.query.get(user_id)
    if not u:
        return {"error": "No such customer."}
    if slots < 1 or slots > 20:
        return {"error": "Between 1 and 20 league slots."}

    p = SmackcastPurchase(
        user_id=u.id,
        plan="single" if slots == 1 else "season",
        league_slots=slots,
        amount_cents=0,
        status="paid",
        paid_at=datetime.utcnow(),
    )
    db.session.add(p)
    db.session.commit()

    print(f"[admin] {by_admin} granted {slots} smackcast slot(s) to user {u.id} ({u.email})")
    return {"ok": True, "purchase_id": p.id, "league_slots": slots}

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
