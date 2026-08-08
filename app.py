import os
import re
from urllib.parse import quote
import json
import functools
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone, date

from flask import Flask, render_template, request, jsonify, Response, url_for, session, redirect
from sqlalchemy import func
import requests
from dotenv import load_dotenv

from models import SmackcastWeeklyNote
from models import db, DailyShow, Setting, Scenario, Order, Smackagram, ChatPost, ChatRating, Battle, BattleLine, BattleVote, BattleViewer, BattleRoundResult, BattleLineReaction, User, SmackcastSubscription, SmackcastPurchase, SmackcastRecap, WalletTransaction, PendingAction, VerifiedPhone, PhoneVerificationCode, WallPost, OptOut, FamousMoment, CallTiming, PageStat, SafetyEvent
from services import news_service, show_service, admin_service, settings_service, show_service
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options, generator_constants, call_audio_service, content_moderation, team_aliases, chat_team_lists, chat_team_colors, team_display, sleeper_service, smackcast_service, espn_service, wallet_service, revenge_service, analytics_service, safety_service
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
else:
    # POSTGRES: SURVIVE STALE CONNECTIONS.
    #
    # The moment the Render instance type changed, every pooled
    # connection from the old box went stale mid-SSL, and the first
    # queries on them threw "decryption failed or bad record mac" -
    # then the wedged transaction cascaded into "Can't reconnect until
    # invalid transaction is rolled back". Four workers made it four
    # times louder.
    #
    # pool_pre_ping tests each connection with a no-op before handing
    # it out, replacing dead ones silently - the standard guard for
    # managed Postgres, where the server end WILL drop idle
    # connections during maintenance, restarts and instance moves.
    # pool_recycle retires anything older than 5 minutes for the same
    # reason.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
# THE SESSION SIGNING KEY.
#
# This fell back to "dev-only-change-me" - a value published in the
# repository. The SECRET_KEY is what stops somebody FORGING a session
# cookie, so a known key means anybody who reads the code can mint a
# cookie saying they are user 1, or an admin, and simply walk in.
#
# Forgetting to set an environment variable should not silently downgrade
# a site to no authentication.
#
# If it is missing now, a random key is generated instead. Everybody gets
# logged out on each restart, which is ANNOYING AND OBVIOUS - and being
# annoying is the point, because a silent fallback to a published key is
# not survivable and a forced logout is.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    import secrets as _secrets
    _secret = _secrets.token_urlsafe(48)
    print("[config] SECRET_KEY IS NOT SET. Using a random key for this "
          "process - everybody will be logged out on every restart. "
          "Set SECRET_KEY in the environment.", flush=True)
app.config["SECRET_KEY"] = _secret

# COOKIE FLAGS.
#
# Flask sets HttpOnly by default and nothing else. Explicit is better than
# inherited here, because these are the settings that decide whether a
# session cookie can be stolen.
#
#   SECURE    never send the cookie over plain HTTP. The site is HTTPS,
#             so this costs nothing and closes a downgrade attack.
#   HTTPONLY  JavaScript cannot read it, so an injected script cannot
#             steal a logged-in session.
#   SAMESITE  "Lax" stops another site silently making a request that
#             carries the cookie. Not "Strict", because that would break
#             somebody arriving from a Stripe redirect or an emailed link
#             and finding themselves logged out.
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_INSECURE", "").lower() not in ("1", "true"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
db.init_app(app)


@app.teardown_request
def _rollback_on_error(exc):
    """
    A request that died mid-transaction must not poison the session.

    The instance-swap SSL failures proved the gap: the first error
    wedged the session, and every later use on that worker thread threw
    "Can't reconnect until invalid transaction is rolled back" -
    including the alert recorder, so the failure could not even report
    itself. One rollback here and each request starts clean.
    """
    if exc is not None:
        try:
            db.session.rollback()
        except Exception:
            pass



# When the shadow comparison last ran. The cron that triggers it fires
# every two minutes; comparing yesterday's finished games that often would
# be thirty pointless requests an hour, so it is gated to once.
# Bumped whenever the terms change materially, so an acceptance record
# says WHICH terms were agreed to rather than merely that something was.
TERMS_VERSION = "2026-08"

_LAST_SHADOW = 0.0


def utc_iso(dt):
    """
    A timestamp the browser will read correctly.

    THE BUG THIS FIXES: everything here stores UTC via datetime.utcnow(),
    which produces a NAIVE datetime - no timezone attached. Calling
    .isoformat() on it gives "2026-08-04T23:36:01" with no marker, and
    JavaScript reads a marker-less timestamp as LOCAL time.

    So a smack sent at 7:36pm in Florida was stored as 23:36 UTC and
    displayed as 11:36pm. Four hours wrong, and wrong by a different
    amount for every user.

    Appending Z says "this is UTC", and every browser then converts it to
    whatever the reader's clock says - which is what the Locker was always
    trying to do.
    """
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.isoformat()
    except AttributeError:
        return None


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


def cron_authorised():
    """
    May this caller run a cron job?

    TWO WAYS IN, and the second is the point.

    A SCHEDULER passes ?key= matching CRON_SECRET. That is how
    cron-job.org calls in, and it has no session to offer.

    AN ADMIN ALREADY LOGGED IN needs nothing. The panel used to prompt
    for the secret every time somebody pressed a tool button - which
    means typing a production credential into a browser prompt, where it
    lands in autofill, in screenshots, and in muscle memory.

    Somebody who can reach the admin panel can already spend money in
    ten other ways. Asking them to retype a key protects nothing and
    teaches a bad habit.
    """
    key = request.args.get("key")
    expected = os.environ.get("CRON_SECRET")
    if expected and key == expected:
        return True
    try:
        user = get_current_user()
        return bool(user and getattr(user, "is_admin", False))
    except Exception:
        return False


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
    # STEP 4 (Twilio handoff): Twilio VERIFY now owns the code -
    # generation, delivery via Twilio's registered pool (no A2P
    # dependency), expiry, retry caps, Fraud Guard. Nothing secret is
    # stored on our side anymore; the legacy columns stay for schema
    # compatibility but hold nothing.
    from services import verify_service
    verify_service.start_verification(user.phone)
    user.two_factor_code = None
    user.two_factor_expires_at = None
    db.session.commit()
    return


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

    # PHONE IS OPTIONAL AT REGISTRATION - David's call, Aug 6 2026.
    # Twilio's A2P review is dragging, and an account does not need a
    # verified phone to exist; it will need one when a PAID feature
    # demands it, which is checkout's job, not signup's. The 2FA
    # machinery stays intact behind the twofactor_customers toggle for
    # the day Twilio clears.
    if not all([first_name, last_name, screen_name, email, dob_str, password]):
        return jsonify({"error": "All fields except phone are required."}), 400
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

    # Customer 2FA is now a runtime setting, changeable from the admin panel
    # rather than a constant needing a deploy. The old TWO_FACTOR_ENABLED
    # constant remains as the seed value only.
    # No phone means no text can be sent - regardless of the 2FA
    # toggle, this account registers without a verification step.
    if not phone or not settings_service.get_bool("twofactor_customers"):
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


@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>")
def reset_password_page(token):
    return render_template("reset_password.html", token=token)


@app.route("/api/forgot-password", methods=["POST"])
def api_forgot_password():
    """
    Send somebody a link to set a new password.

    ALWAYS RETURNS THE SAME THING, whether or not the email exists.
    "No account with that email" is a free tool for working out who has an
    account here, and given what this site is, that is worth protecting.

    Rate limited by the same guard as the login, because otherwise this is
    an unlimited way to send mail to anybody.
    """
    import hashlib
    import secrets
    from datetime import timedelta

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    _ip = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip() \
        or request.remote_addr or ""
    from services import login_guard
    allowed, _ = login_guard.check(f"reset:{email}", _ip)

    same_answer = jsonify({
        "ok": True,
        "message": ("If there is an account with that email, a reset link is "
                    "on its way. Check your spam folder if it does not "
                    "appear."),
    })

    if not allowed or not email or "@" not in email:
        return same_answer

    user = User.query.filter_by(email=email).first()
    if not user:
        login_guard.record_failure(f"reset:{email}", _ip)
        return same_answer

    try:
        from models import PasswordReset
        # Any earlier link for this account stops working now. Two live
        # reset links is one more than anybody needs.
        for old in PasswordReset.query.filter_by(user_id=user.id,
                                                 used_at=None).all():
            old.used_at = datetime.utcnow()

        raw = secrets.token_urlsafe(32)
        db.session.add(PasswordReset(
            user_id=user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            requested_ip=_ip,
        ))
        db.session.commit()

        base = os.environ.get("BASE_URL", request.url_root.rstrip("/"))
        link = f"{base}/reset-password/{raw}"

        from services import email_service
        ok, detail = email_service.send(
            user.email, "Reset your Smackagram password",
            f"Somebody asked to reset the password on your Smackagram "
            f"account.\n\n{link}\n\nThis link works once and expires in an "
            f"hour.\n\nIf that was not you, ignore this - your password has "
            f"not changed.")
        if not ok:
            print(f"[reset] link for {email} could not be sent: {detail}",
                  flush=True)
            from services import alerts
            alerts.record("email", "reset_send_failed", str(detail)[:200],
                          severity="critical")
    except Exception as e:
        db.session.rollback()
        print(f"[reset] failed for {email}: {e}", flush=True)

    return same_answer


@app.route("/api/reset-password", methods=["POST"])
def api_reset_password():
    """
    Set a new password, given a valid link.

    The token is looked up BY ITS HASH - the raw value never touches the
    database, so a leaked table is not a set of working keys.
    """
    import hashlib

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if len(password) < 6:
        return jsonify({"error": "Password needs at least 6 characters."}), 400

    from models import PasswordReset
    rec = PasswordReset.query.filter_by(
        token_hash=hashlib.sha256(token.encode()).hexdigest()).first()

    # One message for every kind of bad token - expired, used, invented.
    # Distinguishing them tells somebody probing which guesses got closer.
    if (not rec or rec.used_at
            or rec.expires_at < datetime.utcnow()):
        return jsonify({"error": "That link has expired or already been "
                                 "used. Ask for a new one."}), 400

    user = User.query.get(rec.user_id)
    if not user:
        return jsonify({"error": "That link is no longer valid."}), 400

    user.set_password(password)
    rec.used_at = datetime.utcnow()
    db.session.commit()

    # Whoever was locked out can try again now.
    from services import login_guard
    login_guard.record_success(user.email, "")

    print(f"[reset] password changed for {user.email}", flush=True)
    return jsonify({"ok": True, "message": "Password updated. You can log in."})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    # BRUTE FORCE PROTECTION.
    #
    # There was none. A script could try a thousand passwords a minute
    # against every email it knows and nothing anywhere would notice.
    from services import login_guard
    _ip = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip() \
        or request.remote_addr or ""

    allowed, wait = login_guard.check(email, _ip)
    if not allowed:
        # DELIBERATELY VAGUE. Saying "you are locked out" confirms the
        # email exists, and saying which limit was hit tells an attacker
        # how to route around it.
        return jsonify({"error": "Too many attempts. Try again shortly."}), 429

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        if login_guard.record_failure(email, _ip):
            try:
                from services import alerts
                alerts.record("auth", "brute_force",
                              f"repeated failures from {_ip} / {email[:40]}",
                              severity="warning")
            except Exception:
                pass
        # Same message whether the email exists or the password is wrong.
        # Anything more specific enumerates accounts.
        return jsonify({"error": "Incorrect email or password."}), 401

    login_guard.record_success(email, _ip)

    # Admins NO LONGER skip 2FA. That exemption was fine when /admin was a
    # couple of diagnostic pages; it is not fine now that the admin panel
    # exposes customer PII, purchase history and the ability to hand out
    # credits. An account that can do that should not be protected by a
    # password alone.
    #
    # ADMIN_BYPASS_2FA exists only so a locked-out admin can recover without
    # a deploy - it should be unset in normal operation.
    # Two independent switches, both set from the admin panel: one for
    # customers, one for admins. They're separate because the risk profiles
    # differ - an admin account can see every customer's details and mint
    # credit, so you may well want it protected even while customer 2FA is
    # off during a delivery problem.
    #
    # ADMIN_BYPASS_2FA is break-glass for lockout recovery. It exists because
    # an admin can turn ON admin 2FA and, if SMS is broken, lock themselves
    # out of the very page that turns it off.
    if user.is_admin:
        needs_2fa = settings_service.get_bool("twofactor_admins")
        if os.environ.get("ADMIN_BYPASS_2FA") == "1":
            needs_2fa = False
    else:
        needs_2fa = settings_service.get_bool("twofactor_customers")

    if not needs_2fa:
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

    # GUARDED TOO.
    #
    # A six-digit code is a million possibilities, which sounds like a lot
    # until you realise an unguarded endpoint can be tried a thousand
    # times a second. Rate limiting is the ONLY thing that makes a short
    # code safe - the length does not.
    from services import login_guard
    _ip = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip() \
        or request.remote_addr or ""
    _key = f"2fa:{pending_user_id}"

    allowed, wait = login_guard.check(_key, _ip)
    if not allowed:
        return jsonify({"error": "Too many attempts. Try again shortly."}), 429

    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "Enter the code we texted you."}), 400
    # Verify owns expiry and attempt limits - one question, one
    # answer. A wrong, expired, or replayed code is simply not
    # approved. Errors (network, bad SID) read as failure, never as
    # a free pass.
    from services import verify_service
    try:
        _approved = verify_service.check_verification(user.phone, code)
    except Exception as _ve:
        print(f"[2fa] verify check errored: {_ve}", flush=True)
        _approved = False
    if not _approved:
        # Count it. Without this the guard above never trips, because
        # nothing tells it an attempt failed.
        login_guard.record_failure(_key, _ip)
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


# Pre-resolved audio URLs for calls about to be placed - see
# call_audio_service.pending_call_audio for the actual dict and why it
# lives there instead of here (scheduler.py's Auto-Smack call path
# needs to reach it too, and importing app.py from there isn't viable).


# ---------- Site-wide password gate ----------
# Set SITE_PASSWORD in Render to lock the whole site behind a simple prompt
# while it's still in development. Leave SITE_PASSWORD unset/blank to make
# the site fully public again (e.g. once you're ready to launch for real).

@app.before_request
def require_site_password():
    # Stripe and Twilio hit these routes directly and can't log in with a
    # username/password — Stripe verifies itself via signature, Twilio's
    # callbacks are unauthenticated by nature (that's how Twilio itself works).
    exempt_prefixes = ("/webhook/stripe", "/call-instructions/", "/call-status/",
        "/recording-ready/", "/recording-done/", "/static/", "/api/cron/",
        # ---- PAGES A CARRIER REVIEWER HAS TO BE ABLE TO SEE ----
        #
        # An A2P submission describes how consent is collected, what the
        # opt-out is, and where the terms live. The reviewer then VISITS
        # THE SITE to check those claims are true.
        #
        # With the site password on, they would have hit a password
        # prompt and been unable to verify a single one - which reads as
        # a description that does not match the site, and is exactly the
        # error the campaign was rejected under.
        #
        # These five pages contain nothing worth gating: they are the
        # legal and consent surface, not the product.
        "/register", "/api/register", "/login", "/api/login",
        "/terms", "/privacy", "/contact", "/api/support", "/opt-out")
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
    automatically once the wallet is topped up, and returns the /refill
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
    return f"/refill?pending_action={pending.id}"


@app.route("/reload")
@app.route("/reload-success")
def reload_moved():
    """
    The old wallet address, kept alive.

    Renamed from Reload to Refill for the same reason the product was
    renamed: "reload" is a firearms word, and the A2P campaign was already
    rejected once under the carriers' SHAFT rules.

    Stripe builds return URLs at checkout time, so a session started
    before this deploy would come back to the old path. The redirect means
    that lands correctly rather than on a 404 after somebody has paid.
    """
    return redirect("/refill", code=301)


@app.route("/refill")
@login_required
def reload_page():
    """
    The wallet top-up page. Reached as the final step of Send a Smack
    or Auto-Smack when the wallet balance can't cover the action -
    not a standalone destination someone browses to directly, though
    it works fine if they do. Shows different copy for a genuine
    first-time buyer ("Load Your Account") versus a returning user
    topping back up ("Refill") - "reload" doesn't make sense for
    someone who's never had a balance to begin with.
    """
    user = get_current_user()
    has_topped_up_before = WalletTransaction.query.filter_by(user_id=user.id, transaction_type="topup").first() is not None

    # If there's a pending action, the step nav needs to know which
    # flow it belongs to (Send a Smack vs Auto-Smack) to show the
    # right step labels and link back to the right page.
    pending_action_id = request.args.get("pending_action")
    pending_action_type = None
    if pending_action_id:
        pending = PendingAction.query.get(pending_action_id)
        if pending and pending.user_id == user.id:
            pending_action_type = pending.action_type

    return render_template(
        "refill.html",
        stripe_publishable_key=os.environ["STRIPE_PUBLISHABLE_KEY"],
        is_first_time_buyer=not has_topped_up_before,
        pending_action_id=pending_action_id,
        pending_action_type=pending_action_type,
    )


@app.route("/refill-success")
@login_required
def reload_success():
    """
    Where Stripe redirects after a successful payment confirmation.
    The wallet itself gets credited by the webhook handler, which may
    still be in flight when this page loads — that's expected and fine,
    since the webhook is the authoritative source of truth here, not
    this page.
    """
    return render_template("refill_success.html")


@app.route("/api/wallet/pending-action-status/<int:pending_action_id>")
@login_required
def api_pending_action_status(pending_action_id):
    """
    Polled by refill_success.html while a resumed Send a Smack / Auto-Smack request may still be in flight (the webhook that actually
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
        # Which generator this came from. Without it the top-up page had no
        # way to know, so it sent everybody back to Send a Smack - including
        # people who were part-way through arming a Auto-Smack.
        "action_type": pending.action_type,
    })


@app.route("/api/pending-action/<int:pending_action_id>")
@login_required
def api_get_pending_action(pending_action_id):
    """
    Returns a pending action's stored payload and type, so a page the
    user navigates back to (e.g. the generator, after clicking "Roast"
    in the Refill page's step nav) can repopulate its form fields with
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

    # RECORD THE ACKNOWLEDGEMENT, SERVER-SIDE.
    #
    # The checkbox on the page can be defeated by anybody with a browser
    # console, so the tick itself proves nothing. What matters is a record
    # - timestamped, with an address - that this person was shown "all
    # sales are final, refunds are issued as credit" at the moment they
    # paid, because that is the term a chargeback six months later turns
    # on.
    #
    # NOT refused when missing. A payment failing because a checkbox did
    # not serialise is worse than one recorded as unacknowledged, and the
    # record shows which happened either way.
    try:
        from models import TermsAcceptance
        db.session.add(TermsAcceptance(
            user_id=getattr(user, "id", None),
            context=("purchase" if data.get("terms_ack")
                     else "purchase-unticked"),
            terms_version=TERMS_VERSION,
            ip=(request.headers.get("X-Forwarded-For")
                or request.remote_addr or "")[:60],
            user_agent=(request.headers.get("User-Agent") or "")[:300],
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[terms] could not record acceptance: {e}", flush=True)

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
    # Refuse BEFORE anything is charged.
    #
    # The dial itself is also guarded, but that is too late - by then the
    # wallet has been debited and somebody has to be refunded for a call
    # that was never going to be allowed. Checking here means the person
    # sending gets a plain answer and keeps their money.
    if is_opted_out(data.get("recipient_phone")):
        raise ValueError(
            "That number has asked not to receive Smackagrams. "
            "We cannot send to it.")

    order = Order(
        # Attributed so it can be listed back in the sender's locker. Minted
        # with a share token at creation rather than on first share, so every
        # order has one and nothing has to back-fill later.
        user_id=user.id,
        share_token=secrets.token_urlsafe(16),
        scenario_id=data.get("scenario_id"),
        custom_message=data.get("custom_message", ""),
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        team=(data.get("team") or "").strip() or None,
        recipient_name=first_name_only(data["recipient_name"]),
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        price_cents=wallet_service.SMACK_COST_CENTS,
        includes_recording=data.get("include_recording", True),
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
        payment_status="captured",  # wallet deduction IS the payment - no async Stripe wait needed
        # Optional send-later time, already converted to UTC by the page.
        # Null means send now, which is every order placed before this
        # existed - additive, nothing to backfill.
        scheduled_for=_parse_schedule(data.get("scheduled_for")),
    )
    db.session.add(order)
    db.session.commit()

    try:
        audio_urls = call_audio_service.resolve_audio_url(order, os.environ["BASE_URL"])
        call_audio_service.stash_call_audio("order", order.id, audio_urls)
        order.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
        # Straight onto the wall. A reply is a Smack Back; anything else is a
        # standard Smackagram.
        publish_to_wall(order,
                        "smackback" if order.replied_to_type else "smackagram",
                        audio_urls[0])

        # SCHEDULED CALLS DO NOT RING NOW.
        #
        # The audio is still generated and the wall post still goes up - the
        # work is done and paid for. Only the dialling waits, and the cron
        # picks it up within three minutes of the chosen time.
        if getattr(order, "scheduled_for", None):
            db.session.commit()
            print(f"[schedule] order {order.id} held until "
                  f"{order.scheduled_for} UTC", flush=True)
            return jsonify({
                "success": True,
                "order_id": order.id,
                "scheduled_for": utc_iso(order.scheduled_for),
                "message": "Locked in. It rings at the time you picked.",
            })

        call_sid = twilio_service.place_prank_call("order", order.id, order.recipient_phone, record=True)
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

    # OPT-OUT, CHECKED ON THE SERVER.
    #
    # The page asks /api/check-optout before letting somebody send. That
    # is a courtesy to the sender, not a control - a direct POST skips it
    # entirely, and so does any future path that forgets to call it.
    #
    # An opt-out that only the front end honours is not an opt-out.
    if is_opted_out(data.get("recipient_phone")):
        print("[optout] refused - recipient has opted out", flush=True)
        return jsonify({
            "error": ("This number has asked not to receive Smackagrams. "
                      "We cannot send to it."),
        }), 403

    custom_message = data.get("custom_message", "")
    safety = content_moderation.check_message_safety(custom_message)
    if not safety["safe"]:
        # Recorded, not just printed. A block used to vanish into the
        # Render log - the customer was refunded and nobody ever learned it
        # happened.
        safety_service.record(
            "send-a-smack", "input", safety,
            user_id=getattr(get_current_user(), "id", None))
        print(f"[safety] blocked order attempt - {safety.get('category','?')}: "
              f"{(safety.get('excerpt') or safety.get('reason') or '')[:90]}")
        return jsonify({
            "error": _moderation_error_text(safety),
            "reason": safety.get("reason"),
            "excerpt": safety.get("excerpt", ""),
            "category": safety.get("category", ""),
            # 503 not 400 when the CHECK failed - it's our outage, and a
            # different status lets the front end offer a retry rather than
            # asking someone to edit text that was never the problem.
            "retryable": not safety.get("available", True),
        }), (503 if not safety.get("available", True) else 400)

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

    try:
        result = _execute_send_smack(user, data)
    except ValueError as e:
        # Deliberate refusals - an opted-out number, most importantly. These
        # were escaping as 500s, so the browser could not read the reason and
        # fell back to a generic message. The wallet was debited above, so it
        # goes back before returning.
        try:
            wallet_service.credit_wallet(
                user, wallet_service.SMACK_COST_CENTS, "smack_refund",
                description="Refused - " + str(e)[:80],
            )
            db.session.commit()
        except Exception as refund_err:
            print(f"[send] refund after refusal failed: {refund_err}", flush=True)
        return jsonify({"error": str(e)}), 400

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

        if metadata.get("smackcast_purchase_id"):
            purchase = SmackcastPurchase.query.get(int(metadata["smackcast_purchase_id"]))
            if purchase and purchase.status != "paid":
                purchase.status = "paid"
                purchase.paid_at = datetime.utcnow()
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
                call_audio_service.stash_call_audio("order", order.id, audio_urls)
                order.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
                # Onto the wall, same as the wallet path above.
                publish_to_wall(order,
                                "smackback" if order.replied_to_type else "smackagram",
                                audio_urls[0])
                call_sid = twilio_service.place_prank_call("order", order.id, order.recipient_phone, record=True)
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


def _moderation_error_text(verdict):
    """
    Turns a verdict into a message someone can actually act on.

    Takes the whole verdict rather than just a reason string, because the two
    failure modes read completely differently:

      CHECK OUTAGE - our problem, nothing to edit. The old version said
      "please edit that part" here, which sent people into a loop retyping
      text that was never the issue.

      VIOLATION - quote the offending words back. The classifier now returns
      the exact excerpt, so instead of "this breaks the rules, guess which
      bit", people see the phrase and fix it in one go.
    """
    if isinstance(verdict, str):          # tolerate the old call shape
        verdict = {"reason": verdict, "available": True}

    if not verdict.get("available", True):
        return ("We couldn't run the safety check just now - nothing's wrong with "
                "your message. Give it a few seconds and try again.")

    excerpt = (verdict.get("excerpt") or "").strip()
    reason = (verdict.get("reason") or "").strip()

    if excerpt:
        return f'This part can\'t go out: "{excerpt}"' + (f" - {reason}" if reason else "")
    if reason:
        return f"This message can't be sent: {reason}"
    return "This message can't be sent. Please revise it and try again."


@app.route("/api/generate-trash-talk", methods=["POST"])
def generate_trash_talk():
    # One free line without an account. Writing costs API credits with no
    # purchase attached, so one is the sales pitch.
    gate = _anon_allowance("anon_generate", "line")
    if gate:
        return gate

    data = request.json
    team = data.get("team", "").strip()
    recipient_name = data.get("recipient_name", "").strip()
    # Optional. Which team the SENDER supports, so the call can be framed as
    # a rivalry rather than an anonymous roast. Never reveals who they are.
    from_team = (data.get("from_team") or "").strip()[:40]
    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)
    # Sanitized server-side too, not just trusting whatever the frontend
    # already limited to 3 — cap length per topic as a light guard
    # against someone pasting something huge into this field.
    raw_topics = data.get("roast_topics") or []
    roast_topics = [str(t).strip()[:60] for t in raw_topics if str(t).strip()][:4]


    if not team or not recipient_name:
        return jsonify({"error": "Both team and recipient name are required"}), 400

    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    # Moderate our OWN output before handing it over. The generator and the
    # moderator are separate rule sets and can disagree, which previously
    # meant someone could be given a line here and then have it rejected at
    # checkout - our fault, and confusing, since they didn't write it.
    # Regenerating is the right response: the fix is a different line, not
    # asking the user to edit something we produced.
    line = None
    last_reason = None
    for attempt in range(3):
        try:
            # THE OUTCOME HANDOFF: a SMACK THIS LOSS click on the board
            # arrives carrying the finished game - so the roast is
            # grounded in THAT loss via the same recap generator that
            # powers Locked & Loaded fire-time calls, rather than a
            # generic team roast.
            _oc = data.get("game_outcome") or {}
            if _oc.get("loser") and _oc.get("winner"):
                _facts = [f"Final score: {_oc['loser']} lost "
                          f"{_oc.get('loser_score','?')}-"
                          f"{_oc.get('winner_score','?')} "
                          f"to {_oc['winner']}"]
                # PLAYER STATS INTO THE ROAST (Andy, Aug 7): the same
                # machinery that feeds the Daily Smack - find last
                # night's game by the loser's nickname, run the show's
                # detail enrichment (statsapi for MLB, Highlightly box
                # scores elsewhere), and hand its per-game facts plus
                # the box detail's named lines to the writer. Failures
                # fall back to the score line - a thinner roast beats
                # a broken generator.
                try:
                    from services import show_service as _shs
                    _sport = (data.get("sport") or "mlb").lower()
                    _ln = (_oc["loser"] or "").split()[-1].lower()
                    _cands = [g for g in
                              _shs.fetch_results(_sport, days_back=1)
                              if _ln and _ln == (g.get("loser") or ""
                                  ).split()[-1].lower()]
                    if _cands:
                        _g = _cands[0]
                        # IDS FIRST - the show attaches provider ids in
                        # a separate step before detail; without them
                        # enrich finds no box and the roast stays
                        # score-only (Andy's caps-lock bug report).
                        try:
                            _shs._attach_highlightly_ids(
                                [_g], log=lambda *a, **k: None)
                        except Exception:
                            pass
                        _shs.enrich_with_detail([_g], log=lambda *a, **k: None)
                        for _f in (_g.get("named_facts") or [])[:6]:
                            _facts.append(str(_f)[:220])
                        for _f in (_g.get("facts") or [])[:4]:
                            _facts.append(str(_f)[:220])
                        for _f in (_g.get("deep_facts") or [])[:6]:
                            _facts.append(str(_f)[:220])
                        print(f"[generate] game-day roast enriched: "
                              f"{len(_facts)} facts for {_oc['loser']}",
                              flush=True)
                except Exception as _ee:
                    print(f"[generate] stats enrichment failed, "
                          f"score-only roast: {_ee}", flush=True)
                candidate = trash_talk_service.generate_game_recap_roast(
                    team=team, recipient_name=recipient_name,
                    key_facts=_facts, sensitivity=sensitivity,
                )
            else:
                candidate = trash_talk_service.generate_trash_talk(
                    team=team, recipient_name=recipient_name,
                    sensitivity=sensitivity, roast_topics=roast_topics,
                    from_team=from_team,
                )
        except Exception as e:
            print(f"[generate] generation failed (attempt {attempt + 1}): {e}")
            continue

        # THE FAST CHECK FIRST.
        #
        # Local, instant, no round trip. Catches the obvious so the model
        # call is spent on the genuinely ambiguous - and works even when
        # that call is timing out.
        #
        # Style swaps are applied quietly: "idiot" becoming "clown" is a
        # house-voice decision, not a safety one.
        #
        # A BLOCK IS NEVER REWRITTEN. The temptation is to swap a threat for
        # something harmless and carry on, but that sends a call that was
        # ALMOST a threat and the safety log never sees it - losing the one
        # signal that a generator has started drifting.
        try:
            from services import fast_filter
            quick = fast_filter.check(candidate)
            if not quick["ok"]:
                print(f"[generate] fast filter blocked "
                      f"({quick['category']}): {quick['excerpt'][:60]}",
                      flush=True)
                try:
                    safety_service.record(
                        "generator", "generated",
                        {"category": quick["category"],
                         "reason": "blocked by the local filter before the "
                                   "model check",
                         "excerpt": quick["excerpt"]},
                        user_id=getattr(get_current_user(), "id", None))
                except Exception:
                    pass
                continue          # regenerate, do not send
            if quick.get("restyled"):
                candidate = quick["text"]
        except Exception as e:
            print(f"[generate] fast filter unavailable: {e}", flush=True)

        try:
            verdict = content_moderation.check_message_safety(candidate)
        except Exception as e:
            # Moderation is a SAFETY NET over our own output here, not the
            # gate that protects users from each other - that check still
            # runs at checkout on whatever is actually sent. So if the
            # moderator is unavailable, don't take the whole generator down
            # with it; hand the line over and let checkout catch anything
            # genuinely bad. Failing closed here would mean an outage in one
            # service breaks a feature it only supervises.
            print(f"[safety] moderation unavailable during generation, passing through: {e}")
            line = candidate
            break

        if verdict["safe"]:
            line = candidate
            break
        # Same reasoning: a moderator that can't reach its API reports unsafe
        # by design. That's right at checkout, wrong here.
        if not verdict.get("available", True):
            print("[safety] moderation unreachable during generation, passing through")
            line = candidate
            break
        last_reason = verdict["reason"]
        # OUR OWN WRITER produced something the gate refused. That is a
        # different and more serious event than a user typing an insult into
        # a box, and it alerts immediately rather than waiting for a burst.
        safety_service.record(
            "generator", "generated", verdict,
            user_id=getattr(get_current_user(), "id", None))
        print(f"[safety] self-generated line failed moderation (attempt {attempt + 1}): {last_reason}")

    if line is None:
        if last_reason:
            # Three strikes on moderation usually means the topics themselves
            # steer somewhere we won't go, so say that rather than blaming
            # the generator.
            return jsonify({
                "error": "Couldn't write a line for that without crossing a line. "
                         "Try different roast topics or a lower intensity.",
                "reason": last_reason,
            }), 400
        # No moderation reason means generation itself kept failing - an
        # upstream problem, not anything the user did. Don't tell them to
        # change their input when their input was fine.
        return jsonify({
            "error": "Couldn't reach the writer just now. Give it a second and try again.",
        }), 503

    return jsonify({"generated_text": line})


@app.route("/api/sensitivity-levels")
def get_sensitivity_levels():
    """Powers the sensitivity/intensity selector UI on the generator pages and Smack Battle creation."""
    return jsonify(trash_talk_service.SENSITIVITY_LEVELS)


@app.route("/api/smack-lab/respond", methods=["POST"])
def smack_lab_respond():
    """
    Powers Smack Lab — live back-and-forth trash-talk sparring with a
    rating + coaching critique on every turn. Rate-limited per IP since
    this is a free feature (no purchase) that costs real Claude API calls.
    """
    # Three free turns without an account. Smack Lab is a back-and-forth -
    # one turn is not a go, it is a tease.
    gate = _anon_allowance("anon_lab", "few rounds")
    if gate:
        return gate

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
        return jsonify({"error": _moderation_error_text(safety), "reason": safety.get("reason"), "excerpt": safety.get("excerpt", ""), "category": safety.get("category", ""), "retryable": not safety.get("available", True)}), (503 if not safety.get("available", True) else 400)

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


def _parse_schedule(raw):
    """
    An ISO timestamp from the page, returned as naive UTC to match
    created_at.

    The page sends UTC, because a scheduled call is the one feature where
    being an hour out is not a small bug - it rings at seven in the morning
    instead of eight at night.

    Refuses anything in the past, since a call scheduled for last Tuesday
    would fire the instant the next cron ran. And anything past 60 days,
    which is almost always a mistyped year.
    """
    if not raw:
        return None
    try:
        from datetime import datetime, timedelta, timezone

        txt = str(raw).strip().replace("Z", "+00:00")
        when = datetime.fromisoformat(txt)
        if when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)

        now = datetime.utcnow()
        if when <= now + timedelta(minutes=2):
            return None            # effectively now - just send it
        if when > now + timedelta(days=60):
            print(f"[schedule] {raw} is too far out, ignoring", flush=True)
            return None
        return when
    except Exception as e:
        print(f"[schedule] could not read '{raw}': {e}", flush=True)
        return None


def _anon_allowance(bucket, what="that"):
    """
    One free go before an account is needed.

    Returns None when the request may proceed, or a ready-made 429 response.

    Requiring a login to TRY the product put a registration form in front of
    somebody deciding whether to spend a dollar - and registering is the
    bigger ask of the two. But generation costs real API credits with no
    purchase attached, so one is the sales pitch and the rest sits behind an
    account.

    Buckets are separate per generator, so trying one thing does not
    silently lock another.
    """
    # This app does NOT use Flask-Login. It has its own get_current_user()
    # reading the session, and I wrote current_user out of habit - which
    # crashed every generate request with a NameError.
    _user = get_current_user()
    if _user is not None:
        # A CEILING FOR ACCOUNTS TOO.
        #
        # This returned None here - no limit whatsoever for anybody logged
        # in. Registration is free, so the route to unlimited Anthropic
        # and ElevenLabs spend was: make an account, call this in a loop.
        # The first sign would have been the invoice.
        #
        # The cap is generous enough that no real person meets it.
        if rate_limiter.user_limited(bucket, _user.id):
            print(f"[limit] user {_user.id} hit the {bucket} ceiling",
                  flush=True)
            try:
                from services import alerts
                alerts.record("abuse", "generator_ceiling",
                              f"user {_user.id} hit the {bucket} hourly cap",
                              severity="warning")
            except Exception:
                pass
            return jsonify({
                "error": ("You have made a lot of these in the last hour. "
                          "Give it a few minutes."),
            }), 429
        return None
    ident = request.headers.get("X-Forwarded-For", request.remote_addr)
    cap = rate_limiter.MAX_ANON_PER_HOUR.get(bucket, 1)
    if rate_limiter.is_limited(bucket, ident, cap):
        return jsonify({
            "error": f"That's your free {what}. Create an account - it's "
                     f"free - to keep going.",
            "needs_account": True,
        }), 429
    rate_limiter.record(bucket, ident)
    return None


@app.route("/api/preview-audio", methods=["POST"])
def preview_audio():
    """
    Free preview — lets someone hear a generated line before buying.
    Rate-limited per IP since this costs real ElevenLabs credits with
    no purchase required.
    """
    identifier = request.headers.get("X-Forwarded-For", request.remote_addr)

    gate = _anon_allowance("anon_preview", "listen")
    if gate:
        return gate

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
        safety_service.record("preview", "input", safety,
                              user_id=getattr(get_current_user(), "id", None))
        print(f"[safety] blocked preview - {safety.get('category','?')}: "
              f"{(safety.get('excerpt') or safety.get('reason') or '')[:90]}")
        return jsonify({"error": _moderation_error_text(safety), "reason": safety.get("reason"), "excerpt": safety.get("excerpt", ""), "category": safety.get("category", ""), "retryable": not safety.get("available", True)}), (503 if not safety.get("available", True) else 400)

    voice_key = request.json.get("voice_key", voice_options.DEFAULT_VOICE_KEY)
    voice_id = voice_options.get_voice_id(voice_key)

    message_url = elevenlabs_service.generate_audio_url(text, voice_id=voice_id)
    outro_url = call_audio_service.get_outro_url(os.environ.get("BASE_URL", request.url_root.rstrip("/")))
    rate_limiter.record_hit(identifier)

    return jsonify({
        "audio_sequence": [message_url, outro_url],
        "previews_remaining": rate_limiter.previews_remaining(identifier),
    })


def _resolve_record(record_type, record_id):
    """
    record_type: "order", "smackagram", or None. None triggers the old
    guess-based lookup (Order first, then Smackagram) - kept ONLY for
    the legacy bare-int fallback routes below, which exist solely to
    handle calls already in flight (placed by pre-deploy code) at the
    moment this namespacing change goes live. Every new call always
    passes an explicit type, so the guess (which silently favored
    Order on any id collision) is never exercised for new calls.
    """
    if record_type == "order":
        return Order.query.get(record_id)
    if record_type == "smackagram":
        return Smackagram.query.get(record_id)

    # NO MORE GUESSING.
    #
    # This used to fall back to "try Order, then Smackagram" for the legacy
    # bare-id routes. Those routes are gone - they existed only for calls
    # already in flight during one deploy, and a call cannot outlive its
    # 119-second limit.
    #
    # THE COLLISION IS REAL: a check found six Smackagram ids that also
    # exist as Orders - every Smackagram in the database. So the old guess
    # would have silently favoured Order on EVERY ONE of them, writing a
    # call status against the wrong record.
    #
    # Refusing loudly beats resolving quietly to the wrong thing. If this
    # ever fires, something is calling with no type and that is the bug to
    # find, not something to paper over.
    print(f"[twilio] REFUSING an untyped lookup for id {record_id} - "
          f"every Smackagram id also exists as an Order, so a guess would "
          f"be wrong more often than right", flush=True)
    return None


def _call_instructions_handler(record_type, record_id):
    # Verified for the same reason as call-status: these are Twilio's
    # endpoints and nobody else's. An unsigned request here could replay
    # a recording URL or make a call read back somebody else's audio.
    from services import twilio_auth
    if not twilio_auth.is_from_twilio(request):
        print(f"[twilio] REJECTED an unsigned call-instructions", flush=True)
        return "", 403

    order = _resolve_record(record_type, record_id)

    # With machine_detection='DetectMessageEnd' set at call-creation time,
    # Twilio only requests this route once it's determined who/what
    # answered — logging this confirms the timing fix is actually working
    # (e.g. "machine_end_beep" means we're being asked to speak right
    # after the voicemail's greeting ended, exactly when we want to).
    answered_by = request.values.get("AnsweredBy")
    try:
        record.answered_by = (answered_by or "")[:32]
        db.session.commit()
    except Exception:
        db.session.rollback()
    print(f"[twilio] call-instructions hit for {record_type or 'legacy'}:{record_id} — AnsweredBy={answered_by!r}")

    # fall back to live resolution only if somehow nothing was pre-cached
    # (e.g. this route got hit directly without going through the webhook).
    # Cache key matches whichever URL style got us here - namespaced calls
    # were cached under (record_type, record_id), legacy in-flight calls
    # under the bare record_id.
    cache_key = (record_type, record_id) if record_type else record_id
    # take() checks this worker's memory, then the SHARED DB - the
    # dead-air fix. The dict-only pop lost ~75% of answered calls to
    # cross-worker misses on a 4-worker box.
    cached = call_audio_service.take_call_audio(record_type, record_id)
    if cached is None:
        print(f"[twilio] CACHE MISS {record_type or 'legacy'}:{record_id} — generating audio live inside the webhook, expect dead air")
        audio_urls = call_audio_service.resolve_audio_url(order, os.environ.get("BASE_URL", request.url_root.rstrip("/")), answered_by)
    else:
        audio_urls = cached

    # Never record voicemail greetings/silence — recording is only
    # meaningful (and only what the buyer paid for) when a real person's
    # live reaction gets captured. AnsweredBy comes from the
    # machine_detection='DetectMessageEnd' set at call-creation time, so
    # by the time we're here it's already resolved.
    #
    # FAIL-SAFE, not fail-open: only "human" counts as a live answer.
    # The previous check (answered_by.startswith("machine")) let
    # "unknown" silently pass through as human - "unknown".startswith
    # ("machine") is False, so an ambiguous/undetermined answer got
    # treated as a confirmed live person. AnsweredBy values are: human,
    # machine_end_beep, machine_end_silence, machine_end_other, fax,
    # unknown. Anything that isn't confidently "human" should NOT record.
    is_live = (answered_by == "human")
    # RECORDING RETIRED (Andy + David's decision, Aug 7). No <Record>
    # means no disclosure - the weld holds in both directions - and
    # Smacky opens the SECOND a human is confirmed. The recording
    # machinery (webhooks, columns, build_twiml's record path) stays
    # intact and welded for any future return of the feature.
    should_record = False  # was: getattr(order, "includes_recording", True) and is_live
    if not is_live and getattr(order, "includes_recording", True):
        print(f"[twilio] record {record_type or 'legacy'}:{record_id} answered_by={answered_by!r} (not confirmed human) — recording skipped even though it was purchased")

    # Persist AnsweredBy instead of just printing it - gives a real
    # answer to "did my smack land?" (call_status says "completed"
    # whether the target laughed or it hit voicemail), and is the only
    # way to know whether machine_detection_timeout is set correctly (a
    # high share of "unknown" means the ceiling is too low).
    if order:
        order.answered_by = answered_by
        db.session.commit()

    # Close the timing loop.
    #
    # Twilio only requests this URL once AMD has decided, so the gap from
    # dialling to here is ring time plus greeting plus AMD's deliberation -
    # and on a voicemail every second of it after the beep is dead air at the
    # front of the recording.
    try:
        sid = request.values.get("CallSid")
        if sid:
            t = CallTiming.query.filter_by(call_sid=sid).first()
            if t:
                now = datetime.now(timezone.utc)
                t.instructions_at = now
                if t.dialed_at:
                    started = t.dialed_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    t.gap_seconds = round((now - started).total_seconds(), 2)
                t.answered_by = answered_by
                db.session.commit()
                print(f"[timing] {record_type}:{record_id} answered_by={answered_by!r} "
                      f"gap={t.gap_seconds}s", flush=True)
    except Exception as e:
        print(f"[timing] could not record instruction time: {e}", flush=True)

    base_url = os.environ.get("BASE_URL", request.url_root.rstrip("/"))
    # ALWAYS TYPED.
    #
    # There used to be an untyped branch here building "/recording-ready/47"
    # for calls with no record_type. Those bare routes are gone, and every
    # caller passes a type - so this would have pointed at a 404.
    #
    # The collision check found SIX ids shared between Orders and
    # Smackagrams, which is every Smackagram in the database. An untyped
    # URL was never safe; it just happened not to be exercised.
    callback_url = f"{base_url}/recording-ready/{record_type}/{record_id}" if should_record else None
    action_url = f"{base_url}/recording-done/{record_type}/{record_id}" if should_record else None

    twiml = twilio_service.build_twiml(
        audio_urls, record=should_record,
        record_callback_url=callback_url, record_action_url=action_url,
    )
    return Response(twiml, mimetype="text/xml")


def _twilio_signed(f):
    """
    STEP 5a (Twilio handoff): these webhooks were exempt from the
    site's password gate and validated NOTHING - /recording-ready/
    took RecordingUrl straight from form data into a customer's row,
    so anyone who guessed an ID (they run 1-27) could overwrite a
    recording with an arbitrary URL. Every Twilio webhook now proves
    it came from Twilio via the X-Twilio-Signature header, computed
    over the exact public URL and POST params with our auth token.
    Set TWILIO_VALIDATE_WEBHOOKS=0 to disable in an emergency (e.g.
    a proxy rewriting the URL breaks signatures) - failures log the
    URL so that condition is visible.
    """
    from functools import wraps
    @wraps(f)
    def _w(*args, **kwargs):
        import os
        if os.environ.get("TWILIO_VALIDATE_WEBHOOKS", "1") == "0":
            return f(*args, **kwargs)
        try:
            from twilio.request_validator import RequestValidator
            v = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
            url = request.url
            # Render terminates TLS at the proxy; Flask may see http.
            # Twilio signed the https URL, so normalize.
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]
            ok = v.validate(url, request.form,
                            request.headers.get("X-Twilio-Signature", ""))
        except Exception as e:
            print(f"[twilio] signature check errored ({e}) - refusing",
                  flush=True)
            ok = False
        if not ok:
            print(f"[twilio] REJECTED unsigned webhook: {request.url}",
                  flush=True)
            return ("", 403)
        return f(*args, **kwargs)
    return _w



