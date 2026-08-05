"""
Wallet service — the single source of truth for touching a user's
balance_cents. All credits and debits go through here specifically so
every change is logged to WalletTransaction, keeping the ledger
auditable. Nothing else in the codebase should modify user.balance_cents
directly.
"""
from models import db, WalletTransaction


# Top-up pack definitions — the three fixed packs from the pricing spec.
# Kept here as the single source of truth for pack amounts, since both
# the checkout page and the PaymentIntent creation endpoint need to
# agree on these exact numbers, and the amount charged must always be
# looked up server-side from this dict, never trusted from the browser.
TOPUP_PACKS = {
    "starter": {"pay_cents": 500, "credit_cents": 600, "free_smackagrams": 1, "label": "Rookie"},
    "loaded": {"pay_cents": 1000, "credit_cents": 1500, "free_smackagrams": 5, "label": "All-Star"},
    "arsenal": {"pay_cents": 2000, "credit_cents": 3000, "free_smackagrams": 10, "label": "MVP"},
}

SMACK_COST_CENTS = 100  # $1.00 per Send a Smack
LOCKED_N_LOADED_COST_CENTS = 100  # $1.00 per Auto-Smack arm - debited immediately, refunded to wallet if the hold releases (target team wins/game canceled)


def has_sufficient_balance(user, amount_cents: int) -> bool:
    return user.balance_cents >= amount_cents


def credit_wallet(user, amount_cents: int, transaction_type: str, stripe_payment_intent_id: str = None, description: str = None) -> WalletTransaction:
    """
    Adds to the user's balance and logs the transaction. Used for
    top-ups (Stripe payments succeeding). amount_cents should be
    positive — this function doesn't enforce that, since the caller
    (the webhook handler) is trusted to pass the right sign, but every
    real call site should only ever credit a positive amount.
    """
    # ATOMIC HERE TOO, for the opposite reason.
    #
    # A debit racing loses money for the customer. A CREDIT racing loses
    # it for you: two refunds arriving together both read 0, both write
    # 100, and one of them vanishes - so somebody is owed a dollar that
    # the ledger says was paid.
    #
    # Same statement, same protection.
    from models import User
    db.session.query(User).filter(User.id == user.id).update(
        {User.balance_cents: User.balance_cents + amount_cents},
        synchronize_session="fetch",
    )
    db.session.refresh(user)
    txn = WalletTransaction(
        user_id=user.id,
        amount_cents=amount_cents,
        balance_after_cents=user.balance_cents,
        transaction_type=transaction_type,
        stripe_payment_intent_id=stripe_payment_intent_id,
        description=description,
    )
    db.session.add(txn)
    return txn


def debit_wallet(user, amount_cents: int, transaction_type: str, description: str = None) -> WalletTransaction | None:
    """
    Deducts from the user's balance and logs the transaction. Returns
    None (and does NOT touch the balance) if the user doesn't have
    enough — the caller is responsible for checking the return value
    and redirecting to Refill if it's None, rather than this function
    raising an exception, since "insufficient balance" is an expected,
    routine outcome here, not an error condition.
    """
    # ONE ATOMIC STATEMENT, NOT READ-THEN-WRITE.
    #
    # This checked the balance, then subtracted - separate steps. Two
    # requests arriving together both read 100, both decide 100 >= 100,
    # and both write 0. Two smacks sent, one dollar taken.
    #
    # TODAY THAT IS PREVENTED ONLY BY RUNNING A SINGLE GUNICORN WORKER,
    # which handles requests one at a time. Safe by accident, not by
    # design - and the accident ends the moment WEB_CONCURRENCY goes above
    # one, which is exactly what "stress test to 1000 simultaneous
    # deliveries" involves doing.
    #
    # The database decides now. The UPDATE only matches a row that still
    # has enough, so if two arrive together one matches and the other does
    # not. There is no window between the check and the subtraction
    # because they are the same statement.
    if amount_cents <= 0:
        return None

    from models import User
    updated = db.session.query(User).filter(
        User.id == user.id,
        User.balance_cents >= amount_cents,
    ).update(
        {User.balance_cents: User.balance_cents - amount_cents},
        synchronize_session="fetch",
    )
    if not updated:
        return None

    # Pull the real value back before writing the ledger. The UPDATE
    # happened in the database, so the object in memory may still hold
    # what it was - and a ledger line recording the wrong balance is
    # worse than no ledger line, because it looks authoritative.
    db.session.refresh(user)
    txn = WalletTransaction(
        user_id=user.id,
        amount_cents=-amount_cents,  # stored as negative for a debit
        balance_after_cents=user.balance_cents,
        transaction_type=transaction_type,
        description=description,
    )
    db.session.add(txn)
    return txn
