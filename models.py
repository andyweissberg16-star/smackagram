from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

db = SQLAlchemy()


class WallPost(db.Model):
    """
    Smacks of the Week - the best lines people actually sent.

    Deliberately NOT a review wall. A carousel of testimonials would have to
    be real to be legal (the FTC rule on fake reviews carries penalties per
    review, per person who saw it), and seeded testimonials on a site that
    takes payments is exactly what that rule was written for.

    A wall of funny smacks avoids all of that AND sells the product better:
    somebody reading an actual line understands what they are buying in a way
    that "great site, five stars" never achieves.

    Everything here is moderated before it appears. It is the front page.
    """
    __tablename__ = "wall_posts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    handle = db.Column(db.String(40), nullable=False)     # username, never a real name
    body = db.Column(db.Text, nullable=False)
    # Which product it came from, so the wall doubles as a menu - somebody
    # reading a Locked & Loaded line learns that product exists.
    product = db.Column(db.String(20), default="smackagram")   # smackagram | smackback | locked

    # The GENERATED SMACK audio - Smacky's line as it was delivered. Never a
    # recording of the call.
    #
    # That distinction is the whole legal position, and it is why no opt-in
    # is needed. Recording a live call captures the recipient's voice, and
    # Florida - where this company is registered - is one of twelve states
    # requiring every party to consent to a recording. PrankDial deals with
    # that by warning users away from those states and pushing the liability
    # onto the sender.
    #
    # Smackagram never records anything. The call is generated audio played
    # AT somebody and nothing comes back, so there is no second party in the
    # file and nobody whose consent is missing.
    #
    # The control here is `approved` - nothing reaches the wall until it has
    # been looked at, which is the right gate for a front page anyway.
    # One short line saying what this was about, so somebody scrolling knows
    # what they are listening to before they press play. "YANKEES LOST 9-2"
    # tells you more in three words than the smack itself does in thirty.
    # Kept so the team's brand colour can be looked up when the card renders,
    # rather than parsing it back out of the headline text.
    team = db.Column(db.String(80), nullable=True)
    headline = db.Column(db.String(80), nullable=True)
    # Stored separately from the headline so the card can colour the name in
    # the team's own colours - the headline is a finished sentence, this is
    # the thing to look up.
    team_name = db.Column(db.String(80), nullable=True)

    audio_url = db.Column(db.String(500), nullable=True)

    # Nothing appears until somebody has looked at it.
    approved = db.Column(db.Boolean, default=False, nullable=False)
    # Marks the seeded examples, so they can be told apart from real posts
    # and labelled honestly on the page.
    is_sample = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


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
    # The team being roasted. The form already sends it but it was never
    # stored, which meant a smack had no way of saying what it was about once
    # it existed - and the wall needs exactly that.
    team = db.Column(db.String(80), nullable=True)
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

    # SEND IT LATER.
    #
    # Null means send immediately, which is every order placed before this
    # existed - so the column is additive and nothing needs backfilling.
    #
    # Stored in UTC. The page collects a local time and converts, because a
    # scheduled call is the one feature where being an hour out is not a
    # small bug: it rings at seven in the morning instead of eight at night.
    scheduled_for = db.Column(db.DateTime, index=True)
    scheduled_sent = db.Column(db.Boolean, default=False)


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
    # ESPN's own id for the game being watched, captured at arm-time. Needed
    # for the summary endpoint, which is where the player lines and the real
    # score come from - SportsDataIO's game_id will not resolve against it.
    espn_event_id = db.Column(db.String(32), nullable=True)
    # Where this call sits when several people smacked the same person about
    # the same game. 1 is the first call, 2 the second, and so on. Baked in
    # at generation time because the script has to KNOW it is call three -
    # Smacky celebrates the pile-on rather than pretending not to notice.
    pile_position = db.Column(db.Integer, nullable=True)
    pile_total = db.Column(db.Integer, nullable=True)
    # Do not dial before this. Calls to the same number are spaced three
    # minutes apart so four of five do not land in voicemail while the first
    # is still connected.
    send_after = db.Column(db.DateTime, nullable=True)
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
    opponent_type = db.Column(db.String(10), default="human", nullable=False)  # human, smacky
    is_public = db.Column(db.Boolean, default=False, nullable=False)
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