@app.route("/call-instructions/<record_type>/<int:record_id>", methods=["GET", "POST"])
@_twilio_signed
def call_instructions(record_type, record_id):
    """
    Twilio hits this the moment the call connects. Serves pre-resolved audio
    URLs instantly — no generation happens here, since that risked Twilio
    timing out and retrying (which replayed the whole call from scratch).

    Namespaced by record_type ("order" or "smackagram") so this never has
    to guess which table an id belongs to - see _resolve_record.
    """
    return _call_instructions_handler(record_type, record_id)



@app.route("/recording-done/<record_type>/<int:record_id>", methods=["GET", "POST"])
@app.route("/recording-done/<int:record_id>", methods=["GET", "POST"])
@_twilio_signed
def recording_done(record_id, record_type=None):
    """
    Where <Record>'s action points once recording finishes. Just hangs up —
    critically, this is NOT the same URL that started the call, which is
    what stops Twilio from re-fetching /call-instructions and replaying the
    whole script (Twilio's default action, if none is given, is to re-request
    the original URL).

    Doesn't actually need to know which record this is for (it does
    nothing but hang up), so both the namespaced and legacy bare-int
    URL shapes map to this same handler.
    """
    twiml = "<Response><Hangup/></Response>"
    return Response(twiml, mimetype="text/xml")


# ---------- Locked-and-loaded smackagrams ----------

# ---------- Locked-and-loaded smackagrams ----------

@app.route("/locked-n-loaded")
@app.route("/locked-n-loaded/success")
def locked_n_loaded_moved():
    """
    The old address, kept alive.

    The product was renamed from Locked & Loaded to Auto-Smack because
    Twilio's A2P campaign review rejected the brand under the carriers'
    SHAFT rules - Sex, Hate, Alcohol, Firearms, Tobacco. "Locked and
    loaded" is a firearms idiom, and a filter reading the site had no way
    to know it was about phone calls.

    This redirect costs nothing and means an old link, a bookmark, a
    Stripe session started before the rename, or anything Twilio still
    holds does not land on a 404.
    """
    return redirect("/auto-smack", code=301)


@app.route("/auto-smack")
@login_required
def locked_n_loaded_page():
    # ?embed=1 renders the generator alone, no nav/hero/footer, so the other
    # generator page can frame it. Kept as a flag on the same route rather
    # than a second template - two copies of a page this complex would drift.
    return render_template("auto_smack.html", embed=request.args.get("embed") == "1")


@app.route("/send-a-smack")
def send_a_smack_page():
    return render_template("send_a_smack.html", embed=request.args.get("embed") == "1")


@app.route("/smack-lab")
@login_required
def smack_lab_page():
    return render_template("smack_lab.html")


@app.route("/smack/<share_token>")
def public_smack(share_token):
    """
    Public playback page for a single smackagram. No login.

    This is what a social share actually points at, so it carries Open Graph
    and Twitter Card tags - without them a shared link renders as a bare URL
    on every platform, which is the difference between a share that gets
    clicked and one that doesn't.

    The token grants PLAYBACK ONLY. It is deliberately separate from
    reply_token, which lets a recipient smack back - so passing this around
    can never be used to send anything.
    """
    rec = Order.query.filter_by(share_token=share_token).first()
    kind = "smackagram"
    if not rec:
        rec = Smackagram.query.filter_by(share_token=share_token).first()
        kind = "locked"
    if not rec:
        return render_template("404.html"), 404

    audio = rec.recording_url or rec.message_audio_url
    return render_template(
        "public_smack.html",
        rec=rec, kind=kind, audio=audio,
        has_reaction=bool(rec.recording_url),
        share_url=f"{os.environ.get('BASE_URL', '')}/smack/{share_token}",
    )


@app.route("/locker")
@login_required
def locker_page():
    """
    Everything a person owns, in two tabs: the smacks they have sent, and
    their fantasy recaps.

    The Fantasy tab only exists for subscribers. A tab that opens onto a
    sales pitch is worse than no tab - it makes the page feel like it is
    withholding something rather than offering it.
    """
    user = get_current_user()

    sub = (SmackcastSubscription.query
           .filter_by(user_id=user.id)
           .order_by(SmackcastSubscription.id.desc())
           .first())

    recaps = []
    if sub:
        recaps = (SmackcastRecap.query
                  .filter_by(subscription_id=sub.id)
                  .order_by(SmackcastRecap.week_number.desc())
                  .limit(4).all())

    # --- received -------------------------------------------------------
    #
    # Only ever shown for a number this user has PROVEN is theirs. The
    # public lookup page lets anybody type any number and hear what that
    # person was sent; this replaces it with something that cannot be
    # abused, which is the whole reason received smacks belong here.
    #
    # Verification needs Twilio A2P registration, which is still pending -
    # so the gate is built and switched off rather than absent. When
    # registration lands, VERIFICATION_LIVE flips and this opens up with no
    # other change.
    verification_live = os.getenv("VERIFICATION_LIVE", "").lower() in ("1", "true", "yes")

    verified = (VerifiedPhone.query
                .filter_by(user_id=user.id)
                .order_by(VerifiedPhone.id.desc())
                .first())
    # SAME RULE AS SMACK BACK while verification is off: the phone on
    # the account counts as the key. A logged-in user who typed their
    # number at registration should not see an emptier page than a
    # stranger typing the same number on /did-you-get-smacked. Flips
    # back to code-verified the moment the admin toggle does.
    from services import settings_service as _ss2
    if not _ss2.get_bool("smackback_requires_verification"):
        verification_live = True
        if not verified and user.phone:
            class _P:  # shaped like VerifiedPhone for the code below
                phone_digits = "".join(
                    c for c in user.phone if c.isdigit())[-10:]
            verified = _P()

    received = []
    if verified and verification_live:
        # VerifiedPhone stores phone_digits, not .phone - asking for
        # .phone 500'd the locker the first time a Verify-verified
        # user opened it (Aug 7, caught by the alert email+SMS within
        # seconds). Match on the last-10 digits like every other
        # phone lookup in the site.
        _vd = verified.phone_digits
        rows = (Smackagram.query
                .filter(Smackagram.recipient_phone.like(f"%{_vd}"))
                .order_by(Smackagram.id.desc())
                .limit(30).all())
        for r in rows:
            received.append({
                "when": (r.created_at.strftime("%d %B") if getattr(r, "created_at", None) else ""),
                "audio_url": getattr(r, "audio_url", None),
            })

    return render_template(
        "locker.html",
        has_smackcast=sub is not None,
        smackcast_league=(sub.league_name if sub else None),
        recaps=recaps,
        phone_verified=bool(verified and verification_live),
        verified_number=(verified.phone_digits if verified else None),
        verification_available=verification_live,
        received=received,
    )


@app.route("/api/locker")
@login_required
def api_locker():
    """
    Everything the customer has bought, newest first, as one timeline.

    Orders and Smackagrams are separate tables with different shapes, so they
    are normalised into a common row here rather than in the template - the
    page shouldn't have to know which table a row came from.

    Playback logic worth stating once: recording_url is a recording of the
    WHOLE CALL, so it already contains Smacky's message and whatever the
    recipient said. It is not a separate reaction file. When there's no
    recording - voicemail, no answer - message_audio_url is the synthesized
    clip on its own. That's why each row has exactly one play button whose
    label changes, rather than two buttons playing overlapping audio.
    """
    user = get_current_user()
    items = []

    for o in Order.query.filter_by(user_id=user.id).all():
        has_call = bool(o.recording_url)
        items.append({
            "kind": "smackagram",
            "id": o.id,
            "recipient": o.recipient_name,
            "team": None,
            "status": o.call_status,
            "answered_by": o.answered_by,
            "message": (o.custom_message or "")[:160],
            "audio_url": o.recording_url or o.message_audio_url,
            "audio_label": "Play the call" if has_call else "What Smacky said",
            "has_reaction": has_call,
            "share_token": o.share_token,
            "created_at": utc_iso(o.created_at),
            "pending": False,
        })

    for s in Smackagram.query.filter_by(user_id=user.id).all():
        has_call = bool(s.recording_url)
        # An armed one has no audio at all yet - Smacky doesn't write it until
        # the game ends - so it's shown as pending rather than as a broken row.
        pending = s.status == "armed"
        items.append({
            "kind": "locked",
            "id": s.id,
            "recipient": s.recipient_name,
            "team": s.target_team,
            "matchup": f"{s.away_team} @ {s.home_team}" if s.away_team else None,
            "status": s.status,
            "answered_by": s.answered_by,
            "message": (s.custom_message or "")[:160],
            "audio_url": None if pending else (s.recording_url or s.message_audio_url),
            "audio_label": "Play the call" if has_call else "What Smacky said",
            "has_reaction": has_call,
            "share_token": s.share_token,
            "created_at": utc_iso(s.created_at),
            "pending": pending,
        })

    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return jsonify({
        "balance_smacks": user.smackagram_count,
        "items": items,
    })


@app.route("/api/locker/download/<kind>/<int:item_id>")
@login_required
def locker_download(kind, item_id):
    """
    Serves a recording as a real download with a sensible filename.

    Proxied rather than linking to S3 for the same reason as the Smackcast
    library: the object key is a bare UUID, so a direct link saves as
    gibberish. Ownership is checked - ids are sequential, so without it anyone
    logged in could walk the range and pull down other people's calls.
    """
    user = get_current_user()
    if kind == "smackagram":
        rec = Order.query.get(item_id)
        owned = rec and rec.user_id == user.id
    else:
        rec = Smackagram.query.get(item_id)
        owned = rec and rec.user_id == user.id
    # 404 rather than 403 - no reason to confirm a record exists to someone
    # who doesn't own it.
    if not owned:
        return "Not found.", 404

    url = rec.recording_url or rec.message_audio_url
    if not url:
        return "Nothing to download yet.", 404

    who = re.sub(r"[^a-z0-9]+", "-", (rec.recipient_name or "smackagram").lower()).strip("-")
    when = rec.created_at.strftime("%Y-%m-%d") if rec.created_at else "smackagram"
    try:
        upstream = requests.get(url, stream=True, timeout=30)
        if upstream.status_code != 200:
            return "Couldn't retrieve that recording.", 502
    except Exception as e:
        print(f"[locker] download failed for {kind} {item_id}: {e}")
        return "Couldn't retrieve that recording.", 502

    return Response(
        upstream.iter_content(chunk_size=64 * 1024),
        mimetype="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="smackagram-{who}-{when}.mp3"'},
    )


def _require_admin():
    """
    One gate for every admin surface.

    Returns (user, None) when allowed, or (None, response) to return straight
    back. Centralised deliberately - the previous pattern repeated the same
    two-line check in each handler, which is exactly how one eventually gets
    written wrong.
    """
    user = get_current_user()
    if not user:
        return None, (jsonify({"error": "Not signed in."}), 401)
    if not user.is_admin:
        # Deliberately vague, and logged. A non-admin poking at admin URLs is
        # worth knowing about.
        print(f"[admin] denied: user {user.id} ({user.email}) tried {request.path}")
        return None, (jsonify({"error": "Not found."}), 404)
    return user, None


@app.route("/admin")
@login_required
def admin_home():
    user, err = _require_admin()
    if err:
        return "Not found.", 404
    return render_template("admin_panel.html")


@app.after_request
def _count_page_view(response):
    """
    Count a page view after the response is built.

    AFTER, not before, so a page that errored is not counted as a visit -
    and so nothing analytics does can delay or break the response itself.
    Only real page loads: no assets, no API calls, no bot probes.
    """
    try:
        if (request.method == "GET"
                and response.status_code == 200
                and not request.path.startswith(("/static", "/api"))):
            analytics_service.record(
                request,
                is_logged_in=get_current_user() is not None)
    except Exception:
        pass
    return response


@app.route("/api/admin/trace-audio")
@login_required
def api_admin_trace_audio():
    """
    Walk the audio chain for one order and report where it breaks.

    Silence on a call has at least five possible causes and the log does not
    distinguish them: no script written, no audio generated, an S3 key that
    does not exist, a URL that 404s, or empty TwiML. Guessing between them
    costs more than checking.

    Read-only. Fetches URLs but changes nothing.
    """
    user, err = _require_admin()
    if err:
        return err

    oid = request.args.get("order")
    order = (Order.query.get(int(oid)) if oid
             else Order.query.order_by(Order.id.desc()).first())
    if not order:
        return jsonify({"error": "no orders found"}), 404

    out = {"order_id": order.id, "steps": []}

    def step(name, ok, detail=""):
        out["steps"].append({"step": name, "ok": bool(ok), "detail": str(detail)[:300]})

    # Audio is generated on demand from custom_message - there is no stored
    # script or audio column. An empty custom_message with no scenario is
    # therefore silence by construction.
    msg = getattr(order, "custom_message", None)
    step("message text", bool(msg) or bool(order.scenario_id),
         (msg or f"no custom_message; falls back to scenario {order.scenario_id}")[:200])

    step("voice selected", True, getattr(order, "voice_key", None) or "(default)")
    step("call placed", bool(order.twilio_call_sid),
         f"sid={order.twilio_call_sid} status={order.call_status} "
         f"answered_by={order.answered_by}")

    try:
        base = os.environ.get("BASE_URL", request.url_root.rstrip("/"))
        urls = call_audio_service.resolve_audio_url(order, base)
        step("resolve_audio_url", bool(urls),
             urls if urls else "returned nothing - this is what Twilio would play")
    except Exception as e:
        urls = []
        step("resolve_audio_url", False, f"{type(e).__name__}: {e}")

    # Does each URL actually serve audio? A URL that exists in the database
    # and a URL that returns bytes are different things.
    import urllib.request
    for u in (urls or []):
        try:
            req = urllib.request.Request(u, method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as r:
                ln = r.headers.get("Content-Length")
                ct = r.headers.get("Content-Type")
                step(f"fetch {u.split('/')[-1][:40]}",
                     r.status == 200 and (int(ln or 0) > 1000),
                     f"HTTP {r.status}, {ln} bytes, {ct}")
        except Exception as e:
            step(f"fetch {u.split('/')[-1][:40]}", False, f"{type(e).__name__}: {e}")

    try:
        twiml = twilio_service.build_twiml(urls or [], record=False)
        has_play = "<Play" in twiml
        step("TwiML has a Play verb", has_play, twiml[:300])
    except Exception as e:
        step("build_twiml", False, f"{type(e).__name__}: {e}")

    out["verdict"] = ("everything resolves - the problem is downstream of here"
                      if all(x["ok"] for x in out["steps"])
                      else "first failing step above is the cause")
    return jsonify(out)


@app.route("/api/admin/pulse")
@login_required
def api_admin_pulse():
    """
    Anything sent since the id the admin page last saw.

    Polled rather than pushed. A websocket would be the textbook answer, but
    this runs on a single Gunicorn worker and a poll every ten seconds costs
    two indexed lookups - the complexity is not worth what it buys.

    Returns only what is NEW, so the page can tell the difference between
    "nothing has happened" and "the page just loaded".
    """
    user, err = _require_admin()
    if err:
        return err

    try:
        since_order = int(request.args.get("order", 0))
        since_lnl = int(request.args.get("locked", 0))
    except (TypeError, ValueError):
        since_order = since_lnl = 0

    fresh = []

    q = Order.query.order_by(Order.id.desc()).limit(20).all()
    for o in q:
        if o.id > since_order:
            fresh.append({
                "kind": "smackagram",
                "id": o.id,
                "team": getattr(o, "team", None) or getattr(o, "target_team", None),
                "when": utc_iso(o.created_at),
            })

    q2 = Smackagram.query.order_by(Smackagram.id.desc()).limit(20).all()
    for sm in q2:
        if sm.id > since_lnl:
            fresh.append({
                "kind": "locked",
                "id": sm.id,
                "team": getattr(sm, "target_team", None),
                "status": getattr(sm, "status", None),
                "when": utc_iso(sm.created_at),
            })

    return jsonify({
        "new": sorted(fresh, key=lambda x: x["id"], reverse=True)[:12],
        "count": len(fresh),
        # The high-water marks, so the next poll only asks for what follows.
        "order": q[0].id if q else since_order,
        "locked": q2[0].id if q2 else since_lnl,
        # First call after a page load reports the marks WITHOUT the backlog,
        # so opening /admin does not fire an alarm for everything sent today.
        "priming": since_order == 0 and since_lnl == 0,
    })


@app.route("/api/admin/safety")
@login_required
def api_admin_safety():
    """Everything the moderation gate stopped, newest first."""
    user, err = _require_admin()
    if err:
        return err
    only_new = request.args.get("unreviewed") == "1"
    return jsonify({
        "summary": safety_service.summary(days=30),
        "events": safety_service.recent(limit=120, only_unreviewed=only_new),
    })


@app.route("/api/admin/safety/<int:event_id>/reviewed", methods=["POST"])
@login_required
def api_admin_safety_reviewed(event_id):
    """Mark one as looked at, so the unreviewed count means something."""
    user, err = _require_admin()
    if err:
        return err
    ev = SafetyEvent.query.get(event_id)
    if not ev:
        return jsonify({"error": "not found"}), 404
    ev.reviewed = True
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/analytics")
@login_required
def api_admin_analytics():
    """Traffic and the funnel, for the admin page."""
    user, err = _require_admin()
    if err:
        return err
    try:
        days = min(int(request.args.get("days", 7)), 90)
    except (TypeError, ValueError):
        days = 7
    return jsonify(analytics_service.summary(days=days))


@app.route("/api/admin/summary")
@login_required
def api_admin_summary():
    user, err = _require_admin()
    if err:
        return err
    return jsonify(admin_service.accounting_summary())


@app.route("/api/admin/customers")
@login_required
def api_admin_customers():
    user, err = _require_admin()
    if err:
        return err
    return jsonify({
        "customers": admin_service.customer_list(
            search=request.args.get("q", ""),
            limit=min(int(request.args.get("limit", 50)), 200),
        )
    })


@app.route("/api/admin/customer/<int:user_id>")
@login_required
def api_admin_customer(user_id):
    user, err = _require_admin()
    if err:
        return err
    detail = admin_service.customer_detail(user_id)
    if not detail:
        return jsonify({"error": "No such customer."}), 404
    return jsonify(detail)


@app.route("/api/admin/settings")
@login_required
def api_admin_settings_get():
    user, err = _require_admin()
    if err:
        return err
    s = settings_service.all_settings()
    # Surfaced so the panel can warn that the break-glass var is live -
    # otherwise admin 2FA would appear on while silently doing nothing.
    s["admin_bypass_env"] = os.environ.get("ADMIN_BYPASS_2FA") == "1"
    return jsonify(s)


@app.route("/api/admin/settings", methods=["POST"])
@login_required
def api_admin_settings_set():
    """
    Changes a runtime setting.

    Refuses to turn on admin 2FA unless the SMS path has actually been proven,
    because the failure mode is locking yourself out of the page that would
    undo it. The check is deliberate friction, not paranoia - Twilio is
    currently reporting messages as sent that never arrive.
    """
    user, err = _require_admin()
    if err:
        return err

    data = request.json or {}
    key = (data.get("key") or "").strip()
    value = bool(data.get("value"))

    if key not in ("twofactor_customers", "twofactor_admins",
                   "smackback_requires_verification"):
        return jsonify({"error": "Unknown setting."}), 400

    if key == "twofactor_admins" and value:
        if os.environ.get("ADMIN_BYPASS_2FA") == "1":
            pass    # break-glass is set, safe to enable
        elif not data.get("confirm_sms_works"):
            return jsonify({
                "error": "Confirm SMS delivery works first.",
                "needs_confirmation": True,
                "detail": ("If texts aren't arriving, turning this on locks you "
                           "out of this page. Set ADMIN_BYPASS_2FA=1 in Render "
                           "first, or tick the box to confirm you've received a "
                           "test code."),
            }), 400

    settings_service.set_value(key, value, changed_by=user.screen_name)
    return jsonify({"ok": True, "settings": settings_service.all_settings()})


@app.route("/api/admin/grant", methods=["POST"])
@login_required
def api_admin_grant():
    """
    Hands out free smacks or Smackcast slots.

    Every grant is logged with WHO did it, because this is the one admin
    action that creates value out of nothing and the audit trail matters more
    than the convenience.
    """
    user, err = _require_admin()
    if err:
        return err

    data = request.json or {}
    target_id = data.get("user_id")
    kind = (data.get("kind") or "").strip()
    amount = int(data.get("amount") or 0)
    note = (data.get("note") or "").strip()

    if not target_id:
        return jsonify({"error": "Pick a customer."}), 400

    if kind == "smacks":
        result = admin_service.grant_smacks(int(target_id), amount, note, user.screen_name)
    elif kind == "smackcast":
        result = admin_service.grant_smackcast(int(target_id), amount, note, user.screen_name)
    else:
        return jsonify({"error": "kind must be 'smacks' or 'smackcast'."}), 400

    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/admin/espn")
@login_required
def admin_espn_page():
    user = get_current_user()
    if not user.is_admin:
        return "Not authorized.", 403
    return render_template("admin_espn.html")


@app.route("/api/admin/espn-preview")
@login_required
def admin_espn_preview():
    """
    Everything ESPN gives us for one night, scores and headlines side by side.

    Exists to answer two questions before any of it feeds the show: are the
    scores real (they weren't, on the previous provider), and is there enough
    headline volume to be worth the safety screen it requires.
    """
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    from services import espn_scores

    days_back = int(request.args.get("days_back", 1))
    leagues = [l.strip() for l in request.args.get("leagues", "mlb,wnba").split(",")]

    scores = []
    per_league = {}
    for lg in leagues:
        got = espn_scores.fetch_finals(lg, days_back=days_back)
        per_league[lg] = {"games": len(got)}
        scores.extend(got)

    # Headlines dropped entirely. ESPN's news feed returns ~6 auto-generated
    # game PREVIEWS per league ("Pirates bring 3-game losing streak into
    # matchup with the Reds") - boilerplate about games that haven't happened.
    # SportsDataIO gave 8 real stories across four leagues. Neither is enough
    # to be worth the safety screen it requires, so the show is scores only.

    scores.sort(key=lambda g: g["margin"], reverse=True)

    return jsonify({
        "per_league": per_league,
        "game_count": len(scores),
        "games": scores,
    })


@app.route("/admin/show")
@login_required
def admin_show_page():
    user = get_current_user()
    if not user.is_admin:
        return "Not authorized.", 403
    return render_template("admin_show.html")


@app.route("/api/admin/show-material")
@login_required
def admin_show_material():
    """
    What a given night actually gives Smacky to work with.

    Exists so the MATERIAL can be judged before any audio is generated -
    whether a typical night produces enough to fill 90 seconds, and whether
    the facts are ones a person would actually find funny.
    """
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    days_back = int(request.args.get("days_back", 1))
    leagues = [l.strip() for l in request.args.get("leagues", "mlb,nfl,nba,nhl").split(",")]
    return jsonify(show_service.get_show_material(leagues=leagues, days_back=days_back))


@app.route("/admin/news")
@login_required
def admin_news_page():
    user = get_current_user()
    if not user.is_admin:
        return "Not authorized.", 403
    return render_template("admin_news.html")


@app.route("/api/admin/news-preview")
@login_required
def admin_news_preview():
    """
    Shows the FULL pipeline, not just the survivors.

    The daily show publishes unreviewed, so the thing that needs reviewing is
    the FILTER, not the output. That means seeing what was rejected and why -
    a list of accepted stories tells you nothing about whether the screen is
    working.
    """
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    days_back = int(request.args.get("days_back", 1))
    sports = request.args.get("sports", "nfl,nba,mlb,nhl").split(",")

    raw = []
    per_league = {}
    for sport in sports:
        got = news_service.fetch_headlines(sport.strip(), days_back=days_back)
        per_league[sport.strip()] = len(got)
        raw.extend(got)

    seen, deduped = set(), []
    for item in raw:
        key = item["title"].lower()[:70]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    # Keyword pass, keeping the reason for each rejection.
    kw_passed, kw_rejected = [], []
    for item in deduped:
        hit = news_service.keyword_hit(item)
        if hit:
            kw_rejected.append({**item, "rejected_by": hit})
        else:
            kw_passed.append(item)

    # Model pass over whatever survived.
    model_passed = news_service.model_safe(kw_passed)
    passed_titles = {i["title"] for i in model_passed}
    model_rejected = [i for i in kw_passed if i["title"] not in passed_titles]

    ranked = sorted(model_passed, key=news_service._juice_score, reverse=True)

    return jsonify({
        "fetched": len(raw),
        "per_league": per_league,
        "after_dedupe": len(deduped),
        "selected": [
            {**i, "juice": news_service._juice_score(i)} for i in ranked[:6]
        ],
        "also_passed": [
            {**i, "juice": news_service._juice_score(i)} for i in ranked[6:]
        ],
        "rejected_by_model": model_rejected,
        "rejected_by_keyword": kw_rejected,
    })


@app.route("/api/admin/grant-credit", methods=["POST"])
@login_required
def admin_grant_credit():
    """
    Tops up a wallet for testing. Admin only.

    Deliberately goes through wallet_service.credit_wallet rather than writing
    the balance directly, so a WalletTransaction row is created exactly as a
    real Stripe top-up would - test balances then behave like real ones
    everywhere downstream, and the ledger stays consistent.
    """
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    data = request.json or {}
    target_name = (data.get("username") or user.screen_name or "").strip()
    smacks = int(data.get("smacks") or 0)
    if smacks < 1 or smacks > 500:
        return jsonify({"error": "Give a number of smacks between 1 and 500."}), 400

    target = User.query.filter(
        db.or_(User.screen_name == target_name, User.email == target_name)
    ).first()
    if not target:
        return jsonify({"error": f"No user found matching '{target_name}'."}), 404

    amount = smacks * wallet_service.SMACK_COST_CENTS
    wallet_service.credit_wallet(
        target, amount, "admin_grant",
        description=f"Admin test credit — {smacks} smack(s)",
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "user": target.screen_name,
        "granted_smacks": smacks,
        "new_balance_cents": target.balance_cents,
        "new_balance_smacks": target.smackagram_count,
    })


