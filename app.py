import os
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv

from models import db, Scenario, Order, Smackagram
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options
from scheduler import start_scheduler

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smackagram.db")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
db.init_app(app)


# ---------- Site-wide password gate ----------
# Set SITE_PASSWORD in Render to lock the whole site behind a simple prompt
# while it's still in development. Leave SITE_PASSWORD unset/blank to make
# the site fully public again (e.g. once you're ready to launch for real).

@app.before_request
def require_site_password():
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

    order = Order(
        scenario_id=data.get("scenario_id"),
        custom_message=data.get("custom_message"),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=data["consent_confirmed"],
        price_cents=price,
        includes_recording=data.get("include_recording", True),
    )

    if not order.consent_confirmed:
        return jsonify({"error": "Consent confirmation required"}), 400

    intent = stripe_service.create_immediate_payment_intent(price)
    order.stripe_payment_intent_id = intent.id
    db.session.add(order)
    db.session.commit()

    return jsonify({"order_id": order.id, "client_secret": intent.client_secret})


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

    audio_url = elevenlabs_service.generate_audio_url(text, voice_id=voice_id)
    rate_limiter.record_hit(identifier)

    return jsonify({
        "audio_url": audio_url,
        "previews_remaining": rate_limiter.previews_remaining(identifier),
    })


@app.route("/call-instructions/<int:record_id>")
def call_instructions(record_id):
    """Twilio hits this the moment the call connects."""
    order = Order.query.get(record_id) or Smackagram.query.get(record_id)
    audio_url = resolve_audio_url(order)
    twiml = twilio_service.build_twiml(audio_url)
    return Response(twiml, mimetype="text/xml")


def resolve_audio_url(record):
    """Pre-recorded clip, or generate TTS on the fly for custom messages."""
    if record.custom_message:
        return elevenlabs_service.generate_audio_url(record.custom_message)
    scenario = Scenario.query.get(record.scenario_id)
    return scenario.audio_url


# ---------- Locked-and-loaded smackagrams ----------

@app.route("/api/games/upcoming")
def upcoming_games():
    """Powers the game picker — only games within 48h. ?sport=nfl|nba|mlb|nhl|ncaaf"""
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

if __name__ == "__main__":
    start_scheduler()  # local dev only — production runs this as a separate worker, see README
    app.run(debug=True)
