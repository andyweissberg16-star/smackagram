from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Scenario(db.Model):
    """A pre-recorded or scripted prank scenario in the library."""
    __tablename__ = "scenarios"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))
    audio_url = db.Column(db.String(500))          # pre-recorded clip on S3, null if custom-TTS-only
    is_custom_text = db.Column(db.Boolean, default=False)  # True = "write your own" option
    active = db.Column(db.Boolean, default=True)


class Order(db.Model):
    """An immediate 'send it now' smackagram — the simple v1 flow."""
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey("scenarios.id"))
    custom_message = db.Column(db.Text, nullable=True)   # if using "write your own"
    recipient_name = db.Column(db.String(120))
    recipient_phone = db.Column(db.String(20))
    consent_confirmed = db.Column(db.Boolean, default=False)

    price_cents = db.Column(db.Integer, default=200)     # $2 bundle default, $1 call-only option
    includes_recording = db.Column(db.Boolean, default=True)

    stripe_payment_intent_id = db.Column(db.String(120))
    payment_status = db.Column(db.String(20), default="pending")  # pending, captured, failed

    twilio_call_sid = db.Column(db.String(120), nullable=True)
    call_status = db.Column(db.String(20), default="not_sent")    # not_sent, ringing, delivered, no_answer, failed
    recording_url = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Smackagram(db.Model):
    """
    A 'locked and loaded' conditional smackagram — armed against a live game,
    fires only if the target team loses. Card is authorized but not captured
    until the outcome is known.
    """
    __tablename__ = "smackagrams"

    id = db.Column(db.Integer, primary_key=True)

    # Game + condition
    game_id = db.Column(db.String(64), nullable=False)       # ID from the sports data API
    sport = db.Column(db.String(20), nullable=False, default="nfl")  # nfl, nba, mlb, nhl, ncaaf
    home_team = db.Column(db.String(80))
    away_team = db.Column(db.String(80))
    target_team = db.Column(db.String(80), nullable=False)   # the team that must lose
    game_start_time = db.Column(db.DateTime, nullable=False)

    # Scenario + recipient (same shape as Order)
    scenario_id = db.Column(db.Integer, db.ForeignKey("scenarios.id"))
    custom_message = db.Column(db.Text, nullable=True)
    recipient_name = db.Column(db.String(120))
    recipient_phone = db.Column(db.String(20))
    consent_confirmed = db.Column(db.Boolean, default=False)

    price_cents = db.Column(db.Integer, default=200)

    # Stripe — authorized now, captured/canceled once the game resolves
    stripe_payment_intent_id = db.Column(db.String(120))
    auth_status = db.Column(db.String(20), default="authorized")  # authorized, captured, canceled, expired

    # Outcome + delivery
    status = db.Column(db.String(20), default="armed")  # armed, fired, released, canceled
    twilio_call_sid = db.Column(db.String(120), nullable=True)
    recording_url = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
