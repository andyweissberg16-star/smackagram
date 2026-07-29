import os
import json
import functools
import secrets
import threading
from datetime import datetime, timedelta, timezone, date

from flask import Flask, render_template, request, jsonify, Response, url_for, session, redirect
from sqlalchemy import func
import requests
from dotenv import load_dotenv

from models import db, Scenario, Order, Smackagram, ChatPost, ChatRating, Battle, BattleLine, BattleVote, BattleRoundResult, User, SmackcastSubscription, SmackcastRecap, WalletTransaction, PendingAction, VerifiedPhone, PhoneVerificationCode
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options, generator_constants, call_audio_service, content_moderation, team_aliases, chat_team_lists, chat_team_colors, team_display, sleeper_service, smackcast_service, espn_service, wallet_service
from scheduler import check_armed_smackagrams, generate_weekly_smackcasts

load_dotenv()

app = Flask(__name__)

# Temporarily disabled while sorting out an SMS delivery issue (likely
# A2P 10DLC carrier filtering — messages report as "sent" from Twilio
# but never actually reach the phone). Flip back to True once that's
# resolved — every login/registration path already checks this flag,
# so re-enabling is just this one line.
TWO_FACTOR_ENABLED = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smackagram.db")
# Render (and Heroku before it) provides Postgres connection strings
# starting with "postgres://" — modern SQLAlchemy (1.4+) requires
# "postgresql://" instead and will raise an error on startup otherwise.
# This is a well-known, common gotcha when moving off SQLite onto a
# managed Postgres instance; harmless no-op for SQLite or any URL that
# doesn't start with the old scheme.
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql://", 1)
# SQLite's default driver flatly refuses to let a connection be used
# from a different thread than the one that created it — which is
# exactly what the background round-judging and recap-generation
# threads do. Without this, every database write from those threads
# throws (silently caught and logged, not visible to the user), leaving
# a round permanently stuck showing "Judging this round..." since the
# result never actually gets saved. Harmless if/when this migrates to
# Postgres later — this option is SQLite-specific and just gets ignored
# by other database engines.
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
db.init_app(app)


