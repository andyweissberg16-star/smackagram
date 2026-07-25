import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, Smackagram, Scenario
from services import sports_service, stripe_service, twilio_service, trash_talk_service, call_audio_service, content_moderation


def check_armed_smackagrams():
    """
    Runs every few minutes. For every 'armed' smackagram tied to a game
    that has gone final, decide whether to fire (capture + call) or
    release (cancel hold, no charge).
    """
    armed = Smackagram.query.filter_by(status="armed").all()
    print(f"[scheduler] check_armed_smackagrams running — {len(armed)} armed smackagram(s) to check")
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
        base_url = os.environ["BASE_URL"]

        for s in matching:
            if s.target_team == loser:
                # condition met — target team lost, fire the smackagram
                try:
                    if s.mode == "auto_summary":
                        # generate the recap roast now, using real facts from
                        # the game that just ended — this is the "set it and
                        # walk away, get a roast grounded in what actually
                        # happened" feature
                        summary = sports_service.get_game_summary(s.game_id, sport=s.sport)
                        s.custom_message = trash_talk_service.generate_game_recap_roast(
                            team=s.target_team,
                            recipient_name=s.recipient_name,
                            key_facts=summary["key_facts"],
                            sensitivity=s.sensitivity,
                        )
                    # else mode == "custom" — s.custom_message was already
                    # written by the buyer at arm-time, nothing to generate,
                    # and was already checked for safety at arm-time.

                    # Safety backstop — even though AI-generated content has
                    # guardrails baked into its own prompt, this is the same
                    # check applied to every user-typed message elsewhere,
                    # run here as defense-in-depth before anything gets
                    # charged or dialed. Every generator, present or future,
                    # should have its final output pass through this same
                    # gate at the point of actually sending/charging.
                    safety = content_moderation.check_message_safety(s.custom_message)
                    if not safety["safe"]:
                        stripe_service.release_hold(s.stripe_payment_intent_id)
                        s.status = "failed"
                        print(f"[safety] Locked smackagram {s.id} blocked at fire-time — reason: {safety['reason']}")
                        s.resolved_at = datetime.utcnow()
                        continue

                    stripe_service.capture_hold(s.stripe_payment_intent_id)
                    audio_urls = call_audio_service.resolve_audio_url(s, base_url)
                    call_sid = twilio_service.place_prank_call(s.id, s.recipient_phone, record=True)
                    s.twilio_call_sid = call_sid
                    s.status = "fired"
                except Exception as e:
                    s.status = "failed"
                    print(f"Locked smackagram {s.id} failed to fire: {e}")
            else:
                # target team won — release the hold, nothing charged
                stripe_service.release_hold(s.stripe_payment_intent_id)
                s.status = "released"
            s.resolved_at = datetime.utcnow()

        db.session.commit()


def start_scheduler(app):
    """
    Takes the Flask app instance so the scheduled job can push an
    application context before touching the database — APScheduler runs
    jobs in a background thread, which has no Flask app context by
    default, and Flask-SQLAlchemy's db.session requires one or every
    query raises "working outside of application context".
    """
    def run_with_context():
        print("[scheduler] job invoked — entering app context now")
        try:
            with app.app_context():
                check_armed_smackagrams()
        except Exception as e:
            import traceback
            print(f"[scheduler] JOB CRASHED: {e}")
            traceback.print_exc()

    scheduler = BackgroundScheduler()
    # TEMPORARY: 30 seconds instead of 3 minutes — purely for fast diagnostic
    # testing right now, to quickly confirm whether the recurring job fires
    # at all, instead of waiting 3+ minutes per uncertain data point. Change
    # back to minutes=3 once confirmed working.
    scheduler.add_job(run_with_context, "interval", seconds=30)
    scheduler.start()
    print("[scheduler] started — DIAGNOSTIC MODE: checking every 30 seconds")

    # Run once immediately on startup too — don't wait for the first
    # interval to elapse. This isolates two different possible failures:
    # if this immediate run works but the recurring one never appears,
    # the problem is with the interval scheduling itself (e.g. the
    # process getting recycled before 3 minutes pass). If even THIS
    # immediate run never prints anything, the problem is inside
    # check_armed_smackagrams or run_with_context itself.
    print("[scheduler] running an immediate check now (not waiting for the first interval)")
    run_with_context()

    return scheduler
