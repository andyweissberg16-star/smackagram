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
    "starter": {"pay_cents": 500, "credit_cents": 600, "free_smackagrams": 1, "label": "Starter Plan"},
    "loaded": {"pay_cents": 1000, "credit_cents": 1500, "free_smackagrams": 5, "label": "Loaded Package"},
    "arsenal": {"pay_cents": 2000, "credit_cents": 3000, "free_smackagrams": 10, "label": "Arsenal Package"},
}

SMACK_COST_CENTS = 100  # $1.00 per Send a Smack
LOCKED_N_LOADED_COST_CENTS = 100  # $1.00 per Locked & Loaded arm - debited immediately, refunded to wallet if the hold releases (target team wins/game canceled)


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
    user.balance_cents += amount_cents
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
    and redirecting to Reload if it's None, rather than this function
    raising an exception, since "insufficient balance" is an expected,
    routine outcome here, not an error condition.
    """
    if not has_sufficient_balance(user, amount_cents):
        return None

    user.balance_cents -= amount_cents
    txn = WalletTransaction(
        user_id=user.id,
        amount_cents=-amount_cents,  # stored as negative for a debit
        balance_after_cents=user.balance_cents,
        transaction_type=transaction_type,
        description=description,
    )
    db.session.add(txn)
    return txn
