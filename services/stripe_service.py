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


def create_checkout_session(order_id: int, amount_cents: int, base_url: str) -> stripe.checkout.Session:
    """
    Creates a Stripe-hosted checkout page for a smackagram order. Using
    Stripe's hosted Checkout instead of a custom card form keeps us out of
    PCI-compliance territory and is far less code to get right.
    """
    _configure()
    label = "Call + recording" if amount_cents == 200 else "Call only"
    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Smackagram — {label}"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        metadata={"order_id": str(order_id)},
        success_url=f"{base_url}/order-success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/",
    )


def verify_webhook(payload: bytes, sig_header: str, webhook_secret: str):
    """Verifies a Stripe webhook actually came from Stripe, not a forged request."""
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)


def release_hold(payment_intent_id: str):
    """Target team won (or game postponed/canceled) — release the hold, charge nothing."""
    _configure()
    return stripe.PaymentIntent.cancel(payment_intent_id)
