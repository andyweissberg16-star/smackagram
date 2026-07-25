import os
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv

from models import db, Scenario, Order, Smackagram
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options, generator_constants, call_audio_service
from scheduler import start_scheduler

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smackagram.db")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
db.init_app(app)

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
    exempt_prefixes = ("/webhook/stripe", "/call-instructions/", "/call-status/", "/recording-ready/", "/recording-done/", "/static/")
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
    return render_template("index.html", scenarios=scenarios)


# ---------- Immediate "send it now" flow ----------

@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.json
    price = 200 if data.get("include_recording", True) else 100

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    order = Order(
        scenario_id=data.get("scenario_id"),
        custom_message=data.get("custom_message"),
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        price_cents=price,
        includes_recording=data.get("include_recording", True),
    )
    db.session.add(order)
    db.session.commit()  # commit first so order.id exists for the checkout metadata

    session = stripe_service.create_checkout_session(
        order_id=order.id,
        amount_cents=price,
        base_url=os.environ.get("BASE_URL", request.url_root.rstrip("/")),
    )
    order.stripe_payment_intent_id = session.id
    db.session.commit()

    return jsonify({"checkout_url": session.url})


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
                call_sid = twilio_service.place_prank_call(order.id, order.recipient_phone, record=True)
                order.twilio_call_sid = call_sid
                order.call_status = "ringing"
                db.session.commit()
            except Exception as e:
                order.call_status = "failed"
                db.session.commit()
                print(f"Call failed for order {order.id}: {e}")

    return jsonify({"received": True})


@app.route("/api/generate-trash-talk", methods=["POST"])
def generate_trash_talk():
    data = request.json
    team = data.get("team", "").strip()
    recipient_name = data.get("recipient_name", "").strip()

    if not team or not recipient_name:
        return jsonify({"error": "Both team and recipient name are required"}), 400

    line = trash_talk_service.generate_trash_talk(team=team, recipient_name=recipient_name)
    return jsonify({"generated_text": line})


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

    # fall back to live resolution only if somehow nothing was pre-cached
    # (e.g. this route got hit directly without going through the webhook)
    audio_urls = _pending_call_audio.pop(record_id, None) or call_audio_service.resolve_audio_url(order, os.environ.get("BASE_URL", request.url_root.rstrip("/")))

    should_record = getattr(order, "includes_recording", True)
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
def locked_n_loaded_page():
    return render_template("locked_n_loaded.html")


@app.route("/locked-n-loaded/success")
def locked_n_loaded_success():
    session_id = request.args.get("session_id")
    return render_template("locked_n_loaded_success.html", session_id=session_id)


@app.route("/api/games/upcoming")
def upcoming_games():
    """Powers the game picker — only games within 48h. ?sport=nfl|nba|mlb|nhl|ncaaf&team=yankees"""
    sport = request.args.get("sport", "nfl")
    team_query = request.args.get("team", "").strip() or None
    return jsonify(sports_service.get_upcoming_games(sport=sport, hours_ahead=48, team_query=team_query))


@app.route("/api/smackagrams", methods=["POST"])
def arm_smackagram():
    """
    Locks in a smackagram against a future game. Uses the same hosted-
    Checkout flow as regular orders, but with capture_method='manual' — the
    card is authorized (held), not charged. It only actually gets charged
    if the target team loses; otherwise the hold is released with nothing
    charged. See scheduler.py for the polling job that resolves this once
    the game ends.
    """
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

    smackagram = Smackagram(
        game_id=data["game_id"],
        sport=data.get("sport", "nfl"),
        home_team=data["home_team"],
        away_team=data["away_team"],
        target_team=data["target_team"],
        game_start_time=game_start,
        mode=mode,
        custom_message=data.get("custom_message") if mode == "custom" else None,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
    )
    db.session.add(smackagram)
    db.session.commit()  # commit first so smackagram.id exists for the checkout metadata

    session = stripe_service.create_authorized_checkout_session(
        smackagram_id=smackagram.id,
        amount_cents=smackagram.price_cents,
        base_url=os.environ.get("BASE_URL", request.url_root.rstrip("/")),
    )
    # store the Checkout Session id for now — the webhook swaps this for the
    # actual PaymentIntent id once checkout completes, since that's what
    # capture_hold()/release_hold() actually need
    smackagram.stripe_payment_intent_id = session.id
    db.session.commit()

    return jsonify({"checkout_url": session.url})


# ---------- Twilio status callbacks ----------

@app.route("/call-status/<int:record_id>", methods=["POST"])
def call_status(record_id):
    status = request.form.get("CallStatus")
    order = Order.query.get(record_id)
    if order:
        order.call_status = status
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


with app.app_context():
    db.create_all()

# CRITICAL: start_scheduler() must run unconditionally here, not just
# inside `if __name__ == "__main__"` — that block never executes under
# gunicorn (which imports this file as a module rather than running it as
# a script), so the background job that resolves locked-and-loaded
# smackagrams was never actually running in production. Safe to start here
# since Render is configured with WEB_CONCURRENCY=1 (a single process), so
# this won't create duplicate scheduler instances.
start_scheduler(app)

if __name__ == "__main__":
    app.run(debug=True)