class BattleLineReaction(db.Model):
    """
    Fire or ice on a single line. Attached to the LINE, not the battle, so
    counts say which smack landed. Deliberately does not feed scoring.
    """
    __tablename__ = "battle_line_reactions"

    id = db.Column(db.Integer, primary_key=True)
    line_id = db.Column(db.Integer, db.ForeignKey("battle_lines.id"), nullable=False)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"), nullable=False)
    reactor_id = db.Column(db.String(64), nullable=False)
    reaction = db.Column(db.String(4), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("line_id", "reactor_id", name="uq_line_reactor"),
    )


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

    # --- what makes this league THIS league -------------------------------
    #
    # A box score is the same everywhere. "You lost by forty" is a joke that
    # works in every league in the country, which is another way of saying
    # it works in none of them. "You lost by forty to the guy who sits two
    # desks away" only works in one - and that is the one people screenshot.
    #
    # All optional. A commissioner who fills in nothing still gets a recap;
    # they just get a more generic one.
    #
    # Written by the COMMISSIONER only. Letting any member add details about
    # other members is a harassment vector wearing a feature's clothes - and
    # whatever gets written arrives in Smacky's voice, which makes it ours.
    how_they_know_each_other = db.Column(db.String(40), nullable=True)
    # Who arrived this season. A first-year member is a target from week one,
    # and it changes every year, which keeps the profile from going stale.
    newest_member = db.Column(db.String(80), nullable=True)
    # Different from never winning - this is the person who leaves points on
    # the bench every week, which is a recurring joke rather than a
    # season-long one.
    worst_at_lineups = db.Column(db.String(80), nullable=True)
    buy_in = db.Column(db.String(60), nullable=True)      # free, small, serious
    trophy = db.Column(db.String(200), nullable=True)
    last_place_punishment = db.Column(db.Text, nullable=True)
    league_age = db.Column(db.String(40), nullable=True)

    # People. Names only, no accusations - the prompt turns these into
    # affectionate needling about FANTASY, never about the person.
    commissioner_name = db.Column(db.String(80), nullable=True)
    # Last season specifically, as opposed to "wins constantly" - a reigning
    # champion is a target in a way a historical one is not.
    reigning_champion = db.Column(db.String(80), nullable=True)
    runner_up = db.Column(db.String(80), nullable=True)
    perennial_winner = db.Column(db.String(80), nullable=True)
    perennial_loser = db.Column(db.String(80), nullable=True)
    biggest_talker = db.Column(db.String(80), nullable=True)
    most_absent = db.Column(db.String(80), nullable=True)

    # Where they all talk. "The group chat is going to be unbearable tonight"
    # only works if Smacky knows there is one.
    group_chat = db.Column(db.String(60), nullable=True)

    running_jokes = db.Column(db.Text, nullable=True)
    rivalries = db.Column(db.Text, nullable=True)
    anything_else = db.Column(db.Text, nullable=True)
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


