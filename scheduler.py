import os
import secrets
from datetime import datetime

from models import db, Smackagram, Scenario, SmackcastSubscription, SmackcastRecap, User
from services import sports_service, stripe_service, twilio_service, trash_talk_service, call_audio_service, content_moderation, sleeper_service, smackcast_service, elevenlabs_service, espn_service, wallet_service


def _refund_released_smackagram(s):
    """
    Credits the $1 debited at arm-time back to the user's wallet when a
    hold releases (target team won, game postponed/canceled) - the
    wallet equivalent of Stripe's old release_hold(), since there's no
    card authorization to cancel anymore, just a wallet debit to undo.
    """
    user = User.query.get(s.user_id)
    if user:
        wallet_service.credit_wallet(
            user, wallet_service.LOCKED_N_LOADED_COST_CENTS, "locked_n_loaded_refund",
            description=f"Locked & Loaded refund - {s.target_team} won, hold released",
        )


def check_armed_smackagrams():
    """
    Called via the /api/cron/check-smackagrams route, which an external
    scheduler (cron-job.org or similar) hits every 3 minutes. For every
    'armed' smackagram tied to a game that has gone final, decide whether
    to fire (capture + call) or release (cancel hold, no charge).

    NOTE: this used to run via an in-process APScheduler background
    thread, but that proved unreliable on Render's free tier — the
    recurring job never survived long enough to fire, confirmed through
    extensive diagnostic testing. Moving this to be triggered by a real
    HTTP request (same mechanism every other working feature already
    uses) sidesteps that entirely.
    """
    armed = Smackagram.query.filter_by(status="armed").all()
    print(f"[cron] check_armed_smackagrams running — {len(armed)} armed smackagram(s) to check")
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
                _refund_released_smackagram(s)
                s.status = "canceled"
                s.resolved_at = datetime.utcnow()
            db.session.commit()
            continue

        if result["status"] == "tie":
            for s in matching:
                _refund_released_smackagram(s)
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
                        _refund_released_smackagram(s)
                        s.status = "failed"
                        print(f"[safety] Locked smackagram {s.id} blocked at fire-time — reason: {safety['reason']}")
                        s.resolved_at = datetime.utcnow()
                        continue

                    # No capture step needed - the $1 was already debited
                    # from the wallet at arm time, so the debit simply
                    # stands now that the condition (target team lost) is met.
                    audio_urls = call_audio_service.resolve_audio_url(s, base_url)
                    s.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
                    call_sid = twilio_service.place_prank_call("smackagram", s.id, s.recipient_phone, record=True)
                    s.twilio_call_sid = call_sid
                    s.status = "fired"
                except Exception as e:
                    s.status = "failed"
                    print(f"Locked smackagram {s.id} failed to fire: {e}")
            else:
                # target team won — refund the $1 back to the wallet
                _refund_released_smackagram(s)
                s.status = "released"
            s.resolved_at = datetime.utcnow()

        db.session.commit()