@app.route("/privacy")
def privacy():
    """
    The policy lives inside the Terms page rather than standing alone. This
    route is kept as an alias so /privacy still resolves - useful because
    Twilio's A2P review wants a URL that lands ON the policy, and because
    anything already linking to /privacy keeps working.
    """
    return redirect("/terms#privacy")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


# The topics somebody can pick. Ordered by how urgent they are to us
# rather than alphabetically - a smack that never arrived is somebody who
# paid and got nothing, and that should be the first thing on the list.
SUPPORT_TOPICS = [
    "My Smackagram never arrived",
    "I was charged incorrectly",
    # Content complaints sit high deliberately. Somebody reporting that
    # Smacky went too far is telling us the generator crossed a line, and
    # that is worth knowing FAST - it may be one bad call or it may be a
    # prompt that has drifted and is doing it to everybody.
    "Smacky was too aggressive (explicit content)",
    "I received a Smackagram and want it to stop",
    "Something on the site is broken",
    "Question about how it works",
    "Partnership or business enquiry",
    "Something else",
]


@app.route("/api/support", methods=["POST"])
def api_support_submit():
    """
    Take a message from the contact form.

    Deliberately forgiving about what it accepts. Somebody who has been
    charged wrongly and cannot get through is a worse outcome than a
    ticket with a malformed phone number, so only the fields we genuinely
    cannot act without are required.
    """
    d = request.get_json(silent=True) or request.form or {}

    first = (d.get("first_name") or "").strip()[:60]
    last = (d.get("last_name") or "").strip()[:60]
    email = (d.get("email") or "").strip()[:200]
    phone = (d.get("phone") or "").strip()[:30]
    topic = (d.get("topic") or "").strip()[:60]
    message = (d.get("message") or "").strip()

    missing = []
    if not first:
        missing.append("your first name")
    if not email or "@" not in email:
        missing.append("an email address we can reply to")
    if not message:
        missing.append("a message")
    if missing:
        return jsonify({"error": "Still need " + ", ".join(missing) + "."}), 400

    if topic not in SUPPORT_TOPICS:
        topic = "Something else"

    try:
        from models import SupportTicket
        user = get_current_user()
        t = SupportTicket(
            first_name=first, last_name=last, email=email, phone=phone,
            topic=topic, message=message[:8000],
            user_id=getattr(user, "id", None),
            user_agent=(request.headers.get("User-Agent") or "")[:300],
            ip=(request.headers.get("X-Forwarded-For")
                or request.remote_addr or "")[:60],
        )
        db.session.add(t)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[support] could not save: {e}", flush=True)
        try:
            from services import alerts
            # Critical: somebody is trying to reach us and cannot.
            alerts.record("support", "save_failed", str(e)[:200],
                          severity="critical")
        except Exception:
            pass
        return jsonify({"error": "Something went wrong saving that. Email "
                                 "support@smackagram.com and we will pick "
                                 "it up."}), 500

    print(f"[support] #{t.id} {topic} from {email}", flush=True)

    # EMAIL THE OWNERS. EVERY TICKET, NOT A SELECTION.
    #
    # A ticket used to land in the database and wait for somebody to think
    # of checking a URL. That is how a small complaint becomes a
    # chargeback: the customer cannot tell whether it arrived, so they
    # escalate to their bank instead of to us.
    #
    # reply_to is the CUSTOMER, so hitting Reply in a mail client answers
    # them directly rather than a noreply address. Small thing, and it
    # decides whether anybody actually replies.
    try:
        from services import mail
        mail.send(
            os.environ.get("SUPPORT_INBOX", "owners@smackagram.com"),
            # Subject format is David's spec (Aug 6 2026): the ticket
            # number IS the subject, so the inbox sorts and searches by
            # it. The topic still leads the body's first lines.
            f"Smackagram Support Ticket #{t.id}",
            f"{first} {last} <{email}>\n"
            f"Phone: {phone or 'not given'}\n"
            f"Topic: {topic}\n"
            f"Ticket: #{t.id}\n"
            f"{'-' * 46}\n\n{message}\n\n"
            f"{'-' * 46}\n"
            f"Reply from the admin panel so the answer is recorded "
            f"against the ticket.",
            reply_to=email)
    except Exception as e:
        # A failed notification must never lose the ticket - it is already
        # saved by this point, and visible in the panel either way.
        print(f"[support] could not email owners: {e}", flush=True)

    # Tell somebody, but only for the ones that involve money or a
    # missing delivery. Alerting on every "how does this work" trains
    # you to ignore the alerts, which is worse than not having them.
    try:
        from services import safety_service
        # An explicit-content report alerts too. If the generator has
        # started producing something it should not, every call going out
        # in the meantime has the same problem - that is not a thing to
        # find in a queue tomorrow morning.
        if topic in ("My Smackagram never arrived",
                     "I was charged incorrectly",
                     "Smacky was too aggressive (explicit content)"):
            safety_service._notify(
                f"Support #{t.id}: {topic} - {first} {last} ({email})")
    except Exception as e:
        print(f"[support] alert failed: {e}", flush=True)

    return jsonify({"ok": True, "id": t.id,
                    "message": "Got it. Smacky will get back to you shortly."})


@app.route("/contact")
def contact_page():
    # Topics come from one list in Python rather than being typed into the
    # template, so the dropdown and the validation can never disagree about
    # what a valid topic is.
    return render_template("contact.html", topics=SUPPORT_TOPICS)


@app.route("/smack-zone")
def smack_zone_page():
    """
    Hub for the free, text-only features (Lab, Chat, Battle). Grouping
    these under one nav slot is what got the top-level nav from nine
    product links down to five - but a hub only beats a plain dropdown if
    it actually sells each feature, hence cards with real copy rather than
    a list of links. It's also a landing page that can rank, which a nav
    item never will.

    The individual routes are untouched and stay linked from here; this is
    purely additive. Nothing that used to be reachable stopped being
    reachable.
    """
    return render_template("smack_zone.html")


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

    # WHOSE CONVERSATION IS THIS?
    #
    # There was no check at all. Any logged-in account could walk
    # reply_id 1, 2, 3 and read other people's smacks and replies, with
    # the audio URLs - and the ids are sequential, so it was a for-loop
    # away from every private message on the site.
    #
    # Two people are entitled to see this: whoever sent the original, and
    # whoever sent the reply. Nobody else, admins aside.
    _viewer = get_current_user()
    _mine = (
        (getattr(original, "user_id", None) is not None
         and original.user_id == _viewer.id)
        or (getattr(reply, "user_id", None) is not None
            and reply.user_id == _viewer.id)
        or getattr(_viewer, "is_admin", False)
    )
    if not _mine:
        # 404, not 403. There is no reason to confirm a conversation
        # exists to somebody with no business seeing it - a 403 tells a
        # script which ids are real.
        print(f"[idor] user {_viewer.id} tried conversation {reply_id}",
              flush=True)
        return jsonify({"error": "Conversation not found"}), 404

    return jsonify({
        "original": {
            "message": original.custom_message,
            "audio_url": original.message_audio_url,
            "created_at": utc_iso(original.created_at),
        },
        "reply": {
            "message": reply.custom_message,
            "audio_url": reply.message_audio_url,
            "created_at": utc_iso(reply.created_at),
        },
    })


# OFF THE SITE, not deleted.
#
# Nothing linked to it, so it was reachable only by typing the URL - an
# unreachable page still has to be maintained, and still shows up in a
# search index. The template, the models and the API routes are all intact,
# so relinking is one line whenever it earns a place.
#
# @app.route("/smack-chat")
# @login_required
# def smack_chat_page():
#     return render_template("smack_chat.html")


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
        "created_at": utc_iso(p.created_at),
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
        return jsonify({"error": _moderation_error_text(safety), "reason": safety.get("reason"), "excerpt": safety.get("excerpt", ""), "category": safety.get("category", ""), "retryable": not safety.get("available", True)}), (503 if not safety.get("available", True) else 400)

    post = ChatPost(league=league, team=team, display_name=display_name or "Anonymous", message=message)
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "id": post.id,
        "display_name": post.display_name,
        "message": post.message,
        "average_rating": post.average_rating,
        "rating_count": post.rating_count,
        "created_at": utc_iso(post.created_at),
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

    reaction_counts = {}
    for line_id, reaction, n in (
        db.session.query(
            BattleLineReaction.line_id,
            BattleLineReaction.reaction,
            db.func.count(BattleLineReaction.id),
        )
        .filter(BattleLineReaction.battle_id == battle.id)
        .group_by(BattleLineReaction.line_id, BattleLineReaction.reaction)
        .all()
    ):
        reaction_counts.setdefault(line_id, {})[reaction] = n
    round_results = BattleRoundResult.query.filter_by(battle_id=battle.id).order_by(BattleRoundResult.round_number.asc()).all()
    # Computed server-side (comparing against utcnow() here, not on the
    # client) specifically to avoid any client/server clock skew — a
    # 3-second "still typing" window is a reasonable match for how
    # Slack/iMessage-style indicators typically behave.
    now = datetime.utcnow()
    is_typing_a = bool(battle.last_typed_a and (now - battle.last_typed_a).total_seconds() < 3)
    is_typing_b = bool(battle.last_typed_b and (now - battle.last_typed_b).total_seconds() < 3)
    # 20-second window - long enough that a brief poll/network hiccup
    # doesn't make someone flicker in and out of the count, short enough
    # that someone who actually closed the tab drops off within a few
    # heartbeat cycles rather than staying "live" for minutes.
    viewer_cutoff = now - timedelta(seconds=20)
    viewer_count = BattleViewer.query.filter(BattleViewer.battle_id == battle.id, BattleViewer.last_seen >= viewer_cutoff).count()

    # "Opponent left" detection - only meaningful mid-battle (before
    # active there's no opponent yet to leave; once complete the battle
    # itself is already over). A side only counts as "left" once it has
    # a real last_seen_X value that's gone stale - a None value just
    # means they haven't had a chance to ping yet (e.g. right after
    # joining), not that they've left, so it's deliberately excluded
    # rather than treated as "left from the start."
    presence_cutoff = now - timedelta(seconds=30)
    side_a_left = bool(battle.status == "active" and battle.last_seen_a and battle.last_seen_a < presence_cutoff)
    # Smacky never "leaves" - he has no browser sending presence pings, so
    # without this exception a solo battle would tell the player their
    # opponent walked out moments after the first round.
    side_b_left = bool(
        battle.opponent_type != "smacky"
        and battle.status == "active"
        and battle.last_seen_b
        and battle.last_seen_b < presence_cutoff
    )

    return {
        "challenge_code": battle.challenge_code,
        "league": battle.league,
        "intensity": battle.intensity,
        "max_rounds": battle.max_rounds,
        "status": battle.status,
        "current_turn": battle.current_turn,
        "turn_started_at": utc_iso(battle.turn_started_at),
        "round_number": battle.round_number,
        "display_name_a": battle.display_name_a,
        "team_a": battle.team_a,
        "display_name_b": battle.display_name_b,
        "opponent_type": battle.opponent_type,
        "team_b": battle.team_b,
        "lines": [{"id": l.id, "side": l.side, "round": l.round_number,
                    "message": l.message, "created_at": utc_iso(l.created_at),
                    "timed_out": l.timed_out,
                    "fire": reaction_counts.get(l.id, {}).get("fire", 0),
                    "ice": reaction_counts.get(l.id, {}).get("ice", 0)} for l in lines],
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
        "viewer_count": viewer_count,
        "side_a_left": side_a_left,
        "side_b_left": side_b_left,
    }


@app.route("/api/battles", methods=["POST"])
@login_required
def create_battle():
    data = request.json
    league = data.get("league", "")
    team_a = (data.get("team_a") or "").strip()
    display_name_a = (data.get("display_name_a") or "Anonymous").strip()[:40]
    intensity = data.get("intensity", 4)
    max_rounds = data.get("max_rounds", 5)

    if not league or not team_a:
        return jsonify({"error": "League and your team are required"}), 400
    if intensity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid intensity level"}), 400
    if max_rounds not in (3, 5, 10):
        return jsonify({"error": "Rounds must be 3, 5 or 10"}), 400

    challenge_code = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8]
    battle = Battle(challenge_code=challenge_code, league=league, team_a=team_a, display_name_a=display_name_a or "Anonymous", intensity=intensity, max_rounds=max_rounds)

    # Solo battles have nobody to wait for, so they skip "waiting" entirely
    # and open ACTIVE with side B already filled in. Everything downstream -
    # the intro, the countdown, the bell, the phase machine - then works
    # unchanged, because as far as the room is concerned both sides joined.
    battle.is_public = bool(data.get("is_public"))

    if (data.get("opponent") or "human").lower() == "smacky":
        battle.opponent_type = "smacky"
        battle.display_name_b = "Smacky"
        chosen = (data.get("team_b") or "").strip()
        battle.team_b = chosen or trash_talk_service.pick_smacky_battle_team(league, team_a)
        battle.status = "active"
        battle.current_turn = "a"

    db.session.add(battle)
    db.session.commit()

    return jsonify({"challenge_code": challenge_code,
                    "opponent_type": battle.opponent_type})


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
    # Deliberately left null, not datetime.utcnow() - the frontend plays
    # a ~5.9s team-names + 3-2-1 countdown intro before side A's input
    # box actually appears for round 1. Starting the clock here would
    # silently burn several seconds of side A's 60-second window on an
    # animation they can't even respond during. The frontend explicitly
    # calls /start-turn the moment that intro finishes (see playIntro).
    battle.turn_started_at = None
    db.session.commit()

    return jsonify(_battle_state_json(battle))


def _smacky_turn_async(app_obj, battle_id, round_number):
    """
    Smacky's reply in a solo battle.

    Runs on its own thread with a deliberate delay: an instant answer is
    uncanny, and the typing indicator only reads as real if something is
    actually taking time. Once his line lands the round has two sides, so
    this hands straight off to the SAME judging path a human-vs-human round
    uses - solo mode adds an opponent, it does not add a second rulebook.
    """
    import random
    with app_obj.app_context():
        try:
            battle = Battle.query.get(battle_id)
            if not battle or battle.round_number != round_number or battle.status != "active":
                return

            # Show the typing indicator while he "thinks".
            battle.last_typed_b = datetime.utcnow()
            db.session.commit()

            prior = BattleLine.query.filter_by(battle_id=battle.id).order_by(BattleLine.created_at.asc()).all()
            history = [
                (battle.display_name_a if ln.side == "a" else "Smacky", ln.message)
                for ln in prior
            ]
            their_last = next(
                (ln.message for ln in reversed(prior)
                 if ln.side == "a" and ln.round_number == round_number), None
            )

            line = trash_talk_service.generate_smacky_battle_line(
                my_team=battle.team_b or "Smacky",
                their_team=battle.team_a,
                their_name=battle.display_name_a,
                round_number=round_number,
                previous_lines=history,
                intensity=battle.intensity,
                their_last_line=their_last,
            )

            # Human-plausible pause. Generation already burned a few seconds,
            # so this tops it up rather than adding a full delay on top.
            time.sleep(random.uniform(1.5, 4.0))

            battle = Battle.query.get(battle_id)
            if not battle or battle.round_number != round_number or battle.status != "active":
                return

            db.session.add(BattleLine(
                battle_id=battle.id, side="b", round_number=round_number,
                message=line, timed_out=False,
            ))
            battle.awaiting_next_round = True
            battle.ready_a = False
            battle.ready_b = False
            battle.last_typed_b = None
            db.session.commit()

            line_a = BattleLine.query.filter_by(
                battle_id=battle.id, round_number=round_number, side="a").first()
            # Its own thread: _judge_round_async opens an app context of its
            # own, and nesting one inside this function's context would
            # leave the session in a confusing state.
            threading.Thread(
                target=_judge_round_async,
                args=(battle.id, round_number, battle.team_a,
                      line_a.message if line_a else "", battle.team_b, line),
                daemon=True,
            ).start()
        except Exception as e:
            print(f"[battle] Smacky turn failed for battle {battle_id}: {e}", flush=True)
            import traceback
            traceback.print_exc()


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
    is_timeout = bool(data.get("is_timeout"))

    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400
    if side != battle.current_turn:
        return jsonify({"error": "It's not your turn"}), 400
    if len(message) > 500:
        return jsonify({"error": "Keep it under 500 characters"}), 400

    timed_out = False
    if is_timeout:
        # Auto-submitted because the 60-second turn timer ran out. Empty
        # text, or text that fails the safety check right as time expired,
        # are both treated the same way: a missed turn, not a real line -
        # unsafe content is never stored or shown even under a timeout.
        if not message:
            timed_out = True
        else:
            safety = content_moderation.check_message_safety(message)
            if not safety["safe"]:
                print(f"[safety] timeout submission blocked — reason: {safety['reason']}")
                timed_out = True
        if timed_out:
            message = ""
    else:
        # Normal manual submission - unchanged from before: empty and
        # unsafe are both hard rejections, never silently converted into
        # a timeout just because someone didn't pass the safety check.
        if not message:
            return jsonify({"error": "Message can't be empty"}), 400
        safety = content_moderation.check_message_safety(message)
        if not safety["safe"]:
            print(f"[safety] blocked battle line — reason: {safety['reason']}")
            return jsonify({"error": _moderation_error_text(safety), "reason": safety.get("reason"), "excerpt": safety.get("excerpt", ""), "category": safety.get("category", ""), "retryable": not safety.get("available", True)}), (503 if not safety.get("available", True) else 400)

    db.session.add(BattleLine(battle_id=battle.id, side=side, round_number=battle.round_number, message=message, timed_out=timed_out))

    if side == "a":
        battle.current_turn = "b"
        # Deliberately set to null, not datetime.utcnow() - side B needs
        # unlimited time to actually read side A's line before their own
        # 60-second clock starts. Left null until side B explicitly hits
        # "Respond Now" (see start_turn below), which is what the
        # frontend uses to decide whether to show the line unobstructed
        # or show the response box + timer.
        battle.turn_started_at = None
        db.session.commit()

        # Solo: Smacky answers on his own thread. Nothing to wait for.
        if battle.opponent_type == "smacky":
            threading.Thread(
                target=_smacky_turn_async,
                args=(app, battle.id, battle.round_number),
                daemon=True,
            ).start()
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
        line_a_timed_out = line_a.timed_out if line_a else False

        if line_a_timed_out or timed_out:
            _resolve_timeout_round(battle, line_a_timed_out, timed_out)
        else:
            threading.Thread(
                target=_judge_round_async,
                args=(battle.id, battle.round_number, battle.team_a, line_a.message if line_a else "", battle.team_b, message),
                daemon=True,
            ).start()

    return jsonify(_battle_state_json(battle))


@app.route("/api/battles/<challenge_code>/start-turn", methods=["POST"])
@login_required
def start_turn(challenge_code):
    """
    Explicitly starts the 60-second turn timer - called when the user
    clicks "Respond Now" after actually reading whatever the opponent
    just said. Side A's turn at the start of a fresh round still starts
    its timer immediately (set directly in ready_for_next_round) since
    there's no prior line in that round to read yet; this endpoint is
    specifically for side B's turn within the same round, where
    turn_started_at is deliberately left null until this is called.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404

    data = request.json
    side = data.get("side", "")
    if side not in ("a", "b"):
        return jsonify({"error": "Invalid side"}), 400
    if side != battle.current_turn:
        return jsonify({"error": "It's not your turn"}), 400

    battle.turn_started_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_battle_state_json(battle))


def _resolve_timeout_round(battle, a_timed_out, b_timed_out):
    """
    Resolves a round where at least one side missed the 60-second turn
    timer (or had their last-second submission fail the safety check) -
    skips the AI judge entirely since there's nothing real to compare,
    and awards the round directly. Scores are fixed, not AI-generated:
    0 for a missed turn, 5 (a neutral "won by default, not on merit")
    for an opponent who only won because the other side didn't enter.
    """
    existing = BattleRoundResult.query.filter_by(battle_id=battle.id, round_number=battle.round_number).first()
    if existing:
        return

    if a_timed_out and b_timed_out:
        winner, score_a, score_b = "tie", 0, 0
        critique_a = "Neither side entered a line in time — no winner this round."
        critique_b = "Neither side entered a line in time — no winner this round."
    elif a_timed_out:
        winner, score_a, score_b = "b", 0, 5
        critique_a = "You didn't enter a line in time — this round goes to your opponent."
        critique_b = "Your opponent didn't enter in time — round awarded to you."
    else:
        winner, score_a, score_b = "a", 5, 0
        critique_a = "Your opponent didn't enter in time — round awarded to you."
        critique_b = "You didn't enter a line in time — this round goes to your opponent."

    db.session.add(BattleRoundResult(
        battle_id=battle.id,
        round_number=battle.round_number,
        winner=winner,
        critique_a=critique_a,
        critique_b=critique_b,
        score_a=score_a,
        score_b=score_b,
        coach_message_a="",
        coach_message_b="",
    ))
    db.session.commit()


@app.route("/api/battles/<challenge_code>/ready", methods=["POST"])
@login_required
def ready_for_next_round(challenge_code):
    """
    Marks one side as ready for the next round. The round only actually
    advances once BOTH sides have confirmed ready - a single side
    clicking this no longer immediately drags the other person into the
    next round before they've had a chance to actually read the
    critique/coach notes for the round that just finished.
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

    if side == "a":
        battle.ready_a = True
    else:
        battle.ready_b = True

    # Smacky is always ready. Without this a solo battle freezes after the
    # first round: the gate below waits for both sides to confirm, and he
    # has no browser to confirm from.
    if battle.opponent_type == "smacky":
        battle.ready_b = True

    if not (battle.ready_a and battle.ready_b):
        # Only one side has confirmed so far - record it and wait for
        # the other side. The round does NOT advance yet; the frontend
        # shows this side a "waiting on the other person" state while
        # polling picks up the eventual change once both are ready.
        db.session.commit()
        return jsonify(_battle_state_json(battle))

    battle.awaiting_next_round = False
    battle.ready_a = False
    battle.ready_b = False
    battle.current_turn = "a"
    battle.round_number += 1
    # Deliberately left null, not utcnow() - the frontend plays a 3-2-1
    # countdown before the new round's input appears, and starting the
    # clock here would burn those seconds off side A's 60 before they
    # could even type. playRoundCountdown() calls /start-turn the moment
    # its countdown finishes, exactly as round 1's intro already does.
    battle.turn_started_at = None
    if battle.round_number > battle.max_rounds:
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


def _readable_on_dark(hex_color, fallback):
    """
    A team's real brand colour can be near-black (several are), which
    disappears on this card's dark background. Mirrors the frontend's
    readableColor: keep the colour if it has enough luminance, otherwise
    fall back to the brand accent.
    """
    if not hex_color:
        return fallback
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return fallback
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return fallback
    # Rec. 601 luma - cheap and good enough for a "is this too dark" test.
    luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return hex_color if luma >= 0.32 else fallback