class SmackcastWeeklyNote(db.Model):
    """
    What happened in the league THIS week.

    Kept apart from the profile deliberately. The profile is season-long and
    gets overwritten - who the commissioner is, what the punishment is. These
    are dated, and that is the whole point: a note has to belong to a
    specific week or the system cannot tell whether "Dave made a terrible
    trade" was meant for the recap being written tomorrow or the one after.

    The week is stamped when the note is SAVED, from whatever week is
    currently open for collection. Monday 11:58pm goes into tomorrow's
    episode; Tuesday 12:01am waits for the following one. The stamp decides,
    never the timing of the job.

    Nothing is deleted at the end of a week. Old notes are what let Smacky
    say "three weeks ago somebody told me Dave made a terrible trade, and
    Dave has now lost four in a row" - which is worth more than any single
    week's material.
    """
    __tablename__ = "smackcast_weekly_notes"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("smackcast_subscriptions.id"), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    season_year = db.Column(db.Integer, nullable=False)

    big_trade = db.Column(db.Text, nullable=True)
    brutal_loss = db.Column(db.Text, nullable=True)
    loudest_in_chat = db.Column(db.Text, nullable=True)
    anything_else = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # One note per subscription per week - saving again edits the same row
    # rather than stacking up duplicates.
    __table_args__ = (
        db.UniqueConstraint("subscription_id", "week_number", "season_year",
                            name="uq_weekly_note_sub_week"),
    )

    def has_content(self):
        return any([self.big_trade, self.brutal_loss,
                    self.loudest_in_chat, self.anything_else])


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


class FamousMoment(db.Model):
    """
    A famous sports moment, stored as FACTS.

    Deliberately no transcript field. The original commentary is somebody
    else's copyrighted work, and putting it in the prompt would pull the
    model straight towards the phrases that ARE the moment. Everything here
    is fact - score, clock, who did what, what was at stake - which nobody
    owns, plus a DESCRIPTION of how the broadcast felt.

    Smacky writes from the facts, so the call is entirely his.
    """
    __tablename__ = "famous_moments"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    sport = db.Column(db.String(20), default="mlb")
    moment_date = db.Column(db.String(40))          # "October 3, 1951"
    game = db.Column(db.String(160))                # "NL Playoff - Game 3"
    teams = db.Column(db.String(160))               # "Giants vs Dodgers"

    # The losing side, so the roast has a target. Nullable - some moments
    # (a perfect game, a record) have no clean loser to aim at.
    losing_team = db.Column(db.String(80))
    hero = db.Column(db.String(80))                 # Bobby Thomson
    goat = db.Column(db.String(80))                 # Ralph Branca - nullable

    situation = db.Column(db.Text)                  # bullets, one per line
    stakes = db.Column(db.Text)                     # why it mattered
    broadcast_style = db.Column(db.Text)            # DESCRIBED, never quoted

    # Cached output so a page load is not fifty Claude calls.
    call_text = db.Column(db.Text)
    followup_text = db.Column(db.Text)
    roast_text = db.Column(db.Text)
    audio_url = db.Column(db.String(400))
    generated_at = db.Column(db.DateTime)

    sort_order = db.Column(db.Integer, default=0)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class CallTiming(db.Model):
    """
    How long AMD took, per call.

    Answering-machine detection holds the line until it believes the greeting
    has ended, and only then does Twilio fetch our TwiML. On a voicemail the
    mailbox starts recording at the beep, so every second AMD spends deciding
    after that beep becomes dead air at the FRONT of the recording - and
    mailboxes commonly stop at sixty seconds, so that silence can push the
    end of the message off the tape.

    Nothing measured this. One row per call, so tuning is done against real
    numbers rather than one remembered call.
    """
    __tablename__ = "call_timings"

    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(20))          # order | smackagram
    record_id = db.Column(db.Integer)
    call_sid = db.Column(db.String(64), index=True)

    dialed_at = db.Column(db.DateTime)              # when we asked Twilio to call
    instructions_at = db.Column(db.DateTime)        # when Twilio came back for TwiML

    # The number that matters: seconds between dialling and the message
    # being able to start. On a voicemail this is roughly ring time plus
    # greeting plus AMD's deliberation.
    gap_seconds = db.Column(db.Float)

    answered_by = db.Column(db.String(30))
    call_status = db.Column(db.String(30))
    duration_seconds = db.Column(db.Integer)        # from Twilio's status callback
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class SafetyEvent(db.Model):
    """
    Anything the moderation gate stopped, kept.

    These were print() only - written to the Render log, which rolls off and
    which nobody reads at two in the morning. So a block would happen, the
    person would be refunded, and you would never learn it occurred.

    That matters in both directions. If somebody is repeatedly probing the
    generators you want to know tonight, not from a complaint later. And if
    the gate is firing on harmless messages, you want to know that too -
    a false positive costs a paying customer their call.
    """
    __tablename__ = "safety_events"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           index=True)

    # Where it happened, so a pattern in one product is visible.
    surface = db.Column(db.String(40), index=True)   # send-a-smack, locked, lab...
    stage = db.Column(db.String(30))                 # input | generated | fire-time

    user_id = db.Column(db.Integer, index=True)
    record_type = db.Column(db.String(20))
    record_id = db.Column(db.Integer)

    category = db.Column(db.String(60), index=True)
    reason = db.Column(db.Text)
    # The offending words only, not the whole message. Enough to judge it,
    # not a transcript of everything anybody has ever typed.
    excerpt = db.Column(db.Text)

    # Was money involved, and did it come back.
    refunded = db.Column(db.Boolean, default=False)
    reviewed = db.Column(db.Boolean, default=False, index=True)


