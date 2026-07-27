import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, jsonify, Response, url_for
from sqlalchemy import func
import requests
from dotenv import load_dotenv

from models import db, Scenario, Order, Smackagram, ChatPost, ChatRating, Battle, BattleLine, BattleVote, BattleRoundResult
from services import twilio_service, stripe_service, sports_service, elevenlabs_service, trash_talk_service, rate_limiter, voice_options, generator_constants, call_audio_service, content_moderation, team_aliases, chat_team_lists, chat_team_colors
from scheduler import check_armed_smackagrams

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smackagram.db")
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
    return render_template("index.html", scenarios=scenarios)


# ---------- Immediate "send it now" flow ----------

@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.json
    price = 200 if data.get("include_recording", True) else 100

    if not data.get("consent_confirmed"):
        return jsonify({"error": "Consent confirmation required"}), 400

    custom_message = data.get("custom_message", "")
    safety = content_moderation.check_message_safety(custom_message)
    if not safety["safe"]:
        print(f"[safety] blocked order attempt — reason: {safety['reason']}")
        return jsonify({"error": "This message can't be sent — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    order = Order(
        scenario_id=data.get("scenario_id"),
        custom_message=custom_message,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        price_cents=price,
        includes_recording=data.get("include_recording", True),
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
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
def generate_trash_talk():
    data = request.json
    team = data.get("team", "").strip()
    recipient_name = data.get("recipient_name", "").strip()
    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)

    if not team or not recipient_name:
        return jsonify({"error": "Both team and recipient name are required"}), 400

    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    line = trash_talk_service.generate_trash_talk(team=team, recipient_name=recipient_name, sensitivity=sensitivity)
    return jsonify({"generated_text": line})


@app.route("/api/sensitivity-levels")
def get_sensitivity_levels():
    """Powers the sensitivity selector UI on both generator pages."""
    return jsonify(trash_talk_service.SENSITIVITY_LEVELS)


@app.route("/api/smack-lab/respond", methods=["POST"])
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
def locked_n_loaded_page():
    return render_template("locked_n_loaded.html")


@app.route("/send-a-smack")
def send_a_smack_page():
    return render_template("send_a_smack.html")


@app.route("/smack-lab")
def smack_lab_page():
    return render_template("smack_lab.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/contact")
def contact_page():
    return render_template("contact.html")


@app.route("/did-you-get-smacked")
def did_you_get_smacked_page():
    return render_template("did_you_get_smacked.html")


@app.route("/reply/<token>")
def reply_page(token):
    return render_template("reply.html", reply_token=token)


@app.route("/conversation/<int:reply_id>")
def conversation_page(reply_id):
    return render_template("conversation.html", reply_id=reply_id)


@app.route("/api/conversation/<int:reply_id>")
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
def report_chat_post(post_id):
    post = ChatPost.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    post.report_count += 1
    db.session.commit()
    return jsonify({"reported": True})


@app.route("/smack-battle")
def smack_battle_page():
    return render_template("smack_battle.html")


@app.route("/battle/<challenge_code>")
def battle_room_page(challenge_code):
    return render_template("battle_room.html", challenge_code=challenge_code)


def _battle_state_json(battle):
    lines = BattleLine.query.filter_by(battle_id=battle.id).order_by(BattleLine.created_at.asc()).all()
    round_results = BattleRoundResult.query.filter_by(battle_id=battle.id).order_by(BattleRoundResult.round_number.asc()).all()
    return {
        "challenge_code": battle.challenge_code,
        "league": battle.league,
        "status": battle.status,
        "current_turn": battle.current_turn,
        "round_number": battle.round_number,
        "display_name_a": battle.display_name_a,
        "team_a": battle.team_a,
        "display_name_b": battle.display_name_b,
        "team_b": battle.team_b,
        "lines": [{"side": l.side, "round": l.round_number, "message": l.message, "created_at": l.created_at.isoformat()} for l in lines],
        "round_results": [{"round": r.round_number, "winner": r.winner, "critique_a": r.critique_a, "critique_b": r.critique_b, "score_a": r.score_a, "score_b": r.score_b} for r in round_results],
        "awaiting_next_round": battle.awaiting_next_round,
        "ready_a": battle.ready_a,
        "ready_b": battle.ready_b,
        "overall_winner": battle.overall_winner,
        "recap_winner_text": battle.recap_winner_text,
        "recap_loser_text": battle.recap_loser_text,
        "rematch_requested_a": battle.rematch_requested_a,
        "rematch_requested_b": battle.rematch_requested_b,
        "rematch_challenge_code": battle.rematch_challenge_code,
        "vote_count_a": battle.vote_count_a if battle.status == "complete" else None,
        "vote_count_b": battle.vote_count_b if battle.status == "complete" else None,
    }


@app.route("/api/battles", methods=["POST"])
def create_battle():
    data = request.json
    league = data.get("league", "")
    team_a = (data.get("team_a") or "").strip()
    display_name_a = (data.get("display_name_a") or "Anonymous").strip()[:40]

    if not league or not team_a:
        return jsonify({"error": "League and your team are required"}), 400

    challenge_code = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8]
    battle = Battle(challenge_code=challenge_code, league=league, team_a=team_a, display_name_a=display_name_a or "Anonymous")
    db.session.add(battle)
    db.session.commit()

    return jsonify({"challenge_code": challenge_code})


