import os
import secrets
from datetime import datetime, timedelta

from models import db, Smackagram, Scenario, SmackcastSubscription, SmackcastRecap, User
from services import sports_service, stripe_service, twilio_service, trash_talk_service, call_audio_service, content_moderation, sleeper_service, smackcast_service, elevenlabs_service, espn_service, wallet_service, espn_scores


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
            description=f"Auto-Smack refund - {s.target_team} won, hold released",
        )


def shadow_compare_sources():
    """
    Ask BOTH sources what happened last night, and log where they differ.

    RUNS ON ITS OWN, not inside the Auto-Smack loop.

    The first version was wired into that loop, which meant it needed an
    ESPN event id before Highlightly was asked anything - so during an ESPN
    outage it produced NO comparison at all. That is exactly backwards: an
    ESPN outage is the scenario Highlightly is being bought to survive, and
    it is when you most want to know whether the replacement works.

    Now it asks each independently. If ESPN is blocked, the log says so and
    still reports what Highlightly returned - which is useful information
    rather than silence.

    Cheap: one call per source per league, cached. Safe: decides nothing.
    """
    from datetime import datetime as _dt, timedelta as _td
    from services import espn_scores, highlightly

    if not highlightly.enabled():
        return

    # Yesterday in Eastern - the same window the daily show uses.
    # Yesterday in Eastern - the window the daily show uses. Ten hours back
    # from UTC was a rough approximation of the same thing; this is the
    # actual answer and it does not drift with the seasons.
    from services import highlightly as _hl
    day = _hl.sport_day(1)

    for sport in ("mlb", "nfl", "nhl"):
        mine = {}
        try:
            mine = espn_scores.league_results(sport) or {}
        except Exception as e:
            print(f"[shadow] ESPN unavailable for {sport}: {e}", flush=True)

        if not mine:
            # Report what the other source found anyway. "ESPN gave us
            # nothing and Highlightly gave us eight games" is the single
            # most useful line this can print during an outage.
            try:
                theirs = highlightly.finals(sport, day)
                # STORE THEM. A finished game never changes, so this is the
                # last time anybody needs to ask about these.
                try:
                    from services import results_store
                    results_store.remember_many(sport, day, theirs,
                                                "highlightly")
                except Exception as _e:
                    print(f"[results] store failed: {_e}", flush=True)
                if theirs:
                    print(f"[shadow] {sport}: ESPN returned NOTHING, "
                          f"Highlightly returned {len(theirs)} final(s). "
                          f"This is what the switch is for.", flush=True)
                    for v in list(theirs.values())[:3]:
                        print(f"[shadow]   {v['winner']} {v['winner_score']}-"
                              f"{v['loser_score']} {v['loser']}", flush=True)
            except Exception as e:
                print(f"[shadow] both sources failed for {sport}: {e}",
                      flush=True)
            continue

        # Store what ESPN found too - whichever source got there first
        # wins, and a later disagreement is flagged rather than overwritten.
        try:
            from services import results_store
            results_store.remember_many(sport, day, mine, "espn",
                                        id_field="espn")
        except Exception as _e:
            print(f"[results] store failed: {_e}", flush=True)

        try:
            highlightly.compare(sport, day, mine)
        except Exception as e:
            print(f"[shadow] compare failed for {sport}: {e}", flush=True)


def _sample_for(armed, game_id, sport):
    """One armed row for this game, for its team names."""
    return next((x for x in armed
                 if x.game_id == game_id and x.sport == sport), None)


def _order_game_day(sample):
    """
    The ONLY date this order's result may come from: the EASTERN date
    the game started. THE FALSE-CALL BUG OF AUG 7, 3:30AM: resolution
    walked (today, yesterday) and matched teams by last word - so in
    a SERIES, yesterday's Red Sox final was accepted for tonight's
    LIVE Red Sox game, remembered in the store under the walked date,
    and FIRED: a call announcing a final score for a game still in the
    12th inning. The wrong-day disease, one layer deeper than the
    Padres bug and worse - this one dialled a phone. A game that
    started tonight can only ever finish tonight (UTC spillover is
    already handled inside the finals() day filter), so the date walk
    is deleted and every lookup binds here.
    """
    from datetime import timedelta, timezone as _tz
    st = getattr(sample, "game_start_time", None)
    if st is None:
        from datetime import datetime as _dtx
        st = _dtx.utcnow()
    if st.tzinfo is None:
        st = st.replace(tzinfo=_tz.utc)
    # Eastern = UTC-4 (EDT); a 1h DST drift cannot move a date across
    # midnight for any real game start
    return (st - timedelta(hours=4)).strftime("%Y-%m-%d")


