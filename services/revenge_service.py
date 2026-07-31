"""
The revenge loop's money mechanics.

Someone gets smacked, comes to the site to hear it, and is - for a few
seconds - the most motivated potential customer this business will ever
see. They are angry, they know exactly who did it, and they want to hit
back. The whole job of this module is to make sure nothing stands between
that feeling and their first send.

The lever is a single comped smack. Not a discount, not a trial with a
card on file - one free send, granted the moment they've proved the
number is theirs. The comp is deliberately worth exactly one smack
(SMACK_COST_CENTS) rather than a round dollar figure, so it can never
drift out of sync with the real price if that price changes.

Eligibility deliberately requires a VERIFIED phone rather than just an
account. Two reasons, and the second is the important one:

  1. It stops the obvious abuse - make an account, claim a free smack,
     repeat. Verification costs an SMS round-trip and a real phone.
  2. It means the comp only ever goes to somebody who was ACTUALLY
     smacked. That is the entire point. A free smack handed to a random
     signup is a cost; a free smack handed to a person holding a fresh
     grudge is the cheapest customer acquisition available, because the
     motivation is already there and was created by an existing customer.

The comp is booked as transaction_type "comp", which admin_service's
COMP_TYPES already excludes from revenue reporting. That matters: comped
sends must never inflate the revenue numbers, or the accounting quietly
becomes fiction. They show up as comped, which is what they are.
"""

from models import db, WalletTransaction, VerifiedPhone
from services import wallet_service

# Must stay inside COMP_TYPES in admin_service, or comped sends start
# counting as revenue.
COMP_TYPE = "comp"

# Used as the idempotency marker as well as the ledger note - this exact
# string is what has_claimed_comp() looks for, so changing it would let
# everybody claim a second comp. If it ever needs rewording, migrate the
# existing rows to match rather than just editing it here.
COMP_DESCRIPTION = "First smack back - comped"


def comp_amount_cents() -> int:
    """Always one smack, read live so a price change can't desync it."""
    return wallet_service.SMACK_COST_CENTS


def has_verified_phone(user) -> bool:
    if not user:
        return False
    return VerifiedPhone.query.filter_by(user_id=user.id).first() is not None


def has_claimed_comp(user) -> bool:
    if not user:
        return False
    return WalletTransaction.query.filter_by(
        user_id=user.id,
        transaction_type=COMP_TYPE,
        description=COMP_DESCRIPTION,
    ).first() is not None


def comp_status(user) -> dict:
    """
    Describes where this person stands, with a machine-readable reason so
    the front end can show the right prompt rather than a generic "no".
    Never raises - a logged-out visitor is a normal case here, not an
    error, because this page is reachable without an account by design.
    """
    amount = comp_amount_cents()

    if not user:
        return {"eligible": False, "claimed": False,
                "reason": "not_logged_in", "amount_cents": amount}

    if not has_verified_phone(user):
        return {"eligible": False, "claimed": False,
                "reason": "phone_not_verified", "amount_cents": amount}

    if has_claimed_comp(user):
        return {"eligible": False, "claimed": True,
                "reason": "already_claimed", "amount_cents": amount}

    return {"eligible": True, "claimed": False,
            "reason": None, "amount_cents": amount}


def claim_comp(user) -> dict:
    """
    Grants the one free smack. Re-checks eligibility immediately before
    crediting rather than trusting a status fetched earlier by the
    browser, since that value could be stale or forged.

    Note on races: two simultaneous claims could in principle both pass
    the check before either writes. The app runs a single Gunicorn worker
    today so this cannot currently happen, and the blast radius is one
    extra dollar of credit rather than anything dangerous. If it ever
    scales to multiple workers, add a unique index on
    (user_id, transaction_type, description) and catch the IntegrityError.
    """
    status = comp_status(user)
    if not status["eligible"]:
        return {"granted": False, **status}

    amount = comp_amount_cents()
    wallet_service.credit_wallet(
        user,
        amount,
        transaction_type=COMP_TYPE,
        description=COMP_DESCRIPTION,
    )
    db.session.commit()

    return {
        "granted": True,
        "eligible": False,
        "claimed": True,
        "reason": "already_claimed",
        "amount_cents": amount,
        "balance_cents": user.balance_cents,
    }
