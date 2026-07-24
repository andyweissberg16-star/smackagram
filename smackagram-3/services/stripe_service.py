import os
import stripe


def _configure():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]


def create_immediate_payment_intent(amount_cents: int) -> stripe.PaymentIntent:
    """v1 flow: charge right away when someone sends a smackagram now."""
    _configure()
    return stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
    )


def create_authorized_hold(amount_cents: int) -> stripe.PaymentIntent:
    """
    Locked-and-loaded flow: authorize the card (funds held, not charged)
    when a smackagram is armed against a future game. We capture or cancel
    this once the game result is known. Stripe holds expire after 7 days,
    which is why smackagrams can only be armed within 48h of kickoff.
    """
    _configure()
    return stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        capture_method="manual",
        automatic_payment_methods={"enabled": True},
    )


def capture_hold(payment_intent_id: str):
    """Target team lost — condition met, actually charge the card now."""
    _configure()
    return stripe.PaymentIntent.capture(payment_intent_id)


def release_hold(payment_intent_id: str):
    """Target team won (or game postponed/canceled) — release the hold, charge nothing."""
    _configure()
    return stripe.PaymentIntent.cancel(payment_intent_id)