@app.route("/battle/<challenge_code>/card")
def battle_share_card(challenge_code):
    """
    A standalone, portrait share card for a finished battle - shaped 9:16
    so it screenshots cleanly straight into an Instagram story or any
    other vertical feed. Deliberately its own page rather than a resized
    version of the in-page scorecard: the playing view wants a wide card
    in the page column, a shareable graphic wants tall and self-contained,
    and trying to make one layout do both compromises both.

    Rendered entirely server-side so there's no empty flash or half-built
    state to accidentally capture in a screenshot.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return render_template("404.html"), 404

    results = BattleRoundResult.query.filter_by(battle_id=battle.id).order_by(BattleRoundResult.round_number.asc()).all()
    wins_a = sum(1 for r in results if r.winner == "a")
    wins_b = sum(1 for r in results if r.winner == "b")

    scores_a = [r.score_a for r in results if r.score_a is not None]
    scores_b = [r.score_b for r in results if r.score_b is not None]
    avg_a = round(sum(scores_a) / len(scores_a), 1) if scores_a else None
    avg_b = round(sum(scores_b) / len(scores_b), 1) if scores_b else None

    # Per-round winner, padded out to the battle's full length so an
    # abandoned battle still shows its unplayed rounds as blanks.
    by_round = {r.round_number: r.winner for r in results}
    rounds = [{"n": n, "winner": by_round.get(n)} for n in range(1, (battle.max_rounds or 5) + 1)]

    winner_name = None
    if battle.overall_winner == "a":
        winner_name = battle.display_name_a
    elif battle.overall_winner == "b":
        winner_name = battle.display_name_b

    return render_template(
        "battle_card.html",
        battle=battle,
        wins_a=wins_a,
        wins_b=wins_b,
        avg_a=avg_a,
        avg_b=avg_b,
        rounds=rounds,
        winner_name=winner_name,
        color_a=_readable_on_dark(_lookup_team_color(battle.league, battle.team_a), "#FFD400"),
        color_b=_readable_on_dark(_lookup_team_color(battle.league, battle.team_b), "#E8142C"),
        intensity_label=trash_talk_service.SENSITIVITY_LEVELS.get(battle.intensity, {}).get("label", "Savage"),
        # Smacky judged every round, so the card is framed as his ruling.
        # recap_winner_text is written in second person ("you dismantled
        # them"), which only reads right if it's explicitly addressed -
        # hence the "Smacky to <winner>" attribution in the template.
        recap_text=battle.recap_winner_text,
        # Same existence check the Meet Smacky page uses, so a missing
        # portrait degrades to a text-only card instead of a broken image.
        smacky_image_exists=os.path.exists(os.path.join(app.root_path, "static", "img", "smacky-hero.png")),
    )


@app.route("/api/admin/espn-probe")
def espn_probe():
    """Diagnostic only. Delete once the roast extraction is built."""
    # Either the scheduler's key or an admin who is already logged in.
    if not cron_authorised():
        return jsonify({"error": "nope"}), 403

    from services import espn_scores

    league = (request.args.get("league") or "mlb").lower()
    event_id = request.args.get("event")

    if not event_id:
        # Was hardcoded to 1, which silently ignored the days_back argument -
        # every probe hit yesterday regardless of what was asked for.
        try:
            _db = max(1, int(request.args.get("days_back", 1)))
        except (TypeError, ValueError):
            _db = 1
        finals = espn_scores.fetch_finals(league, days_back=_db)
        if not finals:
            return jsonify({"error": f"no {league} finals yesterday"}), 404
        sample = finals[0]
        event_id = sample.get("espn_id")
        if not event_id:
            return jsonify({"error": "no espn_id captured", "sample_game": sample}), 500

    # Runs the real extraction rather than dumping raw JSON, so this tests
    # the whole path: fetch, parse, and the fact lines Smacky writes from.
    if request.args.get("raw"):
        import json as _j
        from urllib.request import Request, urlopen
        _p = espn_scores.LEAGUE_PATHS.get(league)
        _u = f"{espn_scores.BASE}/{_p[0]}/{_p[1]}/summary?event={event_id}"
        with urlopen(Request(_u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as _r:
            _raw = _j.load(_r)
        _g = []
        for _b in ((_raw.get("boxscore") or {}).get("players") or []):
            for _s in (_b.get("statistics") or []):
                _a = (_s.get("athletes") or [{}])[0]
                _g.append({"team": ((_b.get("team") or {}).get("name")),
                           "group": _s.get("name") or _s.get("type"),
                           "labels": _s.get("labels"),
                           "player": ((_a.get("athlete") or {}).get("displayName")),
                           "stats": _a.get("stats"),
                           "starter": _a.get("starter"),
                           "keys": sorted(_a.keys())})
        return jsonify({"top_level_keys": sorted(_raw.keys()), "stat_groups": _g})

    detail = espn_scores.fetch_game_detail(league, event_id)
    return jsonify({
        "event_id": event_id,
        "detail": detail,
        "roast_facts": espn_scores.roast_facts(detail),
    })


@app.route("/smack-board")
def smack_board():
    """Live scores across every league, with a smack button on each game."""
    return render_template("smack_board.html")


# Seed content for Smacks of the Week.
#
# EXAMPLE SMACKS, not customer reviews. That distinction is the whole design:
# seeded testimonials on a site that takes payments is what the FTC rule on
# fake reviews was written for, and it carries penalties per review per person
# who saw it. Lines somebody could have sent make no claim about anybody's
# experience - and they sell the product better, because reading an actual
# smack tells you what a dollar buys in a way "great site, five stars" never
# does.
#
# Flagged as samples so they are labelled honestly and pushed out on their own
# as real posts arrive.
WALL_SAMPLES = [
    # Placeholder rows so the rail is not empty before the first real call.
    # Each is just a team and a handle - there is no line and no audio,
    # because there was no call. Flagged as samples, labelled on the page,
    # and pushed out on their own as real smacks arrive.
    ("bigmike_47",        "smackagram", "Yankees"),
    ("thecommish",        "locked",     "Cowboys"),
    ("dontatme_dave",     "smackback",  "Browns"),
    ("kellyfromohio",     "smackagram", "Bengals"),
    ("nunez_theproblem",  "locked",     "Mets"),
    ("saltyseahawk",      "smackagram", "Seahawks"),
    ("d_wrightt",         "smackback",  "Eagles"),
    ("hoopsandhops",      "smackagram", "Knicks"),
    ("greg_in_accounting","locked",     "Bears"),
    ("mamaknowsball",     "smackagram", "Cubs"),
    ("redzone_rachel",    "locked",     "Tigers"),
    ("cheeseheadchris",   "smackback",  "Packers"),
]


# How many smacks the wall holds. The fifty-first pushes the oldest off.
#
# Nothing is lost by pruning: a WallPost is only a display row. The smack
# itself lives on in its Order or Smackagram record, and the audio stays on
# S3 - so this is housekeeping on a carousel, not deleting anybody's smack.
WALL_KEEP = 50


def prune_wall():
    """Drop wall entries beyond the most recent WALL_KEEP."""
    try:
        keep = [r.id for r in (WallPost.query
                               .filter_by(is_sample=False)
                               .order_by(WallPost.id.desc())
                               .limit(WALL_KEEP).all())]
        if len(keep) < WALL_KEEP:
            return
        (WallPost.query
         .filter_by(is_sample=False)
         .filter(~WallPost.id.in_(keep))
         .delete(synchronize_session=False))
        db.session.commit()
    except Exception as e:
        print(f"[wall] prune skipped: {e}", flush=True)
        try:
            db.session.rollback()
        except Exception:
            pass


def wall_when(dt):
    """
    When this went out, in words.

    "Today" and "Yesterday" rather than a date, because they say the wall is
    alive - a visitor seeing "Sent to a Yankees fan, today" understands that
    people are using this right now, which a date never conveys. Anything
    older falls back to the date, since "eleven days ago" is just arithmetic
    somebody has to do.
    """
    if not dt:
        return None
    try:
        from datetime import datetime, timezone as _tz, timedelta
        now = datetime.now(_tz.utc)
        # Rows written before timezone awareness landed have no tzinfo.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        days = (now.date() - dt.date()).days
        if days <= 0:
            return "Today"
        if days == 1:
            return "Yesterday"
        if days < 7:
            return f"{days} days ago"
        return dt.strftime("%d %B").lstrip("0")
    except Exception:
        return None


# Cities are noise on a card this small. "Sent to a New York Yankees fan"
# wastes the width and reads worse than "Sent to a Yankees fan" - the
# nickname is what a fan calls themselves.
_CITY_WORDS = {
    "new", "york", "los", "angeles", "san", "francisco", "diego", "jose",
    "kansas", "city", "tampa", "bay", "green", "golden", "state", "oklahoma",
    "st", "st.", "saint", "louis", "las", "vegas", "salt", "lake", "north",
    "south", "east", "west", "fort", "worth", "chicago", "boston", "dallas",
    "miami", "denver", "detroit", "houston", "phoenix", "seattle", "atlanta",
    "baltimore", "buffalo", "carolina", "cincinnati", "cleveland", "columbus",
    "indianapolis", "jacksonville", "memphis", "milwaukee", "minnesota",
    "nashville", "orlando", "philadelphia", "pittsburgh", "portland",
    "sacramento", "toronto", "utah", "washington", "arizona", "brooklyn",
    "charlotte", "anaheim", "oakland", "colorado", "texas", "tennessee",
    "vancouver", "calgary", "edmonton", "montreal", "ottawa", "winnipeg",
    "florida", "vegas", "jersey", "england", "orleans", "antonio",
}


def _nickname_only(name):
    """
    "New York Yankees" -> "Yankees". "Cowboys" -> "Cowboys".

    Strips leading city words rather than taking the last word, because
    plenty of nicknames are two words - Red Sox, Blue Jays, White Sox,
    Trail Blazers - and the last word alone would give "Sox" and "Jays".
    """
    if not name:
        return None
    parts = str(name).strip().split()
    if not parts:
        return None
    # Drop city words from the FRONT only, and never all of them.
    while len(parts) > 1 and parts[0].lower().strip(".") in _CITY_WORDS:
        parts.pop(0)
    return " ".join(parts) or None


def wall_headline(record, product):
    """
    Three or four words saying what this smack was about.

    Somebody scrolling the wall needs to know what they are listening to
    before they press play - "YANKEES LOST 9-2" tells you more in three words
    than the smack itself does in thirty.

    Built from whatever the record actually has. Auto-Smack knows the
    fixture and the result; a plain Smackagram only knows the team, so it
    gets the shorter version rather than an invented scoreline.
    """
    def clean(v):
        return (v or "").strip()

    # Whose fan caught this. Auto-Smack records the target explicitly;
    # a standard smack only has the team that was being roasted, which comes
    # to the same thing from the recipient's side.
    team = (clean(getattr(record, "target_team", None))
            or clean(getattr(record, "team", None)))
    if not team:
        return None

    # "Yankees" -> "a Yankees fan". Reads as a person rather than a fixture,
    # which is what the wall is actually about - somebody got a phone call.
    return f"SENT TO A {team.upper()} FAN"


def _stitch_wall_audio_later(post_id, message_url, base_url):
    """
    Swap a wall post's audio for the full package, in the background.

    Stitching downloads two files, runs ffmpeg and uploads - ten seconds or
    so. publish_to_wall is called from inside order creation, so doing it
    inline would put that squarely in the middle of somebody's checkout.

    The post goes up immediately with the message-only audio and this
    upgrades it a moment later. Worst case it stays as it was, which is what
    the wall has been playing all along.
    """
    def run():
        with app.app_context():
            try:
                full = call_audio_service.stitch_full_call(message_url, base_url)
                if full and full != message_url:
                    post = WallPost.query.get(post_id)
                    if post:
                        post.audio_url = full
                        db.session.commit()
            except Exception as e:
                print(f"[wall] stitch failed for post {post_id}: {e}", flush=True)

    threading.Thread(target=run, daemon=True).start()


def publish_to_wall(record, product, audio_url=None):
    """
    Put a smack on the wall as it is created.

    Everything goes up. The generator already runs every message through
    content_moderation before it is allowed to exist, so the wall inherits
    that gate rather than adding a second one - and a wall that only fills
    when somebody remembers to approve things is a wall that stays empty.

    The audio is Smacky's GENERATED LINE, never a recording of the call.
    Nothing is captured from the other end, so no second party is in the file
    and there is nobody whose consent is missing - which is the whole reason
    this can be automatic rather than opt-in.

    Never raises. A wall post failing must not take down a call somebody has
    already paid for.
    """
    try:
        body = (getattr(record, "custom_message", None) or "").strip()
        if not body:
            return

        user = None
        try:
            user = User.query.get(record.user_id) if record.user_id else None
        except Exception:
            pass

        # NO SCREEN NAME ON THE WALL. EVER.
        #
        # This published the SENDER'S screen name next to the actual call
        # audio. A recipient who heard their smack could find that exact
        # recording on the public wall and read off who sent it.
        #
        # "They never find out it was you" is on the homepage twice. It
        # cannot be true while the wall names the sender.
        #
        # The field is kept and filled with a constant rather than
        # removed, so nothing downstream that reads it breaks - and so
        # anybody reading this later sees the reason rather than an
        # unexplained gap.
        handle = "anonymous"

        post = WallPost(
            user_id=getattr(record, "user_id", None),
            handle=handle,
            body=body,
            product=product,
            headline=wall_headline(record, product),
            team_name=_nickname_only(
                getattr(record, "target_team", None)
                or getattr(record, "team", None)),
            team=((getattr(record, "target_team", None)
                   or getattr(record, "team", None) or "").strip() or None),
            # Goes up with the plain message immediately; the stitched
            # version replaces it a few seconds later - see below.
            audio_url=audio_url,
            approved=True,
            is_sample=False,
        )
        db.session.add(post)
        db.session.commit()

        # Upgrade the audio to the full package in the background - the post
        # is already live with the message-only version, which is what the
        # wall has always played.
        if audio_url:
            _stitch_wall_audio_later(
                post.id, audio_url, os.environ.get("BASE_URL", "")
            )
        prune_wall()
    except Exception as e:
        print(f"[wall] could not publish: {e}", flush=True)
        try:
            db.session.rollback()
        except Exception:
            pass


@app.route("/api/smacks-today")
def api_smacks_today():
    """
    How many smacks have gone out today.

    Counts wall_posts, which is the SAME source the wall reads. Previously
    this queried the orders tables directly, so the number beside the hero
    and the cards below it could disagree - and a counter that contradicts
    the thing underneath it is worse than no counter.

    Every smack writes a wall post as it is created, so this is a true count
    of calls placed today.
    """
    from datetime import datetime, timezone as _tz

    try:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            now = datetime.now(_tz.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total = (WallPost.query
                 .filter(WallPost.is_sample == False)  # noqa: E712
                 .filter(WallPost.created_at >= start_of_day)
                 .count())
    except Exception as e:
        print(f"[counter] failed: {e}", flush=True)
        return jsonify({"show": False, "count": 0})

    # Shown as soon as there is anything at all. A real number, however
    # small, is honest; hiding it until some threshold means the first
    # people through never see the site working.
    return jsonify({"show": total > 0, "count": total})


@app.route("/api/ticker")
def api_ticker():
    """
    Games for the homepage ticker, across every league in season.

    Live first, then upcoming, then finals. Uses the same cached board fetch
    as the Smack Board, so a busy homepage is one call to ESPN every 45
    seconds rather than one per visitor.
    """
    from services import espn_scores

    leagues = ["mlb", "wnba", "nfl", "ncaaf", "nba", "ncaab", "nhl"]

    items = []
    for lg in leagues:
        try:
            games = espn_scores.fetch_board(lg)
        except Exception:
            continue                      # league out of season, or ESPN down
        for g in games:
            loser = None
            if g.get("losing") == "home":
                loser = g.get("home")
            elif g.get("losing") == "away":
                loser = g.get("away")

            home, away = g.get("home") or {}, g.get("away") or {}
            items.append({
                "league": lg.upper(),
                "live": bool(g.get("live")),
                "final": bool(g.get("final")),
                "upcoming": bool(g.get("upcoming")),
                "status": g.get("status") or "",
                "away": away.get("nick") or away.get("abbr"),
                "home": home.get("nick") or home.get("abbr"),
                "away_score": away.get("score"),
                "home_score": home.get("score"),
                # Who the link points at. An upcoming game has no loser yet,
                # so it arms against the home side and the arming page lets
                # them switch.
                "target": (loser or {}).get("nick") or home.get("nick"),
                "sport": lg,
                "tag": espn_scores.ticker_tag(g, lg),
            })

    items.sort(key=lambda x: (0 if x["live"] else (1 if x["upcoming"] else 2)))
    # Sixteen rather than twenty-four. At a readable scroll speed the extra
    # eight push the loop past two minutes, and nobody waits that long to see
    # the end of a ticker.
    return jsonify({"count": len(items), "items": items[:16]})


def _digits(phone):
    """Just the digits, so formatting cannot hide a match."""
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def first_name_only(name):
    """
    Keep the first name, drop the rest.

    Every smack opens by addressing the recipient, and the wall publishes
    the smack text - so whatever is typed here ends up on a public page
    about somebody who never agreed to be on one.

    A first name in a sports joke is not identifying. "Mike Sullivan"
    beside a team and the audio of the call is a different thing, and the
    old placeholder asked for exactly that.

    Enforced here as well as in the form, because a placeholder is a
    suggestion and this is the only place it becomes true.
    """
    n = (name or "").strip()
    if not n:
        return n
    # Hyphenated and apostrophed first names survive intact;
    # "Mike Sullivan" becomes "Mike".
    return n.split()[0][:20]


def is_opted_out(phone):
    """
    Has this number asked never to be called?

    Compares on digits only - "+1 (727) 555-0100" and "7275550100" are the
    same person, and a formatting difference letting a call through would
    defeat the whole point.

    Never raises. If the check itself fails, the call is BLOCKED rather than
    allowed: a smack that does not arrive is a refund, a smack that arrives
    after somebody opted out is a complaint.
    """
    d = _digits(phone)
    if not d:
        return False
    try:
        # Last ten digits, so a stored +1 and an entered bare number match.
        tail = d[-10:]
        return db.session.query(
            OptOut.query.filter(OptOut.phone.endswith(tail)).exists()
        ).scalar()
    except Exception as e:
        print(f"[optout] check failed, blocking to be safe: {e}", flush=True)
        return True


@app.route("/api/check-optout")
def api_check_optout():
    """
    Is this number opted out?

    Lets a generator warn while somebody is still typing, rather than at the
    final button after they have filled in everything else. Returns only a
    boolean - it never confirms whether a number exists on the system, only
    whether this specific one has asked to be left alone.
    """
    return jsonify({"opted_out": is_opted_out(request.args.get("phone"))})


# OFF THE SITE, not deleted. See the note on /smack-chat above.
#
# Removed from the homepage during the redesign and never relinked. The 20
# loaded moments, their generated audio and the admin endpoints all still
# work - only the public page is closed.
def _smacky_makes_the_call_disabled():
    """
    Smacky calls the most famous moments in sports history.

    Reads from cached text rather than generating per visit - fifty moments
    would be fifty Claude calls on every page load. Regenerated deliberately
    via the admin endpoint below.
    """
    moments = (FamousMoment.query
               .filter_by(published=True)
               .order_by(FamousMoment.sort_order, FamousMoment.id)
               .all())
    return render_template("smacky_calls.html", moments=moments)


@app.route("/api/admin/call-timings")
def admin_call_timings():
    """
    The last fifty calls with their timing, newest first.

    gap_seconds is the number that matters: dial to the message being able to
    start. On a voicemail everything after the beep in that window is dead
    air at the front of the recording.
    """
    if request.args.get("key") != os.environ.get("CRON_KEY", "smack2026secure99xyz"):
        return jsonify({"error": "nope"}), 403

    rows = (CallTiming.query
            .order_by(CallTiming.id.desc())
            .limit(50).all())

    out = [{
        "when": utc_iso(t.dialed_at),
        "product": "Auto-Smack" if t.record_type == "smackagram" else "Smackagram",
        "answered_by": t.answered_by,
        "status": t.call_status,
        "gap_to_message_s": t.gap_seconds,
        "call_length_s": t.duration_seconds,
        # What actually reached the mailbox, roughly.
        "message_time_s": (round(t.duration_seconds - t.gap_seconds, 1)
                           if (t.duration_seconds and t.gap_seconds) else None),
    } for t in rows]

    machines = [r for r in out if (r["answered_by"] or "").startswith("machine")]
    gaps = [r["gap_to_message_s"] for r in machines if r["gap_to_message_s"]]

    return jsonify({
        "calls": out,
        "voicemail_count": len(machines),
        "avg_gap_on_voicemail_s": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "worst_gap_on_voicemail_s": max(gaps) if gaps else None,
    })


@app.route("/api/admin/seed-moments")
def admin_seed_moments():
    """
    Load data/famous_moments.json into the table.

    Safe to hit repeatedly - existing rows are UPDATED by slug rather than
    duplicated, and any call text already generated is left alone so
    re-seeding to fix a typo in the facts does not wipe fifty calls.
    """
    if request.args.get("key") != os.environ.get("CRON_KEY", "smack2026secure99xyz"):
        return jsonify({"error": "nope"}), 403

    import json
    path = os.path.join(os.path.dirname(__file__), "data", "famous_moments.json")
    try:
        rows = json.load(open(path))
    except Exception as e:
        return jsonify({"error": f"could not read {path}: {e}"}), 500

    added = updated = 0
    for r in rows:
        m = FamousMoment.query.filter_by(slug=r["slug"]).first()
        if not m:
            m = FamousMoment(slug=r["slug"])
            db.session.add(m)
            added += 1
        else:
            updated += 1
        for field in ("title", "sport", "moment_date", "game", "teams",
                      "losing_team", "hero", "goat", "situation", "stakes",
                      "broadcast_style", "sort_order"):
            if field in r:
                setattr(m, field, r[field])
    db.session.commit()
    return jsonify({"added": added, "updated": updated, "total": len(rows)})


@app.route("/api/admin/generate-call/<slug>")
def admin_generate_call(slug):
    """
    Write (or rewrite) one moment's call. Admin only.

    One at a time on purpose - fifty in a loop would take several minutes and
    time out, and you want to hear the first one before spending fifty calls
    finding out the prompt is wrong.
    """
    if request.args.get("key") != os.environ.get("CRON_KEY", "smack2026secure99xyz"):
        return jsonify({"error": "nope"}), 403

    from services import moment_service

    m = FamousMoment.query.filter_by(slug=slug).first()
    if not m:
        return jsonify({"error": f"no moment with slug {slug}"}), 404

    try:
        call, followup, roast = moment_service.generate_call(m)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    m.call_text = call
    m.followup_text = followup
    m.roast_text = roast
    m.generated_at = datetime.now(timezone.utc)
    db.session.commit()

    # Audio unless told otherwise. ?audio=0 writes the text only, which is
    # what you want while the prompt is still being tuned - no sense paying
    # for a voice on a call you are about to throw away.
    audio_url = None
    audio_error = None
    if request.args.get("audio") != "0":
        try:
            audio_url = moment_service.generate_audio(m)
            m.audio_url = audio_url
            db.session.commit()
        except Exception as e:
            # The text is already saved and is the valuable part, so a voice
            # failure is reported rather than thrown - losing a good call
            # because S3 hiccuped would be daft.
            audio_error = str(e)
            print(f"[calls] audio failed for {m.slug}: {e}", flush=True)

    return jsonify({
        "slug": m.slug,
        "title": m.title,
        "call": call,
        "followup": followup,
        "roast": roast,
        "audio_url": audio_url,
        "audio_error": audio_error,
    })


@app.route("/api/admin/voice-call/<slug>")
def admin_voice_call(slug):
    """
    Audio only, for a call whose text is already written and good.

    Separate from generation so a call you are happy with can be voiced
    without rewriting it - and re-voiced if the first take is off.
    """
    if request.args.get("key") != os.environ.get("CRON_KEY", "smack2026secure99xyz"):
        return jsonify({"error": "nope"}), 403

    from services import moment_service

    m = FamousMoment.query.filter_by(slug=slug).first()
    if not m:
        return jsonify({"error": f"no moment with slug {slug}"}), 404

    try:
        m.audio_url = moment_service.generate_audio(m)
        db.session.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"slug": m.slug, "audio_url": m.audio_url})


@app.route("/opt-out", methods=["GET", "POST"])
def opt_out_page():
    """
    Stop the calls.

    No account required, deliberately. The person opting out is the
    recipient, who has no reason to have one - asking them to register in
    order to be left alone would be the same as having no opt-out at all.
    """
    done = False
    error = None
    number = ""

    if request.method == "POST":
        number = (request.form.get("phone") or "").strip()
        d = _digits(number)
        if len(d) < 10:
            error = "That does not look like a full phone number. Include the area code."
        else:
            try:
                tail = d[-10:]
                existing = OptOut.query.filter(OptOut.phone.endswith(tail)).first()
                if not existing:
                    db.session.add(OptOut(
                        phone=tail,
                        reason=(request.form.get("reason") or "").strip()[:200] or None,
                        source="web",
                    ))
                    db.session.commit()
                done = True
            except Exception as e:
                print(f"[optout] save failed: {e}", flush=True)
                try:
                    db.session.rollback()
                except Exception:
                    pass
                error = "Something went wrong saving that. Try again, or contact us and we will do it by hand."

    return render_template("opt_out.html", done=done, error=error, number=number)


@app.route("/api/wall")
def api_wall():
    """
    Smacks of the Week. Real approved posts first, topped up with samples
    while there are not yet enough of them.
    """
    import random

    rows = (WallPost.query
            .filter_by(approved=True, is_sample=False)
            .order_by(WallPost.id.desc())
            .limit(WALL_KEEP).all())

    items = [{
        "handle": r.handle,
        "product": r.product,
        "headline": r.headline,
        # team_name, not team. The key was set twice here and the second one
        # won, so every real post resolved to an empty team and rendered as
        # "SENT TO A MYSTERY FAN".
        #
        # The colour is the team's real brand colour, lightened where it
        # would vanish against a dark card - several are close to black.
        # Stripped on the way out too, so posts written before this change
        # still render as "Yankees" rather than "New York Yankees".
        "team": _nickname_only(r.team_name),
        "team_color": chat_team_colors.readable_color_for_name(r.team_name),
        "when": wall_when(r.created_at),
        # Only ever served when the sender explicitly agreed. A post without
        # consent still appears - it reads rather than plays.
        # Smacky's generated line, not a recording of the call - nobody
        # else's voice is in the file, so there is no consent to gather.
        "audio_url": r.audio_url,
        "sample": False,
    } for r in rows]

    if len(items) < 12:
        pool = list(WALL_SAMPLES)
        random.shuffle(pool)
        for handle, product, team in pool[: 12 - len(items)]:
            items.append({
                "handle": handle, "product": product,
                "team": team,
                "team_color": chat_team_colors.readable_color_for_name(team),
                # Examples carry no audio - there is no call behind them. The
                # card shows the line and says so rather than faking a player.
                "audio_url": None, "when": "Today", "sample": True,
            })

    return jsonify({"count": len(items), "items": items})


_DAMAGE_CACHE = {}   # league -> (fetched_at, finals) - see the note inside


@app.route("/api/board/<league>")
def api_board(league):
    """
    One league's games. Cached server-side for 45 seconds, so a room full of
    people watching the board is still one request to ESPN.
    """
    from services import espn_scores

    lg = (league or "").lower()
    if lg not in espn_scores.LEAGUE_PATHS:
        return jsonify({"error": "unknown league", "games": []}), 404

    games = espn_scores.fetch_board(lg)

    # How many armed calls each team is carrying today.
    #
    # Only Auto-Smack records a team - a plain send-a-smack order does
    # not store one - so this counts armed calls rather than all smacks.
    # Counted by TEAM rather than game id because the two services do not
    # share ids, and the team is what actually resolves.
    counts = {}
    try:
        from sqlalchemy import func
        rows = (db.session.query(Smackagram.target_team, func.count(Smackagram.id))
                .filter(Smackagram.status == "armed")
                .group_by(Smackagram.target_team).all())
        counts = {(t or "").lower(): n for t, n in rows}
    except Exception as e:
        print(f"[board] smack counts unavailable: {e}", flush=True)

    for g in games:
        for side in ("home", "away"):
            nick = (g[side].get("nick") or "").lower()
            g[side]["smacks"] = counts.get(nick, 0)

    # Smacky's line on each card. Dealt across the whole response so no two
    # visible cards carry the same one - twelve drawing independently from
    # one pool repeats obviously on a grid.
    for g, quip in zip(games, espn_scores.board_quips(games, lg)):
        g["quip"] = quip

    # Which half of the sport each game belongs to, so the board can group
    # them. Taken from the HOME side; an inter-league game is listed under
    # the host, which is how a schedule reads anyway.
    #
    # None for college and anything unmapped - those stay ungrouped rather
    # than getting a heading invented for them.
    for g in games:
        g["conference"] = chat_team_colors.conference_for_abbr(
            lg, (g.get("home") or {}).get("abbr"))

    # LAST NIGHT'S DAMAGE (Andy, Aug 7): after the midnight-ET flip the
    # board showed only the new slate, and yesterday's losers - the
    # smackable ones - vanished at 9pm Pacific, mid-ribbing-window. The
    # finals now stay served until 3PM EASTERN (noon Pacific: everyone's
    # morning survives; by then the evening slate wants the screen).
    # CACHED HARD (Aug 7, the board-hang fix): the first version called
    # Highlightly live inside EVERY board request - and the board page
    # fans out to every league tab on load, so each click paid a fresh
    # external roundtrip. Yesterday's finals never change; ten minutes
    # of cache makes the damage section cost one lookup per league per
    # ten minutes instead of one per click.
    damage = []
    try:
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        import time as _time
        _now_et = _dt.now(_tz.utc) - _td(hours=4)
        if _now_et.hour < 15:
            _c = _DAMAGE_CACHE.get(lg)
            if _c and (_time.time() - _c[0]) < 600:
                damage = _c[1]
            else:
                from services import highlightly as _hl
                if _hl.enabled():
                    _yday = (_now_et - _td(days=1)).strftime("%Y-%m-%d")
                    damage = [g for g in (_hl.board(lg, _yday) or [])
                              if g.get("final")]
                if not damage:
                    # EVERY LEAGUE (Andy, Aug 7): Highlightly has no
                    # WNBA and can gap elsewhere - fall back to the
                    # SHOW'S finals path (it fed this morning's
                    # episode), adapted into card shape.
                    try:
                        from services import espn_scores as _es
                        for _g in (_es.fetch_finals(lg, days_back=1)
                                   or []):
                            damage.append({
                                "final": True, "live": False,
                                "upcoming": False, "losing": "away",
                                "home": {"nick": _g.get("winner"),
                                         "score": _g.get("winner_score")},
                                "away": {"nick": _g.get("loser"),
                                         "score": _g.get("loser_score")},
                            })
                    except Exception as _fe:
                        print(f"[board] damage fallback failed "
                              f"{lg}: {_fe}", flush=True)
                _DAMAGE_CACHE[lg] = (_time.time(), damage)
    except Exception as _e:
        print(f"[board] damage fetch failed for {lg}: {_e}", flush=True)
        _DAMAGE_CACHE[lg] = (__import__("time").time(), [])

    return jsonify({
        "league": lg.upper(),
        "count": len(games),
        "live": sum(1 for g in games if g.get("live")),
        "damage": damage,
        "damage": damage,
        "games": games,
    })


@app.route("/api/battles/live")
def battles_live():
    """
    Public battles worth watching. Falls back to recently finished ones when
    nothing is running - an empty "live now" panel reads as a dead site.
    """
    now = datetime.utcnow()
    stale = now - timedelta(minutes=30)

    live = (Battle.query
            .filter(Battle.is_public.is_(True),
                    Battle.status == "active",
                    Battle.created_at >= stale)
            .order_by(Battle.created_at.desc())
            .limit(8).all())

    recent = []
    if len(live) < 4:
        recent = (Battle.query
                  .filter(Battle.is_public.is_(True),
                          Battle.status == "complete")
                  .order_by(Battle.created_at.desc())
                  .limit(6 - len(live)).all())

    viewer_cutoff = now - timedelta(seconds=20)

    def row(b, is_live):
        wins_a = BattleRoundResult.query.filter_by(battle_id=b.id, winner="a").count()
        wins_b = BattleRoundResult.query.filter_by(battle_id=b.id, winner="b").count()
        viewers = BattleViewer.query.filter(
            BattleViewer.battle_id == b.id,
            BattleViewer.last_seen >= viewer_cutoff).count() if is_live else 0
        return {
            "challenge_code": b.challenge_code,
            "name_a": b.display_name_a, "team_a": b.team_a,
            "name_b": b.display_name_b or "waiting", "team_b": b.team_b,
            "round": b.round_number, "max_rounds": b.max_rounds,
            "wins_a": wins_a, "wins_b": wins_b,
            "viewers": viewers, "live": is_live, "league": b.league,
        }

    return jsonify({
        "live": [row(b, True) for b in live],
        "replays": [row(b, False) for b in recent],
    })


@app.route("/api/battles/<challenge_code>/angles", methods=["POST"])
def battle_angles(challenge_code):
    """
    Three angles for whoever is stuck. Participants only - a spectator has
    nothing to write, and this costs a model call.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found."}), 404

    side = (request.json or {}).get("side")
    if side not in ("a", "b"):
        return jsonify({"error": "Not in this battle."}), 403

    mine = battle.team_a if side == "a" else battle.team_b
    theirs = battle.team_b if side == "a" else battle.team_a

    used = [ln.message for ln in BattleLine.query.filter_by(
        battle_id=battle.id, side=side).order_by(BattleLine.created_at.asc()).all()]

    angles = trash_talk_service.generate_battle_angles(
        their_team=theirs or "", my_team=mine or "",
        already_said=used, intensity=battle.intensity)

    if not angles:
        return jsonify({"error": "Nothing came to me. Try again."}), 503
    return jsonify({"angles": angles})