def generate_weekly_smackcasts():
    """
    Called via a new /api/cron/generate-smackcasts route, hit by the
    same external cron mechanism as check_armed_smackagrams (an actual
    in-process "wake up every Tuesday" scheduler was already proven
    unreliable on Render's free tier — see that function's docstring).
    The external cron just needs to be configured to hit this weekly;
    this function itself checks whether each subscription has already
    gotten this week's recap, so it's safe to hit more often than
    strictly necessary without generating duplicates.

    Handles Sleeper (NFL, NBA — Sleeper has no real baseball leagues)
    and ESPN (NFL, NBA, MLB). Yahoo follows once OAuth credentials
    exist for it. Current week/period is determined per-subscription
    rather than once globally, since football, basketball, and
    baseball each have entirely different current periods, and ESPN's
    own numbering isn't guaranteed to match Sleeper's anyway — Sleeper
    subscriptions ask Sleeper's own week-state endpoint (cached per
    sport within a single run, since that's identical across every
    subscription for that sport), ESPN subscriptions ask ESPN's own
    league status directly (can't be cached the same way, since it
    needs that specific league's own credentials).

    Only supports Head-to-Head Points scoring for now, on all three
    sports — Rotisserie and Head-to-Head Categories are common
    especially in baseball and basketball, but need a genuinely
    different data model (no weekly matchups at all for Roto; multiple
    separate stat comparisons instead of one combined score for
    Categories) that isn't built yet.
    """
    subscriptions = SmackcastSubscription.query.filter(
        SmackcastSubscription.is_active == True,
        SmackcastSubscription.platform.in_(["sleeper", "espn"]),
    ).all()
    print(f"[smackcast] Checking {len(subscriptions)} active subscription(s)")

    sleeper_week_cache = {}  # sport -> current week, computed once per sport per run

    for sub in subscriptions:
        try:
            if sub.platform == "sleeper":
                if sub.sport not in sleeper_service.SUPPORTED_SPORTS:
                    print(f"[smackcast] Subscription {sub.id} has unsupported Sleeper sport {sub.sport!r} — skipping")
                    continue
                if sub.sport not in sleeper_week_cache:
                    sleeper_week_cache[sub.sport] = sleeper_service.get_current_week(sub.sport)
                current_week = sleeper_week_cache[sub.sport]
            elif sub.platform == "espn":
                current_week = espn_service.get_current_matchup_period(
                    sub.league_id, str(sub.season_year), sport=sub.sport,
                    swid=sub.espn_swid, espn_s2=sub.espn_s2,
                )
            else:
                continue  # unsupported platform, shouldn't happen given the query filter above

            if not current_week:
                print(f"[smackcast] No current week available for subscription {sub.id} (likely offseason) — skipping")
                continue

            if sub.last_recap_week == current_week:
                continue  # already generated this week's recap for this league

            if sub.platform == "sleeper":
                week_data = sleeper_service.get_week_recap_data(sub.league_id, current_week)
            else:
                week_data = espn_service.get_week_recap_data(
                    sub.league_id, str(sub.season_year), current_week, sport=sub.sport,
                    swid=sub.espn_swid, espn_s2=sub.espn_s2,
                )

            if not week_data or not week_data["matchups"]:
                print(f"[smackcast] No matchup data yet for subscription {sub.id}, week {current_week} — will retry next check")
                continue

            result = smackcast_service.generate_weekly_recap_script(
                league_name=sub.league_name or "Your League",
                week=current_week,
                matchups=week_data["matchups"],
                team_count=sub.team_count or week_data["team_count"],
                sport=sub.sport,
            )
            script = result["full_text"]
            best_line = result["best_line"]
            audio_url = smackcast_service.assemble_recap_audio(
                result["intro"], result["segments"], result["outro"]
            )

            # Meme generation failure shouldn't block the actual recap
            # from delivering — the audio/script are the core product,
            # the meme is a nice-to-have on top.
            meme_url = None
            if best_line:
                try:
                    meme_url = smackcast_service.generate_meme_image(best_line, sub.league_name or "Your League", current_week)
                except Exception as e:
                    print(f"[smackcast] meme generation failed for subscription {sub.id}: {e}")

            recap = SmackcastRecap(
                subscription_id=sub.id,
                week_number=current_week,
                season_year=sub.season_year,
                script_text=script,
                audio_url=audio_url,
                meme_image_url=meme_url,
                best_line=best_line,
                share_token=secrets.token_urlsafe(16),
                status="ready",
            )
            db.session.add(recap)
            db.session.flush()  # get recap.id before delivery, without a separate commit

            base_url = os.environ["BASE_URL"]
            share_url = f"{base_url}/smackcast-recap/{recap.share_token}"

            if sub.deliver_phone_call and sub.phone_call_number:
                try:
                    twilio_service.place_smackcast_call(recap.id, sub.phone_call_number)
                except Exception as e:
                    print(f"[smackcast] phone delivery failed for subscription {sub.id}: {e}")

            if sub.deliver_sms and sub.sms_number:
                try:
                    twilio_service.send_sms(sub.sms_number, f"Your Smackcast for Week {current_week} is ready: {share_url}")
                except Exception as e:
                    print(f"[smackcast] SMS delivery failed for subscription {sub.id}: {e}")

            if sub.deliver_discord and sub.discord_webhook_url:
                smackcast_service.deliver_to_discord(sub.discord_webhook_url, sub.league_name or "Your League", current_week, audio_url, share_url, meme_url=meme_url)

            if sub.deliver_groupme and sub.groupme_bot_id:
                smackcast_service.deliver_to_groupme(sub.groupme_bot_id, sub.league_name or "Your League", current_week, share_url)

            recap.delivered_at = datetime.utcnow()
            sub.last_recap_week = current_week
            db.session.commit()
            print(f"[smackcast] Generated and delivered week {current_week} recap for subscription {sub.id}")

        except Exception as e:
            db.session.rollback()
            print(f"[smackcast] Failed to generate recap for subscription {sub.id}: {e}")
