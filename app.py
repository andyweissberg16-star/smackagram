import os
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv

from models import db, Scenario, Order, Smackagram
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options, generator_constants
from scheduler import start_scheduler

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smackagram.db")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
db.init_app(app)

_pending_call_audio = {}


@app.before_request
def require_site_password():
    exempt_prefixes = ("/webhook/stripe", "/call-instructions/", "/call-status/", "/recording-ready/", "/recording-done/")
    if request.path.startswith(exempt_prefixes):
        return

    site_password = os.environ.get("SITE_PASSWORD")
    if not site_password:
        return

    auth = request.authorization
    if not auth or auth.password != site_password:
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Smackagram"'},
        )


@app.route("/")
def home():
    scenarios = Scenario.query.filter_by(active=True).all()
    return render_template("index.html", scenarios=scenarios)


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
    db.session.commit()

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
        order_id = int(session["metadata"]["order_id"])
        order = Order.query.get(order_id)

        if order and order.payment_status != "captured":
            order.payment_status = "captured"
            db.session.commit()

            try:
                audio_urls = resolve_audio_url(order)
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
    line = trash_talk_service.generate_trash_talk(team=data["team"])
    return jsonify({"generated_text": line})


@app.route("/api/voice-options")
def get_voice_options():
    return jsonify(voice_options.list_voice_options())


@app.route("/api/voice-sample/<voice_key>")
def voice_sample(voice_key):
    voice_id = voice_options.get_voice_id(voice_key)
    preview_url = elevenlabs_service.get_voice_preview_url(voice_id)
    return jsonify({"preview_url": preview_url})


@app.route("/api/preview-audio", methods=["POST"])
def preview_audio():
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
    sfx_url = elevenlabs_service.generate_sound_effect(generator_constants.SLAP_SFX_PROMPT)
    tagline_url = elevenlabs_service.generate_audio_url(generator_constants.CLOSING_TAGLINE, voice_id=voice_id)
    rate_limiter.record_hit(identifier)

    return jsonify({
        "audio_sequence": [message_url, sfx_url, tagline_url],
        "previews_remaining": rate_limiter.previews_remaining(identifier),
    })


@app.route("/call-instructions/<int:record_id>", methods=["GET", "POST"])
def call_instructions(record_id):
    order = Order.query.get(record_id) or Smackagram.query.get(record_id)

    audio_urls = _pending_call_audio.pop(record_id, None) or resolve_audio_url(order)

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
    twiml = "<Response><Hangup/></Response>"
    return Response(twiml, mimetype="text/xml")


def resolve_audio_url(record):
    voice_id = voice_options.get_voice_id(getattr(record, "voice_key", None) or voice_options.DEFAULT_VOICE_KEY)

    if record.custom_message:
        message_url = elevenlabs_service.generate_audio_url(record.custom_message, voice_id=voice_id)
    else:
        scenario = Scenario.query.get(record.scenario_id)
        message_url = scenario.audio_url

    sfx_url = elevenlabs_service.generate_sound_effect(generator_constants.SLAP_SFX_PROMPT)
    tagline_url = elevenlabs_service.generate_audio_url(generator_constants.CLOSING_TAGLINE, voice_id=voice_id)

    return [message_url, sfx_url, tagline_url]


@app.route("/api/games/upcoming")
def upcoming_games():
    sport = request.args.get("sport", "nfl")
    return jsonify(sports_service.get_upcoming_games(sport=sport, hours_ahead=48))


@app.route("/api/smackagrams", methods=["POST"])
def arm_smackagram():
    data = request.json

    game_start = datetime.fromisoformat(data["game_start_time"])
    if game_start > datetime.utcnow() + timedelta(hours=48):
        return jsonify({"error": "Games can only be armed within 48 hours of kickoff"}), 400

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    intent = stripe_service.create_authorized_hold(200)

    smackagram = Smackagram(
        game_id=data["game_id"],
        sport=data.get("sport", "nfl"),
        home_team=data["home_team"],
        away_team=data["away_team"],
        target_team=data["target_team"],
        game_start_time=game_start,
        scenario_id=data.get("scenario_id"),
        custom_message=data.get("custom_message"),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        stripe_payment_intent_id=intent.id,
    )
    db.session.add(smackagram)
    db.session.commit()

    return jsonify({
        "smackagram_id": smackagram.id,
        "client_secret": intent.client_secret,
        "status": "armed",
    })


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

if __name__ == "__main__":
    start_scheduler()
    app.run(debug=True)