class PageStat(db.Model):
    """
    Traffic, counted rather than logged.

    ONE ROW PER PATH PER DAY, incremented - not one row per request. A busy
    day would otherwise write tens of thousands of rows onto a Postgres
    instance that is also serving the site, to answer a question ("how many
    people came") that a counter answers just as well.

    No IP address, no user agent, no fingerprint. Visitors are counted by a
    rotating daily hash so returning visitors are not tracked across days,
    which keeps this a traffic counter rather than a surveillance record.
    """
    __tablename__ = "page_stats"

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, index=True)
    path = db.Column(db.String(120), index=True)
    views = db.Column(db.Integer, default=0)
    visitors = db.Column(db.Integer, default=0)     # distinct, that day only
    logged_in = db.Column(db.Integer, default=0)    # of those views

    __table_args__ = (db.UniqueConstraint("day", "path", name="uq_day_path"),)


class OptOut(db.Model):
    """
    Numbers that must never be called again.

    A service that places unsolicited calls needs a way for the person on the
    receiving end to stop them, and "email support" is not good enough for
    somebody who wants to be left alone right now. This is checked before
    every dial.

    Deliberately NOT tied to an account. The person opting out is the
    recipient, who almost certainly has no account and no reason to make one
    - requiring a login to stop being called would be the same as having no
    opt-out at all.

    Numbers are stored normalised to digits so "+1 (727) 555-0100" and
    "7275550100" cannot both be on file with only one of them matching.
    """
    __tablename__ = "opt_outs"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    reason = db.Column(db.String(200), nullable=True)
    source = db.Column(db.String(20), default="web")   # web | sms | support
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


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


class GameResult(db.Model):
    """
    A finished game, stored forever.

    THE POINT: a final score never changes. Once Toronto has beaten Houston
    3-1, that is true permanently - so it should be fetched ONCE and read
    from the database from then on.

    Everything on this site was re-asking a provider the same settled
    question over and over, which meant an outage at any provider took away
    facts we already knew. ESPN blocked this server for hours on 4 August
    and the site lost access to games that had finished the night before -
    games it had already fetched successfully.

    This is the single biggest resilience win available, and it is
    independent of which provider is used. A stored result survives every
    outage, every rate limit and every provider change.

    RESULTS ARE WRITTEN ONCE AND NOT UPDATED. If two sources disagree the
    first one wins and the disagreement is logged rather than overwriting -
    silently changing a result somebody was already called about is worse
    than being wrong consistently.
    """
    __tablename__ = "game_results"

    id = db.Column(db.Integer, primary_key=True)

    # How each provider refers to this game. Either may be null - a game
    # found through Highlightly has no ESPN id and vice versa.
    espn_event_id = db.Column(db.String(40), index=True)
    highlightly_id = db.Column(db.String(40), index=True)
    sportsdata_id = db.Column(db.String(40), index=True)

    league = db.Column(db.String(16), nullable=False, index=True)
    game_date = db.Column(db.String(10), nullable=False, index=True)

    # The answer everything actually wants.
    winner = db.Column(db.String(80), nullable=False)
    loser = db.Column(db.String(80), nullable=False)
    winner_score = db.Column(db.Integer)
    loser_score = db.Column(db.Integer)
    margin = db.Column(db.Integer)

    # Which provider supplied it, for tracing a wrong result back.
    source = db.Column(db.String(20))

    # Set when a second provider disagreed. The stored result does NOT
    # change; this records that it was contested so it can be looked at.
    contested = db.Column(db.Boolean, default=False)
    contested_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # A team pairing on a date identifies a game across providers, since
    # their ids do not match each other.
    __table_args__ = (
        db.Index("ix_game_results_lookup", "league", "game_date"),
    )


