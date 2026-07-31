from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
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

    price_cents = db.Column(db.Integer, default=100)     # flat $1 per smack - wallet_service.SMACK_COST_CENTS, recording always included now
    includes_recording = db.Column(db.Boolean, default=True)

    stripe_payment_intent_id = db.Column(db.String(120))
    payment_status = db.Column(db.String(20), default="pending")  # pending, captured, failed

    twilio_call_sid = db.Column(db.String(120), nullable=True)
    call_status = db.Column(db.String(20), default="not_sent")    # not_sent, ringing, delivered, no_answer, failed
    recording_url = db.Column(db.String(500), nullable=True)

    # Twilio's AnsweredBy value from machine_detection: human,
    # machine_end_beep, machine_end_silence, machine_end_other, fax, or
    # unknown. Previously only print()ed and discarded - persisting it
    # gives a real answer to "did my smack land?" (call_status says
    # "completed" whether the target laughed or it hit voicemail), and
    # is the only way to know whether machine_detection_timeout is set
    # correctly (a high share of "unknown" means the ceiling is too low).
    answered_by = db.Column(db.String(30), nullable=True)

    # The actual ElevenLabs-generated message audio URL used for THIS call,
    # persisted at call-time. Needed for the reply "hear it again" replay —
    # regenerating later isn't reliable since the S3 key is randomly
    # generated per-call, not content-based, so a fresh generation would
    # produce a different file, not the original.
    message_audio_url = db.Column(db.String(500), nullable=True)

    # Who sent it. Absent until now, which meant a customer's own orders
    # couldn't be listed back to them at all - the wallet ledger recorded the
    # spend but never which order it paid for. Nullable because rows created
    # before this column existed can't be attributed retroactively; there is
    # no stored link to recover.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    # Public token for sharing a single smackagram. Separate from reply_token,
    # which grants the RECIPIENT a reply - this one only grants playback, so
    # handing it around can't be used to send anything.
    share_token = db.Column(db.String(64), unique=True, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Smackagram(db.Model):
    """
    A 'locked and loaded' conditional smackagram — armed against a live game,
    fires only if the target team loses. The $1 wallet cost is debited
    immediately at arm time (a wallet balance can't be "authorized" the
    way a card can); if the target team wins or the game is postponed,
    the $1 is credited back to the wallet by scheduler.py's resolution
    job. If the target team loses, the debit simply stands.
    """
    __tablename__ = "smackagrams"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

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

    price_cents = db.Column(db.Integer, default=100)  # flat $1, matching wallet_service.LOCKED_N_LOADED_COST_CENTS - debited immediately, refunded if the hold releases
    stripe_payment_intent_id = db.Column(db.String(120))
    auth_status = db.Column(db.String(20), default="authorized")  # authorized, captured, canceled, expired

    # Outcome + delivery
    status = db.Column(db.String(20), default="armed")  # armed, fired, released, canceled
    twilio_call_sid = db.Column(db.String(120), nullable=True)
    call_status = db.Column(db.String(20), nullable=True)  # raw Twilio CallStatus once the call completes
    recording_url = db.Column(db.String(500), nullable=True)
    answered_by = db.Column(db.String(30), nullable=True)  # see comment on Order — same purpose
    message_audio_url = db.Column(db.String(500), nullable=True)  # see comment on Order — same purpose
    share_token = db.Column(db.String(64), unique=True, nullable=True)  # see comment on Order — same purpose

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

    # 1 (Clean) through 4 (Savage) - same scale as trash_talk_service.SENSITIVITY_LEVELS,
    # used everywhere else on the site. Set once by whoever creates the
    # battle, fixed for its entire lifetime - shapes both the judge's
    # scoring standard and the actual tone of its critiques/coach
    # messages. Defaults to 4 (Savage) to match the battle judge's
    # original always-brutal behavior for anyone who doesn't pick.
    intensity = db.Column(db.Integer, default=4, nullable=False)

    # 5 or 10 - set once by whoever creates the battle, fixed for its
    # entire lifetime. Defaults to 5 to match the site's original
    # fixed-length behavior for anyone who doesn't pick.
    max_rounds = db.Column(db.Integer, default=5, nullable=False)

    display_name_a = db.Column(db.String(40), nullable=False)
    team_a = db.Column(db.String(80), nullable=False)
    display_name_b = db.Column(db.String(40), nullable=True)
    team_b = db.Column(db.String(80), nullable=True)

    status = db.Column(db.String(20), default="waiting")  # waiting, active, complete
    current_turn = db.Column(db.String(1), default="a")   # "a" or "b" — whose turn it is
    round_number = db.Column(db.Integer, default=1)        # 1-5

    # Set to utcnow() every time current_turn changes (including a fresh
    # round starting) - the server-side reference point for the 60-second
    # per-turn timer, so the countdown is consistent regardless of when
    # either person's browser actually loaded/polled the page, rather than
    # a purely client-side timer that could drift or reset on refresh.
    turn_started_at = db.Column(db.DateTime, nullable=True)

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

    # Per-side presence heartbeat, updated by the same viewer-ping the
    # live viewer count already uses (see /viewer-ping) whenever the
    # ping identifies itself as side a or b. Powers the "your opponent
    # left" notification - computed server-side the same way
    # last_typed_a/b are, so a stale value naturally means "hasn't
    # pinged in a while" without needing an explicit "I'm leaving"
    # signal (unreliable anyway - someone can just close the tab).
    last_seen_a = db.Column(db.DateTime, nullable=True)
    last_seen_b = db.Column(db.DateTime, nullable=True)

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

    # True when this row is a placeholder for a missed 60-second turn timer
    # rather than a real line - either nothing was typed in time, or what
    # was typed failed the safety check right as the clock ran out. message
    # is always empty in that case - unsafe text is never stored/displayed,
    # even as a "what they almost said" artifact.
    timed_out = db.Column(db.Boolean, default=False, nullable=False)


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


class BattleViewer(db.Model):
    """
    Live viewer presence for a battle - one row per distinct browser
    (viewer_id, same anonymous-id pattern as BattleVote's voter_id),
    upserted on a periodic heartbeat ping rather than inserted fresh
    each time. The two actual participants ping the same way as any
    spectator, so they're naturally included in the live count rather
    than needing special-cased logic - "how many people currently have
    this battle open" is the same question for a participant or a
    spectator. last_seen is what actually determines "currently
    viewing" - a row existing doesn't mean the viewer is still present,
    only that they were at some point; the count query filters to
    recent last_seen values.
    """
    __tablename__ = "battle_viewers"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"), nullable=False)
    viewer_id = db.Column(db.String(64), nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("battle_id", "viewer_id", name="one_viewer_row_per_battle"),)


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


class User(db.Model):
    """
    Registered user account — required to use any real feature on the
    site (sending smacks, battles, chat, etc). customer_number is a
    separate, business-facing ID from the internal db id, starting at
    1,000,001 for the first real registered customer (assigned in the
    registration endpoint, not via DB auto-increment, since starting
    values for auto-increment aren't portably configurable across
    SQLite vs Postgres). The admin test account is seeded below that
    range at customer_number 1,000,000.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(db.Integer, unique=True, nullable=False)

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    screen_name = db.Column(db.String(30), unique=True, nullable=False)  # displayed everywhere identity is shown (chat, battles) instead of real name
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    # 2FA — a fresh code is generated and texted at every login (and
    # right after registration, to confirm the phone number is real).
    # Only email 2FA is deferred until email-sending infrastructure
    # exists on this site — SMS is the only channel actually wired up
    # right now.
    two_factor_code = db.Column(db.String(10), nullable=True)
    two_factor_expires_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Wallet: a single dollar-balance-in-cents field, per the pricing
    # spec. Smackagram counts are NEVER stored separately — they're a
    # display-only translation (floor(balance_cents / 100)), computed
    # fresh every time via the smackagram_count property below. This
    # avoids the two-units reconciliation drift that comes from
    # tracking "15 smacks" AND "$10" as separate numbers that could
    # drift out of sync — one ledger, one source of truth. Balances
    # (including bonus credits from top-up packs) never expire.
    balance_cents = db.Column(db.Integer, default=0, nullable=False)

    @property
    def smackagram_count(self):
        """Display-only Smackagram count, computed fresh from the
        wallet balance — never persisted as its own column."""
        return self.balance_cents // 100

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class PendingAction(db.Model):
    """
    When a user tries to Send a Smack or arm Locked & Loaded but their
    wallet balance is insufficient, the full original request payload
    gets stored here (as JSON) instead of being lost, before redirecting
    to /reload. Once the user successfully tops up, the Stripe webhook
    itself (not the browser) looks up this record by id, re-runs the
    original action using the stored payload, and marks it completed -
    the user never has to re-enter anything. This is intentionally
    server-side and webhook-driven rather than client-side storage
    (sessionStorage etc), since the webhook is the one place we can be
    certain payment actually succeeded, regardless of what happens to
    the browser tab in between.
    """
    __tablename__ = "pending_actions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    action_type = db.Column(db.String(30), nullable=False)  # "send_smack" or "locked_n_loaded"
    payload_json = db.Column(db.Text, nullable=False)  # json.dumps() of the original request body

    status = db.Column(db.String(20), default="pending")  # pending, completed, failed, expired
    result_redirect = db.Column(db.String(255), nullable=True)  # where the resumed action ended up (e.g. /order-success) - lets reload_success.html show something meaningful
    error_message = db.Column(db.Text, nullable=True)  # populated if resuming failed for some reason

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


class Setting(db.Model):
    """
    Runtime configuration, changeable from the admin panel without a deploy.

    Key/value rather than typed columns on purpose: the settings this needs to
    carry will keep growing (2FA switches now; the show's leagues, runtime and
    kill switch next), and rows are cheaper to add than migrations.

    updated_by records WHO changed it. For settings that affect security -
    which the 2FA switches do - knowing who flipped it matters as much as
    knowing what it is.
    """
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), unique=True, nullable=False, index=True)
    value = db.Column(db.String(255), nullable=False)
    updated_by = db.Column(db.String(60))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyShow(db.Model):
    """
    One episode of The Smacky Report.

    Rows are kept rather than overwritten so a bad morning can be rolled back
    to the previous show, and so there's a record of what aired on any date.
    is_live is what the home page reads - publishing sets it on the new row
    and clears it everywhere else, which also makes the kill switch a single
    boolean rather than a deploy.
    """
    __tablename__ = "daily_shows"

    id = db.Column(db.Integer, primary_key=True)
    audio_url = db.Column(db.String(500), nullable=False)
    date_label = db.Column(db.String(60))        # "Thursday, July 30"
    minutes = db.Column(db.Float)
    game_count = db.Column(db.Integer)
    leagues = db.Column(db.String(200))
    best_line = db.Column(db.Text)
    is_live = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WalletTransaction(db.Model):
    """
    Append-only audit log of every wallet balance change — both
    top-ups (Stripe payments) and deductions (sending a smack, arming
    Locked & Loaded). amount_cents is signed: positive for a credit
    (top-up), negative for a debit (spending). This exists specifically
    so the wallet's running balance is always reconstructable and
    auditable, rather than trusting a single mutable balance_cents
    field with no history behind it — important given real money is
    involved here.
    """
    __tablename__ = "wallet_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount_cents = db.Column(db.Integer, nullable=False)  # signed: +credit, -debit
    balance_after_cents = db.Column(db.Integer, nullable=False)  # snapshot for easy auditing without replaying the whole log

    # What kind of transaction this was, for display/support purposes.
    # "topup" - a Stripe purchase credited the wallet
    # "smack" - a main-generator send debited the wallet
    # "locked_n_loaded" - arming a Locked & Loaded hold debited the wallet
    # "locked_n_loaded_refund" - a released hold credited the wallet back
    transaction_type = db.Column(db.String(30), nullable=False)

    # Links back to the Stripe PaymentIntent for topups (for support/
    # dispute lookup), nullable since deductions have no Stripe object.
    stripe_payment_intent_id = db.Column(db.String(255), nullable=True)

    description = db.Column(db.String(255), nullable=True)  # human-readable note, e.g. "Loaded Package - $10 for 15 Smackagrams (5 free)"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



    """
    Append-only audit log of every wallet balance change — both
    top-ups (Stripe payments) and deductions (sending a smack, arming
    Locked & Loaded). amount_cents is signed: positive for a credit
    (top-up), negative for a debit (spending). This exists specifically
    so the wallet's running balance is always reconstructable and
    auditable, rather than trusting a single mutable balance_cents
    field with no history behind it — important given real money is
    involved here.
    """
    __tablename__ = "wallet_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount_cents = db.Column(db.Integer, nullable=False)  # signed: +credit, -debit
    balance_after_cents = db.Column(db.Integer, nullable=False)  # snapshot for easy auditing without replaying the whole log

    # What kind of transaction this was, for display/support purposes.
    # "topup" - a Stripe purchase credited the wallet
    # "smack" - a main-generator send debited the wallet
    # "locked_n_loaded" - arming a Locked & Loaded hold debited the wallet
    transaction_type = db.Column(db.String(30), nullable=False)

    # Links back to the Stripe PaymentIntent for topups (for support/
    # dispute lookup), nullable since deductions have no Stripe object.
    stripe_payment_intent_id = db.Column(db.String(255), nullable=True)

    description = db.Column(db.String(255), nullable=True)  # human-readable note, e.g. "Loaded Package - $10 for 15 Smackagrams (5 free)"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SmackcastSubscription(db.Model):
    """
    A season-long Smackcast pass tied to one fantasy league. One-time
    payment, then recaps auto-generate weekly for the rest of the
    season — no further charge. Platform-specific credentials are
    nullable since only the fields for whichever platform was chosen
    actually get used; ESPN needs cookies only for private leagues,
    Yahoo needs OAuth tokens since it doesn't support a simple
    paste-your-ID flow like Sleeper does.
    """
    __tablename__ = "smackcast_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Null for subscriptions created under the old connect-then-pay flow.
    purchase_id = db.Column(db.Integer, db.ForeignKey("smackcast_purchases.id"), nullable=True)
    # "single" stops after one delivered recap; "season" runs weekly.
    plan = db.Column(db.String(20), nullable=True)

    platform = db.Column(db.String(20), nullable=False)  # "sleeper", "espn", "yahoo"
    sport = db.Column(db.String(10), nullable=False, default="nfl")  # "nfl", "nba", "mlb" - mlb is ESPN-only, Sleeper has no baseball leagues
    league_id = db.Column(db.String(100), nullable=False)
    league_name = db.Column(db.String(200), nullable=True)  # fetched from the platform once connected
    team_count = db.Column(db.Integer, nullable=True)  # drives recap length scaling
    season_year = db.Column(db.Integer, nullable=False)

    # ESPN-only — cookies required for private leagues, unused/null for
    # public leagues and for any other platform entirely.
    espn_swid = db.Column(db.String(255), nullable=True)
    espn_s2 = db.Column(db.Text, nullable=True)

    # Yahoo-only — OAuth tokens, since Yahoo has no simple paste-an-ID
    # flow. Access tokens expire and need refreshing over a season, so
    # both are stored.
    yahoo_access_token = db.Column(db.Text, nullable=True)
    yahoo_refresh_token = db.Column(db.Text, nullable=True)
    yahoo_token_expires_at = db.Column(db.DateTime, nullable=True)

    # Delivery — the owner can pick any combination. Web link is the
    # universal fallback (works for literally any platform someone
    # pastes it into) so it defaults on.
    deliver_web_link = db.Column(db.Boolean, default=True)
    deliver_phone_call = db.Column(db.Boolean, default=False)
    phone_call_number = db.Column(db.String(30), nullable=True)
    deliver_sms = db.Column(db.Boolean, default=False)
    sms_number = db.Column(db.String(30), nullable=True)
    deliver_discord = db.Column(db.Boolean, default=False)
    discord_webhook_url = db.Column(db.Text, nullable=True)
    deliver_groupme = db.Column(db.Boolean, default=False)
    groupme_bot_id = db.Column(db.String(100), nullable=True)

    stripe_checkout_session_id = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=False)  # flips True on successful payment
    last_recap_week = db.Column(db.Integer, nullable=True)  # avoids double-generating the same week

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SmackcastPurchase(db.Model):
    """
    One Smackcast transaction, created BEFORE any league is connected.

    The flow used to be connect-league-then-pay, which meant a
    SmackcastSubscription row could only exist after the league details
    were known. The product page inverts that - someone buys first, then
    connects - so the purchase has to be able to stand alone and hold
    the entitlement until leagues get attached to it.

    league_slots is how many leagues this purchase entitles. A single
    recap is 1. A season pass is 1 plus however many extra leagues were
    added at checkout. Subscriptions attach to a purchase as they get
    connected, and slots_used tells us when the entitlement is spent.
    """
    __tablename__ = "smackcast_purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    plan = db.Column(db.String(20), nullable=False)   # "single" or "season"
    league_slots = db.Column(db.Integer, nullable=False, default=1)
    amount_cents = db.Column(db.Integer, nullable=False)

    stripe_session_id = db.Column(db.String(255), nullable=True)
    # pending until Stripe confirms, then paid. Nothing is usable until paid.
    status = db.Column(db.String(20), default="pending")  # pending, paid, failed

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    @property
    def slots_used(self):
        return SmackcastSubscription.query.filter_by(purchase_id=self.id).count()

    @property
    def slots_remaining(self):
        return max(0, (self.league_slots or 0) - self.slots_used)


class SmackcastRecap(db.Model):
    """
    One week's generated recap for one subscription. status tracks
    progress through the multi-step pipeline (pull league data ->
    generate script -> generate audio -> deliver), same reasoning as
    Smackagram order statuses elsewhere on the site — several things
    can fail independently and it's worth knowing which step broke.
    """
    __tablename__ = "smackcast_recaps"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("smackcast_subscriptions.id"), nullable=False)

    week_number = db.Column(db.Integer, nullable=False)
    season_year = db.Column(db.Integer, nullable=False)

    script_text = db.Column(db.Text, nullable=True)
    audio_url = db.Column(db.String(500), nullable=True)
    meme_image_url = db.Column(db.String(500), nullable=True)
    best_line = db.Column(db.Text, nullable=True)
    share_token = db.Column(db.String(64), unique=True, nullable=True)

    status = db.Column(db.String(20), default="generating")  # generating, ready, failed
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("subscription_id", "week_number", "season_year", name="one_recap_per_week_per_subscription"),)


class VerifiedPhone(db.Model):
    """
    Proof that a logged-in user actually controls a given phone number -
    established once by receiving and correctly entering an SMS code
    sent to that exact number. Powers the Smack Inbox privacy fix:
    anyone can search whether a number has a Smackagram on record, but
    only someone who has verified ownership of that specific number can
    see the message content, rather than any logged-in user being able
    to read anyone else's messages. A user can hold multiple verified
    numbers over time (e.g. checked a work phone once, a personal phone
    another time) - this is intentionally not just the single phone
    field on the User's own account, since the number someone wants to
    check might differ from what they registered with.
    """
    __tablename__ = "verified_phones"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    phone_digits = db.Column(db.String(15), nullable=False)  # normalized: digits only, last 10 kept for matching, same convention as check_if_smacked()'s existing matching logic
    verified_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "phone_digits", name="uq_user_verified_phone"),)


class PhoneVerificationCode(db.Model):
    """
    A single in-progress attempt to verify ownership of a phone number -
    separate from the User model's own two_factor_code/two_factor_expires_at
    fields, which are specifically for verifying the account holder's own
    registered phone at login/registration. This is for verifying an
    arbitrary number (which may or may not match the account's own phone)
    in order to unlock viewing Smack Inbox messages sent to it.
    """
    __tablename__ = "phone_verification_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    phone_digits = db.Column(db.String(15), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
