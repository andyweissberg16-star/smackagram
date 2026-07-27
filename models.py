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


class ChatPost(db.Model):
    """
    Smack Chat — a real user typing their own trash talk into a public
    team/league room. Purely manual, no AI generation anywhere in this
    flow. Every post still passes through the same safety check used
    everywhere else on the site before it's allowed to go live (flags
    genuine threats/hate speech/etc, not ordinary crude trash talk).

    display_name is freeform and unverified for now — real accounts will
    replace this later, but the room/posting/rating functionality doesn't
    need to wait on that to work.
    """
    __tablename__ = "chat_posts"

    id = db.Column(db.Integer, primary_key=True)
    league = db.Column(db.String(20), nullable=False)   # nfl, nba, mlb, nhl
    team = db.Column(db.String(10), nullable=False)      # team code, e.g. "DAL", "NYY"
    display_name = db.Column(db.String(40), nullable=False, default="Anonymous")
    message = db.Column(db.Text, nullable=False)

    rating_total = db.Column(db.Integer, default=0)   # sum of all ratings given
    rating_count = db.Column(db.Integer, default=0)    # how many people rated it
    report_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def average_rating(self):
        if self.rating_count == 0:
            return None
        return round(self.rating_total / self.rating_count, 1)


class ChatRating(db.Model):
    """
    One individual rating on one ChatPost. This is what actually enforces
    "only once" server-side — not just a running total on ChatPost.

    rater_id is a random anonymous ID generated and stored in the rater's
    browser today (no accounts exist yet). The design is deliberate: once
    real accounts exist, rater_id just becomes the real logged-in user's
    account ID instead — same table, same uniqueness constraint, same
    enforcement logic, no rework needed. Only the browser-side generation
    of rater_id changes, not this table or the rating endpoint's logic.
    """
    __tablename__ = "chat_ratings"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("chat_posts.id"), nullable=False)
    rater_id = db.Column(db.String(64), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("post_id", "rater_id", name="one_rating_per_rater_per_post"),)


class Order(db.Model):
    """An immediate 'send it now' smackagram — the simple v1 flow."""
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey("scenarios.id"))
    custom_message = db.Column(db.Text, nullable=True)   # if using "write your own"
    voice_key = db.Column(db.String(40), default="default")  # which ElevenLabs voice to use
    recipient_name = db.Column(db.String(120))
    recipient_phone = db.Column(db.String(20))
    consent_confirmed = db.Column(db.Boolean, default=False)

    # "Did you just get smacked?" reply flow — opt-in only. If the buyer
    # agrees to receive a reply smack, we store their own number here;
    # otherwise this stays null and no reply is possible for this order.
    # reply_token is what actually gets shown/passed around anywhere a
    # reply link exists — the raw sender_phone is NEVER sent to the
    # browser or put in a URL; it only ever gets read server-side, at the
    # moment the reply is actually being submitted.
    sender_phone = db.Column(db.String(20), nullable=True)
    reply_opt_in = db.Column(db.Boolean, default=False)
    reply_token = db.Column(db.String(64), nullable=True, unique=True)
    replied = db.Column(db.Boolean, default=False)  # True once someone has replied to THIS smack

    # Set only on records that ARE themselves a reply — points back to
    # whichever original smack (Order or Smackagram) this replied to.
    # replied_to_type is "order" or "smackagram" since the original could
    # be either; replied_to_id is that record's id in its own table.
    replied_to_type = db.Column(db.String(12), nullable=True)
    replied_to_id = db.Column(db.Integer, nullable=True)

    price_cents = db.Column(db.Integer, default=200)     # $2 bundle default, $1 call-only option
    includes_recording = db.Column(db.Boolean, default=True)

    stripe_payment_intent_id = db.Column(db.String(120))
    payment_status = db.Column(db.String(20), default="pending")  # pending, captured, failed

    twilio_call_sid = db.Column(db.String(120), nullable=True)
    call_status = db.Column(db.String(20), default="not_sent")    # not_sent, ringing, delivered, no_answer, failed
    recording_url = db.Column(db.String(500), nullable=True)

    # The actual ElevenLabs-generated message audio URL used for THIS call,
    # persisted at call-time. Needed for the reply "hear it again" replay —
    # regenerating later isn't reliable since the S3 key is randomly
    # generated per-call, not content-based, so a fresh generation would
    # produce a different file, not the original.
    message_audio_url = db.Column(db.String(500), nullable=True)

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
    voice_key = db.Column(db.String(40), default="default")
    mode = db.Column(db.String(20), default="custom")  # "custom" (write your own) or "auto_summary" (AI recap after game ends)
    sensitivity = db.Column(db.Integer, default=4)  # 1 (clean) - 4 (max aggression); only used for auto_summary mode, generated at game-end time
    recipient_name = db.Column(db.String(120))
    recipient_phone = db.Column(db.String(20))
    consent_confirmed = db.Column(db.Boolean, default=False)

    # Same reply opt-in as Order — see comment there.
    sender_phone = db.Column(db.String(20), nullable=True)
    reply_opt_in = db.Column(db.Boolean, default=False)
    reply_token = db.Column(db.String(64), nullable=True, unique=True)
    replied = db.Column(db.Boolean, default=False)  # True once someone has replied to THIS smack

    price_cents = db.Column(db.Integer, default=200)

    # Stripe — authorized now, captured/canceled once the game resolves
    stripe_payment_intent_id = db.Column(db.String(120))
    auth_status = db.Column(db.String(20), default="authorized")  # authorized, captured, canceled, expired

    # Outcome + delivery
    status = db.Column(db.String(20), default="armed")  # armed, fired, released, canceled
    twilio_call_sid = db.Column(db.String(120), nullable=True)
    call_status = db.Column(db.String(20), nullable=True)  # raw Twilio CallStatus once the call completes
    recording_url = db.Column(db.String(500), nullable=True)
    message_audio_url = db.Column(db.String(500), nullable=True)  # see comment on Order — same purpose

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)