@app.route("/api/battles/<challenge_code>/react", methods=["POST"])
def battle_react(challenge_code):
    """
    Fire or ice on one line. Open to spectators, no account needed.
    Judged rounds only - reacting before Smacky rules would let a pile-on
    land before the verdict.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found."}), 404

    data = request.json or {}
    line_id = data.get("line_id")
    reaction = (data.get("reaction") or "").lower()
    reactor_id = (data.get("reactor_id") or "").strip()[:64]

    if reaction not in ("fire", "ice"):
        return jsonify({"error": "Unknown reaction."}), 400
    if not reactor_id:
        return jsonify({"error": "Missing reactor id."}), 400

    line = BattleLine.query.filter_by(id=line_id, battle_id=battle.id).first()
    if not line:
        return jsonify({"error": "Line not found."}), 404

    judged = BattleRoundResult.query.filter_by(
        battle_id=battle.id, round_number=line.round_number).first()
    if not judged:
        return jsonify({"error": "That round has not been scored yet."}), 400

    existing = BattleLineReaction.query.filter_by(
        line_id=line.id, reactor_id=reactor_id).first()
    if existing:
        if existing.reaction == reaction:
            db.session.delete(existing)
        else:
            existing.reaction = reaction
    else:
        db.session.add(BattleLineReaction(
            line_id=line.id, battle_id=battle.id,
            reactor_id=reactor_id, reaction=reaction))
    db.session.commit()

    return jsonify(_battle_state_json(battle))


@app.route("/api/battles/<challenge_code>/viewer-ping", methods=["POST"])
def battle_viewer_ping(challenge_code):
    """
    Heartbeat ping for the live viewer count - called periodically by
    anyone with the battle page open, participant or spectator alike
    (no login required, matching the battle page itself and the state-
    polling endpoint, both open to anonymous spectators). Upserts
    rather than inserting fresh each time, so repeat pings from the
    same browser just refresh last_seen instead of piling up rows.

    Optionally also carries which side (a/b) this browser is - when
    present, updates Battle.last_seen_a/b too, which is what powers the
    "your opponent left" notification (see _battle_state_json). A
    spectator's ping has no side and only affects the generic viewer
    count, not presence detection.
    """
    battle = Battle.query.filter_by(challenge_code=challenge_code).first()
    if not battle:
        return jsonify({"error": "Battle not found"}), 404

    data = request.json
    viewer_id = (data.get("viewer_id") or "").strip()[:64]
    side = data.get("side")
    if not viewer_id:
        return jsonify({"error": "Missing viewer identifier"}), 400

    if side == "a":
        battle.last_seen_a = datetime.utcnow()
    elif side == "b":
        battle.last_seen_b = datetime.utcnow()

    existing = BattleViewer.query.filter_by(battle_id=battle.id, viewer_id=viewer_id).first()
    if existing:
        existing.last_seen = datetime.utcnow()
    else:
        db.session.add(BattleViewer(battle_id=battle.id, viewer_id=viewer_id, last_seen=datetime.utcnow()))
    db.session.commit()
    return jsonify({"ok": True})


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
            intensity=battle.intensity,
            max_rounds=battle.max_rounds,
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

    # Enumeration guard. Message CONTENT is already safe behind
    # VerifiedPhone, but the unverified path still answers "yes, this
    # number has 3 smacks waiting" - so an unthrottled endpoint lets
    # somebody walk a list of numbers and learn who has been smacked and
    # how often. That is a real (if modest) privacy leak, and it gets
    # worse the moment this page becomes a marketing destination. Own
    # bucket, not the voice-preview one.
    identifier = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    identifier = identifier.split(",")[0].strip()
    if rate_limiter.is_limited("inbox", identifier, rate_limiter.MAX_INBOX_LOOKUPS_PER_HOUR):
        return jsonify({
            "error": "That's a lot of lookups. Give it a few minutes and try again."
        }), 429
    rate_limiter.record("inbox", identifier)

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
        # NEUTRAL (handoff 4c-b): the no-match answer is IDENTICAL to
        # the unverified-match answer, so this form cannot be used to
        # discover who got smacked. Verification is where truth lives:
        # a verified no-match user simply sees an empty locker.
        return jsonify({"found": True, "verified": False})

    all_matches.sort(key=lambda r: r.created_at, reverse=True)

    user = get_current_user()
    # WHILE VERIFICATION IS OFF, the number itself is the key.
    # David's call, Aug 6 2026 - Twilio cannot text codes until A2P
    # clears, and a recipient hitting "found: 3 smacks" followed by a
    # code button that cannot work is a dead end at the exact moment
    # of highest interest. Flip smackback_requires_verification in the
    # admin panel and this line stops mattering.
    from services import settings_service as _ss
    is_verified = not _ss.get_bool("smackback_requires_verification")
    if user:
        is_verified = VerifiedPhone.query.filter_by(user_id=user.id, phone_digits=digits[-10:]).first() is not None

    if not is_verified:
        # Teaser only - enough for the frontend to show something
        # enticing is there, without exposing any actual content.
        return jsonify({"found": True, "verified": False})

    items = []
    for record in all_matches:
        record_type = "order" if isinstance(record, Order) else "smackagram"
        preview = (record.custom_message or "")[:90]
        item = {
            "type": record_type,
            "id": record.id,
            "preview": preview,
            "created_at": utc_iso(record.created_at),
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

# PHASE 2 OF THE HANDOFF - three fixes in one block:
    # DB GATE: an OTP goes out ONLY if this number actually received
    # a smack (recipient_phone on either table). Without this the
    # form is an open "text any number on earth" endpoint - the
    # primary fraud control. NEUTRAL: match or not, the response is
    # identical, so the form cannot be used to discover who got
    # smacked. VERIFY: Twilio Verify sends the code (registered pool,
    # Fraud Guard, no A2P dependency) - no homegrown codes, no raw
    # send_sms to user-typed numbers, ever. channel="voice" reads
    # the code aloud for landline/VoIP recipients.
    _last10 = phone_digits[-10:]
    _match = (Order.query.filter(
                  Order.recipient_phone.like(f"%{_last10}")).first()
              or Smackagram.query.filter(
                  Smackagram.recipient_phone.like(f"%{_last10}")).first())
    _channel = "voice" if (data.get("channel") == "voice") else "sms"
    if _match:
        try:
            from services import verify_service
            verify_service.start_verification(raw_phone, channel=_channel)
        except Exception as e:
            print(f"[verify-phone] verify send failed: {e}", flush=True)
    else:
        print(f"[verify-phone] no smack on record for that number - "
              f"neutral response, nothing sent", flush=True)
    # the row doubles as the rate-limit log either way
    db.session.add(PhoneVerificationCode(
        user_id=user.id, phone_digits=phone_digits,
        code="VERIFY",
        expires_at=datetime.utcnow() + timedelta(minutes=10)))
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
    # Verify owns the answer now; the stored row is only the rate log.
    from services import verify_service
    try:
        # SAME NUMBER AS THE SEND (Andy's live test, first try): the
        # first version hand-built "+" + last-10-digits, which is not
        # the E.164 the send used - Verify saw a different phone,
        # found no pending verification, and refused a correct code.
        # The service normalizes internally; hand it the raw phone.
        _ok = verify_service.check_verification(raw_phone, code)
    except Exception as _e:
        print(f"[verify-phone] check errored: {_e}", flush=True)
        _ok = False
    if not _ok:
        return jsonify({"error": "That code doesn't match — double-check it and try again."}), 400

    already_verified = VerifiedPhone.query.filter_by(user_id=user.id, phone_digits=phone_digits).first()
    if not already_verified:
        db.session.add(VerifiedPhone(user_id=user.id, phone_digits=phone_digits))
    db.session.commit()

    return jsonify({"ok": True})


def _find_by_reply_token(token):
    """Shared lookup — checks both Order and Smackagram, same record_id space pattern used elsewhere."""
    return Order.query.filter_by(reply_token=token).first() or Smackagram.query.filter_by(reply_token=token).first()


@app.route("/api/revenge/comp-status")
def api_revenge_comp_status():
    """
    Whether this visitor can claim their one free smack back. Deliberately
    NOT login_required - the page is reachable logged-out, and the front
    end needs to know to show "verify to claim your free one" rather than
    nothing at all. Returns a reason code, never an error, for a logged-out
    caller.
    """
    return jsonify(revenge_service.comp_status(get_current_user()))


@app.route("/api/revenge/claim-comp", methods=["POST"])
@login_required
def api_revenge_claim_comp():
    """
    Grants the comped smack as wallet credit. Eligibility is re-checked
    server-side inside claim_comp - the browser's copy of the status is
    never trusted, since it is both stale-able and forgeable.
    """
    result = revenge_service.claim_comp(get_current_user())
    if not result.get("granted"):
        return jsonify(result), 400
    app.logger.info("[revenge] comped smack granted to user %s", getattr(get_current_user(), "id", "?"))
    return jsonify(result)


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

    # OPT-OUT, CHECKED ON THE SERVER.
    #
    # The page asks /api/check-optout before letting somebody send. That
    # is a courtesy to the sender, not a control - a direct POST skips it
    # entirely, and so does any future path that forgets to call it.
    #
    # An opt-out that only the front end honours is not an opt-out.
    if is_opted_out(data.get("recipient_phone")):
        print("[optout] refused - recipient has opted out", flush=True)
        return jsonify({
            "error": ("This number has asked not to receive Smackagrams. "
                      "We cannot send to it."),
        }), 403

    custom_message = data.get("custom_message", "")
    safety = content_moderation.check_message_safety(custom_message)
    if not safety["safe"]:
        print(f"[safety] blocked reply order attempt — reason: {safety['reason']}")
        return jsonify({
            "error": _moderation_error_text(safety),
            "reason": safety["reason"],
        }), 400

    price = 200 if data.get("include_recording", True) else 100
    order = Order(
        # A reply can come from someone with no account, so user_id stays
        # null here - but it's still shareable.
        share_token=secrets.token_urlsafe(16),
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


@app.route("/auto-smack/success")
def locked_n_loaded_success():
    session_id = request.args.get("session_id")
    return render_template("auto_smack_success.html", session_id=session_id)


@app.route("/api/games/upcoming")
def upcoming_games():
    """Powers the game picker — only games within 48h. ?sport=nfl|nba|mlb|nhl|ncaaf&team=yankees"""
    sport = request.args.get("sport", "nfl").lower().strip()
    # Same allowlist as arming - the picker must not show games the
    # resolver cannot settle, or the form sells promises it cannot keep.
    from services.sports_service import AUTO_SMACK_SPORTS
    if sport not in AUTO_SMACK_SPORTS:
        return jsonify({"games": [], "error":
                        "That league is not covered by Auto-Smack yet"}), 400
    team_query = request.args.get("team", "").strip() or None
    resp = jsonify(sports_service.get_upcoming_games(sport=sport, hours_ahead=48, team_query=team_query))
    # Explicitly forbid caching — this powers live scores, and a cached
    # response (even briefly) would show a stale score during a live game,
    # since the browser might otherwise reuse an identical prior request
    # instead of hitting the server again on every auto-refresh.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


def _validated_sport(sport):
    """
    Refuse to arm what the resolvers cannot resolve.
    The old line read sport=data.get("sport", "nfl") - client-supplied,
    unvalidated, silently defaulting to NFL. A league outside the
    covered set (or a typo'd one) produced an order that could NEVER
    fire: armed forever, no call, no error, no refund. ValueError here
    rides the existing refusal machinery, so the wallet is re-credited
    and the customer sees a real sentence instead of silence.
    """
    from services.sports_service import AUTO_SMACK_SPORTS
    s = (sport or "").lower().strip()
    if s not in AUTO_SMACK_SPORTS:
        raise ValueError(
            f"Auto-Smack does not cover that league yet"
            + (f" ('{s}')" if s else "")
            + " - supported: " + ", ".join(sorted(AUTO_SMACK_SPORTS)))
    return s


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
    # Refuse before the wallet is touched - same reasoning as Send a Smack.
    if is_opted_out(data.get("recipient_phone")):
        raise ValueError(
            "That number has asked not to receive Smackagrams. "
            "We cannot arm one against it.")

    # A game in progress is still armable, and deliberately so - the whole
    # premise is that the call fires when the target loses, and a game that
    # has kicked off has not been lost yet. Arming at 2-0 down in the third
    # is arguably the best moment to do it.
    #
    # The old check refused anything past its start time, which blocked every
    # live game. The scheduler resolves on the RESULT, not on the clock, so
    # nothing downstream needs a game to be unstarted: if the target wins, the
    # hold is released and the money comes back.
    game_start = datetime.fromisoformat(data["game_start_time"])

    # auto_summary is the only supported mode. A pre-written line can't
    # reference a result that hasn't happened yet, which is the entire point
    # of Auto-Smack - so "custom" is refused rather than silently
    # accepted from a stale client.
    mode = data.get("mode") or "auto_summary"
    if mode != "auto_summary":
        mode = "auto_summary"

    smackagram = Smackagram(
        share_token=secrets.token_urlsafe(16),
        user_id=user.id,
        game_id=data["game_id"],
        sport=_validated_sport(data.get("sport")),
        home_team=data["home_team"],
        away_team=data["away_team"],
        target_team=data["target_team"],
        game_start_time=game_start,
        mode=mode,
        sensitivity=data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY),
        custom_message=data.get("custom_message") if mode == "custom" else None,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=first_name_only(data["recipient_name"]),
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
        price_cents=wallet_service.LOCKED_N_LOADED_COST_CENTS,
    )
    db.session.add(smackagram)
    db.session.commit()

    return {"smackagram_id": smackagram.id, "redirect": "/auto-smack/success"}


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

    # OPT-OUT, CHECKED ON THE SERVER.
    #
    # The page asks /api/check-optout before letting somebody send. That
    # is a courtesy to the sender, not a control - a direct POST skips it
    # entirely, and so does any future path that forgets to call it.
    #
    # An opt-out that only the front end honours is not an opt-out.
    if is_opted_out(data.get("recipient_phone")):
        print("[optout] refused - recipient has opted out", flush=True)
        return jsonify({
            "error": ("This number has asked not to receive Smackagrams. "
                      "We cannot send to it."),
        }), 403

    # auto_summary is the only supported mode. A pre-written line can't
    # reference a result that hasn't happened yet, which is the entire point
    # of Auto-Smack - so "custom" is refused rather than silently
    # accepted from a stale client.
    mode = data.get("mode") or "auto_summary"
    if mode != "auto_summary":
        mode = "auto_summary"
    if mode not in ("custom", "auto_summary"):
        return jsonify({"error": "Invalid mode"}), 400

    if mode == "custom" and not data.get("custom_message", "").strip():
        return jsonify({"error": "Custom message can't be empty"}), 400

    if mode == "custom":
        safety = content_moderation.check_message_safety(data.get("custom_message", ""))
        if not safety["safe"]:
            print(f"[safety] blocked smackagram arm attempt — reason: {safety['reason']}")
            return jsonify({
            "error": _moderation_error_text(safety),
            "reason": safety["reason"],
        }), 400

    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)
    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    if not wallet_service.has_sufficient_balance(user, wallet_service.LOCKED_N_LOADED_COST_CENTS):
        redirect = _store_pending_action(user, "locked_n_loaded", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    txn = wallet_service.debit_wallet(
        user, wallet_service.LOCKED_N_LOADED_COST_CENTS, "locked_n_loaded",
        description=f"Auto-Smack - {data.get('target_team', 'target')} armed",
    )
    if txn is None:
        redirect = _store_pending_action(user, "locked_n_loaded", data)
        return jsonify({"error": "insufficient_balance", "redirect": redirect}), 402

    try:
        result = _execute_arm_smackagram(user, data)
    except ValueError as e:
        # These are the deliberate refusals - "this game has already
        # started", and so on. They were escaping as 500s, so the browser
        # could not read the message and fell back to "something went wrong",
        # which tells somebody nothing about a situation they could fix.
        #
        # The wallet was debited above, so put it back before returning.
        try:
            wallet_service.credit_wallet(
                user, wallet_service.LOCKED_N_LOADED_COST_CENTS,
                "locked_n_loaded_refund",
                description="Arming refused - " + str(e)[:80],
            )
            db.session.commit()
        except Exception as refund_err:
            print(f"[arm] refund after refusal failed: {refund_err}", flush=True)
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


# ---------- Twilio status callbacks ----------

def _refund_undeliverable(record, record_type, status):
    """
    Put the credit back when a call could not be delivered.

    IDEMPOTENT. Twilio retries webhooks, and a retry that refunds a second
    time is money walking out of the door. The flag on the record is what
    stops that, checked before anything is credited.

    Never raises - a refund failing should not break the webhook, because
    a webhook that errors gets retried, and a retry loop on a payment path
    is worse than a missed refund somebody can chase.
    """
    try:
        if getattr(record, "refunded", False):
            return
        user_id = getattr(record, "user_id", None)
        if not user_id:
            # A guest checkout has no wallet to credit. Flag it loudly -
            # somebody has to refund this by hand, and silence here is a
            # complaint waiting to happen.
            from services import alerts
            alerts.record("delivery", "guest_refund_owed",
                          f"{record_type} {record.id} was {status} - guest "
                          f"checkout, needs a manual refund",
                          severity="critical")
            return

        from models import User
        user = User.query.get(user_id)
        if not user:
            return

        cents = getattr(record, "price_cents", None) or 100
        wallet_service.credit_wallet(
            user, cents, "undeliverable_refund",
            description=(f"Refund - call could not be delivered ({status})"))

        record.refunded = True
        db.session.commit()
        print(f"[refund] {record_type} {record.id} was {status} - "
              f"{cents}c returned to {user.email}", flush=True)

        from services import alerts
        alerts.record("delivery", "undeliverable",
                      f"{record_type} {record.id}: {status}, refunded",
                      severity="error")
    except Exception as e:
        db.session.rollback()
        print(f"[refund] could not refund {record_type} {record.id}: {e}",
              flush=True)
        try:
            from services import alerts
            alerts.record("delivery", "refund_failed",
                          f"{record_type} {record.id}: {e}",
                          severity="critical")
        except Exception:
            pass


@app.route("/call-status/<record_type>/<int:record_id>", methods=["POST"])
@_twilio_signed
def call_status(record_type, record_id):
    # PROVE IT CAME FROM TWILIO.
    #
    # This endpoint now triggers a REFUND on a failed call. Without
    # verification, anybody could send a smack, receive it, then post
    # "failed" here and get their dollar back - free smacks for the cost
    # of an email address.
    #
    # Twilio signs the full URL and every parameter, so a signature
    # cannot be replayed against a different order id.
    from services import twilio_auth
    if not twilio_auth.is_from_twilio(request):
        print(f"[twilio] REJECTED an unsigned call-status for "
              f"{record_type}:{record_id}", flush=True)
        try:
            from services import alerts
            alerts.record("twilio", "forged_webhook",
                          f"unsigned call-status for {record_type} "
                          f"{record_id}", severity="critical")
        except Exception:
            pass
        return "", 403

    """
    Twilio's real call-completion webhook — registered at call-creation
    time in place_prank_call(). Namespaced by record_type so this never
    has to guess which table an id belongs to.
    """
    status = request.form.get("CallStatus")
    record = _resolve_record(record_type, record_id)
    if record:
        record.call_status = status
        db.session.commit()

        # REFUND AN UNDELIVERABLE CALL.
        #
        # This webhook recorded the failure and did nothing else. Somebody
        # paid a dollar, the call did not reach anybody, and they kept
        # neither the money nor the smack.
        #
        # The terms promise a credit for anything undeliverable, so this
        # is not generosity - it is the thing already agreed to, happening
        # without anybody having to ask for it.
        #
        # "completed" is not in this list on purpose. A call that reached
        # a voicemail IS delivered - that is the product working.
        if status in ("failed", "busy", "no-answer", "canceled"):
            _refund_undeliverable(record, record_type, status)

    # Duration closes the picture: with gap_seconds you can see how much of
    # the call was AMD deliberating versus the message actually playing, and
    # a voicemail that stops at a suspiciously round number - 30s, 60s - is
    # the mailbox's own limit rather than anything on our side.
    try:
        sid = request.form.get('CallSid')
        if sid:
            t = CallTiming.query.filter_by(call_sid=sid).first()
            if t:
                t.call_status = status
                dur = request.form.get('CallDuration')
                if dur and str(dur).isdigit():
                    t.duration_seconds = int(dur)
                db.session.commit()
                print(f'[timing] {record_type}:{record_id} status={status} '
                      f'duration={t.duration_seconds}s gap={t.gap_seconds}s', flush=True)
    except Exception as e:
        print(f'[timing] could not record duration: {e}', flush=True)
    return "", 204



@app.route("/recording-ready/<record_type>/<int:record_id>", methods=["POST"])
@_twilio_signed
def recording_ready(record_type, record_id):
    # Verified for the same reason as call-status: these are Twilio's
    # endpoints and nobody else's. An unsigned request here could replay
    # a recording URL or make a call read back somebody else's audio.
    from services import twilio_auth
    if not twilio_auth.is_from_twilio(request):
        print(f"[twilio] REJECTED an unsigned recording-ready", flush=True)
        return "", 403

    """Namespaced by record_type so this never has to guess which table an id belongs to."""
    recording_url = request.form.get("RecordingUrl")
    target = _resolve_record(record_type, record_id)
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
    # The scheduler's key, or an admin already logged in - see
    # cron_authorised(). Prompting a logged-in admin for a production
    # credential protects nothing and teaches a bad habit.
    if not cron_authorised():
        return jsonify({"error": "unauthorized"}), 401

    # GUARDED, SO A CRASH DOES NOT STOP THE CRON.
    #
    # This ran bare. An exception became a 500, cron-job.org logged a
    # failure nobody reads, and the next run two minutes later hit the
    # same thing. Delivery would stop and the only sign would be smacks
    # not arriving.
    try:
        check_armed_smackagrams()
    except Exception as e:
        import traceback
        print(f"[cron] check_armed_smackagrams FAILED\n{traceback.format_exc()}",
              flush=True)
        try:
            from services import alerts
            # Critical: nothing is being delivered while this is broken.
            alerts.record("delivery", "cron_failed", str(e)[:200],
                          severity="critical")
        except Exception:
            pass

    # Scheduled sends ride the SAME three-minute cron rather than needing a
    # second job to set up and forget about. Three minutes is close enough
    # for "eight o'clock on his birthday".
    #
    # Wrapped separately so a failure here cannot stop the armed check -
    # that one is holding real money.
    scheduled = {}
    try:
        from scheduler import send_scheduled_smackagrams
        scheduled = send_scheduled_smackagrams()
    except Exception as e:
        print(f"[cron] scheduled sends failed: {e}", flush=True)

    # SHADOW COMPARISON, at most once an hour.
    #
    # Runs here rather than inside the armed-smackagram loop, because that
    # loop needs an ESPN event id first - so during an ESPN outage it
    # produced no comparison at all, which is exactly when the evidence
    # matters most.
    #
    # Rate-limited to once an hour by a module-level timestamp: this cron
    # fires every two minutes and there is no sense comparing last night's
    # finished games thirty times an hour.
    try:
        from services import highlightly
        if highlightly.enabled():
            import time as _t
            global _LAST_SHADOW
            if _t.time() - _LAST_SHADOW > 3600:
                _LAST_SHADOW = _t.time()
                from scheduler import shadow_compare_sources
                shadow_compare_sources()
    except Exception as e:
        print(f"[shadow] hourly compare failed: {e}", flush=True)

    return jsonify({"ok": True, "scheduled": scheduled})


# Published sample recaps shown on the product page. Empty until real ones
# are cut from /smackcast/test - see smackcast_page().
# Shape: {"league_name", "sport", "week", "best_line", "audio_url"}
SMACKCAST_SAMPLES = []


@app.route("/smackcast")
def smackcast_page():
    """
    Public - this is the product page, so requiring a login to read the
    pricing would be self-defeating. It carried @login_required only
    because it used to be the league-connection form. Checkout itself
    still requires an account; the page handles that by bouncing to login
    and returning to #pricing.

    The product page. Used to be the league-connection form, which meant
    someone had to connect a fantasy league before ever seeing a price -
    that flow now lives at /smackcast/connect and happens after checkout.

    SMACKCAST_SAMPLES is deliberately empty until real sample recaps are
    published. The page hides the whole "hear it" section rather than
    showing a dead player, and filling this list is the only change needed
    to turn it on. Generate them at /smackcast/test, then paste the
    resulting audio URL, best line, league name, sport and week here.
    """
    # A subscriber gets their own links rather than being sold something they
    # already own. Looked up here so the page can be both the shopfront and
    # the front door.
    _u = get_current_user()
    _sub = None
    if _u:
        _sub = (SmackcastSubscription.query
                .filter_by(user_id=_u.id)
                .order_by(SmackcastSubscription.id.desc())
                .first())

    return render_template(
        "smackcast_product.html",
        has_smackcast=_sub is not None,
        smackcast_league=(_sub.league_name if _sub else None),
        samples=SMACKCAST_SAMPLES,
        smacky_image_exists=os.path.exists(os.path.join(app.root_path, "static", "img", "smacky-hero.png")),
        hero_image_exists=os.path.exists(os.path.join(app.root_path, "static", "img", "smackcast-hero.png")),
    )


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
    """
    Kicks off a test generation and returns a job id immediately. The page
    then polls /test-status/<job_id>. Previously this ran the whole pipeline
    inline, which blocked the site's only worker for minutes.
    """
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    data = request.json or {}
    sport = (data.get("sport") or "nfl").strip()
    league_name = (data.get("league_name") or "Test League").strip()
    team_count = int(data.get("team_count") or 10)
    week = int(data.get("week") or 1)
    # Stress mode replaces every team name with a deliberately awkward one,
    # for testing the read-aloud handling rather than a realistic league.
    stress = bool(data.get("stress"))
    save_to_library = bool(data.get("save_to_library"))

    if sport not in ("nfl", "nba", "mlb"):
        return jsonify({"error": "Unsupported sport."}), 400
    if team_count < 4 or team_count > 20:
        return jsonify({"error": "Team count must be between 4 and 20."}), 400

    job_id = secrets.token_urlsafe(12)
    _smackcast_test_jobs[job_id] = {"status": "generating"}
    threading.Thread(
        target=_run_smackcast_test_async,
        args=(job_id, sport, league_name, team_count, week, stress, save_to_library, user.id),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "status": "generating"})


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

    # Buy-first flow: the league has to be claimed against a purchase the
    # user has already paid for and still has a slot on. Picks the oldest
    # open purchase so a single recap bought before a season pass gets
    # consumed first rather than being orphaned.
    open_purchases = [p for p in SmackcastPurchase.query
                      .filter_by(user_id=user.id, status="paid")
                      .order_by(SmackcastPurchase.id.asc()).all()
                      if p.slots_remaining > 0]
    if not open_purchases:
        return jsonify({"error": "No open Smackcast pass. Grab one first.", "needs_purchase": True}), 402
    purchase = open_purchases[0]

    subscription = SmackcastSubscription(
        user_id=user.id,
        purchase_id=purchase.id,
        plan=purchase.plan,
        is_active=True,
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

    # Already paid for, so there's no checkout leg here any more - straight
    # to the library, which is where their recaps will show up.
    return jsonify({
        "ok": True,
        "redirect_url": "/smackcast/library",
        "slots_remaining": purchase.slots_remaining,
    })


@app.route("/smackcast/success")
@login_required
def smackcast_success_page():
    return render_template("smackcast_success.html")


def _recap_filename(recap, subscription):
    """
    A filename someone would actually want in their Downloads folder.
    S3 keys are bare UUIDs, so a direct link saves as
    "a3f9c2e1-....mp3" with no indication of what it is.
    """
    league = (subscription.league_name or "league").lower()
    league = re.sub(r"[^a-z0-9]+", "-", league).strip("-") or "league"
    return f"smackcast-{league}-week{recap.week_number}-{recap.season_year}.mp3"


@app.route("/smackcast/recap/<int:recap_id>/download")
@login_required
def smackcast_download_recap(recap_id):
    """
    Serves a subscriber their own recap audio as a proper download.

    Proxied rather than linking straight to S3 for one reason: the object
    key is a UUID, so a direct link downloads as gibberish. Going through
    here lets us set Content-Disposition with a real filename.

    Streamed in chunks rather than read into memory - a multi-minute recap
    is several MB and this box has already hit its memory ceiling once.

    Ownership is checked against the requesting user. Recap IDs are
    sequential integers, so without this anyone logged in could walk the
    range and pull down other people's audio.
    """
    user = get_current_user()
    recap = SmackcastRecap.query.get(recap_id)
    if not recap:
        return "Recap not found.", 404

    subscription = SmackcastSubscription.query.get(recap.subscription_id)
    if not subscription or subscription.user_id != user.id:
        # Deliberately 404 rather than 403 - no reason to confirm that a
        # recap with this id exists to someone who doesn't own it.
        return "Recap not found.", 404

    if not recap.audio_url:
        return "That recap has no audio yet.", 404

    try:
        upstream = requests.get(recap.audio_url, stream=True, timeout=30)
        if upstream.status_code != 200:
            return "Couldn't retrieve that audio file.", 502
    except Exception as e:
        print(f"[smackcast] download failed for recap {recap_id}: {e}")
        return "Couldn't retrieve that audio file.", 502

    name = _recap_filename(recap, subscription)

    headers = {
        # filename* as well as filename. Some mobile browsers ignore the
        # plain one and save the URL's last path segment instead, which
        # here would be the word "download" with no extension.
        "Content-Disposition":
            f'attachment; filename="{name}"; filename*=UTF-8\'\'{quote(name)}',
        # Lets a phone seek and resume rather than pulling the whole file
        # before it can do anything with it.
        "Accept-Ranges": "bytes",
    }

    # Only if S3 gave us one. An empty string is an invalid header value.
    length = upstream.headers.get("Content-Length")
    if length:
        headers["Content-Length"] = length

    return Response(
        upstream.iter_content(chunk_size=64 * 1024),
        mimetype="audio/mpeg",
        headers=headers,
    )


# Fields the commissioner can set. Listed explicitly rather than looping
# over the form, so a renamed input can never write to a column nobody
# intended - the model has payment and platform fields on the same table.
_LEAGUE_PROFILE_FIELDS = (
    "how_they_know_each_other", "newest_member", "worst_at_lineups",
    "buy_in", "trophy",
    "last_place_punishment", "league_age", "commissioner_name",
    "reigning_champion", "runner_up", "group_chat",
    "perennial_winner", "perennial_loser", "biggest_talker", "most_absent",
    "running_jokes", "rivalries", "anything_else",
)


_WEEKLY_NOTE_FIELDS = ("big_trade", "brutal_loss", "loudest_in_chat", "anything_else")


@app.route("/smackcast/this-week", methods=["GET", "POST"])
@login_required
def smackcast_weekly_note():
    """
    What happened in the league this week.

    The week is worked out from the clock, not chosen - anything saved
    before 11:59pm Monday belongs to the week just finished, anything after
    midnight belongs to the next one. The page says which, so nobody has to
    guess.
    """
    from services.smackcast_service import current_notes_week

    user = get_current_user()
    sub = (SmackcastSubscription.query
           .filter_by(user_id=user.id)
           .order_by(SmackcastSubscription.id.desc())
           .first())

    # An admin with no subscription of their own still needs to see this
    # page - otherwise the only way to check the design is to create a fake
    # league, which then sits in the database forever. Preview mode hands
    # over an unsaved object: the page renders exactly as a subscriber sees
    # it, and saving is refused rather than writing junk.
    preview = False
    if not sub:
        if user.is_admin:
            preview = True
            sub = SmackcastSubscription(league_name="Preview League")
        else:
            return redirect("/smackcast")

    week, season_year, closes = current_notes_week()

    note = None if preview else SmackcastWeeklyNote.query.filter_by(
        subscription_id=sub.id, week_number=week, season_year=season_year).first()

    saved = False
    if request.method == "POST" and not preview:
        if not note:
            note = SmackcastWeeklyNote(subscription_id=sub.id,
                                       week_number=week, season_year=season_year)
            db.session.add(note)
        for field in _WEEKLY_NOTE_FIELDS:
            value = (request.form.get(field) or "").strip()
            setattr(note, field, value or None)
        db.session.commit()
        saved = True

    # Earlier weeks, so somebody can see what they have already told him.
    past = [] if preview else (SmackcastWeeklyNote.query
            .filter_by(subscription_id=sub.id, season_year=season_year)
            .filter(SmackcastWeeklyNote.week_number != week)
            .order_by(SmackcastWeeklyNote.week_number.desc())
            .limit(6).all())

    return render_template("smackcast_weekly_note.html",
                           sub=sub, note=note, week=week, closes=closes,
                           past=[p for p in past if p.has_content()],
                           saved=saved, preview=preview)


@app.route("/smackcast/league-profile", methods=["GET", "POST"])
@login_required
def smackcast_league_profile():
    """
    What makes one league different from every other league.

    Commissioner only - specifically, whoever owns the subscription. Letting
    any member write details about other members would be a harassment
    vector wearing a feature's clothes, and whatever gets written comes back
    out in Smacky's voice, which makes it ours.
    """
    user = get_current_user()
    sub = (SmackcastSubscription.query
           .filter_by(user_id=user.id)
           .order_by(SmackcastSubscription.id.desc())
           .first())

    # Same preview allowance as the weekly page - an admin with no league of
    # their own can still see how it renders, and saving is refused so no
    # placeholder subscription ends up in the database.
    preview = False
    if not sub:
        if user.is_admin:
            preview = True
            sub = SmackcastSubscription(league_name="Preview League")
        else:
            return redirect("/smackcast")

    saved = False
    if request.method == "POST" and not preview:
        for field in _LEAGUE_PROFILE_FIELDS:
            value = (request.form.get(field) or "").strip()
            setattr(sub, field, value or None)
        db.session.commit()
        saved = True

    return render_template("smackcast_league_profile.html",
                           sub=sub, saved=saved, preview=preview)


@app.route("/smackcast/connect")
@login_required
def smackcast_connect_page():
    """
    Connect a fantasy league to a Smackcast subscription.

    The template and all three APIs it calls have existed for a while; the
    route never did. Three pages linked to /smackcast/connect and every one
    of them 404'd - so anybody who paid for Smackcast had no way to attach a
    league, and no recap could ever be generated for them.
    """
    user = get_current_user()

    # If they already have one connected, show it rather than starting over.
    existing = (SmackcastSubscription.query
                .filter_by(user_id=user.id)
                .order_by(SmackcastSubscription.id.desc())
                .first())

    return render_template(
        "smackcast_connect.html",
        existing=existing,
        stripe_publishable_key=os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
    )


@app.route("/smackcast/library")
@login_required
def smackcast_library_page():
    """
    A subscriber's own archive of every recap their leagues have produced.

    This was a real hole: recaps were only ever reachable by their
    share_token, which arrives once by text or call and is easy to lose.
    Someone pays for a full season and then has no way back to week 3.
    Groups it by subscription since one person can run Smackcast on
    several leagues at once.
    """
    user = get_current_user()
    subs = SmackcastSubscription.query.filter_by(user_id=user.id).order_by(SmackcastSubscription.id.desc()).all()

    groups = []
    for sub in subs:
        recaps = (SmackcastRecap.query
                  .filter_by(subscription_id=sub.id)
                  .order_by(SmackcastRecap.week_number.desc())
                  .all())
        groups.append({"sub": sub, "recaps": recaps})

    # The library has its own banner. Falls back to the product page's hero
    # if that file isn't present, so the page never renders a broken image
    # and never loses its header if the dedicated art is missing.
    img_dir = os.path.join(app.root_path, "static", "img")
    own_hero = os.path.exists(os.path.join(img_dir, "smackcast-library-hero.png"))
    shared_hero = os.path.exists(os.path.join(img_dir, "smackcast-hero.png"))
    return render_template(
        "smackcast_library.html",
        groups=groups,
        hero_image_exists=own_hero or shared_hero,
        hero_image="img/smackcast-library-hero.png" if own_hero else "img/smackcast-hero.png",
    )


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


_smackcast_test_jobs = {}


def _run_smackcast_test_async(job_id, sport, league_name, team_count, week, stress=False, save_to_library=False, user_id=None):
    """
    The test generator's pipeline, moved off the request. Inline it blocked
    the single gunicorn worker for minutes, which took the entire site down
    until the 180s timeout killed and restarted it.
    """
    with app.app_context():
        try:
            matchups = smackcast_service.generate_sample_matchups(sport, team_count, stress=stress)
            result = smackcast_service.generate_weekly_recap_script(
                league_name=league_name, week=week, matchups=matchups,
                team_count=team_count, sport=sport,
            )
            audio_url = smackcast_service.assemble_recap_audio(
                result["intro"], result["segments"], result["outro"]
            )
            meme_url = None
            if result.get("best_line"):
                try:
                    meme_url = smackcast_service.generate_meme_image(
                        result["best_line"], league_name, week
                    )
                except Exception as e:
                    print(f"[smackcast test] meme generation failed: {e}")
            # Optionally persist it as a real library recap. Useful for two
            # things: seeing the library populated without waiting for a
            # paying subscriber, and producing keepable samples for the
            # product page (the audio already lives on S3 either way - this
            # just gives it a row, a share link and a download filename).
            if save_to_library:
                try:
                    sub = (SmackcastSubscription.query
                           .filter_by(user_id=user_id, league_id="__admin_test__")
                           .first())
                    if not sub:
                        sub = SmackcastSubscription(
                            user_id=user_id, platform="sleeper", sport=sport,
                            league_id="__admin_test__",
                            league_name=f"{league_name} (test)",
                            team_count=team_count, season_year=datetime.utcnow().year,
                            deliver_web_link=True, is_active=True, plan="season",
                        )
                        db.session.add(sub)
                        db.session.flush()
                    db.session.add(SmackcastRecap(
                        subscription_id=sub.id, week_number=week,
                        season_year=sub.season_year,
                        script_text=result["full_text"], audio_url=audio_url,
                        meme_image_url=meme_url, best_line=result["best_line"],
                        share_token=secrets.token_urlsafe(16), status="ready",
                    ))
                    db.session.commit()
                except Exception as e:
                    # Never let a save failure lose the generation itself -
                    # the audio is already made and paid for.
                    db.session.rollback()
                    print(f"[smackcast test] save to library failed: {e}")

            _smackcast_test_jobs[job_id] = {
                "status": "ready",
                "matchups": matchups,
                "script": result["full_text"],
                "best_line": result["best_line"],
                "audio_url": audio_url,
                "meme_url": meme_url,
            }
        except Exception as e:
            print(f"[smackcast test] generation failed: {e}")
            _smackcast_test_jobs[job_id] = {"status": "failed", "error": str(e)}


@app.route("/api/smackcast/test-status/<job_id>")
@login_required
def api_smackcast_test_status(job_id):
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403
    job = _smackcast_test_jobs.get(job_id)
    if not job:
        return jsonify({"status": "unknown"}), 404
    if job["status"] in ("ready", "failed"):
        # Hand it over once and drop it - these are disposable previews and
        # the audio itself lives on S3, so there's nothing to keep.
        return jsonify(_smackcast_test_jobs.pop(job_id))
    return jsonify(job)


def _generate_smackcasts_async():
    """
    Background wrapper for the weekly Smackcast run. Needs its own app
    context since it runs outside the request cycle, and swallows nothing
    silently - a failure here means somebody's paid recap didn't generate,
    so it needs to show up in the logs.
    """
    with app.app_context():
        try:
            generate_weekly_smackcasts()
            print("[smackcast cron] weekly run finished")
        except Exception as e:
            print(f"[smackcast cron] weekly run FAILED: {e}")


# ONE SHOW AT A TIME.
#
# There was no guard at all. Two presses of the admin button - or the
# button while the 5:55 cron is running - started TWO FULL RENDERS in
# parallel. Both write scripts through Claude and both render five
# minutes of speech through ElevenLabs, so a double-click cost double.
#
# A plain flag rather than a lock: a second caller should be TOLD NO and
# go away, not queue up and run the whole thing again a minute later.
_show_running = {"since": None}

# THE LAST DRY RUN, KEPT SO SOMEBODY CAN READ IT.
#
# A dry run writes the WHOLE SCRIPT - every segment, every league, the
# planned running order - and then printed one summary line and threw
# the rest away. The one thing worth looking at ended up buried in a log
# stream.
#
# In memory rather than the database: it is a scratch result, and a
# restart losing it costs nothing but another free run.
_last_dry_run = {"at": None, "result": None}
_show_lock = threading.Lock()


def show_in_progress():
    """Seconds the current render has been going, or None."""
    with _show_lock:
        started = _show_running["since"]
    if not started:
        return None
    return int(time.time() - started)


def _produce_daily_show_async(app_obj, dry_run: bool = False, days_back: int = 1):
    """
    The actual work, off the request thread.

    Rendering five minutes of speech takes well over a minute, and Render cuts
    a request off long before that - the endpoint has to hand off and return.
    Same pattern already used for battle recaps and smackcast generation.
    """
    # ONE AT A TIME - claim the slot or go home.
    #
    # A second render started while the first is going costs a second
    # full set of Claude and ElevenLabs charges for an episode that will
    # be thrown away, because only one can be published.
    #
    # Refusing beats queueing: somebody who double-clicks wants one show,
    # not two three minutes apart.
    with _show_lock:
        if _show_running["since"]:
            been = int(time.time() - _show_running["since"])
            print(f"[show] ALREADY RUNNING for {been}s - refusing this one. "
                  f"Two renders in parallel means paying twice.", flush=True)
            return
        _show_running["since"] = time.time()

    try:
        with app_obj.app_context():
            try:
                result = show_service.produce_daily_show(days_back=days_back, dry_run=dry_run)
            except Exception as e:
                # Swallowed on purpose. Yesterday's episode keeps playing and the
                # error is in the logs, rather than the home page losing its player.
                print(f"[show] production failed, keeping previous episode: {e}")
                return

            if result.get("dry_run"):
                # Kept so /api/admin/dry-run can show it. Printing alone
                # meant the script was only readable in the Render log.
                _last_dry_run["at"] = utc_iso(datetime.utcnow())
                _last_dry_run["result"] = result
                print(f"[show] dry run complete - {result.get('segment_count')} segments, "
                      f"no audio generated, nothing published", flush=True)
                return

            if not result.get("published"):
                print(f"[show] not published: {result.get('reason')}")
                return

            show = DailyShow(
                audio_url=result["audio_url"],
                date_label=result.get("date_label", ""),
                minutes=result.get("minutes"),
                game_count=result.get("game_count"),
                leagues=", ".join(result.get("leagues", [])),
                best_line=result.get("best_line", ""),
                # The segment checklist from this run, as JSON - what
                # the admin panel's daily list reads.
                segment_report=json.dumps(result.get("segment_report"))
                               if result.get("segment_report") else None,
                is_live=True,
            )
            DailyShow.query.filter_by(is_live=True).update({"is_live": False})
            db.session.add(show)
            db.session.commit()
            print(f"[show] published #{show.id}: {result['minutes']}min, {result['game_count']} games")


    finally:
        # ALWAYS release, including on a crash. A flag left set would
        # block every future render until the next deploy - which is a
        # worse failure than the one it prevents.
        with _show_lock:
            _show_running["since"] = None

@app.route("/api/cron/daily-show", methods=["GET", "POST"])
def cron_daily_show():
    """
    Kicks off The Daily Smack. Hit once each morning by the external
    scheduler - same mechanism as the armed-smackagram check.

    Returns immediately and does the work in the background, because a
    five-minute TTS render takes far longer than a request is allowed to live.
    Progress and failures go to the logs; /admin/show-status reads the result.
    """
    # Either the scheduler's key or an admin who is already logged in.
    if not cron_authorised():
        return "Nope.", 403

    # ?dry=1 writes the script and reports the running order and where the
    # commercial break would land, then stops WITHOUT generating audio.
    # A full run is ~13 ElevenLabs calls; the dry run is one Claude call, so
    # placement and ordering can be debugged without paying for a render
    # every attempt.
    dry = request.args.get("dry") in ("1", "true", "yes")

    # days_back lets the show be pointed at any past date - mainly to hear
    # how it sounds on a sport that is out of season. Defaults to 1, which
    # is last night and what the morning cron uses.
    try:
        days_back = max(1, int(request.args.get("days_back", 1)))
    except (TypeError, ValueError):
        days_back = 1

    # TELL THE CALLER, rather than starting a thread that will refuse.
    #
    # The thread guard alone would return 202 "started" and then quietly
    # decline - so somebody pressing twice sees two successes and waits
    # for an episode that is not coming from the second one.
    been = show_in_progress()
    if been is not None:
        return jsonify({
            "started": False,
            "already_running_for_seconds": been,
            "note": ("A render is already going. Starting a second costs a "
                     "second full set of Claude and ElevenLabs charges for "
                     "an episode that would be thrown away."),
        }), 409

    threading.Thread(
        target=_produce_daily_show_async, args=(app,),
        kwargs={"dry_run": dry, "days_back": days_back}, daemon=True
    ).start()
    return jsonify({
        "started": True,
        "dry_run": dry,
        "note": ("DRY RUN - writing the script and reporting placement only, no audio. "
                 "Watch the logs for [show] lines.") if dry else
                ("Producing in the background. Check /api/show/current in a few minutes, "
                 "or the logs for [show] lines.")
    }), 202


@app.route("/api/admin/bdl-probe")
@login_required
def api_admin_bdl_probe():
    """
    Diagnostic: raw balldontlie rows, untouched, so date/time semantics
    can be read off the real thing instead of guessed.

    The Padres bug: their MLB "date" looks like a UTC day, which puts a
    Tuesday 9:40pm ET game on Wednesday and Wednesday's late games on
    Thursday. This shows the actual fields so the fix filters on facts.

    ?league=mlb&date=2026-08-05  (defaults: mlb, yesterday Eastern)
    """
    user, err = _require_admin()
    if err:
        return err
    from services import balldontlie as _bdl
    from zoneinfo import ZoneInfo
    lg = (request.args.get("league") or "mlb").lower()
    day = request.args.get("date") or (
        datetime.now(ZoneInfo("America/New_York"))
        - timedelta(days=1)).strftime("%Y-%m-%d")
    d = _bdl._get(lg, "games", {"dates[]": day, "per_page": 50})
    rows = (d or {}).get("data") if isinstance(d, dict) else None
    rows = rows or []
    return jsonify({
        "league": lg, "date_queried": day, "row_count": len(rows),
        "matchups": [
            {"home": (_bdl._team_name(r.get("home_team")) or "?"),
             "away": _bdl._sides(r)[1],
             "date": r.get("date"), "time": r.get("time"),
             "status": r.get("status"),
             "datetime": r.get("datetime")}
            for r in rows[:20]],
        "first_row_raw": rows[0] if rows else None,
    })


@app.route("/api/admin/segment-checklist")
@login_required
def api_admin_segment_checklist():
    """
    The daily yes/no list: did every branded segment make the episode?

    Reads the report saved with the latest live show - Smack Ball,
    Certified Cooker, Clown Show, both Winners and Whiners, the WNBA's
    rotating award - plus tonight's greeting name and whether the
    parallel writers ran. Episodes produced before this existed say so
    rather than pretending.
    """
    user, err = _require_admin()
    if err:
        return err
    show = (DailyShow.query.filter_by(is_live=True)
            .order_by(DailyShow.id.desc()).first())
    if not show:
        return jsonify({"episode": None,
                        "note": "No live episode yet."})
    report = None
    if show.segment_report:
        try:
            report = json.loads(show.segment_report)
        except Exception:
            report = None
    out = {
        "episode": {
            "date_label": show.date_label,
            "minutes": show.minutes,
            "game_count": show.game_count,
            "leagues": show.leagues,
            "produced_at": utc_iso(show.created_at)
                           if show.created_at else None,
        },
    }
    if not report:
        out["note"] = ("This episode was produced before the checklist "
                       "existed - the next episode will carry one.")
        return jsonify(out)
    segs = report.get("segments") or []
    out["greeting"] = report.get("greeting")
    out["parallel_writers"] = report.get("parallel")
    # Three states, not two: delivered / dropped / not scheduled.
    # "Not scheduled" means the layout had no material for it tonight
    # (no qualifying streak, no box score) - correct, not a failure.
    out["segments"] = []
    for r in segs:
        if r.get("allocated") is False:
            out["segments"].append({"name": r.get("name"),
                                    "status": "not scheduled tonight"})
        else:
            out["segments"].append({"name": r.get("name"),
                                    "status": "delivered"
                                    if r.get("hit") else "DROPPED"})
    _scheduled = [r for r in segs if r.get("allocated") is not False]
    out["all_delivered"] = (all(r.get("hit") for r in _scheduled)
                            if _scheduled else None)
    return jsonify(out)


@app.route("/api/admin/pipeline-check")
@login_required
def api_admin_pipeline_check():
    """
    Does the show pipeline survive the data it will actually get?

    Runs the whole layout against games shaped like each source really
    returns - rich Highlightly with a box score, balldontlie with plays
    but no box, scoreline only, and the least any source could send.

    NO NETWORK AND NO COST. Worth running after any change to the show,
    or to a data source, BEFORE spending three minutes of TTS finding
    out at runtime.
    """
    user, err = _require_admin()
    if err:
        return err
    import io, contextlib, sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    buf = io.StringIO()
    try:
        from tools import pipeline_check
        with contextlib.redirect_stdout(buf):
            code = pipeline_check.run()
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return jsonify({"passed": code == 0,
                    "report": buf.getvalue().split("\n")})


@app.route("/set-up")
def set_up_page():
    """Themed arming page for an UPCOMING game (like Game Day, but the
    game hasn't happened). All matchup state rides the query string;
    the buyer picks nobody - the board button pre-loaded it."""
    return render_template("set_up.html")


@app.route("/set-up/armed")
def set_up_armed():
    return render_template("set_up_armed.html")


@app.route("/api/arm-smackagram", methods=["POST"])
@login_required
def api_arm_smackagram():
    """
    Direct arming for the SET UP page. Mirrors the three-doorway
    money logic of the order path: logged in + balance -> arm now;
    logged in + broke -> 402 to packs (the page stashes and returns);
    not logged in -> the @login_required redirect sends them to login
    with a return to /set-up. Fires automatically after the game via
    the existing scheduler (check_armed_smackagrams).
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "login required"}), 401
    data = request.json or {}
    for _f in ("game_start_time", "home_team", "away_team", "target_team",
               "recipient_name", "recipient_phone"):
        if not str(data.get(_f, "")).strip():
            return jsonify({"error": f"missing {_f}"}), 400
    if not wallet_service.has_sufficient_balance(
            user, wallet_service.LOCKED_N_LOADED_COST_CENTS):
        return jsonify({"error": "insufficient_balance",
                        "redirect": "/get-smackagrams?next=/set-up"}), 402
    try:
        result = _execute_arm_smackagram(user, data)
    except Exception as e:
        print(f"[set-up] arm failed: {e}", flush=True)
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "redirect": result.get("redirect")})