def _team_is(target, official):
    """
    Does the user's target_team mean this official team name?
    THE FIFTH NAME BUG OF AUG 7: firing used exact string equality
    between a USER-TYPED team ("mets", lowercase, from the pulse's own
    data) and the FEED'S official loser ("New York Mets"). Any mismatch
    fell into the else at the bottom - silently refunded as "target
    won", no log line, on a game the target LOST. Both of Andy's live
    tests took that door.
    Tolerant on purpose, asymmetric on purpose: the short form the
    person typed should live inside the official name.
    """
    t = (target or "").lower().strip()
    o = (official or "").lower().strip()
    if not t or not o:
        return False
    if t == o:
        return True
    # "mets" in "new york mets"; "blue jays" endswith; word membership
    if o.endswith(t) or t.endswith(o):
        return True
    return t in o.split() or t in o


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
    # THE STALE-ARMED ALARM. An armed order is a promise with a clock
    # on it - no game runs 12 hours. Anything armed longer than that
    # is stuck (unresolvable league, dead game id, resolver outage)
    # and would otherwise sit silent until an angry customer found it
    # first. One alert per order per day via the alerts dedup, straight
    # to owners@ now that email works.
    try:
        from datetime import datetime as _dt, timedelta as _td
        _cutoff = _dt.utcnow() - _td(hours=12)
        for _s in armed:
            _made = getattr(_s, "created_at", None)
            if _made and _made < _cutoff:
                from services import alerts
                _age = int((_dt.utcnow() - _made).total_seconds() // 3600)
                alerts.record(
                    "delivery", f"stale_armed_{_s.id}",
                    f"Smackagram #{_s.id} ({_s.sport} game {_s.game_id}, "
                    f"team {_s.target_team}) armed for {_age}h with no "
                    f"result - stuck, needs a look",
                    severity="error")
                print(f"[locked] STALE: #{_s.id} armed {_age}h "
                      f"({_s.sport}/{_s.game_id})", flush=True)
    except Exception as _e:
        print(f"[locked] stale-armed sweep failed: {_e}", flush=True)
    print(f"[cron] check_armed_smackagrams running — {len(armed)} armed smackagram(s) to check")
    if not armed:
        return

    # avoid hitting the API once per row — group by (game_id, sport)
    keys = {(s.game_id, s.sport) for s in armed}

    for game_id, sport in keys:
        # ALREADY KNOWN? THEN ASK NOBODY.
        #
        # A finished game never changes. If the result is in the database
        # already, no provider is contacted at all - which is what makes an
        # outage cost nothing for games that have already ended.
        #
        # This is checked FIRST, before any network call, deliberately.
        result = None
        try:
            from services import results_store
            from datetime import datetime as _dt, timedelta as _td
            _sample = next((x for x in armed
                            if x.game_id == game_id and x.sport == sport), None)
            if _sample and _sample.home_team and _sample.away_team:
                for _day in (_order_game_day(_sample),):
                    _hit = results_store.lookup(sport, _day,
                                                _sample.home_team,
                                                _sample.away_team)
                    if _hit:
                        result = {"final": True, "winner": _hit.winner,
                                  "loser": _hit.loser,
                                  "winner_score": _hit.winner_score,
                                  "loser_score": _hit.loser_score,
                                  "margin": _hit.margin}
                        print(f"[locked] {game_id}: result already stored "
                              f"({_hit.source}) - no provider contacted",
                              flush=True)
                        break
        except Exception as _e:
            print(f"[locked] store lookup failed: {_e}", flush=True)

        # HIGHLIGHTLY DECIDES NOW.
        #
        # The order is: stored result, then Highlightly, then ESPN, then
        # SportsDataIO as a last resort.
        #
        # SportsDataIO went from primary to last because its free tier
        # SCRAMBLES SCORES by roughly 2.5x - verified across ten MLB games.
        # "Who lost" survived that scrambling, which is why it worked at
        # all, but surviving by luck is not the same as being right, and
        # this decides whether somebody gets charged.
        #
        # ESPN went from deciding to fallback because it blocked this
        # server for hours today with no warning, no appeal and no
        # published limits.
        if result is None and _sample_for(armed, game_id, sport):
            _s = _sample_for(armed, game_id, sport)
            try:
                from services import highlightly, results_store
                from datetime import datetime as _dt2, timedelta as _td2
                if highlightly.enabled():
                    for _d in (_order_game_day(_s),):
                        # BALLDONTLIE WHEN HIGHLIGHTLY CANNOT ANSWER.
                        #
                        # Two cases. WNBA, which Highlightly does not
                        # carry at all - confirmed 5 August, their
                        # basketball segment had Philippine leagues that
                        # day and no WNBA. And any night Highlightly is
                        # down, which used to be ESPN's job until ESPN
                        # started refusing Render's address outright.
                        #
                        # Auto-Smack TAKES MONEY for a call that depends
                        # on knowing who lost, so having no second source
                        # is not an inconvenience, it is a refund.
                        _fin = highlightly.finals(sport, _d)
                        if not _fin:
                            try:
                                from services import balldontlie
                                if balldontlie.covers(sport):
                                    _fin = balldontlie.finals(sport, _d)
                                    if _fin:
                                        print(f"[locked] {game_id}: "
                                              f"balldontlie answered where "
                                              f"Highlightly did not",
                                              flush=True)
                            except Exception as _e:
                                print(f"[locked] balldontlie failed: {_e}",
                                      flush=True)

                        # BOTH SOURCES SILENT IS THE REAL EMERGENCY.
                        #
                        # One provider failing is a warning - the other
                        # covers it, which is the entire point of having
                        # two. BOTH failing means an Auto-Smack that was
                        # PAID FOR cannot be resolved: we do not know who
                        # lost, so the call cannot go out and the money is
                        # sitting there.
                        #
                        # That is the moment somebody needs telling, and
                        # it is different in kind from a single source
                        # having a bad minute.
                        if not _fin:
                            try:
                                from services import alerts
                                alerts.record(
                                    "data", f"no_source_{sport}",
                                    f"Neither Highlightly nor balldontlie "
                                    f"could return finished {sport.upper()} "
                                    f"games for {_d}. Auto-Smack {_s.id} "
                                    f"cannot be resolved.",
                                    severity="critical")
                            except Exception:
                                pass
                        # Match on the two teams - their ids are their own.
                        for _hid, _r in _fin.items():
                            names = {_r["winner"].split()[-1].lower(),
                                     _r["loser"].split()[-1].lower()}
                            want = {(_s.home_team or "").split()[-1].lower(),
                                    (_s.away_team or "").split()[-1].lower()}
                            if names == want:
                                result = _r
                                # Record WHICH source answered, not a
                                # hardcoded name. A stored result that
                                # claims the wrong provider makes the
                                # shadow comparison meaningless and hides
                                # an outage rather than showing it.
                                _src = _r.get("source") or "highlightly"
                                results_store.remember(
                                    sport, _d, _r, _src,
                                    {_src: str(_hid)})
                                print(f"[locked] {game_id}: Highlightly says "
                                      f"{_r['loser']} lost {_r['loser_score']}"
                                      f"-{_r['winner_score']}", flush=True)
                                break
                        if result:
                            break
            except Exception as _e:
                print(f"[locked] highlightly lookup failed: {_e}", flush=True)

        if result is None:
            # Last resort. Scrambled scores, but the WINNER survives it.
            result = sports_service.get_game_result(game_id, sport=sport)
            if result:
                print(f"[locked] {game_id}: falling back to SportsDataIO - "
                      f"its scores are unreliable, only the loser is trusted",
                      flush=True)

        # ESPN DECIDES THE OUTCOME.
        #
        # SportsDataIO's free tier scrambles scores by roughly 2.5x. The
        # WINNER survived that, which is why this worked at all - but "who
        # lost" surviving a scrambled score is luck rather than a guarantee,
        # and this is the one place on the site where being wrong costs
        # somebody real money and needs a refund.
        #
        # ESPN already supplies the roast facts on the very same call, so it
        # should decide the result too. Both are run and any disagreement is
        # logged - but ESPN wins.
        try:
            _sample = next((x for x in armed
                            if x.game_id == game_id and x.sport == sport), None)
            _eid = getattr(_sample, "espn_event_id", None) if _sample else None
            if not _eid and _sample:
                _eid = espn_scores.find_event_id(
                    sport, _sample.home_team, _sample.away_team)
                if _eid:
                    _sample.espn_event_id = _eid
                    db.session.commit()
            if _eid:
                # ONE CALL PER LEAGUE, NOT ONE PER GAME.
                #
                # This used to make a request per armed game, so fifteen
                # games meant fifteen requests every two minutes - outbound
                # traffic scaling with how well the product sells, which is
                # exactly the wrong way round and is what got this server
                # throttled once already.
                #
                # league_results() returns EVERY finished game in one call,
                # cached for 45 seconds. Fifteen calls become one, and it
                # stays one whether five games are armed or fifty.
                _all = espn_scores.league_results(sport)
                _espn = _all.get(str(_eid))

                # (shadow run moved out of this loop - see below)
                if not _espn:
                    # Not in the finished list - either still playing, or
                    # the scoreboard did not cover it. Fall back to the
                    # single-game lookup, which is rare enough not to
                    # matter and keeps an edge case from stalling a call.
                    _espn = espn_scores.game_result(sport, _eid)
                if _espn:
                    # ESPN NO LONGER OVERRIDES.
                    #
                    # It used to win every disagreement. Now it only fills
                    # in when nothing better answered, because a source
                    # that can block this server for hours without warning
                    # should not be the final word on who gets charged.
                    #
                    # When it disagrees with an answer we already have, the
                    # disagreement is LOGGED and the existing answer kept.
                    if (result and result.get("loser") and _espn.get("loser")
                            and result["loser"] != _espn["loser"]):
                        print(f"[locked] DISAGREEMENT on {game_id}: "
                              f"we have {result['loser']} losing, "
                              f"ESPN says {_espn['loser']}. KEEPING OURS.",
                              flush=True)
                    # Only take ESPN's answer if we have nothing better.
                    if result is None:
                        result = _espn
                elif result:
                    # ESPN not final yet. Hold rather than fire on a source
                    # we do not trust - a call that goes out early cannot be
                    # taken back.
                    print(f"[locked] {game_id}: ESPN not final yet, holding",
                          flush=True)
                    result = None
        except Exception as e:
            print(f"[locked] ESPN check failed for {game_id}, using "
                  f"sportsdata: {e}", flush=True)

        if result is None:
            continue  # game still in progress, check again next run

        matching = [s for s in armed if s.game_id == game_id and s.sport == sport]

        # .get(), NOT BRACKETS - the Highlightly and stored-result paths
        # build result dicts WITHOUT a "status" key (they carry
        # final/winner/loser), and result["status"] raised KeyError here,
        # which killed the ENTIRE cron pass the moment any one game
        # resolved through those paths. Every armed order in the batch
        # then waited forever behind one crash - Andy's MLB call among
        # them, caught live on Aug 7 with the alert email + SMS firing
        # exactly as designed. A missing status means "not postponed,
        # not a tie": the final/winner fields decide from there.
        if result.get("status") == "postponed":
            # ONE BAD RECORD MUST NOT BLOCK THE BATCH.
            #
            # This ran unguarded: if a refund raised for one smack, the
            # commit below never happened and NONE were released - then
            # the same batch retried two minutes later, hit the same
            # record, and failed again. A single corrupt row could hold
            # every refund on the site indefinitely, and nothing would
            # say so.
            for s in matching:
                try:
                    _refund_released_smackagram(s)
                    s.status = "canceled"
                    s.resolved_at = datetime.utcnow()
                except Exception as _e:
                    db.session.rollback()
                    print(f"[locked] could not cancel {s.id}: {_e}",
                          flush=True)
                    try:
                        from services import alerts
                        alerts.record("delivery", "cancel_failed",
                                      f"smackagram {s.id}: {_e}",
                                      severity="critical")
                    except Exception:
                        pass
            db.session.commit()
            continue

        if result.get("status") == "tie":
            for s in matching:
                try:
                    _refund_released_smackagram(s)
                    s.status = "released"
                    s.resolved_at = datetime.utcnow()
                except Exception as _e:
                    db.session.rollback()
                    print(f"[locked] could not releas {s.id}: {_e}",
                          flush=True)
                    try:
                        from services import alerts
                        alerts.record("delivery", "release_failed",
                                      f"smackagram {s.id}: {_e}",
                                      severity="critical")
                    except Exception:
                        pass
            db.session.commit()
            continue

        loser = result.get("loser")
        if not loser:
            # a result with no loser decided nothing - hold this game
            # for the next pass rather than guessing or crashing
            print(f"[locked] {game_id}: result carries no loser yet, "
                  f"holding", flush=True)
            continue
        base_url = os.environ["BASE_URL"]

        # Several people can smack the same person about the same game. Left
        # alone that produces near-identical calls firing simultaneously -
        # one connects, the rest go to voicemail, and the recipient works out
        # it is a script. So they are grouped by phone number, numbered, and
        # spaced out.
        firing = [s for s in matching if _team_is(s.target_team, loser)]
        by_phone = {}
        for s in firing:
            by_phone.setdefault(s.recipient_phone, []).append(s)

        now = datetime.utcnow()
        for phone, group in by_phone.items():
            group.sort(key=lambda x: x.created_at or now)
            for i, s in enumerate(group):
                # Set ONCE. This sweep runs every two minutes, and
                # recalculating send_after each time would push a queued call
                # three minutes further into the future on every pass - it
                # would never fire.
                if s.send_after is not None:
                    continue
                s.pile_position = i + 1
                s.pile_total = len(group)
                # Three minutes apart. Long enough that the previous call has
                # finished, short enough that it still reads as a pile-on
                # rather than a slow drip through the evening.
                s.send_after = now + timedelta(minutes=3 * i)
        db.session.commit()

        # Facts already used on this phone, so no two calls to the same
        # person lean on the same detail.
        used_facts = {}

        for s in matching:
            if _team_is(s.target_team, loser):
                # condition met — target team lost, fire the smackagram
                try:
                    # Already written on an earlier sweep while this call
                    # sat in the queue. Regenerating would burn a model call
                    # and change the script out from under a message that was
                    # already decided.
                    if s.mode == "auto_summary" and not s.custom_message:
                        # generate the recap roast now, using real facts from
                        # the game that just ended — this is the "set it and
                        # walk away, get a roast grounded in what actually
                        # happened" feature
                        # ESPN first: real player lines, real records and a
                        # correct score. SportsDataIO's free tier scrambles
                        # the numbers - it gets the winner right, which is why
                        # this worked at all, but every score it reports is
                        # wrong by roughly a 2.5x multiplier.
                        facts = []
                        espn_id = getattr(s, "espn_event_id", None)

                        # Resolve now if we have not already. The two services
                        # do not share ids - a smackagram stores SportsDataIO's
                        # GameID, which will never match ESPN - so the bridge
                        # is teams and date, done at fire time because a game
                        # armed three days out may not be in ESPN's scoreboard
                        # yet.
                        if not espn_id:
                            try:
                                espn_id = espn_scores.find_event_id(
                                    s.sport, s.home_team, s.away_team)
                                if espn_id:
                                    s.espn_event_id = espn_id
                                    db.session.commit()
                                    print(f"[locked] {s.id} resolved to ESPN "
                                          f"event {espn_id}", flush=True)
                                else:
                                    print(f"[locked] {s.id} no ESPN match for "
                                          f"{s.away_team} at {s.home_team} "
                                          f"({s.sport})", flush=True)
                            except Exception as e:
                                print(f"[locked] {s.id} event lookup failed: {e}",
                                      flush=True)

                        if espn_id:
                            try:
                                detail = espn_scores.fetch_game_detail(s.sport, espn_id)
                                # select_facts rather than roast_facts: a
                                # full extraction produces fifteen lines,
                                # which reads like a stat sheet and makes
                                # every call sound the same. This picks a
                                # different lead and a different handful of
                                # supporting detail each time.
                                facts = espn_scores.select_facts(
                                    detail, avoid=used_facts.get(s.recipient_phone))
                            except Exception as e:
                                print(f"[locked] ESPN detail failed for {s.id}: {e}", flush=True)

                        if not facts:
                            # Fall back rather than not calling at all - a
                            # generic roast beats a purchase that silently
                            # does nothing.
                            summary = sports_service.get_game_summary(s.game_id, sport=s.sport)
                            facts = (summary or {}).get("key_facts") or []
                            print(f"[locked] {s.id} using fallback facts", flush=True)

                        # Remember what this call used so the next one to
                        # the same number reaches for something else.
                        used_facts.setdefault(s.recipient_phone, []).extend(facts)

                        s.custom_message = trash_talk_service.generate_game_recap_roast(
                            team=s.target_team,
                            recipient_name=s.recipient_name,
                            key_facts=facts,
                            sensitivity=s.sensitivity,
                            sport=s.sport,
                            pile_position=s.pile_position,
                            pile_total=s.pile_total,
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
                        # THE ONE THAT MATTERS MOST. This fires
                        # automatically with nobody watching, so a block here
                        # was previously invisible - the customer was
                        # refunded and the event vanished into the log.
                        try:
                            from services import safety_service
                            safety_service.record(
                                "auto-smack", "fire-time", safety,
                                user_id=getattr(s, "user_id", None),
                                record_type="smackagram", record_id=s.id,
                                refunded=True)
                        except Exception as _e:
                            print(f"[safety] record failed: {_e}", flush=True)
                        print(f"[safety] Locked smackagram {s.id} blocked at fire-time — reason: {safety['reason']}")
                        s.resolved_at = datetime.utcnow()
                        continue

                    # No capture step needed - the $1 was already debited
                    # from the wallet at arm time, so the debit simply
                    # stands now that the condition (target team lost) is met.
                    # Hold the queued ones. Firing five calls to the same
                    # number at once means one connects and four go straight
                    # to voicemail - four people paid for a call nobody
                    # hears live. The script is already generated and stored;
                    # this run just leaves it armed and the next sweep picks
                    # it up once its slot arrives.
                    # OPT-OUT, CHECKED AGAIN AT THE MOMENT OF SENDING.
                    #
                    # This is the case the front-end check cannot cover.
                    # An Auto-Smack is armed days before it fires. The
                    # recipient can opt out in between - and at arm time
                    # they had not, so nothing earlier would catch it.
                    #
                    # Checking once, at purchase, is checking at the only
                    # moment the answer is guaranteed to be stale.
                    try:
                        from app import is_opted_out
                        if is_opted_out(s.recipient_phone):
                            s.status = "cancelled_optout"
                            _refund_released_smackagram(s)
                            db.session.commit()
                            print(f"[optout] Auto-Smack {s.id} cancelled - "
                                  f"recipient opted out after it was set up. "
                                  f"Refunded.", flush=True)
                            continue
                    except Exception as _e:
                        # Never let this check stop a send by failing. A
                        # refusal on a database hiccup would silently kill
                        # paid smacks.
                        print(f"[optout] check failed for {s.id}: {_e}",
                              flush=True)

                    if s.send_after and datetime.utcnow() < s.send_after:
                        db.session.commit()
                        print(f"[locked] {s.id} queued - call {s.pile_position} "
                              f"of {s.pile_total}, waiting until "
                              f"{s.send_after:%H:%M:%S}", flush=True)
                        continue

                    audio_urls = call_audio_service.resolve_audio_url(s, base_url)
                    call_audio_service.stash_call_audio("smackagram", s.id, audio_urls)
                    s.message_audio_url = audio_urls[0]  # persist for reply-flow "hear it again" replay
                    # Onto the wall as it fires, same as a standard smack.
                    try:
                        from app import publish_to_wall
                        publish_to_wall(s, "locked", audio_urls[0])
                    except Exception as _e:
                        print(f"[wall] locked publish skipped: {_e}", flush=True)
                    call_sid = twilio_service.place_prank_call("smackagram", s.id, s.recipient_phone, record=True)
                    s.twilio_call_sid = call_sid
                    s.status = "fired"
                except Exception as e:
                    s.status = "failed"
                    print(f"Auto-Smack {s.id} failed to send: {e}", flush=True)
                    # CRITICAL. Somebody paid for this call, the game
                    # finished, and it did not go out. Nobody finds that
                    # out from a log line.
                    try:
                        from services import alerts
                        alerts.record("delivery", "call_failed",
                                      f"Auto-Smack {s.id}: {e}",
                                      severity="critical")
                    except Exception:
                        pass
            else:
                # target team won — refund the $1 back to the wallet.
                # AND SAY SO - this branch released two live test
                # orders in total silence on Aug 7. A door money walks
                # through must never be quiet.
                _refund_released_smackagram(s)
                s.status = "released"
                print(f"[locked] {s.id} RELEASED - target "
                      f"'{s.target_team}' did not match loser "
                      f"'{loser}' - refunded", flush=True)
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
                week_data = sleeper_service.get_week_recap_data(sub.league_id, current_week, sub.sport)
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


def send_scheduled_smackagrams():
    """
    NOT IN USE. Nothing on the site sets a scheduled time.

    Built, then pulled, and the reason is worth keeping: Smackagram means
    "send it now" and Auto-Smack means "send it when they lose". A
    third option - "send it at eight" - blurs both and hands the buyer a
    decision they did not need.

    Left in place because it is inert without a UI feeding it, and because
    if a genuine use appears later (a birthday product, say, where the
    timing IS the point) the plumbing is already correct and tested.

    Fire any Smackagram whose scheduled time has arrived.

    Runs on the SAME three-minute cron as the armed check, so a call goes
    out within three minutes of its slot. That is close enough for "eight
    o'clock on his birthday" and avoids a second cron job to forget about.

    A call is claimed BEFORE it is placed - marked sent, committed, then
    dialled. Two overlapping cron runs would otherwise both find the same
    row and ring somebody twice, which is the kind of bug that costs a
    refund and a complaint rather than just a log line.
    """
    from datetime import datetime

    from models import Order, db

    now = datetime.utcnow()
    due = (Order.query
           .filter(Order.scheduled_for.isnot(None))
           .filter(Order.scheduled_for <= now)
           .filter(Order.scheduled_sent.is_(False))
           # "captured" is what a wallet order is written as - the wallet
           # deduction IS the payment, so there is no separate capture step.
           # Filtering on "paid" would have matched nothing and every
           # scheduled call would have sat there forever.
           .filter(Order.payment_status.in_(("captured", "paid")))
           .limit(25)
           .all())

    if not due:
        return {"checked": 0, "sent": 0}

    sent = 0
    for o in due:
        try:
            # Claim it first. If the call then fails, it is not retried
            # automatically - a scheduled call that rings twice is worse
            # than one that does not ring, and the admin can see it.
            o.scheduled_sent = True
            db.session.commit()

            from services import twilio_service
            # Signature is (record_type, record_id, phone) - passing the
            # object would have thrown on every scheduled send.
            sid = twilio_service.place_prank_call(
                "order", o.id, o.recipient_phone,
                record=bool(getattr(o, "includes_recording", True)))
            o.twilio_call_sid = sid
            db.session.commit()
            sent += 1
            print(f"[scheduled] sent order {o.id} "
                  f"(due {o.scheduled_for})", flush=True)
        except Exception as e:
            db.session.rollback()
            print(f"[scheduled] order {o.id} FAILED: {e}", flush=True)

    return {"checked": len(due), "sent": sent}