class Battle(db.Model):
    """
    Smack Battle — two people go head-to-head, 5 rounds of alternating
    trash talk about their rival teams, with the audience voting on a
    winner once it's done.

    Direct-challenge matchmaking only for v1 (create a battle, share the
    link, someone joins) — no random pairing or scheduled events yet.
    Uses polling for live updates, not true WebSockets — the roadmap
    flagged real-time push as needing bigger infrastructure than this app
    currently has; polling is a real, working v1 tradeoff, not a full
    implementation of that harder piece.
    """
    __tablename__ = "battles"

    id = db.Column(db.Integer, primary_key=True)
    challenge_code = db.Column(db.String(20), nullable=False, unique=True)
    league = db.Column(db.String(20), nullable=False)

    display_name_a = db.Column(db.String(40), nullable=False)
    team_a = db.Column(db.String(80), nullable=False)
    display_name_b = db.Column(db.String(40), nullable=True)
    team_b = db.Column(db.String(80), nullable=True)

    status = db.Column(db.String(20), default="waiting")  # waiting, active, complete
    current_turn = db.Column(db.String(1), default="a")   # "a" or "b" — whose turn it is
    round_number = db.Column(db.Integer, default=1)        # 1-5

    # Once both sides have gone in a round, the round pauses here — no
    # timer, no auto-advance. Each side sees their own critique and a
    # "Start next round" button; the next round only actually begins once
    # BOTH ready flags are true, checked/reset together in the ready
    # endpoint.
    awaiting_next_round = db.Column(db.Boolean, default=False)
    ready_a = db.Column(db.Boolean, default=False)
    ready_b = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Generated once, right when the battle finishes — savage,
    # Smackagram-voiced recap text, one version for whoever won overall
    # and one for whoever lost. Stored rather than regenerated on every
    # request. overall_winner is "a", "b", or "tie" based on who won more
    # of the 5 rounds.
    overall_winner = db.Column(db.String(4), nullable=True)
    recap_winner_text = db.Column(db.Text, nullable=True)
    recap_loser_text = db.Column(db.Text, nullable=True)

    # Live typing indicator — just a timestamp per side, "is typing"
    # gets computed server-side (comparing to utcnow()) rather than
    # storing a boolean directly, so it naturally expires without
    # needing an explicit "stopped typing" signal (which isn't reliable
    # anyway — someone can just close the tab mid-keystroke).
    last_typed_a = db.Column(db.DateTime, nullable=True)
    last_typed_b = db.Column(db.DateTime, nullable=True)

    # Rematch — same "both sides have to agree" gate as advancing a
    # round. Once both flags are true, a brand new Battle gets created
    # (same teams/names) and its challenge_code is stashed here so both
    # people's clients (still polling this old, completed battle) can
    # detect it and redirect themselves to the new one.
    rematch_requested_a = db.Column(db.Boolean, default=False)
    rematch_requested_b = db.Column(db.Boolean, default=False)
    rematch_challenge_code = db.Column(db.String(20), nullable=True)

    @property
    def vote_count_a(self):
        return BattleVote.query.filter_by(battle_id=self.id, voted_for="a").count()

    @property
    def vote_count_b(self):
        return BattleVote.query.filter_by(battle_id=self.id, voted_for="b").count()


class BattleLine(db.Model):
    """One line of trash talk in one round of a battle, from one side."""
    __tablename__ = "battle_lines"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"), nullable=False)
    side = db.Column(db.String(1), nullable=False)   # "a" or "b"
    round_number = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BattleVote(db.Model):
    """
    One audience vote on a completed battle. voter_id is a browser-
    generated anonymous ID (same pattern as Smack Chat's ratings) —
    enforced one-vote-per-voter via a unique constraint, same seamless
    upgrade path to real accounts later as Smack Chat's ratings have.
    """
    __tablename__ = "battle_votes"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"), nullable=False)
    voter_id = db.Column(db.String(64), nullable=False)
    voted_for = db.Column(db.String(1), nullable=False)  # "a" or "b"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("battle_id", "voter_id", name="one_vote_per_voter_per_battle"),)


class BattleRoundResult(db.Model):
    """
    AI-judged outcome of one completed round (both sides have gone).
    Powers the LED-style scorecard under the team names. For now the
    generator decides each round's winner — real per-round audience
    voting is a possible future upgrade, but this is the reasonable
    default until that's worth building.
    """
    __tablename__ = "battle_round_results"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    winner = db.Column(db.String(4), nullable=False)  # "a", "b", or "tie"
    critique_a = db.Column(db.Text, nullable=True)  # a few sentences on side A's line specifically
    critique_b = db.Column(db.Text, nullable=True)  # same, for side B
    score_a = db.Column(db.Integer, nullable=True)  # 0-10 rating of side A's line this round
    score_b = db.Column(db.Integer, nullable=True)  # same, for side B
    coach_message_a = db.Column(db.Text, nullable=True)  # savage/motivational, based on side A's standing so far
    coach_message_b = db.Column(db.Text, nullable=True)  # same, for side B
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("battle_id", "round_number", name="one_result_per_round_per_battle"),)