@app.route("/game-day/sent")
def game_day_sent():
    """The confirmation page - the call is already firing when this
    renders (the order posted and debited before the redirect)."""
    return render_template("game_day_sent.html")


@app.route("/game-day")
def game_day_page():
    """The themed landing for smacking one finished game - see
    templates/game_day.html. All state rides the query string."""
    return render_template("game_day.html")


@app.route("/api/admin/highlightly-probe")
@login_required
def api_admin_highlightly_probe():
    """
    HIGHLIGHTLY DEBUGGING FROM A BROWSER (David, Aug 7). The key rides
    in a request header, so raw browser testing is impossible - this
    endpoint asks Highlightly on your behalf and shows the truth:
      ?sport=nfl&date=2026-08-06            filtered, as the show asks
      ?sport=nfl&date=2026-08-06&raw=1      NO league filter - see
                                            EVERYTHING their endpoint
                                            returns for that segment/day
    Reports: the exact params sent, row count, and each row's OWN
    league name + teams - which is how a mislabeling (baseball rows
    under the football segment) becomes visible in one screen.
    """
    user = get_current_user()
    if not user or not user.is_admin:
        return jsonify({"error": "admin only"}), 403
    from services import highlightly as hl
    sport = (request.args.get("sport") or "nfl").lower()
    date = request.args.get("date") or ""
    if not hl.enabled():
        return jsonify({"error": "highlightly disabled (no key set)"})
    seg = hl.PATHS.get(sport)
    league_name, league_param = (hl.LEAGUES.get(sport) or (None, None))
    params = {"date": date} if date else {}
    if not request.args.get("raw") and league_name:
        params[league_param] = league_name
    try:
        data = hl._get(sport, "matches", params=params, ttl=0)
    except Exception as e:
        return jsonify({"error": f"highlightly call failed: {e}",
                        "params_sent": params})
    rows = (data or {}).get("data") or (data if isinstance(data, list) else [])
    def _teamname(r, side):
        t = (r.get(side) or {})
        return t.get("displayName") or t.get("name") or "?"
    report = [{
        "their_league": ((r.get("league") or {}).get("name")
                         if isinstance(r.get("league"), dict)
                         else r.get("league") or r.get("leagueName")),
        "home": _teamname(r, "homeTeam") or _teamname(r, "home"),
        "away": _teamname(r, "awayTeam") or _teamname(r, "away"),
        "state": (r.get("state") or {}).get("description")
                 if isinstance(r.get("state"), dict) else r.get("state"),
    } for r in rows[:25]]
    return jsonify({
        "asked": {"sport": sport, "segment_used": seg,
                  "params_sent": params, "filtered": "raw" not in request.args},
        "row_count": len(rows),
        "rows": report,
    })


@app.route("/api/admin/inject-game", methods=["POST", "GET"])
@login_required
def api_admin_inject_game():
    """
    Hand the show a HUMAN-VERIFIED game (see the manual door in
    show_service.fetch_results). GET shows what's staged; POST with
    JSON stages a game; POST {"clear": true} empties the list.
    Required: league, winner, loser, winner_score, loser_score.
    Optional: facts (list of strings the writer may use verbatim).
    """
    import json as _json
    user = get_current_user()
    if not user or not user.is_admin:
        return jsonify({"error": "admin only"}), 403
    from models import Setting
    row = Setting.query.filter_by(key="manual_games").first()
    staged = _json.loads(row.value) if row and row.value else []
    # GET with query params stages too - so a verified game can be
    # handed over from a phone browser's address bar, no tooling.
    if request.method == "GET" and not request.args.get("winner"):
        return jsonify({"staged": staged})
    data = (request.json or {}) if request.method == "POST" \
        else {k: v for k, v in request.args.items()}
    if isinstance(data.get("facts"), str):
        data["facts"] = [f.strip() for f in data["facts"].split("|") if f.strip()]
    if data.get("clear"):
        if row:
            row.value = "[]"
            db.session.commit()
        return jsonify({"cleared": True})
    need = ("league", "winner", "loser", "winner_score", "loser_score")
    missing = [k for k in need if not str(data.get(k, "")).strip()]
    if missing:
        return jsonify({"error": f"missing: {', '.join(missing)}"}), 400
    game = {k: data[k] for k in need}
    game["winner_score"] = int(game["winner_score"])
    game["loser_score"] = int(game["loser_score"])
    if isinstance(data.get("facts"), list):
        game["facts"] = [str(f)[:300] for f in data["facts"]][:12]
    staged.append(game)
    if row is None:
        row = Setting(key="manual_games")
        db.session.add(row)
    row.value = _json.dumps(staged)
    db.session.commit()
    print(f"[show] manual game staged by {user.email}: "
          f"{game['winner']} over {game['loser']}", flush=True)
    return jsonify({"staged": staged})


@app.route("/api/admin/dry-run")
@login_required
def api_admin_dry_run():
    """
    The last dry run, in full.

    ?dry=1 writes the entire script and generates no audio - which makes
    it the right way to test a change to the writing or to the data
    behind it, because it costs tokens rather than ElevenLabs credits.

    It used to print one line and discard the script. This shows what was
    actually written.
    """
    user, err = _require_admin()
    if err:
        return err
    if not _last_dry_run["result"]:
        return jsonify({
            "note": ("No dry run since the last restart. Start one at "
                     "/api/cron/daily-show?dry=1 - it writes the whole "
                     "script and makes no audio."),
        })
    return jsonify({"at": _last_dry_run["at"],
                    **(_last_dry_run["result"] or {})})


@app.route("/api/admin/show-status")
@login_required
def admin_show_status():
    """Recent episodes, newest first - so 'did it work' is a page, not a log."""
    user = get_current_user()
    if not user.is_admin:
        return jsonify({"error": "Not authorized."}), 403

    shows = DailyShow.query.order_by(DailyShow.id.desc()).limit(10).all()

    # IS ONE RUNNING RIGHT NOW?
    #
    # A deploy kills the worker and the render dies with it - silently,
    # since the work happens in a background thread. That has already
    # cost one full render today.
    #
    # Nothing in the app can stop Render restarting, but it can at least
    # say "do not deploy for another two minutes".
    running = show_in_progress()

    return jsonify({
        "rendering_now": running is not None,
        "rendering_for_seconds": running,
        "warning": ("A render is in progress - DO NOT DEPLOY. A restart "
                    "kills it and the Claude and ElevenLabs spend is lost."
                    if running is not None else None),
        "shows": [{
        "id": s.id, "audio_url": s.audio_url, "date_label": s.date_label,
        "minutes": s.minutes, "game_count": s.game_count, "leagues": s.leagues,
        "best_line": s.best_line, "is_live": s.is_live,
        "created_at": utc_iso(s.created_at) if s.created_at else "",
    } for s in shows]})


@app.route("/daily-smack")
def daily_smack_page():
    """The show's own page - player, explainer and the archive."""
    return render_template("daily_smack.html")