class Player(db.Model):
    """
    Every player name we have ever seen, kept.

    WHY THIS EXISTS
    ---------------
    The name picker was fetching a team's squad live on every use. That is
    slow, it costs a request per team, and it breaks entirely when a
    provider is unreachable - which happened for most of 4 August.

    THE BETTER REASON, though, is Aaron Judge.

    A player on the injured list appears in NO recent roster. Highlightly's
    baseball feed has no injuries block at all, so somebody out for six
    weeks is simply invisible - and he is exactly the name people want to
    hear about.

    But he WAS in a roster before he got hurt. Storing every name as it is
    seen means the picker keeps offering him long after he stops appearing
    in the data, which is precisely the behaviour wanted.

    LAST_SEEN is what makes that safe. A name is offered whether or not he
    played this week, but the date is kept so somebody who has not appeared
    in a year can be aged out rather than haunting the list forever.
    """
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    team = db.Column(db.String(80), nullable=False, index=True)
    league = db.Column(db.String(16), nullable=False, index=True)

    position = db.Column(db.String(40))
    jersey = db.Column(db.String(8))

    # When this name last turned up in real data. Not "is he injured" -
    # that is a different question and one no feed answers reliably - but
    # enough to say "he has not played in a while", which is the honest
    # version and is often the better joke anyway.
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)

    source = db.Column(db.String(20))

    __table_args__ = (
        db.Index("ix_players_team_league", "team", "league"),
        db.UniqueConstraint("name", "team", "league", name="uq_player_team"),
    )


class SupportTicket(db.Model):
    """
    A message from the contact form.

    The page was three email addresses. That works until somebody actually
    uses it - then a complaint lives in a mailbox, nobody knows whether it
    was answered, and there is no record that it happened at all.

    A ticket here is visible on the admin panel, can be marked done, and
    records WHO closed it and HOW. That last part matters more than it
    looks: "resolved" with no note is the same as no record.
    """
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(200), nullable=False, index=True)
    phone = db.Column(db.String(30))

    topic = db.Column(db.String(60), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)

    # Linked when the sender happened to be logged in, so their history is
    # reachable from the ticket without asking them for an order number.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    status = db.Column(db.String(20), default="open", index=True)
    completed_by = db.Column(db.String(120))
    completed_at = db.Column(db.DateTime)
    resolution = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Kept because a complaint about a call is easier to investigate with
    # the browser and address that sent it.
    user_agent = db.Column(db.String(300))
    ip = db.Column(db.String(60))


class SupportReply(db.Model):
    """
    A reply sent to somebody about their ticket.

    Kept because "we told them X" is the thing you need when they come back
    a week later, and because a note in the resolution field is a summary
    written afterwards rather than what was actually said.

    Only outbound. Their reply arrives in the mailbox, not here - catching
    inbound mail needs a webhook from the mail host and is a separate job.
    """
    __tablename__ = "support_replies"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"),
                          nullable=False, index=True)

    body = db.Column(db.Text, nullable=False)
    sent_by = db.Column(db.String(120))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # False when the mail failed. The reply is still stored, because
    # knowing an attempt was made and did not land matters more than a
    # clean record - otherwise a customer waits for something that never
    # left the building.
    delivered = db.Column(db.Boolean, default=True)
    error = db.Column(db.String(300))
