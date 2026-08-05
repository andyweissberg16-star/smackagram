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


def create_wallet_topup_payment_intent(amount_cents: int, user_id: int, pack_key: str, pending_action_id: int = None) -> stripe.PaymentIntent:
    """
    Wallet top-up flow: charges immediately (not a hold) for the
    selected pack's real dollar amount. amount_cents must be looked up
    server-side from wallet_service.TOPUP_PACKS by the caller — never
    trust a client-supplied amount, since that would let someone edit
    the price in their browser. Metadata identifies the user and pack
    so the webhook handler knows which wallet to credit and how much
    bonus to add once payment succeeds. pending_action_id, when present,
    tells the webhook there's an original Send a Smack / Auto-Smack
    request waiting to be resumed automatically once the wallet is
    credited - the user shouldn't have to re-enter anything.
    """
    _configure()
    metadata = {"type": "wallet_topup", "user_id": str(user_id), "pack_key": pack_key}
    if pending_action_id is not None:
        metadata["pending_action_id"] = str(pending_action_id)
    return stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
        metadata=metadata,
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


SMACKCAST_SINGLE_CENTS = 799
SMACKCAST_SEASON_CENTS = 3999
SMACKCAST_EXTRA_LEAGUE_CENTS = 2999


def create_smackcast_checkout_session(subscription_id: int, base_url: str) -> stripe.checkout.Session:
    """
    One-time season pass checkout — $39.99, no recurring billing. Same
    hosted-Checkout pattern as create_checkout_session above.
    """
    _configure()
    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Smackcast — Season Pass"},
                "unit_amount": 3999,
            },
            "quantity": 1,
        }],
        metadata={"smackcast_subscription_id": str(subscription_id)},
        success_url=f"{base_url}/smackcast/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/smackcast",
    )


def create_smackcast_purchase_session(purchase, base_url: str) -> stripe.checkout.Session:
    """
    Checkout for the new buy-first flow. Unlike
    create_smackcast_checkout_session (which assumed a single $39.99
    season pass for an already-connected league), the amount here varies:
    a single recap, or a season pass plus any number of extra leagues.

    The extra leagues go on as their own line item with a quantity so the
    receipt itemises what was bought rather than showing one opaque total.
    Success lands on the connect flow, since after this the buyer still
    has leagues to hook up.
    """
    _configure()

    if purchase.plan == "single":
        line_items = [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Smackcast — Single Recap"},
                "unit_amount": SMACKCAST_SINGLE_CENTS,
            },
            "quantity": 1,
        }]
    else:
        line_items = [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Smackcast — Season Pass"},
                "unit_amount": SMACKCAST_SEASON_CENTS,
            },
            "quantity": 1,
        }]
        extra = max(0, (purchase.league_slots or 1) - 1)
        if extra:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Smackcast — Additional League"},
                    "unit_amount": SMACKCAST_EXTRA_LEAGUE_CENTS,
                },
                "quantity": extra,
            })

    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=line_items,
        metadata={"smackcast_purchase_id": str(purchase.id)},
        success_url=f"{base_url}/smackcast/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/smackcast",
    )


def create_authorized_checkout_session(smackagram_id: int, amount_cents: int, base_url: str) -> stripe.checkout.Session:
    """
    Same hosted-Checkout UX as create_checkout_session, but for locked-and-
    loaded smackagrams: the card is authorized (funds held) via
    payment_intent_data.capture_method='manual', NOT charged immediately.
    We capture or cancel the resulting PaymentIntent later, once the game's
    outcome is known (see scheduler.py). This means the buyer goes through
    the exact same familiar checkout flow as a regular order, they just
    aren't charged until/unless their condition is met.
    """
    _configure()
    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Smackagram — Auto-Smack"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        payment_intent_data={"capture_method": "manual"},
        metadata={"type": "smackagram", "smackagram_id": str(smackagram_id)},
        success_url=f"{base_url}/auto-smack/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/auto-smack",
    )


def verify_webhook(payload: bytes, sig_header: str, webhook_secret: str):
    """Verifies a Stripe webhook actually came from Stripe, not a forged request."""
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)


def release_hold(payment_intent_id: str):
    """Target team won (or game postponed/canceled) — release the hold, charge nothing."""
    _configure()
    return stripe.PaymentIntent.cancel(payment_intent_id)