@app.route("/api/show/current")
def api_current_show():
    """What the home page player asks for. Public, cached briefly."""
    show = DailyShow.query.filter_by(is_live=True).order_by(DailyShow.id.desc()).first()
    if not show:
        return jsonify({"live": False})
    # NO-STORE, because the browser cached this JSON and served a
    # newly-published episode minutes late - refresh after refresh
    # showed the old one while the new file sat live on S3. The page
    # must always ask fresh; the payload is 300 bytes.
    resp = jsonify({
        "live": True,
        # The episode number the show already announces in its logs
        # ("published #37") - the player wants it on the front too.
        "episode": show.id,
        "audio_url": show.audio_url,
        "date_label": show.date_label,
        "minutes": show.minutes,
        "game_count": show.game_count,
        "leagues": show.leagues,
        "best_line": show.best_line,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/show/recent")
def api_recent_shows():
    """
    The "Recent Episodes" shelf on /daily-smack: up to the last 7
    published episodes BEFORE the one currently live.

    SHELF_EPOCH is the shelf's launch date - nothing created before it
    is ever listed, per the decision to clear all history and let the
    shelf fill naturally one day at a time from here on. Only the
    newest 7 are returned, so the oldest rolls off automatically as
    each new episode publishes.
    """
    SHELF_EPOCH = datetime(2026, 8, 8)

    live = DailyShow.query.filter_by(is_live=True).order_by(
        DailyShow.id.desc()).first()

    q = DailyShow.query.filter(DailyShow.created_at >= SHELF_EPOCH)
    if live:
        q = q.filter(DailyShow.id != live.id)
    shows = q.order_by(DailyShow.id.desc()).limit(7).all()

    resp = jsonify({
        "episodes": [{
            "episode": s.id,
            "audio_url": s.audio_url,
            "date_label": s.date_label,
            "minutes": s.minutes,
            "game_count": s.game_count,
        } for s in shows]
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
    # The scheduler's key, or an admin already logged in - see
    # cron_authorised(). Prompting a logged-in admin for a production
    # credential protects nothing and teaches a bad habit.
    if not cron_authorised():
        return jsonify({"error": "unauthorized"}), 401

    # Runs in a background thread rather than inline. This loops over every
    # subscription and, for each, makes a Claude call plus one ElevenLabs
    # call per matchup plus an S3 upload plus a meme generation - minutes of
    # work per subscriber. Render runs a single gunicorn worker with a 180s
    # timeout, so inline it would (a) block every other request on the site
    # for the whole run and (b) get the worker killed partway through,
    # leaving most subscribers with no recap at all.
    #
    # Safe to fire and forget: generate_weekly_smackcasts already skips any
    # subscription that already has this week's recap, so a re-hit after an
    # interrupted run picks up where it left off rather than duplicating.
    threading.Thread(target=_generate_smackcasts_async, daemon=True).start()
    return jsonify({"ok": True, "started": True})


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
    # The scheduler's key, or an admin already logged in - see
    # cron_authorised(). Prompting a logged-in admin for a production
    # credential protects nothing and teaches a bad habit.
    if not cron_authorised():
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


@app.route("/api/admin/check-id-collisions")
def admin_check_id_collisions():
    """
    One-time diagnostic tool — Order and Smackagram are separate tables
    with separate autoincrementing primary keys, but every Twilio
    webhook URL (/call-instructions/<id>, /call-status/<id>, etc.)
    carries only the bare integer id and resolves it by guessing
    (Order.query.get(id) or Smackagram.query.get(id)), with Order
    always winning. Any Smackagram whose id also exists in Orders
    would silently get served the WRONG record's audio, with no
    error logged. This checks whether that's actually happening.

    Read-only - three plain COUNT/MIN/MAX queries, nothing written.

    ?key=... (same secret as the cron endpoint)
    Not linked from anywhere in the UI — visit directly to run it.
    """
    provided_key = request.args.get("key", "")
    # The scheduler's key, or an admin already logged in - see
    # cron_authorised(). Prompting a logged-in admin for a production
    # credential protects nothing and teaches a bad habit.
    if not cron_authorised():
        return jsonify({"error": "unauthorized"}), 401

    orders_stats = db.session.execute(db.text(
        "SELECT MIN(id), MAX(id), COUNT(*) FROM orders"
    )).fetchone()
    smackagrams_stats = db.session.execute(db.text(
        "SELECT MIN(id), MAX(id), COUNT(*) FROM smackagrams"
    )).fetchone()
    collision_count = db.session.execute(db.text(
        "SELECT COUNT(*) FROM orders o JOIN smackagrams s ON o.id = s.id"
    )).scalar()

    collision_ids = []
    if collision_count:
        rows = db.session.execute(db.text(
            "SELECT o.id FROM orders o JOIN smackagrams s ON o.id = s.id ORDER BY o.id LIMIT 50"
        )).fetchall()
        collision_ids = [r[0] for r in rows]

    return jsonify({
        "orders": {"min_id": orders_stats[0], "max_id": orders_stats[1], "count": orders_stats[2]},
        "smackagrams": {"min_id": smackagrams_stats[0], "max_id": smackagrams_stats[1], "count": smackagrams_stats[2]},
        "collision_count": collision_count,
        "collision_ids_sample": collision_ids,
        "verdict": "BROKEN - collisions exist, calls are being served wrong audio" if collision_count else "clean - no collisions currently, but fix is still worth doing since a collision will eventually occur",
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
            # STEP 3f (Twilio handoff): AnsweredBy was printed and
            # discarded - now stored, so the Locker can say "human
            # answered, reaction recorded" vs "hit voicemail", and so
            # the share of 'unknown' results tells us whether the AMD
            # timeout is set right.
            conn.execute(db.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS answered_by VARCHAR(32)"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS answered_by VARCHAR(32)"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS user_id INTEGER"))
            conn.execute(db.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id INTEGER"))
            conn.execute(db.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS team VARCHAR(80)"))
            # Refund tracking. Twilio retries webhooks, so without a flag
            # a retried failure notification refunds twice - and that is
            # money leaving with nothing to show for it.
            conn.execute(db.text(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS "
                "refunded BOOLEAN DEFAULT FALSE"))
            conn.execute(db.text(
                "ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS "
                "refunded BOOLEAN DEFAULT FALSE"))
            conn.execute(db.text(
                "ALTER TABLE support_replies ADD COLUMN IF NOT EXISTS "
                "channel VARCHAR(10) DEFAULT 'email'"))
            # The daily show's segment checklist (JSON text).
            conn.execute(db.text(
                "ALTER TABLE daily_shows ADD COLUMN IF NOT EXISTS "
                "segment_report TEXT"))

            # INDEXES.
            #
            # db.create_all() adds indexes for NEW tables only - an index
            # added to an existing model never reaches a live database
            # without this, which is the same trap the wallet columns hit.
            #
            # CONCURRENTLY is deliberately NOT used: it cannot run inside a
            # transaction, and these tables are small enough that a brief
            # lock on deploy costs nothing.
            for stmt in (
                "CREATE INDEX IF NOT EXISTS ix_smackagrams_status "
                "ON smackagrams (status)",
                "CREATE INDEX IF NOT EXISTS ix_wallet_tx_user "
                "ON wallet_transactions (user_id)",
                "CREATE INDEX IF NOT EXISTS ix_wallet_tx_intent "
                "ON wallet_transactions (stripe_payment_intent_id)",
                "CREATE INDEX IF NOT EXISTS ix_battle_lines_battle "
                "ON battle_lines (battle_id)",
            ):
                try:
                    conn.execute(db.text(stmt))
                except Exception as _e:
                    print(f"[migrate] index skipped: {_e}", flush=True)

            # SCRUB SCREEN NAMES ALREADY ON THE WALL.
            #
            # Publishing them stopped, but the ones already stored are
            # still there and still being served. A promise that starts
            # applying today is not a promise.
            try:
                conn.execute(db.text(
                    "UPDATE wall_posts SET handle = 'anonymous' "
                    "WHERE handle IS DISTINCT FROM 'anonymous'"))
            except Exception as _e:
                print(f"[migrate] wall handles: {_e}", flush=True)


            # Numbers that must never be called again. Checked before every
            # dial - see is_opted_out().
            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS famous_moments (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(80) UNIQUE NOT NULL,
                title VARCHAR(120) NOT NULL,
                sport VARCHAR(20) DEFAULT 'mlb',
                moment_date VARCHAR(40),
                game VARCHAR(160),
                teams VARCHAR(160),
                losing_team VARCHAR(80),
                hero VARCHAR(80),
                goat VARCHAR(80),
                situation TEXT,
                stakes TEXT,
                broadcast_style TEXT,
                call_text TEXT,
                followup_text TEXT,
                roast_text TEXT,
                audio_url VARCHAR(400),
                generated_at TIMESTAMP,
                sort_order INTEGER DEFAULT 0,
                published BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP
            )"""))

            for _col, _type in (("scheduled_for", "TIMESTAMP"),
                                ("scheduled_sent", "BOOLEAN DEFAULT FALSE")):
                conn.execute(db.text(
                    f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {_col} {_type}"))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_orders_scheduled "
                "ON orders (scheduled_for)"))

            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS safety_events (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP,
                surface VARCHAR(40),
                stage VARCHAR(30),
                user_id INTEGER,
                record_type VARCHAR(20),
                record_id INTEGER,
                category VARCHAR(60),
                reason TEXT,
                excerpt TEXT,
                refunded BOOLEAN DEFAULT FALSE,
                reviewed BOOLEAN DEFAULT FALSE
            )"""))
            for _ix in ("ix_safety_created ON safety_events (created_at)",
                        "ix_safety_user ON safety_events (user_id)",
                        "ix_safety_cat ON safety_events (category)",
                        "ix_safety_reviewed ON safety_events (reviewed)"):
                conn.execute(db.text(f"CREATE INDEX IF NOT EXISTS {_ix}"))

            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS page_stats (
                id SERIAL PRIMARY KEY,
                day DATE,
                path VARCHAR(120),
                views INTEGER DEFAULT 0,
                visitors INTEGER DEFAULT 0,
                logged_in INTEGER DEFAULT 0,
                CONSTRAINT uq_day_path UNIQUE (day, path)
            )"""))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_page_stats_day ON page_stats (day)"))

            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS call_timings (
                id SERIAL PRIMARY KEY,
                record_type VARCHAR(20),
                record_id INTEGER,
                call_sid VARCHAR(64),
                dialed_at TIMESTAMP,
                instructions_at TIMESTAMP,
                gap_seconds DOUBLE PRECISION,
                answered_by VARCHAR(30),
                call_status VARCHAR(30),
                duration_seconds INTEGER,
                created_at TIMESTAMP
            )"""))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_call_timings_sid ON call_timings (call_sid)"))

            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS opt_outs (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) UNIQUE NOT NULL,
                reason VARCHAR(200),
                source VARCHAR(20) DEFAULT 'web',
                created_at TIMESTAMP
            )"""))
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_opt_outs_phone ON opt_outs (phone)"))

            # What makes a league THIS league. All optional - a commissioner
            # who fills in nothing still gets recaps, just more generic ones.
            for _col, _type in [
                ("how_they_know_each_other", "VARCHAR(40)"),
                ("newest_member", "VARCHAR(80)"),
                ("worst_at_lineups", "VARCHAR(80)"),
                ("buy_in", "VARCHAR(60)"),
                ("trophy", "VARCHAR(200)"),
                ("last_place_punishment", "TEXT"),
                ("league_age", "VARCHAR(40)"),
                ("commissioner_name", "VARCHAR(80)"),
                ("reigning_champion", "VARCHAR(80)"),
                ("runner_up", "VARCHAR(80)"),
                ("group_chat", "VARCHAR(60)"),
                ("perennial_winner", "VARCHAR(80)"),
                ("perennial_loser", "VARCHAR(80)"),
                ("biggest_talker", "VARCHAR(80)"),
                ("most_absent", "VARCHAR(80)"),
                ("running_jokes", "TEXT"),
                ("rivalries", "TEXT"),
                ("anything_else", "TEXT"),
            ]:
                conn.execute(db.text(
                    f"ALTER TABLE smackcast_subscriptions "
                    f"ADD COLUMN IF NOT EXISTS {_col} {_type}"))
            # What happened in the league each week. Separate from the
            # season-long profile because a note has to belong to a specific
            # week - otherwise nothing can tell whether it was meant for the
            # recap being written tomorrow or the one after.
            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS smackcast_weekly_notes (
                id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL,
                week_number INTEGER NOT NULL,
                season_year INTEGER NOT NULL,
                big_trade TEXT,
                brutal_loss TEXT,
                loudest_in_chat TEXT,
                anything_else TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                CONSTRAINT uq_weekly_note_sub_week
                    UNIQUE (subscription_id, week_number, season_year)
            )"""))

            # Smacks of the Week. Nothing appears until approved - it is the
            # front page of a site that takes payments.
            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS wall_posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                handle VARCHAR(40) NOT NULL,
                body TEXT NOT NULL,
                product VARCHAR(20) DEFAULT 'smackagram',
                team VARCHAR(80),
                headline VARCHAR(80),
                team_name VARCHAR(80),
                audio_url VARCHAR(500),
                approved BOOLEAN DEFAULT FALSE NOT NULL,
                is_sample BOOLEAN DEFAULT FALSE NOT NULL,
                created_at TIMESTAMP
            )"""))

            # CREATE TABLE IF NOT EXISTS does nothing to a table that already
            # exists, so every column added after the wall shipped needs its
            # own ALTER. Without these, a deploy that adds a field leaves the
            # model and the database disagreeing and every query 500s.
            for _col, _type in [
                ("user_id",    "INTEGER"),
                ("body",       "TEXT"),
                ("product",    "VARCHAR(20)"),
                ("team",       "VARCHAR(80)"),
                ("headline",   "VARCHAR(80)"),
                ("team_name",  "VARCHAR(80)"),
                ("audio_url",  "VARCHAR(500)"),
                ("approved",   "BOOLEAN DEFAULT FALSE"),
                ("is_sample",  "BOOLEAN DEFAULT FALSE"),
                ("created_at", "TIMESTAMP"),
            ]:
                conn.execute(db.text(
                    f"ALTER TABLE wall_posts ADD COLUMN IF NOT EXISTS {_col} {_type}"))

            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS daily_shows (
                id SERIAL PRIMARY KEY,
                audio_url VARCHAR(500) NOT NULL,
                date_label VARCHAR(60),
                minutes DOUBLE PRECISION,
                game_count INTEGER,
                leagues VARCHAR(200),
                best_line TEXT,
                is_live BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )"""))
            conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_daily_shows_live ON daily_shows (is_live)"))
            conn.execute(db.text("""CREATE TABLE IF NOT EXISTS settings (
                id SERIAL PRIMARY KEY,
                key VARCHAR(60) UNIQUE NOT NULL,
                value VARCHAR(255) NOT NULL,
                updated_by VARCHAR(60),
                updated_at TIMESTAMP DEFAULT NOW()
            )"""))
            conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_settings_key ON settings (key)"))
            conn.execute(db.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS share_token VARCHAR(64)"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS share_token VARCHAR(64)"))
            # Indexed because the locker queries by user on every page view.
            conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id)"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS intensity INTEGER DEFAULT 4 NOT NULL"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS turn_started_at TIMESTAMP"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS opponent_type VARCHAR(10) DEFAULT 'human' NOT NULL"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE NOT NULL"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS espn_event_id VARCHAR(32)"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS pile_position INTEGER"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS pile_total INTEGER"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS send_after TIMESTAMP"))
            conn.execute(db.text("""
                CREATE TABLE IF NOT EXISTS battle_line_reactions (
                    id SERIAL PRIMARY KEY,
                    line_id INTEGER NOT NULL REFERENCES battle_lines(id),
                    battle_id INTEGER NOT NULL REFERENCES battles(id),
                    reactor_id VARCHAR(64) NOT NULL,
                    reaction VARCHAR(4) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_line_reactor UNIQUE (line_id, reactor_id)
                )"""))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS max_rounds INTEGER DEFAULT 5 NOT NULL"))
            conn.execute(db.text("ALTER TABLE battle_lines ADD COLUMN IF NOT EXISTS timed_out BOOLEAN DEFAULT FALSE NOT NULL"))
            conn.execute(db.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS answered_by VARCHAR(30)"))
            conn.execute(db.text("ALTER TABLE smackagrams ADD COLUMN IF NOT EXISTS answered_by VARCHAR(30)"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS last_seen_a TIMESTAMP"))
            conn.execute(db.text("ALTER TABLE battles ADD COLUMN IF NOT EXISTS last_seen_b TIMESTAMP"))
            conn.execute(db.text("ALTER TABLE smackcast_subscriptions ADD COLUMN IF NOT EXISTS purchase_id INTEGER"))
            conn.execute(db.text("ALTER TABLE smackcast_subscriptions ADD COLUMN IF NOT EXISTS plan VARCHAR(20)"))
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



@app.route("/api/player-search")
def api_player_search():
    """
    Find a player by name, whether or not he is currently playing.

    THIS IS WHY AARON JUDGE WAS MISSING.

    The picker was filtering a SQUAD - a list reconstructed from match team
    sheets. A team sheet only contains players who were available, so
    anybody on the injured list appears in none of them, anywhere. No
    amount of fetching squads was ever going to find him.

    This searches the whole player database instead. The question changes
    from "who is on this team", which the data cannot answer completely, to
    "who is called this", which it answers fully.

    Results are filtered to the team being smacked, and stored so the next
    search for the same name needs no request at all.
    """
    q = (request.args.get("q") or "").strip()
    team = (request.args.get("team") or "").strip()
    if len(q) < 2:
        return jsonify({"players": coach_hits})

    league = (request.args.get("league") or "").lower()
    if not league and team:
        try:
            from services import team_state
            t = team_state.find_team(team)
            if t:
                league = t.get("league") or ""
        except Exception:
            pass
    league = league or "mlb"

    # THE COACH FIRST, BEFORE ANY PLAYER.
    #
    # A losing fanbase is usually angrier at the manager than at any
    # player - "your season is Aaron Boone's fault" is the argument they
    # are already having with each other.
    #
    # Neither provider has coaches: Highlightly's support confirmed it in
    # writing on 5 August, and balldontlie does not carry them. So this
    # comes from a maintained list.
    #
    # Ahead of the players rather than mixed in, because somebody looking
    # for the manager should not have to scroll past twelve relievers.
    coach_hits = []
    try:
        from services import coaches as _coaches
        _c = _coaches.for_team(league, team) if team else None
        if _c and q.lower() in _c["name"].lower():
            _t = ("interim " + _c["title"]) if _c["interim"] else _c["title"]
            coach_hits.append({
                "name": _c["name"],
                # What the writer is told, so Smacky calls him the right
                # thing. Baseball says MANAGER; everything else says head
                # coach, and getting that wrong is the kind of mistake
                # only somebody who does not watch the sport makes.
                "forWriter": f"{_c['name']} ({_t})",
                "position": _t.title(),
                "is_coach": True,
            })
    except Exception:
        pass

    # THE DATABASE FIRST. A name searched once is a name we keep.
    try:
        from services import player_store
        if team:
            local = [p for p in player_store.squad(league, team)
                     if q.lower() in p["name"].lower()]
            if local:
                # Coach ahead of the squad, not lost inside it.
                return jsonify({"players": (coach_hits + local)[:12],
                                "source": "stored"})
    except Exception as e:
        print(f"[search] store lookup failed: {e}", flush=True)

    out = []
    try:
        from services import highlightly, player_store
        if highlightly.enabled():
            want = (team or "").split()[-1].lower()
            for hit in highlightly.search_players(league, q):
                prof = highlightly.player_profile(league, hit["id"])
                if not prof or not prof.get("name"):
                    continue
                # Only players on the team being smacked.
                if want and want not in (prof.get("team") or "").lower():
                    continue
                row = {"name": prof["name"], "position": prof.get("position"),
                       "number": prof.get("jersey"),
                       "away": prof.get("active") is False}
                out.append(row)
                try:
                    player_store.remember(league, prof.get("team") or team,
                                          [row])
                except Exception:
                    pass
    except Exception as e:
        print(f"[search] {q}: {e}", flush=True)

    merged = coach_hits + out
    resp = jsonify({"players": merged[:12],
                    "source": ("coach+highlightly" if coach_hits and out
                               else "coach" if coach_hits
                               else "highlightly" if out else "none")})
    resp.headers["Cache-Control"] = "no-store" if not out else "public, max-age=600"
    return resp


@app.route("/api/admin/fill-players")
@login_required
def api_admin_fill_players():
    """
    Fill the player table directly, without waiting for a show to run.

    Walks a league's fixtures over the last few days and stores every name
    in every team sheet. One pass covers every club that has played.

    ?league=mlb        which league (default mlb)
    ?days=5            how far back to walk

    Slow on purpose - a request per day plus one per match. Run it when
    you want the table filled, not on a schedule.
    """
    user, err = _require_admin()
    if err:
        return err

    from datetime import datetime as _dt, timedelta as _td
    from services import highlightly, player_store

    if not highlightly.enabled():
        return jsonify({"error": "HIGHLIGHTLY_KEY is not set"}), 400

    league = (request.args.get("league") or "mlb").lower()
    days = max(1, min(int(request.args.get("days") or 5), 14))

    # RESET IS HANDLED AT THE END, NOT HERE.
    #
    # This used to delete first and refill afterwards. When the refill then
    # returned nothing - a rate limit, an outage, an off day with no
    # finished games - the table was left EMPTY, and a picker that had been
    # working stopped working.
    #
    # That happened. A reset=1 run wiped 153 stored players and replaced
    # them with zero.
    #
    # Now nothing is deleted until a refill has actually produced names.
    wants_reset = request.args.get("reset") == "1"

    cfg = highlightly.LEAGUES.get(league)
    if not cfg:
        return jsonify({"error": f"unknown league {league}"}), 400
    league_name, param = cfg

    seen_matches = set()
    report = {"league": league, "days": days, "teams": {}, "added": 0}

    for off in range(days):
        day = highlightly.sport_day(off)
        d = highlightly._get(league, "matches",
                             {param: league_name, "date": day, "limit": 100},
                             ttl=900)
        rows = (d.get("data") if isinstance(d, dict) else d) or []
        for m in rows:
            mid = m.get("id")
            if not mid or mid in seen_matches:
                continue
            seen_matches.add(mid)

            # SKIP GAMES THAT HAVE NOT BEEN PLAYED.
            #
            # An unplayed match has a PROJECTED lineup - nine batters and
            # nothing else - and an empty box score. That is why a refill
            # returned exactly nine players for every single team: it was
            # reading tomorrow's lineup card rather than a squad.
            #
            # A finished game has the full team sheet plus everybody who
            # actually appeared.
            _st = ((m.get("state") or {}).get("description") or "").lower()
            _rep = ((m.get("state") or {}).get("report") or "").lower()
            if "finish" not in _st and _rep != "final":
                continue

            det = highlightly._get(league, f"matches/{mid}", ttl=900)
            blob = det[0] if isinstance(det, list) and det else det
            if not isinstance(blob, dict):
                continue

            for side in ("homeTeam", "awayTeam"):
                # THE FULL NAME. Taking the last word merged Boston
                # Red Sox and Chicago White Sox into one club called
                # "Sox" with their players mixed together.
                team_full = ((m.get(side) or {}).get("displayName") or "")
                nick = team_full
                people = ((blob.get("rosters") or {}).get(side) or [])
                squad = [{"name": r.get("fullName") or r.get("name"),
                          "position": r.get("position"),
                          "number": r.get("jersey")}
                         for r in people if (r.get("fullName") or r.get("name"))]
                # THE BOX SCORE TOO.
                #
                # A team sheet lists who DRESSED for that game - often
                # only nine or ten in baseball. The box score has everyone
                # who actually appeared, including relief pitchers and
                # pinch hitters who are not on the sheet.
                #
                # Between them you get a real squad rather than a starting
                # lineup, which is why the first run stored ten Astros.
                try:
                    for bp in highlightly.box_score(league, mid):
                        if not player_store.matches_team(team_full,
                                                         bp.get("team") or ""):
                            continue
                        if bp["name"] not in {x["name"] for x in squad}:
                            squad.append({"name": bp["name"],
                                          "position": None,
                                          "number": bp.get("jersey")})
                except Exception:
                    pass

                if not squad or not nick:
                    continue
                n = player_store.remember(league, nick, squad)
                report["added"] += n
                report["teams"][nick] = report["teams"].get(nick, 0) + len(squad)

    # WIPE FIRST, if asked.
    #
    # The first run of this stored twenty-nine players under a team called
    # "Sox" - Boston and Chicago merged, their players mixed together.
    # ?reset=1 clears the league before refilling so that bad data does
    # not sit there forever.
    # SAFE TO CLEAR ONLY NOW.
    #
    # Old rows for teams we just refreshed are removed - but only for those
    # teams, and only because we have replacements in hand. A team the walk
    # never reached keeps whatever it had.
    if wants_reset and report["added"] >= 0 and report["teams"]:
        from models import Player
        removed = 0
        for team_name in report["teams"]:
            removed += (Player.query
                        .filter(Player.league == league,
                                Player.team == team_name,
                                Player.last_seen < _dt.utcnow()
                                - _td(minutes=5))
                        .delete(synchronize_session=False))
        db.session.commit()
        report["stale_removed"] = removed
    elif wants_reset:
        report["reset_skipped"] = ("nothing was fetched, so nothing was "
                                   "deleted - the table is untouched")
        print("[players] reset requested but the walk found nothing. "
              "Table left alone rather than emptied.", flush=True)

    report["matches_walked"] = len(seen_matches)
    report["note"] = ("Only FINISHED games are read. An unplayed match has a "
                      "projected nine-batter lineup and no box score, which "
                      "is not a squad. Use more days if counts look thin.")
    report["total_stored"] = player_store.count(league)
    return jsonify(report)


@app.route("/api/admin/players")
@login_required
def api_admin_players():
    """
    How many player names are stored, and for which teams.

    These are read by the picker without any network call - and they
    survive long after a player stops appearing in live data, which is how
    somebody on a long injured list stays findable.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import player_store
    league = request.args.get("league")
    team = request.args.get("team")
    out = {"total": player_store.count(league),
           "teams": len(player_store.teams_known(league))}
    if team and league:
        out["squad"] = player_store.squad(league, team)
    return jsonify(out)


@app.route("/api/admin/stored-results")
@login_required
def api_admin_stored_results():
    """
    Finished games held in the database.

    Every one of these is a game no provider will ever be asked about
    again. "contested" means two sources disagreed - the stored answer was
    kept and the disagreement recorded rather than overwriting something
    somebody may already have been called about.
    """
    user, err = _require_admin()
    if err:
        return err
    from models import GameResult
    rows = (GameResult.query.order_by(GameResult.created_at.desc())
            .limit(60).all())
    return jsonify({
        "total": GameResult.query.count(),
        "contested": GameResult.query.filter(
            GameResult.contested.is_(True)).count(),
        "recent": [{
            "league": r.league, "date": r.game_date,
            "result": f"{r.winner} {r.winner_score}-{r.loser_score} {r.loser}",
            "source": r.source,
            "contested": bool(r.contested),
            "note": r.contested_note,
        } for r in rows],
    })


@app.route("/api/admin/shadow")
@login_required
def api_admin_shadow():
    """
    Where ESPN and Highlightly have disagreed.

    "wrong_loser" is the one that matters - that is a game where the two
    sources name a different losing team, which in production means calling
    somebody about a game they won and charging them for it.

    An empty list after a week of games is the signal that it is safe to
    switch over.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import highlightly
    rows = highlightly.disagreements()
    return jsonify({
        "highlightly": highlightly.status(),
        "total_disagreements": len(rows),
        "wrong_loser_count": sum(1 for r in rows if r.get("wrong_loser")),
        "recent": rows,
    })


@app.route("/api/admin/email-test")
@login_required
def api_admin_email_test():
    """
    Is email working? Send one to yourself and find out.

    ?to=you@example.com

    THIS NOW TESTS THE REAL CHAIN. The first version tested only the
    old SMTP module, so a working Resend key looked broken: the test
    said "SMTP rejected the login" while the alert system - which uses
    the full Resend -> Postmark -> SMTP chain - would have sent fine.
    A test that exercises a different door than production is worse
    than no test.

    Also reports WHICH mail keys the running process can actually see,
    because "is the environment variable really there" was the question
    nobody could answer from outside.
    """
    user, err = _require_admin()
    if err:
        return err
    import os as _os
    out = {
        "keys_visible_to_this_process": {
            "RESEND_API_KEY": bool(_os.environ.get("RESEND_API_KEY")),
            "POSTMARK_API_KEY": bool(_os.environ.get("POSTMARK_API_KEY")),
            "SMTP_HOST": _os.environ.get("SMTP_HOST") or None,
            "SMTP_USER": _os.environ.get("SMTP_USER") or None,
            "SMTP_PASSWORD": bool(_os.environ.get("SMTP_PASSWORD")),
        },
    }
    to = (request.args.get("to") or "").strip()
    if not to:
        out["note"] = ("Add ?to=you@example.com to actually send. "
                       "Without it this only reports the settings.")
        return jsonify(out)
    from services import mail
    ok, detail = mail.send(
        to, "Smackagram email test",
        "This is the test message from /api/admin/email-test.\n\n"
        "If you are reading it, outbound email works.")
    out["sent"] = bool(ok)
    out["detail"] = detail
    return jsonify(out)

@app.route("/api/admin/balldontlie-probe")
@login_required
def api_admin_balldontlie_probe():
    """
    What does the balldontlie key actually get us?

    ESPN now returns 403 to Render on the first request - a single call,
    instantly refused, which is an IP block rather than rate limiting.
    Verified: the same URL returns 200 from a laptop. So the fallback
    that was meant to catch a Highlightly outage has been dead in
    production, and waiting will not fix it.

    That leaves Highlightly as a single point of failure for every sport,
    and Auto-Smack TAKES MONEY for calls that depend on knowing a result.

    Before building against another API, find out what this one gives
    us - the same mistake with Highlightly cost days. This asks their
    API directly rather than trusting a pricing page: rate limits come
    from the response headers, and coverage from what actually answers.
    """
    user, err = _require_admin()
    if err:
        return err

    import requests
    key = os.environ.get("BALLDONTLIE_KEY")
    if not key:
        return jsonify({"error": "BALLDONTLIE_KEY is not set in Render."}), 400

    HEAD = {"Authorization": key}

    def ask(url, params=None):
        try:
            r = requests.get(url, params=params or {}, headers=HEAD,
                             timeout=15)
            try:
                body = r.json()
            except Exception:
                body = r.text[:160]
            return r.status_code, body, dict(r.headers)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"[:140], {}

    out = {"tested": utc_iso(datetime.utcnow())}

    # ---- which sports answer at all? ----
    #
    # Their leagues live on separate hosts. A 401 means the tier does not
    # include that sport; a 200 means it does.
    BASES = {
        "nba":   "https://api.balldontlie.io/v1",
        "wnba":  "https://api.balldontlie.io/wnba/v1",
        "mlb":   "https://api.balldontlie.io/mlb/v1",
        "nfl":   "https://api.balldontlie.io/nfl/v1",
        "nhl":   "https://api.balldontlie.io/nhl/v1",
        "ncaab": "https://api.balldontlie.io/ncaab/v1",
        "ncaaf": "https://api.balldontlie.io/ncaaf/v1",
    }
    out["coverage"] = {}
    for sport, base in BASES.items():
        st, body, hdrs = ask(f"{base}/teams", {"per_page": 3})
        rows = body.get("data") if isinstance(body, dict) else None
        info = {"status": st, "teams": len(rows) if rows else 0}
        if st != 200:
            info["said"] = (body.get("message") if isinstance(body, dict)
                            else str(body))[:120]
        elif rows:
            # Do they carry logos? That is the other thing worth knowing.
            info["team_fields"] = sorted(rows[0].keys())
            info["sample"] = {k: str(v)[:50]
                              for k, v in list(rows[0].items())[:8]}
        # THE RATE LIMIT, FROM THE HEADERS RATHER THAN A PRICING PAGE.
        limits = {k: v for k, v in hdrs.items()
                  if "ratelimit" in k.lower() or "x-rate" in k.lower()}
        if limits:
            info["rate_limit"] = limits
        out["coverage"][sport] = info

    # ---- can it do the two things we actually need? ----
    #
    # 1. finished games on a date, so Auto-Smack knows who lost
    # 2. per-player box scores, so a smack has detail rather than
    #    "your team lost"
    out["what_we_need"] = {}
    day = request.args.get("date") or "2026-08-04"

    for sport, base in (("wnba", BASES["wnba"]), ("mlb", BASES["mlb"])):
        block = {}
        st, body, _ = ask(f"{base}/games", {"dates[]": day, "per_page": 5})
        rows = body.get("data") if isinstance(body, dict) else None
        block["games_on_" + day] = {
            "status": st, "rows": len(rows) if rows else 0,
            "sample": rows[0] if rows else (
                body.get("message") if isinstance(body, dict) else None),
        }
        gid = (rows[0].get("id") if rows else None)
        if gid:
            st, body, _ = ask(f"{base}/stats", {"game_ids[]": gid,
                                                "per_page": 3})
            srows = body.get("data") if isinstance(body, dict) else None
            block["box_score"] = {
                "status": st, "rows": len(srows) if srows else 0,
                "sample": srows[0] if srows else (
                    body.get("message") if isinstance(body, dict) else None),
            }
        out["what_we_need"][sport] = block

    out["why_this_matters"] = (
        "ESPN 403s from Render on the first request - an IP block, not "
        "rate limiting, confirmed by the same URL returning 200 from a "
        "laptop. So Highlightly is currently a single point of failure "
        "for every sport, and WNBA has no source at all since Highlightly "
        "does not carry it.")
    return jsonify(out)


@app.route("/api/admin/roster-probe")
@login_required
def api_admin_roster_probe():
    """
    Which endpoints give us whole rosters, and are coaches in there?

    A full player database needs two things the match data does not
    provide: every TEAM in a league, and every PLAYER on a team.

    squad() currently infers a roster from recent box scores. That finds
    who PLAYED - genuinely better for the picker in season - but it
    cannot find a rookie who has not appeared, or anybody at all during
    the off-season.

    Their documentation mentions Teams and Players without giving paths,
    and says nothing about coaches. This API has already cost days
    through guessing, so this asks. About 20 requests, read once.
    """
    user, err = _require_admin()
    if err:
        return err

    import requests
    key = os.environ.get("HIGHLIGHTLY_KEY")
    if not key:
        return jsonify({"error": "HIGHLIGHTLY_KEY not set"}), 400

    BASE = "https://sports.highlightly.net"
    HEAD = {"x-rapidapi-key": key}

    def ask(path, params=None):
        try:
            r = requests.get(f"{BASE}/{path}", params=params or {},
                             headers=HEAD, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = r.text[:150]
            return r.status_code, body
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"[:120]

    def summarise(st, body):
        if st != 200:
            msg = body.get("message") if isinstance(body, dict) else body
            return {"status": st, "said": str(msg)[:140]}
        rows = body.get("data") if isinstance(body, dict) else body
        if isinstance(rows, list):
            return {"status": 200, "rows": len(rows),
                    "sample": rows[0] if rows else None}
        return {"status": 200, "shape": str(body)[:200]}

    seg = "baseball"
    out = {"segment": seg}

    # WHAT THE LAST PROBE ESTABLISHED
    #
    #   /teams              383 rows, no params, MLB and NCAA together
    #   /teams?name=Yankees exactly one team
    #   /players            1000 rows, and the ONLY filter it accepts is
    #                       name - teamId, team, /teams/{id}/players,
    #                       squads and rosters all fail
    #   team record         abbreviation, displayName, id, league, logo,
    #                       name. NO COACH ANYWHERE.
    #
    # So a roster-per-team backfill is not possible. What IS possible is
    # walking the whole player list. Two things decide whether that is
    # worth doing:
    #
    #   1. how many players are there in total
    #   2. does a player record carry a TEAM - because a name with no
    #      team is far less useful to the picker
    out["how_many"] = {}
    st, body = ask(f"{seg}/players", {})
    if st == 200 and isinstance(body, dict):
        out["how_many"]["pagination"] = body.get("pagination")
        rows = body.get("data") or []
        out["how_many"]["first_page_rows"] = len(rows)
        out["how_many"]["player_fields"] = (
            sorted(rows[0].keys()) if rows else None)

    # Does offset work, and does it actually move?
    st, body = ask(f"{seg}/players", {"offset": 1000})
    rows = body.get("data") if isinstance(body, dict) else []
    out["how_many"]["offset_1000"] = {
        "status": st,
        "rows": len(rows or []),
        "first_name": (rows[0].get("fullName") if rows else None),
        "said": (body.get("message") if isinstance(body, dict)
                 and st != 200 else ""),
    }

    # ---- does a single player record carry a team? ----
    #
    # This is the question that decides everything. A flat list of names
    # with no team tells the picker nothing about who plays where.
    out["player_detail"] = {}
    st, body = ask(f"{seg}/players", {"name": "Judge", "limit": 3})
    rows = body.get("data") if isinstance(body, dict) else []
    out["player_detail"]["search_by_name"] = {
        "status": st, "rows": len(rows or []),
        "sample": rows[0] if rows else None,
    }
    pid = rows[0].get("id") if rows else None
    if pid:
        for label, path in (("players/{id}", f"{seg}/players/{pid}"),
                            ("players/{id}/stats",
                             f"{seg}/players/{pid}/statistics")):
            st, body = ask(path, {})
            rec = body.get("data") if isinstance(body, dict) else body
            if isinstance(rec, list) and rec:
                rec = rec[0]
            out["player_detail"][label] = {
                "status": st,
                "fields": sorted(rec.keys()) if isinstance(rec, dict) else None,
                "sample": (str(rec)[:300] if not isinstance(rec, dict)
                           else {k: str(v)[:60] for k, v in
                                 list(rec.items())[:12]}),
            }

    out["note"] = ("Baseball only, deliberately - it is the one league in "
                   "season, so a wrong answer elsewhere would be ambiguous "
                   "between 'wrong endpoint' and 'no data right now'. "
                   "Their API uses one naming scheme throughout, so "
                   "whatever works here works everywhere.")
    return jsonify(out)


@app.route("/api/admin/highlightly-check")
@login_required
def api_admin_highlightly_check():
    """
    What does Highlightly actually answer, from this server?

    Two things in this codebase are currently GUESSES: which query
    parameter each sport segment wants for the league name, and whether
    box scores live at "box-score" or "box-scores". Our own testing and
    their documentation disagree, and the per-sport APIs we used to call
    are a different product from the unified one we pay for.

    Rather than guess again, this asks. Every combination is tried and
    the answer reported, so the code can be set to match a fact rather
    than an assumption.

    Deliberately NOT run automatically - it is about twenty requests and
    exists to be read by a person once, after a change.
    """
    user, err = _require_admin()
    if err:
        return err

    import requests
    from services import highlightly
    key = os.environ.get("HIGHLIGHTLY_KEY")
    if not key:
        return jsonify({"error": "HIGHLIGHTLY_KEY is not set on this "
                                 "instance."}), 400

    BASE = "https://sports.highlightly.net"
    HEAD = {"x-rapidapi-key": key}
    day = request.args.get("date") or highlightly.sport_day(1)

    SEGMENTS = {
        "mlb":  ("baseball", "MLB"),
        "nfl":  ("american-football", "NFL"),
        "nba":  ("nba", "NBA"),
        "nhl":  ("nhl", "NHL"),
        "wnba": ("basketball", "WNBA"),
    }

    def ask(path, params):
        try:
            r = requests.get(f"{BASE}/{path}", params=params,
                             headers=HEAD, timeout=15)
            body = r.json() if r.headers.get("content-type", "") \
                .startswith("application/json") else r.text[:150]
            return r.status_code, body, dict(r.headers)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"[:150], {}

    # WHAT DOES A 400 ACTUALLY SAY?
    #
    # The first run of this returned 400 for the nba, nhl and
    # american-football segments on both parameter names. A 400 means the
    # request SHAPE is wrong, not that there is no data - wnba returned
    # 200 with nothing, which is what an empty day looks like.
    #
    # So rather than guess again at what they want, this asks with no
    # league parameter at all, and reports the error body verbatim. Their
    # message usually names the offending field.
    # ASK THEIR API TO NAME ITS OWN VALID VALUES.
    #
    # Sending a deliberately wrong league earns a message like
    # "league must be one of the following values: MLB, NCAA" - which is
    # better documentation than their documentation. One request per
    # segment and we stop guessing at league names entirely.
    valid = {}
    for seg, param in (("baseball", "league"), ("nba", "league"),
                       ("nhl", "league"),
                       ("american-football", "league"),
                       ("basketball", "leagueName")):
        st, body, _ = ask(f"{seg}/matches",
                          {param: "ZZZ_NOT_A_LEAGUE", "limit": 1})
        msg = body.get("message") if isinstance(body, dict) else str(body)
        valid[seg] = {"param": param, "api_says": str(msg)[:200]}

    # WHAT LEAGUE NAMES ARE ACTUALLY IN THEIR DATA?
    #
    # valid_leagues only helps for baseball - it is the one segment that
    # validates the value and names the alternatives. Everywhere else, a
    # WRONG LEAGUE NAME RETURNS 200 WITH ZERO ROWS, which is
    # indistinguishable from an empty day.
    #
    # That is the trap WNBA may be sitting in: the league plays through
    # August, so "no fixtures on 4 August" is suspicious.
    #
    # So this asks for matches with NO league filter and reports the
    # distinct league names that come back. Whatever their data calls a
    # competition is the string we have to send.
    seen_leagues = {}
    for seg in ("baseball", "nba", "nhl", "american-football", "basketball"):
        names = set()
        for offset in (0, 30, 90):
            st, body, _ = ask(f"{seg}/matches",
                              {"limit": 40, "offset": offset})
            rows = body.get("data") if isinstance(body, dict) else []
            for r in (rows or []):
                lg = r.get("league") or {}
                nm = lg.get("name") if isinstance(lg, dict) else lg
                if nm:
                    names.add(str(nm)[:40])
            if not rows:
                break
        seen_leagues[seg] = sorted(names) or ["(no matches returned)"]

    out = {"date_tested": day, "valid_leagues": valid,
           "leagues_seen_in_data": seen_leagues, "segments": {}}

    # Does the key work at all, and what does the plan say?
    st, body, hdrs = ask("baseball/matches",
                         {"league": "MLB", "date": day, "limit": 3})
    out["key_works"] = (st == 200)
    out["first_call_status"] = st
    out["rate_limit"] = {
        k: v for k, v in hdrs.items() if k.lower().startswith("x-ratelimit")
    }
    if isinstance(body, dict) and body.get("plan"):
        out["plan"] = body["plan"]
    elif st != 200:
        out["first_call_body"] = body

    for sport, (seg, league) in SEGMENTS.items():
        info = {"segment": seg}
        # EMPTY IS NOT BROKEN.
        #
        # The first version of this tried both parameter names and
        # recorded the LAST status - so a segment that answered 200 with
        # no rows, then 400 on the second attempt, was reported as a 400
        # failure. NBA and NHL looked broken all summer when they were
        # simply out of season.
        #
        # Now it uses the confirmed parameter and distinguishes three
        # outcomes: working with games, working but empty, and refused.
        _name, param = highlightly.LEAGUES.get(sport, (league, "league"))
        st, body, _ = ask(f"{seg}/matches",
                          {param: _name, "date": day, "limit": 20})
        got = body.get("data") if isinstance(body, dict) else (
            body if isinstance(body, list) else None)
        info["league_param"] = param
        info["http"] = st
        if st != 200:
            info["result"] = "REFUSED"
            info["api_says"] = (body.get("message")
                                if isinstance(body, dict) else str(body))[:160]
            out["segments"][sport] = info
            continue
        rows = got or []
        info["games_found"] = len(rows)
        if not rows:
            # AN EMPTY RESULT HAS TWO CAUSES AND THEY LOOK IDENTICAL.
            #
            # Either there are genuinely no fixtures, or the league name
            # is wrong - because only baseball validates the value. The
            # rest return 200 and nothing when the string does not match.
            #
            # So rather than assume "out of season", ask the same segment
            # WITHOUT the league filter. If that returns games, the league
            # name is the problem, not the calendar.
            st2, body2, _ = ask(f"{seg}/matches", {"date": day, "limit": 5})
            any_rows = body2.get("data") if isinstance(body2, dict) else []
            if any_rows:
                info["result"] = ("SEGMENT HAS GAMES BUT THIS LEAGUE NAME "
                                  "MATCHES NONE - the name is likely wrong")
                info["names_in_data_today"] = sorted({
                    str((r.get("league") or {}).get("name"))[:40]
                    for r in any_rows
                    if isinstance(r.get("league"), dict)
                })
            else:
                info["result"] = ("no fixtures anywhere on this segment "
                                  "today - out of season")
            out["segments"][sport] = info
            continue
        info["result"] = "working"

        # A finished game, to test box scores against.
        mid = next((r.get("id") for r in rows
                    if "inish" in str((r.get("state") or {})
                                      .get("description", ""))), None)
        if not mid:
            info["box_score"] = "no finished game on this date to test"
        else:
            info["tested_match"] = mid
            for path in ("box-score", "box-scores"):
                st, body, _ = ask(f"{seg}/{path}/{mid}", {})
                if st == 200 and body:
                    info["box_score"] = path
                    break
            else:
                info["box_score"] = f"neither worked (last HTTP {st})"
        out["segments"][sport] = info

    out["what_the_code_currently_assumes"] = {
        "paths": highlightly.PATHS,
        "league_params": {k: v[1] for k, v in highlightly.LEAGUES.items()},
    }
    return jsonify(out)


@app.route("/api/admin/audio-check")
@login_required
def api_admin_audio_check():
    """
    Are the stored audio URLs actually reachable?

    "The audio does not play" has several possible causes and they look
    identical from the browser - a dead S3 key, a bucket policy that no
    longer allows public reads, a file written under the wrong prefix, or
    a URL that was never valid.

    This asks each one and reports the status code, which distinguishes
    them in one look.
    """
    user, err = _require_admin()
    if err:
        return err

    import requests
    from models import Order, Smackagram

    rows = []
    for model, kind in ((Order, "smackagram"), (Smackagram, "auto-smack")):
        for r in model.query.order_by(model.created_at.desc()).limit(10).all():
            url = getattr(r, "recording_url", None) or \
                getattr(r, "message_audio_url", None)
            if not url:
                rows.append({"kind": kind, "id": r.id, "url": None,
                             "status": "no url stored"})
                continue
            try:
                # HEAD, not GET - no reason to download the audio to find
                # out whether it exists.
                resp = requests.head(url, timeout=6, allow_redirects=True)
                rows.append({"kind": kind, "id": r.id, "url": url,
                             "status": resp.status_code,
                             "type": resp.headers.get("Content-Type"),
                             "bytes": resp.headers.get("Content-Length")})
            except Exception as e:
                rows.append({"kind": kind, "id": r.id, "url": url,
                             "status": f"{type(e).__name__}: {e}"[:120]})

    ok = sum(1 for r in rows if r.get("status") == 200)
    return jsonify({
        "checked": len(rows),
        "reachable": ok,
        "note": ("403 means the bucket is not serving these publicly. "
                 "404 means the file is not there. A timeout means the "
                 "host is wrong."),
        "items": rows,
    })


@app.route("/api/admin/login-guard")
@login_required
def api_admin_login_guard():
    """
    Who is currently locked out of the login, and why.

    An address appearing here repeatedly is somebody working through a
    list. An email appearing here is either a customer who has forgotten
    their password or somebody targeting them - and the count tells you
    which.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import login_guard
    return jsonify(login_guard.status())


@app.route("/api/admin/alerts")
@login_required
def api_admin_alerts():
    """
    What is currently broken.

    Repeats roll up, so "ESPN blocked, 240 times since 14:02" is one entry
    rather than 240. Resolved ones are kept - "this has happened four
    times this month" is the useful fact and it only exists if the history
    survives being cleared.

    ?resolve=12 marks one handled.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import alerts as alert_svc
    from models import SystemAlert

    rid = request.args.get("resolve")
    if rid and rid.isdigit():
        who = getattr(user, "email", None) or "admin"
        alert_svc.resolve(int(rid), by=who)

    rows = alert_svc.open_alerts()
    return jsonify({
        "open": len(rows),
        "critical": sum(1 for r in rows if r.severity == "critical"),
        "alert_recipients": len([
            n for n in (os.environ.get("ADMIN_ALERT_PHONE") or "")
            .replace(";", ",").split(",") if n.strip()]),
        "alerts": [{
            "id": r.id, "system": r.system, "kind": r.kind,
            "severity": r.severity, "detail": r.detail,
            "count": r.count,
            "first_seen": utc_iso(r.first_seen),
            "last_seen": utc_iso(r.last_seen),
        } for r in rows],
        "recently_resolved": [{
            "system": r.system, "kind": r.kind, "count": r.count,
            "resolved_by": r.resolved_by,
            "resolved_at": utc_iso(r.resolved_at),
        } for r in SystemAlert.query.filter_by(resolved=True)
            .order_by(SystemAlert.resolved_at.desc()).limit(10).all()],
    })


@app.route("/api/admin/operations")
@login_required
def api_admin_operations():
    """
    The numbers that say whether this is working, and what it owes.

    ACCOUNTS PAYABLE IS THE ONE TO WATCH. The wallet is prepaid, so every
    unspent balance is a Smackagram somebody has already paid for and not
    yet received. It is a liability, not revenue - and counting it as
    income is how prepaid businesses get into trouble.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import admin_service
    return jsonify(admin_service.operations_summary())


@app.route("/api/admin/terms-acceptances")
@login_required
def api_admin_terms():
    """
    Who agreed to what, and when.

    This is the record a chargeback is answered with: a timestamp, an
    address, and which version of the terms was in force. "They agreed
    when they signed up" is a weaker answer than "they agreed at 19:42 on
    the day they paid, to these terms".

    Anything marked purchase-unticked is a payment where the box did not
    come through - worth looking at rather than assuming.
    """
    user, err = _require_admin()
    if err:
        return err
    from models import TermsAcceptance
    rows = (TermsAcceptance.query
            .order_by(TermsAcceptance.accepted_at.desc()).limit(100).all())
    return jsonify({
        "current_version": TERMS_VERSION,
        "total": TermsAcceptance.query.count(),
        "unticked": TermsAcceptance.query.filter_by(
            context="purchase-unticked").count(),
        "recent": [{
            "when": utc_iso(r.accepted_at), "user_id": r.user_id,
            "context": r.context, "version": r.terms_version, "ip": r.ip,
        } for r in rows],
    })


def _oldest_open_days():
    """
    How long the longest-waiting ticket has been sitting.

    The single most useful number on a support screen. A count of open
    tickets says how much work there is; this says whether anybody is
    being ignored - and one ticket at nine days is a worse problem than
    nine tickets from this morning.
    """
    from models import SupportTicket
    t = (SupportTicket.query.filter_by(status="open")
         .order_by(SupportTicket.created_at.asc()).first())
    if not t or not t.created_at:
        return None
    return (datetime.utcnow() - t.created_at).days


def _mail_providers():
    """Whether a reply can actually be sent, so the panel can say so."""
    try:
        from services import mail
        return mail.configured()
    except Exception:
        return []


@app.route("/api/admin/support")
@login_required
def api_admin_support():
    """
    Every support ticket, open ones first.

    ?status=open      only unresolved
    ?status=done      only closed
    """
    user, err = _require_admin()
    if err:
        return err
    from models import SupportTicket

    q = SupportTicket.query
    want = request.args.get("status")
    if want in ("open", "done"):
        q = q.filter(SupportTicket.status == want)

    rows = q.order_by(SupportTicket.status.asc(),
                      SupportTicket.created_at.desc()).limit(200).all()

    # All replies for these tickets in one query rather than one per
    # ticket - two hundred tickets should not be two hundred round trips.
    from models import SupportReply
    reply_map = {}
    if rows:
        ids = [t.id for t in rows]
        for r in SupportReply.query.filter(
                SupportReply.ticket_id.in_(ids)).all():
            reply_map.setdefault(r.ticket_id, []).append(r)

    return jsonify({
        "total": SupportTicket.query.count(),
        "open": SupportTicket.query.filter_by(status="open").count(),
        # BROKEN DOWN BY TOPIC, so a pattern is visible without reading
        # every ticket. Four "never arrived" in a morning is a delivery
        # problem, not four customers - and that distinction only shows
        # up in a count.
        "by_topic": {
            topic: SupportTicket.query.filter_by(
                topic=topic, status="open").count()
            for topic in SUPPORT_TOPICS
            if SupportTicket.query.filter_by(
                topic=topic, status="open").count()
        },
        # The ones that cost money or reputation if they sit. Surfaced
        # separately so they are not buried under general questions.
        "urgent": SupportTicket.query.filter(
            SupportTicket.status == "open",
            SupportTicket.topic.in_([
                "My Smackagram never arrived",
                "I was charged incorrectly",
                "Smacky was too aggressive (explicit content)",
                "I received a Smackagram and want it to stop",
            ])).count(),
        "oldest_open_days": _oldest_open_days(),
        "mail_providers": _mail_providers(),
        "tickets": [{
            "id": t.id,
            "name": f"{t.first_name} {t.last_name}".strip(),
            "email": t.email,
            "phone": t.phone,
            "topic": t.topic,
            "message": t.message,
            # A one-line version for the list, so somebody can scan
            # twenty tickets without opening any of them.
            "summary": (t.message or "")[:110]
                       + ("..." if len(t.message or "") > 110 else ""),
            "status": t.status,
            "user_id": t.user_id,
            "when": utc_iso(t.created_at),
            "age_days": ((datetime.utcnow() - t.created_at).days
                         if t.created_at else None),
            "resolution": t.resolution,
            "completed_by": t.completed_by,
            "completed_at": utc_iso(t.completed_at),
            "replies": [{
                "body": r.body,
                "by": r.sent_by,
                "channel": getattr(r, "channel", "email"),
                "delivered": bool(r.delivered),
                "error": r.error,
                "when": utc_iso(r.sent_at),
            } for r in SupportReply.query.filter_by(ticket_id=t.id)
                .order_by(SupportReply.sent_at.asc()).all()],
        } for t in rows],
    })


@app.route("/api/admin/support/<int:ticket_id>/reply", methods=["POST"])
@login_required
def api_admin_support_reply(ticket_id):
    """
    Email somebody about their ticket, from support@smackagram.com.

    The reply is STORED whether or not the mail lands. A failed send that
    left no trace is worse than a visible failure - the customer waits for
    something that never left the building and nobody knows.

    Does not close the ticket. Answering and resolving are different
    things, and plenty of replies are questions.
    """
    user, err = _require_admin()
    if err:
        return err

    d = request.get_json(silent=True) or {}
    body = (d.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Nothing to send."}), 400

    from models import SupportTicket, SupportReply
    t = SupportTicket.query.get(ticket_id)
    if not t:
        return jsonify({"error": "No such ticket"}), 404

    from services import email_service
    who = getattr(user, "email", None) or getattr(user, "username", "admin")

    # Matches the notification's subject family so a thread about
    # ticket 12 reads "Smackagram Support Ticket #12" end to end.
    subject = f"Re: Smackagram Support Ticket #{t.id}"
    # Their original message is quoted underneath so the reply makes sense
    # on its own - somebody reading it a week later should not have to
    # remember what they asked.
    full = (f"{body}\n\n"
            f"---\n"
            f"You wrote to us about: {t.topic}\n\n"
            f"{t.message}\n\n"
            f"---\n"
            f"Reply to this email and it comes straight back to us.\n"
            f"Reference #{t.id}")

    # Sent in the foreground here ON PURPOSE, unlike everywhere else.
    #
    # Somebody clicking reply needs to know whether it went. A background
    # send would return "queued" and leave them thinking a customer was
    # answered when the mail may have bounced.
    #
    # The eight-second timeout keeps the worst case short.
    # EMAIL OR TEXT, whichever was asked for.
    #
    # Text is the better channel for short answers - people read a text in
    # a minute and an email in a day - but it is BLOCKED until the A2P
    # campaign is approved, so it will fail for now. The failure is
    # recorded on the reply rather than swallowed, so it is obvious which
    # ones did not land.
    channel = (d.get("channel") or "email").lower()

    if channel == "text":
        if not t.phone:
            return jsonify({"error": "No phone number on this ticket - "
                                     "reply by email instead."}), 400
        try:
            from services import twilio_service
            # No quoted original here: a text has no room for it, and
            # the ticket number tells them what it is about.
            twilio_service.send_sms(
                t.phone,
                f"Smackagram support (#{t.id}): {body[:300]}")
            ok, detail = True, "sent by text"
        except Exception as e:
            ok, detail = False, f"text failed: {e}"
    else:
        # Both providers tried before giving up. email_service (SMTP) is
        # kept as a third fallback for when the instance is paid and
        # SMTP works again.
        from services import mail
        ok, detail = mail.send(t.email, subject, full)
        if not ok:
            ok, detail = email_service.send(t.email, subject, full)

    r = SupportReply(ticket_id=t.id, body=body, sent_by=who,
                     channel=channel,
                     delivered=bool(ok),
                     error=(None if ok else str(detail)[:300]))
    db.session.add(r)
    db.session.commit()

    if not ok:
        print(f"[support] reply to #{t.id} FAILED: {detail}", flush=True)
        return jsonify({"error": f"Saved, but the email did not send: "
                                 f"{detail}", "stored": True}), 502

    print(f"[support] replied to #{t.id} ({t.email}) by {who}", flush=True)
    return jsonify({"ok": True, "ticket": t.id, "sent_to": t.email})


@app.route("/api/admin/support/<int:ticket_id>/complete", methods=["POST"])
@login_required
def api_admin_support_complete(ticket_id):
    """
    Close a ticket, recording WHO closed it and HOW.

    The resolution note is required. A ticket marked done with no
    explanation is the same as no record - somebody looking at it in three
    months learns nothing, and if the customer comes back there is no way
    to know what they were told.
    """
    user, err = _require_admin()
    if err:
        return err

    d = request.get_json(silent=True) or {}
    note = (d.get("resolution") or "").strip()
    if not note:
        return jsonify({"error": "Say what was done. A ticket closed with no "
                                 "note is the same as no record."}), 400

    from models import SupportTicket
    t = SupportTicket.query.get(ticket_id)
    if not t:
        return jsonify({"error": "No such ticket"}), 404

    t.status = "done"
    t.resolution = note[:4000]
    t.completed_by = getattr(user, "email", None) or getattr(user, "username",
                                                             "admin")
    t.completed_at = datetime.utcnow()
    db.session.commit()

    print(f"[support] #{t.id} closed by {t.completed_by}", flush=True)
    return jsonify({"ok": True, "id": t.id, "completed_by": t.completed_by})


@app.route("/api/admin/id-collisions")
@login_required
def api_admin_id_collisions():
    """
    Do any Order and Smackagram share a primary key?

    THIS MATTERS BECAUSE OF TWILIO.

    Both tables have their own auto-incrementing id starting at 1, so
    Order 47 and Smackagram 47 can both exist. If a webhook URL carries
    only the number and the handler guesses which table to look in, a call
    status can be written against the wrong record entirely - the wrong
    person marked as called, the wrong order charged or refunded.

    Zero is the answer you want. Anything above zero means the overlap
    already exists and webhook URLs need namespacing before real money
    moves through this.

    Read-only. Counts rows, changes nothing.
    """
    user, err = _require_admin()
    if err:
        return err

    from sqlalchemy import text
    from models import Order, Smackagram

    # Table names read from the models rather than typed out, so this
    # cannot quietly drift if either is ever renamed.
    ot, st = Order.__tablename__, Smackagram.__tablename__

    out = {}
    try:
        row = db.session.execute(text(
            f"SELECT COUNT(*) FROM {ot} o "
            f"JOIN {st} s ON o.id = s.id")).scalar()
        out["collisions"] = int(row or 0)
    except Exception as e:
        return jsonify({"error": f"query failed: {e}"}), 500

    # Useful context either way - how far each table has counted.
    for table in (ot, st):
        try:
            out[f"{table}_rows"] = int(db.session.execute(text(
                f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
            out[f"{table}_max_id"] = int(db.session.execute(text(
                f"SELECT COALESCE(MAX(id), 0) FROM {table}")).scalar() or 0)
        except Exception:
            pass

    # Whether the collision MATTERS depends on the webhook URLs, not on
    # the count. Namespaced URLs make an overlap harmless.
    from flask import current_app
    bare = [str(r) for r in current_app.url_map.iter_rules()
            if "<int:record_id>" in str(r)
            and "<record_type>" not in str(r)
            and "recording-done" not in str(r)]
    out["untyped_webhook_routes"] = bare

    if bare:
        out["verdict"] = ("COLLISIONS EXIST and there are webhook routes "
                          "that take a bare id: " + ", ".join(bare) +
                          ". Those can resolve to the wrong record.")
    elif out["collisions"]:
        out["verdict"] = ("Collisions exist, but every webhook URL carries "
                          "an explicit record type - so nothing looks up by "
                          "bare id and the overlap is harmless. The one "
                          "remaining bare route only hangs up and never "
                          "resolves a record.")
    else:
        out["verdict"] = "No collisions and no untyped routes."
    return jsonify(out)


@app.route("/api/admin/sources")
@login_required
def api_admin_sources():
    """
    Which data source is answering, and which is not.

    After a week in which the wrong API was being called entirely, ESPN
    started refusing this server's address, and WNBA turned out not to
    exist in the paid provider - this exists so the answer to "where is
    the data coming from" takes one look rather than an investigation.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import espn_gate, highlightly, balldontlie

    day = highlightly.sport_day(1)
    # The gate reports nothing until a source has been used in THIS
    # process - a fresh worker has no history. Say so rather than showing
    # an empty object that reads like a fault.
    _gate = espn_gate.status()
    out = {"date": day,
           "gate": _gate or "no requests yet since the last restart",
           "leagues": {}}
    for lg in ("mlb", "nfl", "nba", "nhl", "ncaaf", "ncaab", "wnba"):
        row = {}
        try:
            row["highlightly"] = (
                "not covered" if lg in highlightly.NOT_COVERED
                else len(highlightly.finals(lg, day) or {}))
        except Exception as e:
            row["highlightly"] = f"error: {e}"[:60]
        row["balldontlie"] = ("available" if balldontlie.covers(lg)
                              else "not covered")
        out["leagues"][lg] = row

    out["espn"] = ("Returns 403 to this server on the first request - an "
                   "IP block rather than rate limiting, confirmed by the "
                   "same URL returning 200 from a laptop. Treat as gone.")
    return jsonify(out)


@app.route("/api/admin/espn-gate")
@login_required
def api_admin_espn_gate():
    """
    Is the gate open, how much budget is left, and has ESPN pushed back.

    Add ?reset=1 to clear a cooldown by hand - useful if you know the
    throttle has passed and do not want to wait it out.
    """
    user, err = _require_admin()
    if err:
        return err
    from services import espn_gate
    # ?reset=1 clears everything, ?reset=espn clears one source.
    r = request.args.get("reset")
    if r:
        espn_gate.reset(None if r == "1" else r)
    return jsonify(espn_gate.status())


@app.route("/api/admin/injury-probe")
@login_required
def api_admin_injury_probe():
    """
    What ESPN actually returns for injuries, from several possible URLs.

    I have been guessing at the shape of this feed and getting it wrong -
    my sandbox cannot reach ESPN, so every parser I write for it is written
    blind. This asks the real thing and shows the raw answer.

    Read-only. Fetches and prints; changes nothing.
    """
    user, err = _require_admin()
    if err:
        return err

    import json as _json
    from urllib.request import Request, urlopen

    team = (request.args.get("team") or "Yankees").strip()
    try:
        from services import team_state
        t = team_state.find_team(team)
    except Exception as e:
        return jsonify({"error": f"team lookup failed: {e}"}), 500
    if not t:
        return jsonify({"error": f"no team matched '{team}'"}), 404

    sport, path = team_state.LEAGUES[t["league"]]
    base = "https://site.api.espn.com/apis/site/v2/sports"
    core = "https://sports.core.api.espn.com/v2/sports"

    # Every URL ESPN might expose this under. One of them is right.
    candidates = [
        f"{base}/{sport}/{path}/teams/{t['id']}/injuries",
        f"{base}/{sport}/{path}/injuries",
        f"{base}/{sport}/{path}/teams/{t['id']}?enable=roster,injuries",
        f"{core}/{sport}/leagues/{path}/teams/{t['id']}/injuries",
    ]

    # THE LEAGUE DOCUMENT, ONE LEVEL DEEPER.
    #
    # The first probe showed me the CLUB level - id, displayName, injuries -
    # but never what is inside an individual injury. So I still had to guess
    # where the player's name lives, and guessed wrong again.
    #
    # This finds the requested team inside the league document and prints
    # one entire injury record, untouched.
    deep = {}
    try:
        url = f"{base}/{sport}/{path}/injuries"
        req = Request(url, headers={"User-Agent": "smackagram/1.0"})
        with urlopen(req, timeout=20) as r:
            d = _json.loads(r.read().decode())
        clubs = d.get("injuries") or []
        deep["clubs_found"] = len(clubs)
        deep["club_ids"] = [str(c.get("id")) for c in clubs[:6]
                            if isinstance(c, dict)]
        deep["looking_for_id"] = str(t["id"])
        mine = None
        for c in clubs:
            if isinstance(c, dict) and str(c.get("id")) == str(t["id"]):
                mine = c
                break
        if mine is None:
            deep["matched"] = False
            deep["note"] = ("this team's id was not found among the club ids "
                            "above - the ids in this feed may not be team ids")
        else:
            deep["matched"] = True
            items = mine.get("injuries") or []
            deep["injury_count"] = len(items)
            if items:
                deep["ONE_WHOLE_RECORD"] = _json.dumps(items[0])[:2500]
                deep["record_keys"] = sorted(items[0].keys())
    except Exception as e:
        deep["error"] = f"{type(e).__name__}: {e}"

    out = {"team": t, "deep": deep, "tried": []}
    for url in candidates:
        row = {"url": url}
        try:
            req = Request(url, headers={"User-Agent": "smackagram/1.0"})
            with urlopen(req, timeout=10) as r:
                raw = r.read().decode()
            d = _json.loads(raw)
            row["status"] = 200
            row["top_level_keys"] = sorted(d.keys())[:12]
            # Where are the names? Walk a little way in and report shape.
            inj = d.get("injuries")
            if inj is not None:
                row["injuries_type"] = type(inj).__name__
                row["injuries_len"] = len(inj) if hasattr(inj, "__len__") else None
                if isinstance(inj, list) and inj:
                    first = inj[0]
                    row["first_item_keys"] = (sorted(first.keys())[:12]
                                              if isinstance(first, dict) else None)
                    row["first_item_sample"] = _json.dumps(first)[:600]
            row["bytes"] = len(raw)
        except Exception as e:
            row["status"] = f"{type(e).__name__}: {e}"
        out["tried"].append(row)
    return jsonify(out)


@app.route("/api/admin/roster-audit")
@login_required
def api_admin_roster_audit():
    """
    Every team in a league at once, with its roster count and who is listed
    as injured.

    Built because checking this by hand is not a plan - there are thirty MLB
    clubs and a hundred and thirty in college football. One page tells you
    whether the injured players are coming through everywhere or nowhere.

    Slow on purpose: it makes a real call per team. Run it when something
    looks wrong, not on a schedule.
    """
    user, err = _require_admin()
    if err:
        return err

    league = (request.args.get("league") or "mlb").lower()
    try:
        from services import team_state
        teams = team_state._teams(league)
    except Exception as e:
        return jsonify({"error": f"unknown league: {e}"}), 400

    try:
        limit = min(int(request.args.get("limit", 8)), 40)
    except (TypeError, ValueError):
        limit = 8

    out, thin, no_injuries = [], 0, 0
    for t in teams[:limit]:
        try:
            names = team_state.roster(t.get("nick") or t.get("name"), league)
        except Exception:
            names = []
        hurt = [x["name"] for x in names if x.get("injured")]
        row = {"team": t.get("nick") or t.get("name"),
               "players": len(names), "injured": len(hurt),
               "injured_names": hurt[:5]}
        if len(names) < 10:
            row["flag"] = "roster looks short"; thin += 1
        if not hurt:
            no_injuries += 1
        out.append(row)

    return jsonify({
        "league": league,
        "checked": len(out),
        "teams": out,
        # The number that matters. Some teams genuinely have nobody hurt;
        # ALL of them having nobody means the injury feed is not parsing.
        "teams_with_no_injuries": no_injuries,
        "short_rosters": thin,
        "verdict": ("the injury feed is not working - no team has anybody hurt"
                    if no_injuries == len(out) and out else
                    "short rosters - a position group is not parsing"
                    if thin else "looks healthy"),
    })


@app.route("/api/roster")
def api_roster():
    """
    The players on one team, for the name picker.

    Only this team's roster - they have already chosen the team, so it is
    25-50 names rather than every player in every league.

    The point is that a name can only be CHOSEN, never typed. A misspelled
    or invented player reaching the generator produces a call about somebody
    who does not exist, and nobody would find out until it had been said
    down the phone.

    Open, like the team list already is - it is public roster information
    and requiring a login to see a dropdown would be silly.
    """
    team = (request.args.get("team") or "").strip()
    # The picker already knows which league the team is in, so it sends it.
    # Without it, an unrecognised name is searched across all fourteen
    # leagues one after another - and the college lists run to hundreds of
    # teams each, so somebody would sit waiting for several seconds.
    league = (request.args.get("league") or "").strip().lower() or None
    if not team:
        return jsonify({"players": []})
    # SAY WHAT HAPPENED AT EACH STEP.
    #
    # This has returned an empty list three times for three different
    # reasons - a throttle, a poisoned cache, a browser cache - and each
    # time the response looked identical. Guessing from the outside has
    # cost several rounds; ?debug=1 reports which step actually stopped.
    # ALWAYS ON, temporarily.
    #
    # ?debug=1 was not reaching this code - something between the browser
    # and Flask is dropping the parameter, and chasing that is a second
    # mystery on top of the first. The trace costs nothing and comes out
    # once the roster is fixed.
    debug = True
    trace = {}
    try:
        from services import team_state, espn_gate
        if debug:
            trace["gate_before"] = espn_gate.status()
            t = team_state.find_team(team, league)
            trace["find_team"] = t
            trace["leagues_searched"] = (
                [league] if league in team_state.LEAGUES
                else list(team_state.LEAGUES))
            # How many teams did the first league actually return?
            first = trace["leagues_searched"][0]
            got = team_state._teams(first)
            trace["teams_in_" + first] = len(got)
            trace["sample"] = got[0] if got else None
        players = team_state.roster(team, league=league)
        if debug:
            trace["gate_after"] = espn_gate.status()
            trace["players_found"] = len(players)
    except Exception as e:
        import traceback
        print(f"[roster] {team}: {e}", flush=True)
        traceback.print_exc()
        if debug:
            trace["exception"] = f"{type(e).__name__}: {e}"
        players = []

    if debug:
        return jsonify({"team": team, "players": players, "trace": trace})
    resp = jsonify({"team": team, "players": players})
    # NEVER CACHE AN EMPTY ANSWER.
    #
    # A roster changes at most daily, so holding a good one in the browser
    # makes the picker instant on the second use. But caching an EMPTY one
    # for an hour means a temporary failure - ESPN throttling us, say -
    # keeps showing the person no players long after the problem is fixed.
    #
    # That happened: the roster looked broken for an hour after the fix was
    # deployed, because the browser never asked again. The server showed
    # zero requests, which made it look like a completely different bug.
    if players:
        resp.headers["Cache-Control"] = "public, max-age=3600"
    else:
        resp.headers["Cache-Control"] = "no-store"
    return resp


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
    # NOT alerted, deliberately. The log already shows dozens of these an
    # hour from bots probing for /wp-admin/install.php, and alerting on
    # them would bury a real failure in noise within a day.
    #
    # A 404 on a path the site actually links to is a different matter -
    # but that is caught by testing, not by an alert at three in the
    # morning.
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    # A CRASH SHOULD NOT BE SILENT.
    #
    # This showed a page and vanished. No log, no record, nothing - so a
    # crash in production was invisible unless somebody happened to be
    # watching the Render log at that moment.
    #
    # The traceback matters more than the message: "TypeError on
    # /auto-smack" is something you can find; "something went wrong" is
    # not.
    try:
        import traceback
        tb = traceback.format_exc()
        where = request.path
        print(f"[500] {where}\n{tb}", flush=True)

        from services import alerts
        # The PATH is the alert key, not the message. Ten different errors
        # on one broken page is one problem worth one alert; the same
        # error on ten pages is ten problems.
        alerts.record("site", f"error:{where[:40]}",
                      tb.strip().split("\n")[-1][:200],
                      severity="critical")
    except Exception:
        # An error handler that raises its own error takes the site down
        # in a way nothing can report. Whatever happens above, the page
        # below still renders.
        pass

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