@app.route("/api/battles/<challenge_code>")
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
            result = trash_talk_service.judge_battle_round(team_a, line_a_message, team_b, line_b_message)
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

            all_lines = BattleLine.query.filter_by(battle_id=battle_id).order_by(BattleLine.created_at.asc()).all()
            recap = trash_talk_service.generate_battle_recap(
                battle.team_a, battle.team_b,
                [{"side": l.side, "round": l.round_number, "message": l.message} for l in all_lines],
                [{"round": r.round_number, "winner": r.winner} for r in all_results],
                overall_winner,
            )
            battle.recap_winner_text = recap["winner_recap"]
            battle.recap_loser_text = recap["loser_recap"]
            db.session.commit()
        except Exception as e:
            print(f"[battle recap async] failed for battle {battle_id}: {e}")


@app.route("/api/battles/<challenge_code>/line", methods=["POST"])
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
def ready_for_next_round(challenge_code):
    """
    One side confirming they're ready to move on from the just-finished
    round. The round only actually advances once BOTH sides have called
    this — no timer, purely gated on both people clicking through on
    their own device.
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

    if battle.ready_a and battle.ready_b:
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
            # background so whoever clicks the second "ready" doesn't sit
            # there waiting for it before seeing the battle end.
            threading.Thread(target=_generate_recap_async, args=(battle.id,), daemon=True).start()
            return jsonify(_battle_state_json(battle))

    db.session.commit()
    return jsonify(_battle_state_json(battle))


@app.route("/api/battles/<challenge_code>/vote", methods=["POST"])
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
    bell.mp3, cheer.mp3, boo.mp3, waiting-music.mp3, critique-reveal.mp3
    """
    sfx_files = {
        "intro_url": "battle-intro.mp3",
        "crowd_loop_url": "crowd-loop.mp3",
        "new_line_url": "new-line.mp3",
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

    Note: no ownership verification exists yet — anyone can look up any
    number. Fine for the current one-off yes/no check, but flagged on the
    roadmap as needed before this inbox holds a fuller history long-term.
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

    return jsonify({"found": True, "items": items})


def _find_by_reply_token(token):
    """Shared lookup — checks both Order and Smackagram, same record_id space pattern used elsewhere."""
    return Order.query.filter_by(reply_token=token).first() or Smackagram.query.filter_by(reply_token=token).first()


@app.route("/api/reply-context/<token>")
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

    if mode == "custom":
        safety = content_moderation.check_message_safety(data.get("custom_message", ""))
        if not safety["safe"]:
            print(f"[safety] blocked smackagram arm attempt — reason: {safety['reason']}")
            return jsonify({"error": "This message can't be sent — it may contain threatening, sexual, or harassing content. Please revise it."}), 400

    sensitivity = data.get("sensitivity", trash_talk_service.DEFAULT_SENSITIVITY)
    if sensitivity not in trash_talk_service.SENSITIVITY_LEVELS:
        return jsonify({"error": "Invalid sensitivity level"}), 400

    smackagram = Smackagram(
        game_id=data["game_id"],
        sport=data.get("sport", "nfl"),
        home_team=data["home_team"],
        away_team=data["away_team"],
        target_team=data["target_team"],
        game_start_time=game_start,
        mode=mode,
        sensitivity=sensitivity,
        custom_message=data.get("custom_message") if mode == "custom" else None,
        voice_key=data.get("voice_key", voice_options.DEFAULT_VOICE_KEY),
        recipient_name=data["recipient_name"],
        recipient_phone=data["recipient_phone"],
        consent_confirmed=True,
        reply_opt_in=bool(data.get("reply_opt_in")),
        sender_phone=data.get("sender_phone") if data.get("reply_opt_in") else None,
        reply_token=secrets.token_urlsafe(24) if data.get("reply_opt_in") else None,
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

if __name__ == "__main__":
    app.run(debug=True)
