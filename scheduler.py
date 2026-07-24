from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, Smackagram, Scenario
from services import sports_service, stripe_service, twilio_service


def check_armed_smackagrams():
    """
    Runs every few minutes. For every 'armed' smackagram tied to a game
    that has gone final, decide whether to fire (capture + call) or
    release (cancel hold, no charge).
    """
    armed = Smackagram.query.filter_by(status="armed").all()
    if not armed:
        return

    # avoid hitting the API once per row — group by (game_id, sport)
    keys = {(s.game_id, s.sport) for s in armed}

    for game_id, sport in keys:
        result = sports_service.get_game_result(game_id, sport=sport)
        if result is None:
            continue  # game still in progress, check again next run

        matching = [s for s in armed if s.game_id == game_id and s.sport == sport]

        if result["status"] == "postponed":
            for s in matching:
                stripe_service.release_hold(s.stripe_payment_intent_id)
                s.status = "canceled"
                s.resolved_at = datetime.utcnow()
            db.session.commit()
            continue

        if result["status"] == "tie":
            for s in matching:
                stripe_service.release_hold(s.stripe_payment_intent_id)
                s.status = "released"
                s.resolved_at = datetime.utcnow()
            db.session.commit()
            continue

        loser = result["loser"]

        for s in matching:
            if s.target_team == loser:
                # condition met — target team lost, fire the smackagram
                stripe_service.capture_hold(s.stripe_payment_intent_id)
                call_sid = twilio_service.place_prank_call(
                    s.id, s.recipient_phone, record=True
                )
                s.twilio_call_sid = call_sid
                s.status = "fired"
            else:
                # target team won — release the hold, nothing charged
                stripe_service.release_hold(s.stripe_payment_intent_id)
                s.status = "released"
            s.resolved_at = datetime.utcnow()

        db.session.commit()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_armed_smackagrams, "interval", minutes=3)
    scheduler.start()
    return scheduler