def get_current_user():
    """Returns the logged-in User object, or None if nobody's logged in."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


@app.context_processor
def inject_current_user():
    """
    Makes current_user automatically available in every template's
    context, site-wide — without this, only routes that manually
    passed current_user=get_current_user() into render_template() would
    have it, which is what the shared site-wide nav partial needs to
    correctly show Login/Register vs My Profile on every single page,
    not just the ones that happened to already pass it.
    """
    return {"current_user": get_current_user()}


def login_required(view_func):
    """
    Gates a route behind having a real account. API routes (path starts
    with /api/) get a clean 401 JSON response — the frontend can show its
    own login prompt. Page routes redirect straight to /login, preserving
    where they were trying to go via ?next=.
    """
    @functools.wraps(view_func)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in to do that.", "login_required": True}), 401
            return redirect(f"/login?next={request.path}")
        return view_func(*args, **kwargs)
    return wrapped


@app.route("/register")
def register_page():
    return render_template("register.html")


def _send_2fa_code(user):
    """
    Generates a fresh 6-digit code, stores it with a 10-minute
    expiration, and texts it via Twilio. Shared by registration and
    login so both go through the exact same path.
    """
    code = f"{secrets.randbelow(1000000):06d}"
    user.two_factor_code = code
    user.two_factor_expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    twilio_service.send_sms(user.phone, f"Your Smackagram verification code is {code}. It expires in 10 minutes.")


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    screen_name = (data.get("screen_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    dob_str = (data.get("date_of_birth") or "").strip()
    password = data.get("password") or ""
    terms_accepted = bool(data.get("terms_accepted"))

    if not all([first_name, last_name, screen_name, email, phone, dob_str, password]):
        return jsonify({"error": "All fields are required."}), 400
    if not terms_accepted:
        return jsonify({"error": "You must agree to the Terms & Conditions."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if len(screen_name) < 3:
        return jsonify({"error": "Screen name must be at least 3 characters."}), 400

    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date of birth."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 400

    # Case-insensitive uniqueness check — "CowboysHater" and "cowboyshater"
    # shouldn't both be allowed to exist, since they're indistinguishable
    # everywhere the screen name actually gets displayed.
    if User.query.filter(db.func.lower(User.screen_name) == screen_name.lower()).first():
        return jsonify({"error": "That screen name is already taken."}), 400

    # Same moderation standard used everywhere else on the site — this
    # is what actually catches slurs and hate speech, not just an
    # obvious-word blocklist that's trivial to get around.
    safety = content_moderation.check_message_safety(screen_name)
    if not safety["safe"]:
        return jsonify({"error": "That screen name isn't allowed. Please choose another."}), 400

    # customer_number starts at 1,000,001 for the first real registered
    # customer — the seeded admin account sits at 1,000,000, just below
    # that range, so this naturally continues from there.
    highest = db.session.query(db.func.max(User.customer_number)).scalar() or 1000000
    new_customer_number = highest + 1

    user = User(
        customer_number=new_customer_number,
        first_name=first_name,
        last_name=last_name,
        screen_name=screen_name,
        email=email,
        phone=phone,
        date_of_birth=dob,
        terms_accepted_at=datetime.utcnow(),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    if not TWO_FACTOR_ENABLED:
        session["user_id"] = user.id
        return jsonify({"ok": True})

    # 2FA right after registration too, not just future logins — this
    # also confirms the phone number they gave us is real and reachable.
    # If sending genuinely fails (bad number, Twilio issue), roll back
    # the account entirely rather than leaving an orphaned, unverifiable
    # user record and crashing with a generic error.
    try:
        _send_2fa_code(user)
    except Exception as e:
        print(f"[register] failed to send 2FA code: {e}")
        db.session.delete(user)
        db.session.commit()
        return jsonify({"error": "Couldn't send a verification text to that phone number — please double-check it and try again."}), 400

    session["pending_verification_user_id"] = user.id
    return jsonify({"ok": True, "requires_verification": True})


@app.route("/verify")
def verify_page():
    return render_template("verify.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Incorrect email or password."}), 401

    # The seeded admin test account always skips 2FA (frictionless
    # testing, no real phone behind it) — and right now, per the
    # TWO_FACTOR_ENABLED toggle above, everyone does while the SMS
    # delivery issue gets sorted out.
    if user.is_admin or not TWO_FACTOR_ENABLED:
        session["user_id"] = user.id
        return jsonify({"ok": True})

    try:
        _send_2fa_code(user)
    except Exception as e:
        print(f"[login] failed to send 2FA code: {e}")
        return jsonify({"error": "Couldn't send a verification text right now — please try again in a moment."}), 500

    session["pending_verification_user_id"] = user.id
    return jsonify({"ok": True, "requires_verification": True})


@app.route("/api/verify-2fa", methods=["POST"])
def api_verify_2fa():
    pending_user_id = session.get("pending_verification_user_id")
    if not pending_user_id:
        return jsonify({"error": "Nothing to verify — please log in again."}), 400

    user = User.query.get(pending_user_id)
    if not user:
        return jsonify({"error": "Something went wrong — please log in again."}), 400

    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "Enter the code we texted you."}), 400
    if not user.two_factor_code or not user.two_factor_expires_at:
        return jsonify({"error": "No active code — request a new one."}), 400
    if datetime.utcnow() > user.two_factor_expires_at:
        return jsonify({"error": "That code expired — request a new one."}), 400
    if code != user.two_factor_code:
        return jsonify({"error": "Incorrect code."}), 400

    # Correct — clear the code so it can't be reused, complete login.
    user.two_factor_code = None
    user.two_factor_expires_at = None
    db.session.commit()
    session.pop("pending_verification_user_id", None)
    session["user_id"] = user.id
    return jsonify({"ok": True})


@app.route("/api/resend-2fa", methods=["POST"])
def api_resend_2fa():
    pending_user_id = session.get("pending_verification_user_id")
    if not pending_user_id:
        return jsonify({"error": "Nothing to resend — please log in again."}), 400
    user = User.query.get(pending_user_id)
    if not user:
        return jsonify({"error": "Something went wrong — please log in again."}), 400
    try:
        _send_2fa_code(user)
    except Exception as e:
        print(f"[resend-2fa] failed to send code: {e}")
        return jsonify({"error": "Couldn't send a new code right now — please try again in a moment."}), 500
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.route("/profile")
@login_required
def profile_page():
    return render_template("profile.html")


@app.route("/api/profile", methods=["GET"])
@login_required
def api_get_profile():
    user = get_current_user()
    return jsonify({
        "customer_number": user.customer_number,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "screen_name": user.screen_name,
        "email": user.email,
        "phone": user.phone,
        "date_of_birth": user.date_of_birth.isoformat(),
    })


@app.route("/api/profile", methods=["POST"])
@login_required
def api_update_profile():
    user = get_current_user()
    data = request.json or {}

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    screen_name = (data.get("screen_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    dob_str = (data.get("date_of_birth") or "").strip()

    if not all([first_name, last_name, screen_name, phone, dob_str]):
        return jsonify({"error": "All fields are required."}), 400
    if len(screen_name) < 3:
        return jsonify({"error": "Screen name must be at least 3 characters."}), 400

    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date of birth."}), 400

    # Only re-check uniqueness/moderation if they actually changed it —
    # no need to re-flag their own existing, already-approved name.
    if screen_name.lower() != user.screen_name.lower():
        existing = User.query.filter(db.func.lower(User.screen_name) == screen_name.lower()).first()
        if existing and existing.id != user.id:
            return jsonify({"error": "That screen name is already taken."}), 400
        safety = content_moderation.check_message_safety(screen_name)
        if not safety["safe"]:
            return jsonify({"error": "That screen name isn't allowed. Please choose another."}), 400

    user.first_name = first_name
    user.last_name = last_name
    user.screen_name = screen_name
    user.phone = phone
    user.date_of_birth = dob
    db.session.commit()
    return jsonify({"ok": True})


# Pre-resolved audio URLs for calls about to be placed, keyed by record id.
# Generating the message/sfx/tagline audio takes a few seconds (multiple
# ElevenLabs calls + S3 uploads) — doing that INSIDE the /call-instructions
# webhook response risks Twilio timing out and retrying, which replays the
# whole call from scratch. So we resolve audio BEFORE placing the call, and
# call-instructions just serves the already-ready URLs instantly.
_pending_call_audio = {}


# ---------- Site-wide password gate ----------
# Set SITE_PASSWORD in Render to lock the whole site behind a simple prompt
# while it's still in development. Leave SITE_PASSWORD unset/blank to make
# the site fully public again (e.g. once you're ready to launch for real).

@app.before_request
def require_site_password():
    # Stripe and Twilio hit these routes directly and can't log in with a
    # username/password — Stripe verifies itself via signature, Twilio's
    # callbacks are unauthenticated by nature (that's how Twilio itself works).
    exempt_prefixes = ("/webhook/stripe", "/call-instructions/", "/call-status/", "/recording-ready/", "/recording-done/", "/static/", "/api/cron/")
    if request.path.startswith(exempt_prefixes):
        return

    site_password = os.environ.get("SITE_PASSWORD")
    if not site_password:
        return  # gate disabled — site is public

    auth = request.authorization
    if not auth or auth.password != site_password:
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Smackagram"'},
        )


# ---------- Pages ----------

@app.route("/")
def home():
    scenarios = Scenario.query.filter_by(active=True).all()
    return render_template("index.html", scenarios=scenarios, current_user=get_current_user())


def _store_pending_action(user, action_type: str, data: dict) -> str:
    """
    Saves the original request payload so the action can be resumed
    automatically once the wallet is topped up, and returns the /reload
    redirect URL carrying the pending action's id. See PendingAction's
    docstring in models.py for why this is server-side/webhook-driven
    rather than client-side storage.
    """
    pending = PendingAction(
        user_id=user.id,
        action_type=action_type,
        payload_json=json.dumps(data),
    )
    db.session.add(pending)
    db.session.commit()
    return f"/reload?pending_action={pending.id}"


@app.route("/reload")
@login_required
def reload_page():
    """
    The wallet top-up page. Reached as the final step of Send a Smack
    or Locked & Loaded when the wallet balance can't cover the action -
    not a standalone destination someone browses to directly, though
    it works fine if they do. Shows different copy for a genuine
    first-time buyer ("Load Your Account") versus a returning user
    topping back up ("Reload") - "reload" doesn't make sense for
    someone who's never had a balance to begin with.
    """
    user = get_current_user()
    has_topped_up_before = WalletTransaction.query.filter_by(user_id=user.id, transaction_type="topup").first() is not None

    # If there's a pending action, the step nav needs to know which
    # flow it belongs to (Send a Smack vs Locked & Loaded) to show the
    # right step labels and link back to the right page.
    pending_action_id = request.args.get("pending_action")
    pending_action_type = None
    if pending_action_id:
        pending = PendingAction.query.get(pending_action_id)
        if pending and pending.user_id == user.id:
            pending_action_type = pending.action_type

    return render_template(
        "reload.html",
        stripe_publishable_key=os.environ["STRIPE_PUBLISHABLE_KEY"],
        is_first_time_buyer=not has_topped_up_before,
        pending_action_id=pending_action_id,
        pending_action_type=pending_action_type,
    )


@app.route("/reload-success")
@login_required
def reload_success():
    """
    Where Stripe redirects after a successful payment confirmation.
    The wallet itself gets credited by the webhook handler, which may
    still be in flight when this page loads — that's expected and fine,
    since the webhook is the authoritative source of truth here, not
    this page.
    """
    return render_template("reload_success.html")


@app.route("/api/wallet/pending-action-status/<int:pending_action_id>")
@login_required
def api_pending_action_status(pending_action_id):
    """
    Polled by reload_success.html while a resumed Send a Smack / Locked
    & Loaded request may still be in flight (the webhook that actually
    completes it can take a few seconds to arrive after payment
    confirms on the frontend). Scoped to the current user only - no
    one should be able to check another user's pending action status.
    """
    user = get_current_user()
    pending = PendingAction.query.get(pending_action_id)
    if not pending or pending.user_id != user.id:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "status": pending.status,
        "redirect": pending.result_redirect,
        "error_message": pending.error_message,
    })


@app.route("/api/pending-action/<int:pending_action_id>")
@login_required
def api_get_pending_action(pending_action_id):
    """
    Returns a pending action's stored payload and type, so a page the
    user navigates back to (e.g. the generator, after clicking "Roast"
    in the Reload page's step nav) can repopulate its form fields with
    whatever they'd already typed, instead of making them start over.
    Scoped to the current user only.
    """
    user = get_current_user()
    pending = PendingAction.query.get(pending_action_id)
    if not pending or pending.user_id != user.id:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "action_type": pending.action_type,
        "payload": json.loads(pending.payload_json),
    })



@app.route("/api/wallet/create-payment-intent", methods=["POST"])
@login_required
def api_wallet_create_payment_intent():
    """
    Creates a real Stripe PaymentIntent for the selected top-up pack.
    The amount is looked up server-side from wallet_service.TOPUP_PACKS
    by pack key — never trusts a dollar amount sent from the browser,
    since that would let someone tamper with the price before paying.
    """
    user = get_current_user()
    data = request.json or {}
    pack_key = data.get("pack")
    pending_action_id = data.get("pending_action_id")

    if pack_key not in wallet_service.TOPUP_PACKS:
        return jsonify({"error": "Invalid pack selected."}), 400

    pack = wallet_service.TOPUP_PACKS[pack_key]
    intent = stripe_service.create_wallet_topup_payment_intent(
        amount_cents=pack["pay_cents"], user_id=user.id, pack_key=pack_key,
        pending_action_id=pending_action_id,
    )

    return jsonify({"client_secret": intent.client_secret})


# ---------- Immediate "send it now" flow ----------

def _execute_send_smack(user, data: dict) -> dict:
    """
    The actual order-creation + call-firing logic, factored out so both
    the normal /api/orders request AND the webhook's "resume this
    pending action now that the wallet is topped up" path can call the
    exact same code. Assumes the wallet has ALREADY been debited by the
    caller - this function only creates the order and fires the call.
    Returns {"order_id": ..., "redirect": ...} on success.
    """
    order = Order(
        scenario_id=data.get("scenario_id"),
        custom_message=data.get("custom_message", ""),
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        price_cents=wallet_service.SMACK_COST_CENTS,
        includes_recording=data.get("include_recording", True),
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
        payment_status="captured",  # wallet deduction IS the payment - no async Stripe wait needed
    )
    db.session.add(order)
    db.session.commit()

    try:
        audio_urls = call_audio_service.resolve_audio_url(order, os.environ["BASE_URL"])
        _pending_call_audio[order.id] = audio_urls
        order.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
        call_sid = twilio_service.place_prank_call(order.id, order.recipient_phone, record=True)
        order.twilio_call_sid = call_sid
        order.call_status = "ringing"

        if order.replied_to_type and order.replied_to_id:
            original_model = Order if order.replied_to_type == "order" else Smackagram
            original_record = original_model.query.get(order.replied_to_id)
            if original_record:
                original_record.replied = True

        db.session.commit()
    except Exception as e:
        order.call_status = "failed"
        db.session.commit()
        print(f"Call failed for order {order.id}: {e}")

    return {"order_id": order.id, "redirect": "/order-success"}


@app.route("/api/orders", methods=["POST"])
@login_required
def create_order():
    user = get_current_user()
    data = request.json

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    custom_message = data.get("custom_message", "")
    safety = content_moderation.check_message_safety(custom_message)
    if not safety["safe"]:
        print(f"[safety] blocked order attempt — reason: {safety['reason']}")
        return jsonify({"error": "This message can't be sent — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    if not wallet_service.has_sufficient_balance(user, wallet_service.SMACK_COST_CENTS):
        redirect = _store_pending_action(user, "send_smack", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    txn = wallet_service.debit_wallet(user, wallet_service.SMACK_COST_CENTS, "smack", description="Send a Smack")
    if txn is None:
        # race condition fallback - balance changed between the check
        # above and this debit (e.g. two rapid requests) - handle it
        # the same way as the upfront insufficient-balance case
        redirect = _store_pending_action(user, "send_smack", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    result = _execute_send_smack(user, data)
    return jsonify(result)


@app.route("/order-success")
def order_success():
    session_id = request.args.get("session_id")
    return render_template("order_success.html", session_id=session_id)


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe_service.verify_webhook(payload, sig_header, webhook_secret)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        metadata = intent.get("metadata", {})

        if metadata.get("type") == "wallet_topup":
            # Idempotency: Stripe can and does redeliver webhooks - if
            # we've already logged a transaction for this exact
            # PaymentIntent, don't credit the wallet a second time.
            existing = WalletTransaction.query.filter_by(stripe_payment_intent_id=intent["id"]).first()
            if existing:
                return jsonify({"received": True})

            user_id = int(metadata["user_id"])
            pack_key = metadata["pack_key"]
            user = User.query.get(user_id)
            pack = wallet_service.TOPUP_PACKS.get(pack_key)

            if user and pack:
                wallet_service.credit_wallet(
                    user, pack["credit_cents"], "topup",
                    stripe_payment_intent_id=intent["id"],
                    description=f"{pack['label']} - ${pack['pay_cents']/100:.2f} for {pack['credit_cents']//100} Smackagrams ({pack['free_smackagrams']} free)",
                )
                db.session.commit()

                # If this top-up was triggered by a Send a Smack / Locked
                # & Loaded attempt that hit insufficient balance, resume
                # that original request now - automatically, without the
                # user re-entering anything. This is the one place we can
                # be certain payment actually succeeded, regardless of
                # what happened to the browser tab in the meantime.
                pending_action_id = metadata.get("pending_action_id")
                if pending_action_id:
                    pending = PendingAction.query.get(int(pending_action_id))
                    if pending and pending.status == "pending":
                        try:
                            payload = json.loads(pending.payload_json)
                            cost = (
                                wallet_service.SMACK_COST_CENTS if pending.action_type == "send_smack"
                                else wallet_service.LOCKED_N_LOADED_COST_CENTS
                            )
                            txn = wallet_service.debit_wallet(
                                user, cost, pending.action_type,
                                description=f"Resumed after reload - {pending.action_type}",
                            )
                            if txn is None:
                                pending.status = "failed"
                                pending.error_message = "Still insufficient balance after reload."
                            else:
                                if pending.action_type == "send_smack":
                                    result = _execute_send_smack(user, payload)
                                else:
                                    result = _execute_arm_smackagram(user, payload)
                                pending.status = "completed"
                                pending.result_redirect = result["redirect"]
                                pending.completed_at = datetime.utcnow()
                        except Exception as e:
                            pending.status = "failed"
                            pending.error_message = str(e)
                            print(f"[wallet] failed to resume pending action {pending.id}: {e}")
                        db.session.commit()

            return jsonify({"received": True})

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})

        if metadata.get("type") == "smackagram":
            # Locked-and-loaded flow: the card is now authorized (held), not
            # charged. Swap the stored id from the Checkout Session to the
            # actual PaymentIntent, since that's what capture_hold()/
            # release_hold() operate on later, once the game resolves.
            smackagram_id = int(metadata["smackagram_id"])
            smackagram = Smackagram.query.get(smackagram_id)
            # only swap if it still holds the original Checkout Session id
            # (starts with "cs_") — avoids re-processing a duplicate webhook
            if smackagram and smackagram.stripe_payment_intent_id == session["id"]:
                smackagram.stripe_payment_intent_id = session.get("payment_intent")
                db.session.commit()
            return jsonify({"received": True})

        if metadata.get("smackcast_subscription_id"):
            subscription_id = int(metadata["smackcast_subscription_id"])
            subscription = SmackcastSubscription.query.get(subscription_id)
            if subscription and not subscription.is_active:
                subscription.is_active = True
                subscription.stripe_checkout_session_id = session["id"]
                db.session.commit()
            return jsonify({"received": True})

        order_id = int(metadata["order_id"])
        order = Order.query.get(order_id)

        if order and order.payment_status != "captured":
            order.payment_status = "captured"
            db.session.commit()

            # Fire the actual call. Wrapped in try/except so a Twilio issue
            # (e.g. not configured yet) doesn't crash the webhook — Stripe
            # needs a fast 200 response regardless, and the payment is
            # already safely recorded either way.
            try:
                audio_urls = call_audio_service.resolve_audio_url(order, os.environ.get("BASE_URL", request.url_root.rstrip("/")))
                _pending_call_audio[order.id] = audio_urls
                order.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
                call_sid = twilio_service.place_prank_call(order.id, order.recipient_phone, record=True)
                order.twilio_call_sid = call_sid
                order.call_status = "ringing"

                # If this order is itself a reply, mark the original smack
                # as replied now — waiting until the call is actually
                # firing (not just at checkout creation) means an
                # abandoned/failed checkout doesn't wrongly lock the
                # original out of ever getting a real reply.
                if order.replied_to_type and order.replied_to_id:
                    original_model = Order if order.replied_to_type == "order" else Smackagram
                    original_record = original_model.query.get(order.replied_to_id)
                    if original_record:
                        original_record.replied = True

                db.session.commit()
            except Exception as e:
                order.call_status = "failed"
                db.session.commit()
                print(f"Call failed for order {order.id}: {e}")

    return jsonify({"received": True})


@app.route("/api/generate-trash-talk", methods=["POST"])
@login_required
def generate_trash_talk():
    data = request.json
    team = data.get("team", "").strip()
    recipient_name = data.get("recipient_name", "").strip()
    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)
    # Sanitized server-side too, not just trusting whatever the frontend
    # already limited to 3 — cap length per topic as a light guard
    # against someone pasting something huge into this field.
    raw_topics = data.get("roast_topics") or []
    roast_topics = [str(t).strip()[:60] for t in raw_topics if str(t).strip()][:3]

    if not team or not recipient_name:
        return jsonify({"error": "Both team and recipient name are required"}), 400

    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    line = trash_talk_service.generate_trash_talk(team=team, recipient_name=recipient_name, sensitivity=sensitivity, roast_topics=roast_topics)
    return jsonify({"generated_text": line})


@app.route("/api/sensitivity-levels")
def get_sensitivity_levels():
    """Powers the sensitivity/intensity selector UI on the generator pages and Smack Battle creation."""
    return jsonify(trash_talk_service.SENSITIVITY_LEVELS)


@app.route("/api/smack-lab/respond", methods=["POST"])
@login_required
def smack_lab_respond():
    """
    Powers Smack Lab — live back-and-forth trash-talk sparring with a
    rating + coaching critique on every turn. Rate-limited per IP since
    this is a free feature (no purchase) that costs real Claude API calls.
    """
    identifier = request.headers.get("X-Forwarded-For", request.remote_addr)
    if rate_limiter.is_rate_limited(identifier):
        return jsonify({
            "error": "You've hit the free Smack Lab limit for now. Take a breather and come back in a bit."
        }), 429

    data = request.json
    team = data.get("team", "").strip()
    my_team = data.get("my_team", "").strip()
    user_line = data.get("user_line", "").strip()
    conversation_history = data.get("conversation_history", [])

    if not team or not user_line:
        return jsonify({"error": "Team and a line to rate are both required"}), 400

    # Same safety gate every user-typed message on this site passes through
    # before an AI does anything with it — this is user-typed text, no
    # different from a custom message elsewhere.
    safety = content_moderation.check_message_safety(user_line)
    if not safety["safe"]:
        return jsonify({"error": "That line can't be processed — it may contain threatening, sexual, or harassing content. Try a different angle."}), 400

    result = trash_talk_service.smack_lab_respond(team=team, my_team=my_team, conversation_history=conversation_history, user_line=user_line)
    rate_limiter.record_hit(identifier)
    return jsonify(result)


@app.route("/api/smack-lab/verdict", methods=["POST"])
@login_required
def smack_lab_verdict():
    """
    Delivers the session-ending report card after 5 rounds of Smack Lab —
    same rate limit as the main respond endpoint since it's still a real
    Claude API call on a free feature.
    """
    identifier = request.headers.get("X-Forwarded-For", request.remote_addr)
    if rate_limiter.is_rate_limited(identifier):
        return jsonify({
            "error": "You've hit the free Smack Lab limit for now. Take a breather and come back in a bit."
        }), 429

    data = request.json
    team = data.get("team", "").strip()
    my_team = data.get("my_team", "").strip()
    average_rating = data.get("average_rating")
    session_lines = data.get("session_lines", [])

    if not team or average_rating is None or not session_lines:
        return jsonify({"error": "Missing session data for verdict"}), 400

    verdict = trash_talk_service.smack_lab_final_verdict(team=team, my_team=my_team, average_rating=float(average_rating), session_lines=session_lines)
    rate_limiter.record_hit(identifier)
    return jsonify({"verdict": verdict})


@app.route("/api/voice-options")
def get_voice_options():
    return jsonify(voice_options.list_voice_options())


@app.route("/api/voice-sample/<voice_key>")
def voice_sample(voice_key):
    """
    Free preview of what a voice sounds like — ElevenLabs' own static
    sample clip, not a generated one. No credits used, no rate limit needed.
    """
    voice_id = voice_options.get_voice_id(voice_key)
    preview_url = elevenlabs_service.get_voice_preview_url(voice_id)
    return jsonify({"preview_url": preview_url})


@app.route("/api/preview-audio", methods=["POST"])
@login_required
def preview_audio():
    """
    Free preview — lets someone hear a generated line before buying.
    Rate-limited per IP since this costs real ElevenLabs credits with
    no purchase required.
    """
    identifier = request.headers.get("X-Forwarded-For", request.remote_addr)

    if rate_limiter.is_rate_limited(identifier):
        return jsonify({
            "error": "You've hit the free preview limit for now. Try again in a bit, "
                      "or go ahead and send the smack for real."
        }), 429

    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Check BEFORE this text ever reaches ElevenLabs — someone previewing a
    # line shouldn't be able to get dangerous content synthesized into audio
    # at all, regardless of whether they ever actually complete an order.
    safety = content_moderation.check_message_safety(text)
    if not safety["safe"]:
        print(f"[safety] blocked preview attempt — reason: {safety['reason']}")
        return jsonify({"error": "This message can't be previewed — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    voice_key = request.json.get("voice_key", voice_options.DEFAULT_VOICE_KEY)
    voice_id = voice_options.get_voice_id(voice_key)

    message_url = elevenlabs_service.generate_audio_url(text, voice_id=voice_id)
    outro_url = call_audio_service.get_outro_url(os.environ.get("BASE_URL", request.url_root.rstrip("/")))
    rate_limiter.record_hit(identifier)

    return jsonify({
        "audio_sequence": [message_url, outro_url],
        "previews_remaining": rate_limiter.previews_remaining(identifier),
    })


@app.route("/call-instructions/<int:record_id>", methods=["GET", "POST"])
def call_instructions(record_id):
    """
    Twilio hits this the moment the call connects. Serves pre-resolved audio
    URLs instantly — no generation happens here, since that risked Twilio
    timing out and retrying (which replayed the whole call from scratch).
    """
    order = Order.query.get(record_id) or Smackagram.query.get(record_id)

    # With machine_detection='DetectMessageEnd' set at call-creation time,
    # Twilio only requests this route once it's determined who/what
    # answered — logging this confirms the timing fix is actually working
    # (e.g. "machine_end_beep" means we're being asked to speak right
    # after the voicemail's greeting ended, exactly when we want to).
    answered_by = request.values.get("AnsweredBy")
    print(f"[twilio] call-instructions hit for record {record_id} — AnsweredBy={answered_by!r}")

    # fall back to live resolution only if somehow nothing was pre-cached
    # (e.g. this route got hit directly without going through the webhook)
    audio_urls = _pending_call_audio.pop(record_id, None) or call_audio_service.resolve_audio_url(order, os.environ.get("BASE_URL", request.url_root.rstrip("/")))

    # Never record voicemail greetings/silence — recording is only
    # meaningful (and only what the buyer paid for) when a real person's
    # live reaction gets captured. AnsweredBy comes from the
    # machine_detection='DetectMessageEnd' set at call-creation time, so
    # by the time we're here it's already resolved.
    is_machine = bool(answered_by) and answered_by.startswith("machine")
    should_record = getattr(order, "includes_recording", True) and not is_machine
    if is_machine and getattr(order, "includes_recording", True):
        print(f"[twilio] record {record_id} went to voicemail — recording skipped even though it was purchased")

    base_url = os.environ.get("BASE_URL", request.url_root.rstrip("/"))
    callback_url = f"{base_url}/recording-ready/{record_id}" if should_record else None
    action_url = f"{base_url}/recording-done/{record_id}" if should_record else None
    twiml = twilio_service.build_twiml(
        audio_urls, record=should_record,
        record_callback_url=callback_url, record_action_url=action_url,
    )
    return Response(twiml, mimetype="text/xml")


@app.route("/recording-done/<int:record_id>", methods=["GET", "POST"])
def recording_done(record_id):
    """
    Where <Record>'s action points once recording finishes. Just hangs up —
    critically, this is NOT the same URL that started the call, which is
    what stops Twilio from re-fetching /call-instructions and replaying the
    whole script (Twilio's default action, if none is given, is to re-request
    the original URL).
    """
    twiml = "<Response><Hangup/></Response>"
    return Response(twiml, mimetype="text/xml")


# ---------- Locked-and-loaded smackagrams ----------

# ---------- Locked-and-loaded smackagrams ----------

@app.route("/locked-n-loaded")
@login_required
def locked_n_loaded_page():
    return render_template("locked_n_loaded.html")


@app.route("/send-a-smack")
def send_a_smack_page():
    return render_template("send_a_smack.html")


@app.route("/smack-lab")
@login_required
def smack_lab_page():
    return render_template("smack_lab.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/contact")
def contact_page():
    return render_template("contact.html")


@app.route("/did-you-get-smacked")
@login_required
def did_you_get_smacked_page():
    return render_template("did_you_get_smacked.html")


@app.route("/meet-smacky")
def meet_smacky_page():
    """
    Brand/mascot introduction page - no login required, this is pure
    marketing content. smacky_image_exists checks whether the real
    generated portrait has been dropped into static/img/smacky-hero.png
    yet; until it has, the template shows a placeholder instead of a
    broken image, and switches over automatically the moment the file
    shows up - no code change needed on launch day.
    """
    image_path = os.path.join(app.root_path, "static", "img", "smacky-hero.png")
    return render_template("meet_smacky.html", smacky_image_exists=os.path.exists(image_path))


@app.route("/reply/<token>")
@login_required
def reply_page(token):
    return render_template("reply.html", reply_token=token)


@app.route("/conversation/<int:reply_id>")
@login_required
def conversation_page(reply_id):
    return render_template("conversation.html", reply_id=reply_id)


@app.route("/api/conversation/<int:reply_id>")
@login_required
def conversation_data(reply_id):
    """
    Both sides of a completed reply exchange — the original smack and the
    reply that was sent back, each with their own real persisted audio.
    """
    reply = Order.query.get(reply_id)
    if not reply or not reply.replied_to_type or not reply.replied_to_id:
        return jsonify({"error": "Conversation not found"}), 404

    original_model = Order if reply.replied_to_type == "order" else Smackagram
    original = original_model.query.get(reply.replied_to_id)
    if not original:
        return jsonify({"error": "Conversation not found"}), 404

    return jsonify({
        "original": {
            "message": original.custom_message,
            "audio_url": original.message_audio_url,
            "created_at": original.created_at.isoformat(),
        },
        "reply": {
            "message": reply.custom_message,
            "audio_url": reply.message_audio_url,
            "created_at": reply.created_at.isoformat(),
        },
    })


@app.route("/smack-chat")
@login_required
def smack_chat_page():
    return render_template("smack_chat.html")


@app.route("/api/chat/teams")
def chat_teams():
    """
    Team list for a Smack Chat league room, from chat_team_lists.py, with
    a live post count per team — real social proof for the browse view,
    showing which rooms already have activity. One grouped query for the
    whole league rather than a separate count query per team.

    Also returns general_chat_count — every league also has a broader,
    not-team-specific room (team="_general" in the ChatPost table), which
    the browse view surfaces prominently above the individual team rooms.
    """
    league = request.args.get("league", "nfl")
    teams = chat_team_lists.CHAT_LEAGUES.get(league, {})
    colors = chat_team_colors.TEAM_COLORS.get(league, {})

    # Reverse-lookup: which division is each team code in, for this league.
    # Leagues without a defined division structure (conferences, soccer)
    # just get None back and render as one flat group on the frontend.
    league_divisions = chat_team_colors.DIVISIONS.get(league, {})
    team_to_division = {}
    for division_name, team_codes in league_divisions.items():
        for code in team_codes:
            team_to_division[code] = division_name

    counts = dict(
        db.session.query(ChatPost.team, func.count(ChatPost.id))
        .filter(ChatPost.league == league)
        .group_by(ChatPost.team)
        .all()
    )

    return jsonify({
        "teams": [
            {
                "code": code,
                "name": name,
                "chat_count": counts.get(code, 0),
                "color": colors.get(code),
                "division": team_to_division.get(code),
            }
            for code, name in sorted(teams.items(), key=lambda x: x[1])
        ],
        "general_chat_count": counts.get("_general", 0),
    })


@app.route("/api/chat/posts")
def chat_posts():
    """
    Posts for a specific team room. sort=top surfaces the highest-rated
    (min 1 rating) first, useful for "best smack talk this week"-style
    browsing; sort=new is straight chronological, the default.
    """
    league = request.args.get("league", "")
    team = request.args.get("team", "")
    sort = request.args.get("sort", "new")

    query = ChatPost.query.filter_by(league=league, team=team)
    posts = query.order_by(ChatPost.created_at.desc()).limit(100).all()

    if sort == "top":
        posts = sorted(posts, key=lambda p: (p.average_rating or 0, p.created_at), reverse=True)

    return jsonify([{
        "id": p.id,
        "display_name": p.display_name,
        "message": p.message,
        "average_rating": p.average_rating,
        "rating_count": p.rating_count,
        "created_at": p.created_at.isoformat(),
    } for p in posts])


@app.route("/api/chat/posts", methods=["POST"])
@login_required
def create_chat_post():
    """
    A real person posting their own manually-typed trash talk — no AI
    generation anywhere in this flow. Still passes through the same
    safety check every custom-typed message on the site goes through
    before it's allowed to go live.
    """
    data = request.json
    league = data.get("league", "")
    team = data.get("team", "")
    display_name = (data.get("display_name") or "Anonymous").strip()[:40]
    message = (data.get("message") or "").strip()

    if not league or not team or not message:
        return jsonify({"error": "League, team, and a message are all required"}), 400
    if len(message) > 500:
        return jsonify({"error": "Keep it under 500 characters"}), 400

    safety = content_moderation.check_message_safety(message)
    if not safety["safe"]:
        print(f"[safety] blocked chat post — reason: {safety['reason']}")
        return jsonify({"error": "That message can't be posted — it may contain threatening, sexual, or harassing content. Try a different angle."}), 400

    post = ChatPost(league=league, team=team, display_name=display_name or "Anonymous", message=message)
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "id": post.id,
        "display_name": post.display_name,
        "message": post.message,
        "average_rating": post.average_rating,
        "rating_count": post.rating_count,
        "created_at": post.created_at.isoformat(),
    })


@app.route("/api/chat/posts/<int:post_id>/rate", methods=["POST"])
@login_required
def rate_chat_post(post_id):
    """
    Records one rating, enforced server-side — the database itself
    rejects a second rating from the same rater_id on the same post
    (unique constraint on ChatRating), not just app logic. rater_id comes
    from the browser today (no accounts yet); once real accounts exist,
    the frontend just sends the real user ID instead and this endpoint
    doesn't need to change at all.
    """
    data = request.json
    rating = data.get("rating")
    rater_id = (data.get("rater_id") or "").strip()

    if not isinstance(rating, int) or rating < 1 or rating > 10:
        return jsonify({"error": "Rating must be a whole number 1-10"}), 400
    if not rater_id:
        return jsonify({"error": "Missing rater identifier"}), 400

    post = ChatPost.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    existing = ChatRating.query.filter_by(post_id=post_id, rater_id=rater_id).first()
    if existing:
        return jsonify({"error": "You've already rated this one"}), 400

    db.session.add(ChatRating(post_id=post_id, rater_id=rater_id, rating=rating))
    post.rating_total += rating
    post.rating_count += 1
    db.session.commit()

    return jsonify({"average_rating": post.average_rating, "rating_count": post.rating_count})


@app.route("/api/chat/posts/<int:post_id>/report", methods=["POST"])
@login_required
def report_chat_post(post_id):
    post = ChatPost.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    post.report_count += 1
    db.session.commit()
    return jsonify({"reported": True})


@app.route("/smack-battle")
@login_required
def smack_battle_page():
    return render_template("smack_battle.html")


@app.route("/battle/<challenge_code>")
@login_required
def battle_room_page(challenge_code):
    return render_template("battle_room.html", challenge_code=challenge_code)


def _lookup_team_color(league, team_name):
    """
    Matches a free-text team name (whatever the person typed when
    creating/joining a battle) to that team's real brand color, using
    the same alias-matching already built for search. Returns None for
    leagues without color data (college sports, soccer) or no match —
    the frontend keeps the default gold/red theme in that case.
    """
    if not team_name:
        return None
    colors = chat_team_colors.TEAM_COLORS.get(league, {})
    for code in colors:
        if team_aliases.matches_search(league, code, team_name):
            return colors[code]
    return None


def _battle_state_json(battle):
    lines = BattleLine.query.filter_by(battle_id=battle.id).order_by(BattleLine.created_at.asc()).all()
    round_results = BattleRoundResult.query.filter_by(battle_id=battle.id).order_by(BattleRoundResult.round_number.asc()).all()
    # Computed server-side (comparing against utcnow() here, not on the
    # client) specifically to avoid any client/server clock skew — a
    # 3-second "still typing" window is a reasonable match for how
    # Slack/iMessage-style indicators typically behave.
    now = datetime.utcnow()
    is_typing_a = bool(battle.last_typed_a and (now - battle.last_typed_a).total_seconds() < 3)
    is_typing_b = bool(battle.last_typed_b and (now - battle.last_typed_b).total_seconds() < 3)
    return {
        "challenge_code": battle.challenge_code,
        "league": battle.league,
        "intensity": battle.intensity,
        "status": battle.status,
        "current_turn": battle.current_turn,
        "round_number": battle.round_number,
        "display_name_a": battle.display_name_a,
        "team_a": battle.team_a,
        "display_name_b": battle.display_name_b,
        "team_b": battle.team_b,
        "lines": [{"side": l.side, "round": l.round_number, "message": l.message, "created_at": l.created_at.isoformat()} for l in lines],
        "round_results": [{"round": r.round_number, "winner": r.winner, "critique_a": r.critique_a, "critique_b": r.critique_b, "score_a": r.score_a, "score_b": r.score_b, "coach_message_a": r.coach_message_a, "coach_message_b": r.coach_message_b} for r in round_results],
        "awaiting_next_round": battle.awaiting_next_round,
        "ready_a": battle.ready_a,
        "ready_b": battle.ready_b,
        "overall_winner": battle.overall_winner,
        "recap_winner_text": battle.recap_winner_text,
        "recap_loser_text": battle.recap_loser_text,
        "rematch_requested_a": battle.rematch_requested_a,
        "rematch_requested_b": battle.rematch_requested_b,
        "rematch_challenge_code": battle.rematch_challenge_code,
        "is_typing_a": is_typing_a,
        "is_typing_b": is_typing_b,
        "team_a_color": _lookup_team_color(battle.league, battle.team_a),
        "team_b_color": _lookup_team_color(battle.league, battle.team_b),
        "vote_count_a": battle.vote_count_a if battle.status == "complete" else None,
        "vote_count_b": battle.vote_count_b if battle.status == "complete" else None,
    }


@app.route("/api/battles", methods=["POST"])
@login_required
def create_battle():
    data = request.json
    league = data.get("league", "")
    team_a = (data.get("team_a") or "").strip()
    display_name_a = (data.get("display_name_a") or "Anonymous").strip()[:40]
    intensity = data.get("intensity", 4)

    if not league or not team_a:
        return jsonify({"error": "League and your team are required"}), 400
    if intensity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid intensity level"}), 400

    challenge_code = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8]
    battle = Battle(challenge_code=challenge_code, league=league, team_a=team_a, display_name_a=display_name_a or "Anonymous", intensity=intensity)
    db.session.add(battle)
    db.session.commit()

    return jsonify({"challenge_code": challenge_code})


@app.route("/api/battles/<challenge_code>")
@login_required
def get_battle(challenge_code):
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    resp = jsonify(_battle_state_json(battle))
    # Mobile Safari in particular can be aggressive about caching GET
    # responses — without this, a poll could silently get served a stale
    # cached response instead of actually hitting the server, which
    # would exactly explain "works fine on desktop, stuck until a manual
    # refresh on mobile."
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/battles/<challenge_code>/join", methods=["POST"])
@login_required
def join_battle(challenge_code):
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    if battle.status != "waiting":
        return jsonify({"error": "This battle already has two sides"}), 400

    data = request.json
    team_b = (data.get("team_b") or "").strip()
    display_name_b = (data.get("display_name_b") or "Anonymous").strip()[:40]
    if not team_b:
        return jsonify({"error": "Your team is required"}), 400

    battle.team_b = team_b
    battle.display_name_b = display_name_b or "Anonymous"
    battle.status = "active"
    db.session.commit()

    return jsonify(_battle_state_json(battle))


def _judge_round_async(battle_id, round_number, team_a, line_a_message, team_b, line_b_message):
    """
    Runs the actual AI judging in a background thread so submitting a
    line responds instantly for both people instead of making whoever
    completes the round sit through a real Claude API call before they
    even see their own message land. Needs its own app context since
    this runs outside the normal request/response cycle.
    """
    with app.app_context():
        try:
            battle = Battle.query.get(battle_id)
            prior_results = BattleRoundResult.query.filter_by(battle_id=battle_id).all()
            wins_a_before = sum(1 for r in prior_results if r.winner == "a")
            wins_b_before = sum(1 for r in prior_results if r.winner == "b")
            scores_a = [r.score_a for r in prior_results if r.score_a is not None]
            scores_b = [r.score_b for r in prior_results if r.score_b is not None]
            avg_a_before = (sum(scores_a) / len(scores_a)) if scores_a else None
            avg_b_before = (sum(scores_b) / len(scores_b)) if scores_b else None

            result = trash_talk_service.judge_battle_round(
                team_a, line_a_message, team_b, line_b_message,
                round_number=round_number, wins_a_before=wins_a_before, wins_b_before=wins_b_before,
                avg_score_a_before=avg_a_before, avg_score_b_before=avg_b_before,
                intensity=battle.intensity if battle else 4,
            )
            existing = BattleRoundResult.query.filter_by(battle_id=battle_id, round_number=round_number).first()
            if not existing:
                db.session.add(BattleRoundResult(
                    battle_id=battle_id,
                    round_number=round_number,
                    winner=result["winner"],
                    critique_a=result["critique_a"],
                    critique_b=result["critique_b"],
                    score_a=result["score_a"],
                    score_b=result["score_b"],
                    coach_message_a=result["coach_message_a"],
                    coach_message_b=result["coach_message_b"],
                ))
                db.session.commit()
        except Exception as e:
            print(f"[battle judge async] failed for battle {battle_id} round {round_number}: {e}")


def _generate_recap_async(battle_id):
    """Same idea as _judge_round_async — the final recap is a real AI call, run in the background so finishing the battle doesn't hang whoever clicks last."""
    with app.app_context():
        try:
            battle = Battle.query.get(battle_id)
            if not battle:
                return
            all_results = BattleRoundResult.query.filter_by(battle_id=battle_id).order_by(BattleRoundResult.round_number.asc()).all()
            wins_a = sum(1 for r in all_results if r.winner == "a")
            wins_b = sum(1 for r in all_results if r.winner == "b")
            overall_winner = "a" if wins_a > wins_b else "b" if wins_b > wins_a else "tie"
            battle.overall_winner = overall_winner

            scores_a = [r.score_a for r in all_results if r.score_a is not None]
            scores_b = [r.score_b for r in all_results if r.score_b is not None]
            avg_a = (sum(scores_a) / len(scores_a)) if scores_a else None
            avg_b = (sum(scores_b) / len(scores_b)) if scores_b else None
            winner_avg_score = avg_a if overall_winner == "a" else avg_b if overall_winner == "b" else None

            all_lines = BattleLine.query.filter_by(battle_id=battle_id).order_by(BattleLine.created_at.asc()).all()
            recap = trash_talk_service.generate_battle_recap(
                battle.team_a, battle.team_b,
                [{"side": l.side, "round": l.round_number, "message": l.message} for l in all_lines],
                [{"round": r.round_number, "winner": r.winner} for r in all_results],
                overall_winner,
                winner_avg_score=winner_avg_score,
            )
            battle.recap_winner_text = recap["winner_recap"]
            battle.recap_loser_text = recap["loser_recap"]
            db.session.commit()
        except Exception as e:
            print(f"[battle recap async] failed for battle {battle_id}: {e}")


@app.route("/api/battles/<challenge_code>/line", methods=["POST"])
@login_required
def submit_battle_line(challenge_code):
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    if battle.status != "active":
        return jsonify({"error": "This battle isn't active"}), 400

    data = request.json
    side = data.get("side", "")
    message = (data.get("message") or "").strip()

    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400
    if side != battle.current_turn:
        return jsonify({"error": "It's not your turn"}), 400
    if not message:
        return jsonify({"error": "Message can't be empty"}), 400
    if len(message) > 500:
        return jsonify({"error": "Keep it under 500 characters"}), 400

    safety = content_moderation.check_message_safety(message)
    if not safety["safe"]:
        print(f"[safety] blocked battle line — reason: {safety['reason']}")
        return jsonify({"error": "That message can't be posted — it may contain threatening, sexual, or harassing content. Try a different angle."}), 400

    db.session.add(BattleLine(battle_id=battle.id, side=side, round_number=battle.round_number, message=message))

    if side == "a":
        battle.current_turn = "b"
        db.session.commit()
    else:
        # Round complete — pause immediately (no timer, no auto-advance;
        # the round only actually moves forward once both sides hit
        # "Start next round" via the /ready endpoint). The actual AI
        # judging happens in the background so this response comes back
        # right away — both people see the line land instantly instead
        # of waiting on a real Claude API call first.
        battle.awaiting_next_round = True
        battle.ready_a = False
        battle.ready_b = False
        db.session.commit()

        line_a = BattleLine.query.filter_by(battle_id=battle.id, round_number=battle.round_number, side="a").first()
        threading.Thread(
            target=_judge_round_async,
            args=(battle.id, battle.round_number, battle.team_a, line_a.message if line_a else "", battle.team_b, message),
            daemon=True,
        ).start()

    return jsonify(_battle_state_json(battle))


@app.route("/api/battles/<challenge_code>/ready", methods=["POST"])
@login_required
def ready_for_next_round(challenge_code):
    """
    Either side confirming they're ready moves the round forward
    immediately for both — one click from whoever gets there first is
    enough, rather than requiring both people to independently confirm.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    if not battle.awaiting_next_round:
        return jsonify({"error": "No round is currently pending"}), 400

    data = request.json
    side = data.get("side", "")
    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400

    battle.awaiting_next_round = False
    battle.ready_a = False
    battle.ready_b = False
    battle.current_turn = "a"
    battle.round_number += 1
    if battle.round_number > 5:
        battle.status = "complete"
        battle.completed_at = datetime.utcnow()
        db.session.commit()

        # Recap generation is a real AI call — run it in the
        # background so whoever clicks ready doesn't sit there waiting
        # for it before seeing the battle end.
        threading.Thread(target=_generate_recap_async, args=(battle.id,), daemon=True).start()
        return jsonify(_battle_state_json(battle))

    db.session.commit()
    return jsonify(_battle_state_json(battle))


@app.route("/api/battles/<challenge_code>/typing", methods=["POST"])
@login_required
def battle_typing_ping(challenge_code):
    """
    Lightweight ping saying "I'm actively typing right now" — the
    frontend throttles these to at most once every couple seconds while
    someone's typing in their turn. No response body needed beyond
    success; the opponent picks this up via their next regular poll.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404

    data = request.json
    side = data.get("side", "")
    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400

    if side == "a":
        battle.last_typed_a = datetime.utcnow()
    else:
        battle.last_typed_b = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/battles/<challenge_code>/vote", methods=["POST"])
@login_required
def vote_battle(challenge_code):
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    if battle.status != "complete":
        return jsonify({"error": "Voting opens once the battle is finished"}), 400

    data = request.json
    voted_for = data.get("voted_for", "")
    voter_id = (data.get("voter_id") or "").strip()

    if voted_for not in ("a", "b"):
        return jsonify({"error": "Invalid vote"}), 400
    if not voter_id:
        return jsonify({"error": "Missing voter identifier"}), 400

    existing = BattleVote.query.filter_by(battle_id=battle.id, voter_id=voter_id).first()
    if existing:
        return jsonify({"error": "You've already voted on this battle"}), 400

    db.session.add(BattleVote(battle_id=battle.id, voter_id=voter_id, voted_for=voted_for))
    db.session.commit()

    return jsonify({"vote_count_a": battle.vote_count_a, "vote_count_b": battle.vote_count_b})


@app.route("/api/battles/<challenge_code>/rematch", methods=["POST"])
@login_required
def request_rematch(challenge_code):
    """
    One side asking for a rematch — same "both sides have to agree" gate
    used for advancing rounds. Once both have requested it, a brand new
    Battle is created with the same teams and names, and its code is
    stashed on the old (completed) battle so both people's clients —
    still polling this old battle — pick it up and redirect themselves.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    if battle.status != "complete":
        return jsonify({"error": "Rematch is only available once the battle is finished"}), 400

    data = request.json
    side = data.get("side", "")
    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400

    if side == "a":
        battle.rematch_requested_a = True
    else:
        battle.rematch_requested_b = True

    if battle.rematch_requested_a and battle.rematch_requested_b and not battle.rematch_challenge_code:
        new_code = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8]
        new_battle = Battle(
            challenge_code=new_code,
            league=battle.league,
            team_a=battle.team_a,
            display_name_a=battle.display_name_a,
            team_b=battle.team_b,
            display_name_b=battle.display_name_b,
            status="active",
        )
        db.session.add(new_battle)
        battle.rematch_challenge_code = new_code

    db.session.commit()
    return jsonify(_battle_state_json(battle))


@app.route("/api/battle-sfx")
def battle_sfx():
    """
    Sound effects for the battle room — served entirely from static
    files, no API calls. Expects these files to exist under
    static/sfx/ (any that are missing just come back as null, and the
    frontend already treats a null URL as "skip this sound," so nothing
    breaks if a file hasn't been added yet):

    battle-intro.mp3, crowd-loop.mp3, new-line.mp3, countdown-tick.mp3,
    bell.mp3, cheer.mp3, boo.mp3, waiting-music.mp3, critique-reveal.mp3,
    judging-beep.mp3
    """
    sfx_files = {
        "intro_url": "battle-intro.mp3",
        "crowd_loop_url": "crowd-loop.mp3",
        "new_line_url": "new-line.mp3",
        "judging_beep_url": "judging-beep.mp3",
        "countdown_tick_url": "countdown-tick.mp3",
        "bell_url": "bell.mp3",
        "cheer_url": "cheer.mp3",
        "boo_url": "boo.mp3",
        "waiting_music_url": "waiting-music.mp3",
        "critique_reveal_url": "critique-reveal.mp3",
    }
    result = {}
    for key, filename in sfx_files.items():
        filepath = os.path.join(app.static_folder, "sfx", filename)
        result[key] = url_for("static", filename=f"sfx/{filename}") if os.path.exists(filepath) else None
    return jsonify(result)


@app.route("/api/check-if-smacked", methods=["POST"])
def check_if_smacked():
    """
    The "Smack Inbox" — returns EVERY delivered smack for a phone number,
    not just one, newest first. Each item is flagged replied/unreplied;
    replied items link to a conversation view, unreplied opted-in items
    link to a reply page. Digit-only comparison so formatting differences
    (+1, dashes, spaces, parens) don't cause false misses.

    Searching itself is intentionally open (no login required) - the
    person checking is often the target of a prank, not necessarily an
    existing Smackagram user, and just wanting to know "did someone send
    something to my number" shouldn't require an account. But the actual
    message content is gated behind proven ownership of that exact
    number (see VerifiedPhone) - previously ANY logged-in user could
    read message content for ANY phone number just by typing it in,
    with zero proof they actually owned it. If there's a match but the
    requester hasn't verified this number, this returns just a count so
    the frontend can show an enticing "something's here" teaser without
    leaking the actual content.
    """
    data = request.json
    raw_phone = data.get("phone", "")
    digits = "".join(c for c in raw_phone if c.isdigit())
    if len(digits) < 10:
        return jsonify({"error": "Enter a valid phone number"}), 400

    def matches(stored_phone):
        return stored_phone and "".join(c for c in stored_phone if c.isdigit()).endswith(digits[-10:])

    # "completed" is Twilio's real CallStatus value for a call that
    # connected and finished normally. For smackagrams, also require
    # status="fired" so we're only matching calls that genuinely fired,
    # not just armed-but-never-resolved.
    delivered_orders = Order.query.filter_by(call_status="completed").order_by(Order.created_at.desc()).all()
    fired_smackagrams = Smackagram.query.filter_by(status="fired", call_status="completed").order_by(Smackagram.created_at.desc()).all()

    all_matches = [r for r in (delivered_orders + fired_smackagrams) if matches(r.recipient_phone)]
    if not all_matches:
        return jsonify({"found": False, "items": []})

    all_matches.sort(key=lambda r: r.created_at, reverse=True)

    user = get_current_user()
    is_verified = False
    if user:
        is_verified = VerifiedPhone.query.filter_by(user_id=user.id, phone_digits=digits[-10:]).first() is not None

    if not is_verified:
        # Teaser only - enough for the frontend to show something
        # enticing is there, without exposing any actual content.
        return jsonify({"found": True, "verified": False, "count": len(all_matches)})

    items = []
    for record in all_matches:
        record_type = "order" if isinstance(record, Order) else "smackagram"
        preview = (record.custom_message or "")[:90]
        item = {
            "type": record_type,
            "id": record.id,
            "preview": preview,
            "created_at": record.created_at.isoformat(),
            "replied": bool(record.replied),
        }
        if record.replied:
            # Find the reply that was sent for this one, to link the
            # conversation view — the reply is always an Order record.
            reply = Order.query.filter_by(replied_to_type=record_type, replied_to_id=record.id).first()
            item["conversation_id"] = reply.id if reply else None
        elif record.reply_opt_in and record.reply_token:
            # Never expose the raw sender_phone — only the token.
            item["reply_token"] = record.reply_token
        items.append(item)

    return jsonify({"found": True, "verified": True, "items": items})


@app.route("/api/verify-phone/send", methods=["POST"])
@login_required
def api_verify_phone_send():
    """
    Sends a 6-digit SMS code to an arbitrary phone number the logged-in
    user is trying to prove ownership of, to unlock viewing Smack Inbox
    messages sent to that number. Deliberately separate from the
    account-registration 2FA flow (_send_2fa_code) - that verifies the
    account holder's OWN registered phone; this verifies an arbitrary
    number that may differ from it.
    """
    user = get_current_user()
    data = request.json or {}
    raw_phone = data.get("phone", "")
    digits = "".join(c for c in raw_phone if c.isdigit())
    if len(digits) < 10:
        return jsonify({"error": "Enter a valid phone number"}), 400
    phone_digits = digits[-10:]

    # Simple abuse guard: don't let someone repeatedly fire texts at a
    # number that isn't theirs. One outstanding code per user+number at
    # a time, and a short cooldown before a fresh one can be requested.
    recent = PhoneVerificationCode.query.filter_by(user_id=user.id, phone_digits=phone_digits).order_by(PhoneVerificationCode.created_at.desc()).first()
    if recent and recent.created_at > datetime.utcnow() - timedelta(seconds=60):
        return jsonify({"error": "Please wait a moment before requesting another code."}), 429

    code = f"{secrets.randbelow(1000000):06d}"
    verification = PhoneVerificationCode(
        user_id=user.id,
        phone_digits=phone_digits,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(verification)

    try:
        twilio_service.send_sms(raw_phone, f"Your Smackagram verification code is {code}. It expires in 10 minutes.")
    except Exception as e:
        db.session.rollback()
        print(f"[verify-phone] failed to send code: {e}")
        return jsonify({"error": "Couldn't send a verification text to that number — please double-check it and try again."}), 400

    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/verify-phone/confirm", methods=["POST"])
@login_required
def api_verify_phone_confirm():
    """
    Checks the code entered against the most recent one sent for this
    user+number, and if it matches and hasn't expired, records a
    VerifiedPhone so future Smack Inbox searches for this number unlock
    full content for this user without needing to re-verify every time.
    """
    user = get_current_user()
    data = request.json or {}
    raw_phone = data.get("phone", "")
    code = (data.get("code") or "").strip()
    digits = "".join(c for c in raw_phone if c.isdigit())
    if len(digits) < 10:
        return jsonify({"error": "Enter a valid phone number"}), 400
    phone_digits = digits[-10:]

    verification = PhoneVerificationCode.query.filter_by(user_id=user.id, phone_digits=phone_digits).order_by(PhoneVerificationCode.created_at.desc()).first()
    if not verification or verification.expires_at < datetime.utcnow():
        return jsonify({"error": "That code has expired — request a new one."}), 400
    if verification.code != code:
        return jsonify({"error": "That code doesn't match — double-check it and try again."}), 400

    already_verified = VerifiedPhone.query.filter_by(user_id=user.id, phone_digits=phone_digits).first()
    if not already_verified:
        db.session.add(VerifiedPhone(user_id=user.id, phone_digits=phone_digits))
    db.session.commit()

    return jsonify({"ok": True})


def _find_by_reply_token(token):
    """Shared lookup — checks both Order and Smackagram, same record_id space pattern used elsewhere."""
    return Order.query.filter_by(reply_token=token).first() or Smackagram.query.filter_by(reply_token=token).first()


@app.route("/api/reply-context/<token>")
@login_required
def reply_context(token):
    """
    Powers the reply page's "instant replay" — the original message text
    and its actual persisted audio URL, so the person can re-read/re-hear
    exactly what was sent before crafting a reply. Safe to expose: no
    phone numbers, no sender identity, just the roast content itself.
    """
    record = _find_by_reply_token(token)
    if not record:
        return jsonify({"error": "This reply link isn't valid"}), 404

    return jsonify({
        "original_message": record.custom_message,
        "message_audio_url": record.message_audio_url,
        "already_replied": bool(record.replied),
    })


@app.route("/api/generate-reply-smack", methods=["POST"])
@login_required
def generate_reply_smack_route():
    """
    AI-assisted comeback — reads the ORIGINAL message server-side (never
    trusts client-supplied text for this, so someone can't feed it an
    arbitrary prompt) and generates a reply that actually responds to
    what was said.
    """
    data = request.json
    token = data.get("reply_token", "")
    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)

    record = _find_by_reply_token(token)
    if not record or not record.custom_message:
        return jsonify({"error": "This reply link isn't valid"}), 404

    reply_text = trash_talk_service.generate_reply_smack(record.custom_message, sensitivity=sensitivity)
    return jsonify({"generated_text": reply_text})


@app.route("/api/reply-orders", methods=["POST"])
@login_required
def create_reply_order():
    """
    Submits the actual reply smack. The real recipient phone number is
    looked up server-side from the token — it's never part of the request
    body, so it's never exposed to or trusted from the browser at any
    point in this flow.
    """
    data = request.json
    token = data.get("reply_token", "")

    original = _find_by_reply_token(token)
    if not original or not original.sender_phone:
        return jsonify({"error": "This reply link isn't valid"}), 404

    if original.replied:
        return jsonify({"error": "A reply has already been sent for this smack"}), 400

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    custom_message = data.get("custom_message", "")
    safety = content_moderation.check_message_safety(custom_message)
    if not safety["safe"]:
        print(f"[safety] blocked reply order attempt — reason: {safety['reason']}")
        return jsonify({"error": "This message can't be sent — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    price = 200 if data.get("include_recording", True) else 100
    order = Order(
        custom_message=custom_message,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name="Unknown",  # we deliberately never learn/store the original sender's name
        recipient_phone=original.sender_phone,
        consent_confirmed=True,
        price_cents=price,
        includes_recording=data.get("include_recording", True),
        # Links back to the original for the conversation view — safe to
        # set now even before payment completes, since this alone doesn't
        # mark the original as "replied" (that only happens once the
        # reply's call actually fires, in the Stripe webhook, so an
        # abandoned checkout doesn't wrongly lock out a real reply later).
        replied_to_type="order" if isinstance(original, Order) else "smackagram",
        replied_to_id=original.id,
    )
    db.session.add(order)
    db.session.commit()

    session = stripe_service.create_checkout_session(
        order_id=order.id,
        amount_cents=price,
        base_url=os.environ.get("BASE_URL", request.url_root.rstrip("/")),
    )
    order.stripe_payment_intent_id = session.id
    db.session.commit()

    return jsonify({"checkout_url": session.url})


@app.route("/locked-n-loaded/success")
def locked_n_loaded_success():
    session_id = request.args.get("session_id")
    return render_template("locked_n_loaded_success.html", session_id=session_id)


@app.route("/api/games/upcoming")
def upcoming_games():
    """Powers the game picker — only games within 48h. ?sport=nfl|nba|mlb|nhl|ncaaf&team=yankees"""
    sport = request.args.get("sport", "nfl")
    team_query = request.args.get("team", "").strip() or None
    resp = jsonify(sports_service.get_upcoming_games(sport=sport, hours_ahead=48, team_query=team_query))
    # Explicitly forbid caching — this powers live scores, and a cached
    # response (even briefly) would show a stale score during a live game,
    # since the browser might otherwise reuse an identical prior request
    # instead of hitting the server again on every auto-refresh.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/api/smackagrams", methods=["POST"])
@login_required
def _execute_arm_smackagram(user, data: dict) -> dict:
    """
    The actual Smackagram-creation logic, factored out so both the
    normal /api/smackagrams request AND the webhook's "resume this
    pending action now that the wallet is topped up" path can call the
    exact same code. Re-validates game timing here specifically (not
    just in the route handler) since real time can pass between the
    original attempt and a resumed one completing payment - a game
    that was armable 48 hours out when first submitted could have
    already started by the time someone finishes topping up. Assumes
    the wallet has ALREADY been debited by the caller. Raises ValueError
    with a user-facing message if the game is no longer valid to arm.
    """
    game_start = datetime.fromisoformat(data["game_start_time"])
    if game_start <= datetime.now(timezone.utc):
        raise ValueError("This game has already started, so it can no longer be armed.")

    mode = data.get("mode", "custom")

    smackagram = Smackagram(
        user_id=user.id,
        game_id=data["game_id"],
        sport=data.get("sport", "nfl"),
        home_team=data["home_team"],
        away_team=data["away_team"],
        target_team=data["target_team"],
        game_start_time=game_start,
        mode=mode,
        sensitivity=data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY),
        custom_message=data.get("custom_message") if mode == "custom" else None,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
        price_cents=wallet_service.LOCKED_N_LOADED_COST_CENTS,
    )
    db.session.add(smackagram)
    db.session.commit()

    return {"smackagram_id": smackagram.id, "redirect": "/locked-n-loaded/success"}


@app.route("/api/smackagrams", methods=["POST"])
@login_required
def arm_smackagram():
    """
    Locks in a smackagram against a future game. Debits the wallet
    immediately when armed - NOT a Stripe card hold anymore, since a
    wallet balance is just a number and can't be "authorized" the way
    a card can. If the target team wins (or the game is postponed/
    canceled), scheduler.py's resolution job credits the $1 back to
    the wallet automatically - see release logic there. If the target
    team loses, the debit simply stands; nothing further happens.
    """
    user = get_current_user()
    data = request.json

    game_start = datetime.fromisoformat(data["game_start_time"])
    if game_start > datetime.now(timezone.utc) + timedelta(hours=48):
        return jsonify({"error": "Games can only be armed within 48 hours of kickoff"}), 400

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    mode = data.get("mode", "custom")
    if mode not in ("custom", "auto_summary"):
        return jsonify({"error": "Invalid mode"}), 400

    if mode == "custom" and not data.get("custom_message", "").strip():
        return jsonify({"error": "Custom message can't be empty"}), 400

    if mode == "custom":
        safety = content_moderation.check_message_safety(data.get("custom_message", ""))
        if not safety["safe"]:
            print(f"[safety] blocked smackagram arm attempt — reason: {safety['reason']}")
            return jsonify({"error": "This message can't be sent — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)
    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    if not wallet_service.has_sufficient_balance(user, wallet_service.LOCKED_N_LOADED_COST_CENTS):
        redirect = _store_pending_action(user, "locked_n_loaded", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    txn = wallet_service.debit_wallet(
        user, wallet_service.LOCKED_N_LOADED_COST_CENTS, "locked_n_loaded",
        description=f"Locked & Loaded - {data.get('target_team', 'target')} armed",
    )
    if txn is None:
        redirect = _store_pending_action(user, "locked_n_loaded", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    result = _execute_arm_smackagram(user, data)
    return jsonify(result)


# ---------- Twilio status callbacks ----------

@app.route("/call-status/<int:record_id>", methods=["POST"])
def call_status(record_id):
    """
    Twilio's real call-completion webhook — registered at call-creation
    time in place_prank_call(). Same record_id space is shared by both
    Order and Smackagram (both use the same place_prank_call function),
    so this has to check both, the same way /call-instructions does.
    """
    status = request.form.get("CallStatus")
    record = Order.query.get(record_id) or Smackagram.query.get(record_id)
    if record:
        record.call_status = status
        db.session.commit()
    return "", 204


@app.route("/recording-ready/<int:record_id>", methods=["POST"])
def recording_ready(record_id):
    recording_url = request.form.get("RecordingUrl")
    order = Order.query.get(record_id)
    smackagram = Smackagram.query.get(record_id)
    target = order or smackagram
    if target:
        target.recording_url = recording_url
        db.session.commit()
    return "", 204


@app.route("/api/cron/check-smackagrams", methods=["GET", "POST"])
def cron_check_smackagrams():
    """
    Called by an external scheduler (e.g. cron-job.org, free tier) every
    3 minutes to resolve any armed locked-and-loaded smackagrams whose
    game has ended. Replaces an in-process background scheduler that
    proved unreliable — this runs as a normal HTTP request, the same
    mechanism every other working feature in this app already uses, so it
    doesn't depend on a background thread surviving inside the web process.

    Protected by a secret key (not the site password, since the external
    cron service can't provide login credentials) — pass it as
    ?key=... matching the CRON_SECRET environment variable.
    """
    provided_key = request.args.get("key", "")
    expected_key = os.environ.get("CRON_SECRET", "")
    if not expected_key or provided_key != expected_key:
        return jsonify({"error": "unauthorized"}), 401

    check_armed_smackagrams()
    return jsonify({"ok": True})


@app.route("/smackcast")
@login_required
def smackcast_page():
    return render_template("smackcast.html")


@app.route("/smackcast/test")
@login_required
def smackcast_test_page():
    """
    Admin-only test tool — runs the full real pipeline (script, audio,
    meme) against realistic sample matchup data instead of a real
    league, so the whole generation flow can be verified without
    needing real fantasy accounts or touching any real strangers' data.
    """
    user = get_current_user()
    if not user.is_admin:
        return "Not authorized.", 403
    return render_template("smackcast_test.html")


@app.route("/api/smackcast/test-generate", methods=["POST"])
@login_required
def api_smackcast_test_generate():
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    data = request.json or {}
    sport = (data.get("sport") or "nfl").strip()
    league_name = (data.get("league_name") or "Test League").strip()
    team_count = int(data.get("team_count") or 10)
    week = int(data.get("week") or 1)

    if sport not in ("nfl", "nba", "mlb"):
        return jsonify({"error": "Unsupported sport."}), 400
    if team_count < 4 or team_count > 20:
        return jsonify({"error": "Team count must be between 4 and 20."}), 400

    try:
        matchups = smackcast_service.generate_sample_matchups(sport, team_count)

        result = smackcast_service.generate_weekly_recap_script(
            league_name=league_name, week=week, matchups=matchups, team_count=team_count, sport=sport,
        )
        script = result["full_text"]
        best_line = result["best_line"]
        audio_url = smackcast_service.assemble_recap_audio(
            result["intro"], result["segments"], result["outro"]
        )
        meme_url = None
        if best_line:
            try:
                meme_url = smackcast_service.generate_meme_image(best_line, league_name, week)
            except Exception as e:
                print(f"[smackcast test] meme generation failed: {e}")
    except Exception as e:
        print(f"[smackcast test] generation failed: {e}")
        return jsonify({"error": f"Generation failed: {e}"}), 500

    return jsonify({
        "matchups": matchups,
        "script": script,
        "best_line": best_line,
        "audio_url": audio_url,
        "meme_url": meme_url,
    })


@app.route("/api/smackcast/find-sleeper-leagues", methods=["POST"])
@login_required
def api_find_sleeper_leagues():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    sport = (data.get("sport") or "nfl").strip()
    if not username:
        return jsonify({"error": "Enter your Sleeper username."}), 400
    if sport not in sleeper_service.SUPPORTED_SPORTS:
        return jsonify({"error": "Unsupported sport for Sleeper."}), 400

    from datetime import datetime as _dt
    season = str(_dt.utcnow().year)
    leagues = sleeper_service.find_leagues_by_username(username, season, sport=sport)
    if not leagues:
        return jsonify({"error": "No leagues found for that username this season."}), 404
    return jsonify({"leagues": leagues, "season": season})


@app.route("/api/smackcast/connect-espn-league", methods=["POST"])
@login_required
def api_connect_espn_league():
    """
    ESPN has no "find my leagues by username" flow like Sleeper — the
    owner provides their league ID directly (found in their ESPN
    Fantasy URL), plus cookies if it's a private league. This endpoint
    doubles as the connection test: get_league_info() will fail here if
    the ID is wrong or the cookies don't match, before any money changes
    hands.
    """
    data = request.json or {}
    league_id = (data.get("league_id") or "").strip()
    sport = (data.get("sport") or "nfl").strip()
    swid = (data.get("swid") or "").strip() or None
    espn_s2 = (data.get("espn_s2") or "").strip() or None

    if not league_id:
        return jsonify({"error": "Enter your ESPN league ID."}), 400
    if sport not in espn_service.GAME_CODES:
        return jsonify({"error": "Unsupported sport for ESPN."}), 400

    from datetime import datetime as _dt
    season = str(_dt.utcnow().year)

    info = espn_service.get_league_info(league_id, season, sport=sport, swid=swid, espn_s2=espn_s2)
    if not info:
        return jsonify({"error": "Couldn't connect to that league. Double-check the league ID — if it's private, you'll need to add your SWID and espn_s2 cookies too."}), 404

    return jsonify({"league": info, "season": season})


@app.route("/api/smackcast/create-subscription", methods=["POST"])
@login_required
def api_create_smackcast_subscription():
    user = get_current_user()
    data = request.json or {}

    platform = (data.get("platform") or "sleeper").strip()
    if platform not in ("sleeper", "espn"):
        return jsonify({"error": "Unsupported platform."}), 400

    sport = (data.get("sport") or "nfl").strip()
    if platform == "sleeper" and sport not in sleeper_service.SUPPORTED_SPORTS:
        return jsonify({"error": "Sleeper doesn't support that sport — only football and basketball leagues exist there."}), 400
    if platform == "espn" and sport not in espn_service.GAME_CODES:
        return jsonify({"error": "Unsupported sport."}), 400

    league_id = (data.get("league_id") or "").strip()
    league_name = (data.get("league_name") or "").strip()
    team_count = data.get("team_count")
    season = data.get("season")

    if not league_id or not season:
        return jsonify({"error": "Missing league information."}), 400

    delivery_methods = data.get("delivery_methods") or {}

    espn_swid = None
    espn_s2 = None
    if platform == "espn":
        espn_swid = (data.get("swid") or "").strip() or None
        espn_s2 = (data.get("espn_s2") or "").strip() or None

    subscription = SmackcastSubscription(
        user_id=user.id,
        platform=platform,
        sport=sport,
        league_id=league_id,
        league_name=league_name,
        team_count=team_count,
        season_year=int(season),
        espn_swid=espn_swid,
        espn_s2=espn_s2,
        deliver_web_link=True,
        deliver_phone_call=bool(delivery_methods.get("phone_call")),
        phone_call_number=(delivery_methods.get("phone_call_number") or "").strip() or None,
        deliver_sms=bool(delivery_methods.get("sms")),
        sms_number=(delivery_methods.get("sms_number") or "").strip() or None,
        deliver_discord=bool(delivery_methods.get("discord")),
        discord_webhook_url=(delivery_methods.get("discord_webhook_url") or "").strip() or None,
        deliver_groupme=bool(delivery_methods.get("groupme")),
        groupme_bot_id=(delivery_methods.get("groupme_bot_id") or "").strip() or None,
    )
    db.session.add(subscription)
    db.session.commit()

    base_url = os.environ["BASE_URL"]
    checkout_session = stripe_service.create_smackcast_checkout_session(subscription.id, base_url)
    return jsonify({"checkout_url": checkout_session.url})


@app.route("/smackcast/success")
@login_required
def smackcast_success_page():
    return render_template("smackcast_success.html")


@app.route("/smackcast-recap/<share_token>")
def smackcast_recap_page(share_token):
    """
    Public, no login required — this is the universal delivery fallback
    that works for literally any platform someone's league already
    chats on, since it's just a link anyone can paste anywhere.
    """
    recap = SmackcastRecap.query.filter_by(share_token=share_token).first()
    if not recap:
        return "Recap not found.", 404
    subscription = SmackcastSubscription.query.get(recap.subscription_id)
    return render_template("smackcast_recap.html", recap=recap, subscription=subscription)


@app.route("/smackcast-call-instructions/<int:recap_id>", methods=["GET", "POST"])
def smackcast_call_instructions(recap_id):
    """
    Twilio hits this once the call connects (see place_smackcast_call).
    Just plays the recap's audio straight through — no branching logic
    needed since this is one-way playback, not an interactive call.
    """
    recap = SmackcastRecap.query.get(recap_id)
    if not recap or not recap.audio_url:
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>', mimetype="text/xml")
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{recap.audio_url}</Play></Response>'
    return Response(twiml, mimetype="text/xml")


@app.route("/api/cron/generate-smackcasts", methods=["GET", "POST"])
def cron_generate_smackcasts():
    """
    Called by an external scheduler configured to hit this every Tuesday
    around 9AM — same reasoning as check_armed_smackagrams above (an
    in-process scheduler already proved unreliable on Render's free
    tier). Safe to hit more than once, since generate_weekly_smackcasts
    itself checks whether each subscription already has this week's
    recap before generating another.
    """
    provided_key = request.args.get("key", "")
    expected_key = os.environ.get("CRON_SECRET", "")
    if not expected_key or provided_key != expected_key:
        return jsonify({"error": "unauthorized"}), 401

    generate_weekly_smackcasts()
    return jsonify({"ok": True})


@app.route("/api/admin/check-team-codes")
def admin_check_team_codes():
    """
    One-time diagnostic tool — pulls SportsDataIO's real Teams list for a
    sport and compares it against our hand-built DISPLAY_NAMES table in
    team_aliases.py, directly flagging any team whose real code doesn't
    match what we have on file (exactly the class of bug that broke the
    White Sox: filed under "CWS" when SportsDataIO actually uses "CHW").

    ?sport=mlb|nfl|nba|nhl&key=... (same secret as the cron endpoint)
    Not linked from anywhere in the UI — visit directly to run it.
    """
    provided_key = request.args.get("key", "")
    expected_key = os.environ.get("CRON_SECRET", "")
    if not expected_key or provided_key != expected_key:
        return jsonify({"error": "unauthorized"}), 401

    sport = request.args.get("sport", "mlb")
    try:
        teams = sports_service.get_all_teams(sport)
    except requests.exceptions.HTTPError as e:
        # Surface exactly what SportsDataIO said instead of a generic
        # crash — this is what should have happened the first time the
        # soccer endpoint guess was wrong, instead of a bare 500.
        return jsonify({
            "sport": sport,
            "error": "SportsDataIO request failed",
            "status_code": e.response.status_code if e.response is not None else None,
            "response_body": e.response.text[:500] if e.response is not None else str(e),
        }), 502

    our_table = team_aliases.DISPLAY_NAMES.get(sport, {})
    real_codes = {}
    for t in teams:
        code = t.get("Key") or t.get("Abbreviation")
        name = t.get("Name") or t.get("City")
        if code:
            real_codes[code] = name

    missing_from_our_table = {code: name for code, name in real_codes.items() if code not in our_table}
    in_our_table_but_not_real = {code: name for code, name in our_table.items() if code not in real_codes}

    return jsonify({
        "sport": sport,
        "real_team_count": len(real_codes),
        "our_table_count": len(our_table),
        "MISMATCHES_missing_from_our_table": missing_from_our_table,
        "MISMATCHES_in_our_table_but_code_not_real": in_our_table_but_not_real,
    })


with app.app_context():
    db.create_all()

    # db.create_all() only creates tables that don't exist yet - it
    # never alters an already-existing table to add a new column. The
    # wallet system added balance_cents to the existing users table and
    # user_id to the existing smackagrams table; those need an explicit
    # migration on a live Postgres database that already has data in it
    # (this is exactly what caused a production outage: the model
    # defined the new column, but the actual database table never got
    # it). Uses IF NOT EXISTS so this is safe to run on every startup,
    # not just once - a real migration tool (Alembic) would be the
    # more correct long-term approach, but this unblocks things now
    # without needing to add that whole system under production pressure.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance_cents INTEGER DEFAULT 0 NOT NULL"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS user_id INTEGER"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS intensity INTEGER DEFAULT 4 NOT NULL"))
            conn.commit()

    # Seed the always-available admin test account, per explicit request.
    # SECURITY NOTE: admin/admin is a deliberately weak, publicly-known
    # credential — acceptable for internal testing before launch, but
    # this MUST be changed or removed before any real public launch.
    admin_user = User.query.filter_by(email="admin").first()
    if not admin_user:
        admin_user = User(
            customer_number=1000000,
            first_name="Admin",
            last_name="Test",
            screen_name="Admin",
            email="admin",
            phone="0000000000",
            date_of_birth=date(1990, 1, 1),
            terms_accepted_at=datetime.utcnow(),
            is_admin=True,
        )
        admin_user.set_password("admin")
        db.session.add(admin_user)
        db.session.commit()
        print("[auth] seeded admin test account (admin/admin)")

    # Second admin account — same reasoning, but a separate login so two
    # people (e.g. the founder and an administrator) can both be logged
    # in simultaneously without sharing one session/account.
    admin1_user = User.query.filter_by(email="admin1").first()
    if not admin1_user:
        admin1_user = User(
            customer_number=999999,
            first_name="Admin",
            last_name="One",
            screen_name="Admin1",
            email="admin1",
            phone="0000000001",
            date_of_birth=date(1990, 1, 1),
            terms_accepted_at=datetime.utcnow(),
            is_admin=True,
        )
        admin1_user.set_password("admin")
        db.session.add(admin1_user)
        db.session.commit()
        print("[auth] seeded second admin test account (admin1/admin)")



@app.route("/api/teams/all")
def all_teams():
    """
    Every team we know about, flattened across all leagues, for the site-wide
    team autocomplete. Smack Chat originally fetched this as 16 separate
    per-league calls; one cached call is cheaper and lets any page reuse it.
    """
    resp = jsonify({"teams": team_display.all_teams()})
    # The list only changes when we edit chat_team_lists.py, so browsers may
    # hold it for five minutes rather than refetching on every page view.
    # stale-while-revalidate lets a stale copy render instantly while a
    # fresh one is fetched in the background, so nobody waits and nobody
    # is stuck on old data for long.
    resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
    return resp


# ---------- Branded error pages ----------
# Without these, Flask serves its default white "Not Found" page, which on a
# black site reads as broken rather than as a wrong URL. Smackcast recap links
# and battle codes both expire, so real people hit these.

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    # A 500 is often a database problem - and the site-wide context processor
    # that injects current_user queries the database on every render. So the
    # error page itself can fail for exactly the same reason. Fall back to
    # plain text rather than letting the error handler raise its own error.
    try:
        return render_template("500.html"), 500
    except Exception:
        return ("Something broke on our end, not yours. "
                "Give it a second and try again."), 500


if __name__ == "__main__":
    app.run(debug=True)
