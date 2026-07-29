# Smackagram — Future Roadmap

Saved for reference. Not yet started. Revisit and prioritize when ready.

## Prerequisites (needed before most of this becomes buildable)
- [ ] **Postgres database or persistent disk** — currently on SQLite,
      which wipes on every Render redeploy AND on the free tier's
      15-minute idle spin-down (confirmed directly — the Smack Chat seed
      script's data got wiped this way, not from a deploy at all, just
      the site sitting idle). Accounts, purchase history, admin
      reporting, and now the Smack Chat seed data all need this fixed to
      actually persist. Two real fix options already scoped: attach a
      persistent disk to a paid Render web service (cheaper/faster), or
      migrate to real Postgres (more robust long-term, needs a paid tier
      too since the free Postgres option expires after 30 days). Revisit
      once ready to stop re-seeding/re-testing against data that keeps
      disappearing.
- [ ] **Email-sending service** (SendGrid, Postmark, etc.) — needed for
      password resets, email verification, and preference confirmations.
      Nothing currently sends transactional email.

## 1. Accounts & Authentication
- [ ] Registration (email + password)
- [ ] Login page
- [ ] Password reset flow — request → emailed token/link → set new password
- [ ] Email verification on signup
- [ ] Guest checkout preserved as an option — accounts should never be
      required to make a purchase, only to save history/preferences
- [ ] Profile page — name, phone, saved payment method (via Stripe Customer)
- [ ] Email preferences — marketing opt-in vs. transactional-only

## 2. Client-Facing Purchase History
- [ ] Order history page — past Orders + Locked & Loaded smackagrams,
      status (fired/released/pending), links to recordings
- [ ] Downloadable/emailed receipts

## 3. Backend Admin Tools
- [ ] Separate admin dashboard (not the public site)
- [ ] View all orders/smackagrams across all users
- [ ] Visibility into scheduler activity — what's currently armed, when
      it'll resolve
- [ ] Manual override — cancel/pause an armed smackagram if something
      looks wrong
- [ ] Time-period filtering (day/week/month) for activity review
- [ ] Basic sales/accounting reporting — revenue, refund/release totals,
      profitability given known cost-per-call (~$0.40–0.48 vs. $2 price)

## 4. Smack Chat — public team/league message boards
Real users post their own trash talk publicly, no AI involved at all —
closer to a subreddit than a chat app. Organized as League > Team rooms
(NFL > Cowboys, MLB > Yankees, etc.), anyone can post, everyone in that
room's public feed sees it.

- [ ] League/team room structure (nested browse: pick league, then team)
- [ ] Public posting — plain text, no AI generation or per-message AI
      moderation (cost/latency prohibitive at real chat volume)
- [ ] Lightweight safety net instead: basic profanity/slur filter +
      user-facing "report" button, rather than full AI review per message
- [ ] Identity decision still open: fully anonymous each time vs. a
      persistent display name/handle (anonymous = less friction to launch;
      persistent handle = real reputation/return-visit habit over time)
- [ ] Upvote/rating on posted lines — reuse the same X/10 rating language
      already built for Smack Lab, surfaces "top smack talk this week" per
      team room
- [ ] Funnel hook: a highly-rated public line gets a "send this as a real
      Smackagram" prompt, same pattern as the existing Smack Lab funnel
- [ ] Technical note: doesn't need true real-time push for the base
      version — polling for new posts every few seconds is fine on the
      current Flask setup. Doesn't need the full account system either —
      a lightweight "pick a display name to post" is enough to start,
      decoupled from the bigger Accounts & Authentication item above.

## 5. Smack Battles — live 1v1 rival battles with spectators (phase 2)
Two users go head-to-head, 5 rounds of alternating trash talk about their
rival teams, live audience watching. Build this AFTER Smack Chat exists —
it needs the same rooms/identities as a foundation, but adds real
complexity on top:

- [ ] Matchmaking — random pairing within a rivalry vs. direct challenge
      vs. scheduled events (each a different scope of build)
- [ ] Turn-based state — track whose turn it is, prevent double-posting,
      consider a per-turn timer for tension (chess-clock style)
- [ ] Genuine real-time push for spectators (WebSockets, not polling) —
      a live battle only feels live if new rounds appear instantly, this
      is the one piece that actually needs the bigger real-time
      infrastructure lift
- [ ] Winner determination — audience vote, which adds its own layer
      (vote counting, one-vote-per-viewer enforcement, live results)

---
*Last updated: 2026-07-26*

# Master Project List (added 2026-07-26)

Andy's full project list, merged in with honest status against what's
actually built so far. This overlaps with sections 1-5 above in places —
noted where relevant. Nothing in this section has been started unless
explicitly marked done.

## User Profile Page
Overlaps heavily with "1. Accounts & Authentication" above — same
underlying blocker (Postgres + email service needed first).
- [ ] Register page
- [ ] Order history
- [~] Sent audio files storage — recordings DO get stored (S3) today, but
      there's no user-facing page to browse/access them. Storage exists,
      retrieval UI doesn't.
- [ ] Billing/accounting history with account balance
- [ ] Password reset for registered users
- [ ] Guest checkout customer record for history retrieval — Stripe
      creates a customer at checkout time, but it's not tied to a
      queryable "customer record" for guest order history
- [ ] Unique customer ID per customer, for records access
- [ ] Add/remove/cancel subscription options — no subscriptions exist yet
      (see pricing strategy discussion, not yet built)

## Delivery Workflow
- [~] Twilio delivery confirmation (answered vs. VM) — we log `AnsweredBy`
      from the machine-detection callback today, but there's no
      structured confirmation/alerting system built around it yet
- [ ] Refunds for undeliverable smackagrams
- [ ] **New flag (2026-07-26)**: related but distinct case — if a buyer
      pays the $2 bundle price specifically for the recording, and the
      call goes to voicemail (so recording is correctly skipped per the
      VM-recording fix), they were still charged the higher price with
      nothing to show for the recording portion. Worth deciding whether
      this should trigger a partial refund/credit, or whether this counts
      as covered by the general "all sales final" policy since the call
      itself was still delivered.
- [~] Log/store records for confirmation — Order/Smackagram DB records
      exist, but not a dedicated delivery-confirmation audit log
- [ ] Alternative delivery (text/email) for undeliverable smackagrams
- [ ] Full workflow testing across various mobile devices
- [ ] Reply Smackagram offer when a call is answered live
- [ ] Redirect-to-site-to-reply flow after a VM delivery
- [ ] 18+ recipient age confirmation checkbox, required except when
      "Clean" sensitivity is selected — **current consent checkbox is
      generic** ("I know this person and this is a prank between
      friends"), not an explicit age-verification checkbox tied to
      sensitivity level. Real gap, easy fix once prioritized.
- [x] **Record the reaction for live-answered calls — already built**
      (`record=True` on `place_prank_call`, stored via S3)
- [ ] **Disable recording entirely when the call goes to VM — confirmed
      NOT done.** Recording is currently controlled only by the
      `include_recording` purchase choice, not by `AnsweredBy`. Now that
      AMD/machine-detection exists (tonight's build), this is a real,
      fairly quick fix: skip `<Record>` when `AnsweredBy` indicates a
      machine.

## Stripe Checkout Pages
- [ ] Explicit T&Cs acknowledgment checkbox (T&Cs page doesn't exist yet
      either — see below)
- [ ] Handling for numbers that can't receive calls (blocked/no VM set up)
- [ ] Text/email copy of the smackagram for a $2 upcharge — related to,
      but distinct from, the audio-file-download product idea discussed
      earlier (that was a separate self-serve product; this is an add-on
      to an existing call order)
- [ ] Subscription tiers — $9.99/mo (20 smackagrams + storage + Smack Lab
      access), $14.99/mo (40 smackagrams + storage + Smack Lab access)

## Terms & Conditions
Confirmed not built at all — flagged multiple times already as a real gap.
- [ ] Age compliance language
- [ ] Recording law disclosures (two-party consent states, etc.)
- [ ] Prohibited content policy
- [ ] "Entertainment purposes only" acknowledgment
- [ ] Right to refuse service for suspected foul play
- [ ] Privacy rights/policy
- [ ] All-sales-final policy, with undeliverable refunds issued as
      account credit rather than cash refunds (note: account credit
      requires the account system to exist first)

## Backend Admin Panel
Only the one-off team-code diagnostic tool exists today (`/api/admin/check-team-codes`).
No real dashboard. Everything below is net-new:
- [ ] Real-time stats: sales, sent/delivered/failed counts, estimated
      gross profit (default: current month), registrations, active
      customers, guest vs. registered checkout split, average order
      value
- [ ] Accounts-payable balance for unsent/armed smackagrams + estimated
      fulfillment cost
- [ ] Alerting for any system failures (API outages, etc.)
- [ ] Full production records — queryable by customer, full history of
      accounting + smackagrams + logs
- [ ] Unique ID per customer AND per smackagram for records retrieval
- [~] **Note**: the "214 smacks sent today" / "2,847 this week" numbers
      currently shown on the home page are **hardcoded placeholder
      copy, not real data** — worth knowing before quoting them anywhere
      real, and this admin panel would be what makes them real.

## Security
- [ ] Formal site-security review
- [ ] Brute-force protection on the DB/auth layer (moot until accounts exist)
- [~] API connections — real API keys used throughout (Stripe, Twilio,
      ElevenLabs, SportsDataIO, Anthropic), but no formal audit of
      exposure/rotation practices. Two keys were flagged as exposed in
      chat earlier this build (SportsDataIO, Twilio auth token) and
      still need rotating — see "Pending Items" further up.
- [ ] "No external API access" — needs clarification on what this means
      in context before it's actionable
- [ ] Database backups/redundancy — moot on SQLite; becomes relevant once
      Postgres migration happens
- [x] **Code repository security — already in place** (private GitHub repo)
- [ ] Stripe data cloud storage + local redundancy — Stripe already hosts
      this by default; unclear if this means something beyond that

## General Requirements
- [ ] Business email addresses (at least 3)
- [~] Hosting — live on Render today, but no scalability validation or
      stress testing done
- [ ] Stress test for up to 1,000 simultaneous deliveries
- [ ] "Contact us" links across all applicable pages
- [ ] "Did you just get smacked?" reply workflow — recipient-initiated
      anonymous reply-to-sender flow, a genuinely new customer/transaction
      type, not built
- [ ] Twilio Caller ID branded as "Smackagram" — needs an EIN (already
      flagged as pending earlier tonight)
- [ ] Additional "laughing" voice profile(s) for ElevenLabs
- [ ] Track and surface high-volume teams on the site (real data — see
      admin panel note above about the currently-fake stats)
- [~] Total smackagrams sent display — exists on the page today but is
      **hardcoded, not live data**
- [ ] Updated/upgraded "smack" sound effect file
- [ ] LLC / ownership structure determination — business/legal, not code
- [ ] Partnership agreement (Andy + David) — business/legal, not code
- [ ] Business bank account(s) — business/legal, not code
- [ ] A real staging/test site separate from production, for trying
      changes before they go live to real customers

## Sponsorships & Partnerships
Business development, not engineering — noted here for completeness,
nothing to build:
- [ ] FanDuel
- [ ] Fantasy league platforms (Discord communities, others)
- [ ] Dave Portnoy / Barstool
- [ ] ESPN
- [ ] Meta/Facebook organic posts
- [ ] Paid social ads (TikTok, Meta, X, Instagram)
- [ ] Social media pages across all platforms, linked back to the site
- [ ] Promo codes for new customers / general promotions

## Smack Inbox — evolving "Did You Get Smacked?" into a real history page
Currently a one-time lookup with a real bug: once someone replies, the
same original smack still shows as reply-eligible forever (no "already
replied" state exists). Rather than a narrow bugfix, the plan is to
rebuild this as an actual inbox tied to a phone number — a real precursor
to what a full account/profile page should eventually look like.

**The core bug to fix (do this regardless of the bigger rebuild):**
- [ ] Once a reply is actually placed against a reply_token, that token
      needs to be invalidated/marked used — a "replied" flag or clearing
      the token after use — so the same original smack can't be replied
      to a second time. Keeps this feature distinct from the separate
      "Smack Battles" roadmap idea, which is meant for people who
      actually want an extended back-and-forth.

**The inbox vision:**
- [ ] `/did-you-get-smacked` becomes a real list view for a phone number
      — every smack ever received, newest first, clearly marked
      **New** vs **Replied**
- [ ] Unreplied items work as they do today — instant replay + reply option
- [ ] Replied items become a link into a **conversation view** — both the
      original message and the reply, each with their own real persisted
      audio (see message_audio_url work already done), playable forever
- [ ] Needs a new explicit link between a reply Order and the original
      smack it replied to — doesn't exist yet, the two records are
      currently unconnected once a reply is placed

**Security — phone verification before showing inbox contents:**
- [ ] Not needed for the simple bugfix, but required before building the
      real inbox. Right now anyone can type in *any* number and see "did
      they get smacked" — fine for a one-time yes/no check, but a much
      bigger deal once it shows a full history. Needs some lightweight
      ownership verification (e.g., a one-time code texted to that
      number) before revealing inbox contents. Real added friction, but
      necessary once there's a real history to protect.

**Other open questions, not yet resolved:**
- [ ] Should the original sender get any notification that their smack
      got a reply? Currently the only way they find out is by literally
      receiving the reply call. Hard to do well without a persistent
      identity/account system to notify against.
- [ ] This inbox is explicitly the seed of a real profile/account history
      page — worth building it in a way that could later just become
      "your profile" once Postgres + accounts exist, rather than as a
      fully separate, throwaway system.

## Built, waiting to deploy (Smack Battle audio polish)
User is queueing up a list of fixes to be deployed together later, not
one at a time. Logging each as it's built:
- [x] Countdown tick/click sound on each 3-2-1 number
- [x] Boxing ring bell sound when the battle starts, right as the
      countdown finishes and the overlay clears
- [x] LED-style round scorecard under the team names — 5 rounds, blinks
      on the current round, lights up gold/red for whoever the AI judged
      as the round winner once both sides have gone (tie shows a split
      gold/red LED). AI decides each round's winner for now — real
      per-round audience voting is a possible future upgrade.
- [x] Removed the "Enable sound" button — sound is on by default now,
      no toggle needed. Honest note: browsers still block audio-with-
      sound from truly autoplaying before any interaction with the
      page — handled with a fallback that catches the very first
      click/tap anywhere and starts the crowd loop then, so it's not
      silent, just possibly starts a beat later than page load on some
      browsers.
- [x] Per-person round result popup after every round — each viewer sees
      their own personalized "You won that round!" or "You lost that
      round" (or "Round tied"), 4 seconds on screen, with cheers for the
      winner and boos for the loser. Match bell now also rings at the
      start of every round, not just the very first one.
- [x] Fixed the real root cause of the typing/focus-loss and click-lag
      bugs — the whole battle screen was rebuilding itself (including
      the textarea and buttons) on every 4-second poll, which kicked
      focus out of the input field and could destroy a button mid-click.
      Restructured so the input/button area only rebuilds when something
      it actually depends on changes (whose turn, round number, battle
      status) — otherwise it's left completely alone across polls. Also
      added a proper disabled state on the send button the instant it's
      clicked, so a slow response or an extra click can't double-submit.
- [x] Round result popup extended from 4 to 5 seconds
- [x] All battle sound effects (bell, cheers, boos, ticks, crowd) now go
      through the same loudness normalization already used for the
      speech generation, targeting a louder level than speech (-10 LUFS
      vs speech's -16) — should be noticeably punchier across the board,
      not just the bell specifically.
- [x] Major flow redesign: the chat area no longer expands the whole
      page — it's a fixed-height box that scrolls internally, and the
      page itself never needs scrolling. Only the CURRENT round's lines
      show at a time (clearly labeled "Round X"), instead of every
      round's lines piling up together. After each round, both sides get
      a short AI critique explaining specifically why they won or lost,
      plus a "Start next round" button. No timer — the next round only
      actually begins once BOTH sides have clicked their own button.
      Clicking it rings the bell immediately for whoever clicked.
- [x] Final battle scorecard, shown once the whole battle (all 5 rounds)
      is over — round-by-round chips showing who won each round, an
      overall score tally (e.g. 3–2), and a savage, Smackagram-voiced
      recap generated once per battle: a victory-lap roast for whoever
      won overall, a "you got smoked" recap for whoever lost, both
      referencing real specific lines from the actual battle rather than
      generic hype.
- [x] Fixed real lag on both ends. Two separate causes: (1) the person
      submitting a line that completes a round had to wait for a real
      Claude API judging call to finish before seeing anything update —
      moved judging (and the final recap generation) to a background
      thread, so the response comes back instantly and the critique/
      recap fills in a moment later via polling instead of blocking the
      whole request. (2) The waiting side was capped by a 4-second
      polling interval — cut to 1.5 seconds. Added proper loading states
      ("Judging this round...", "Writing your recap...") for the brief
      real gap while the AI call is still running in the background.
- [x] "Start New Smack Battle" rematch button below the final scorecard
      — same both-sides-must-agree gate as advancing a round, no
      auto-start. Once both click it, a brand new battle is created with
      the same two teams/names and both people get auto-redirected to
      it (each browser correctly carries its own side over to the new
      battle).
- [x] Round critiques and the final recap are now heavily profane and
      brutal — but scoped specifically to roasting the QUALITY of each
      side's actual lines/performance, never the real person. Same
      "roast the content, never fabricate personal details" boundary
      already used successfully elsewhere in the app (no slurs, no
      threats, no sexual content, no real personal attacks).
- [x] Added a visible on-page notice above the message box, stating
      clearly that sexual, threatening, or harassing content isn't
      allowed and gets automatically blocked — reinforces what the
      backend moderation already enforces, now visible upfront instead
      of only surfacing as an error after the fact.
- [x] Pressing Enter now submits your line, same as clicking the send
      button — Shift+Enter still works for an actual line break if
      someone wants a multi-line message.
- [x] Boxing bell (both at battle start and every round after) pushed
      noticeably louder than the other sound effects (-4 LUFS vs the
      general -10 SFX target) so it actually cuts through instead of
      blending in with everything else.
- [x] Fixed mobile layout cutting off the bottom of the screen (submit
      button and text field going off-screen, needing a refresh to
      reach). Root cause: the page used `100vh` for its height, which on
      mobile browsers measures the largest possible viewport as if the
      address bar were fully hidden — but the actual visible space
      shrinks when that bar is showing, pushing content below what's
      really on screen. Switched to `100dvh` (dynamic viewport height,
      with a fallback for older browsers), which correctly tracks the
      real visible area as the browser chrome shows and hides.
- [x] Full battle playtest fixes, all built together:
      · Real "Copy link" button on the share-link page instead of having
        to manually highlight the URL
      · Sound effects now prefetch in the background right when a battle
        is created, giving them a head start before reaching the battle
        room (was contributing to slow perceived load)
      · New epic cinematic rock instrumental loop plays specifically
        while waiting for an opponent to join
      · Strengthened audio unlock — retries on click/touch/keyboard from
        every button on the page, not just a single one-time listener
        (was working on mobile but not consistently on desktop)
      · Removed the permanent safety notice from constant display — it
        now only appears as an error if a message actually gets blocked
      · Fixed a real bug where refreshing mid-battle replayed the entire
        3-2-1 countdown overlay every time, since that flag reset on any
        fresh page load with no regard for which round it actually was
      · Added a visibility-change listener that forces an immediate
        refresh the moment a backgrounded mobile tab becomes visible
        again, instead of waiting on the next regular poll tick
      · AI judge now scores each side's line 0-10 independently every
        round (not just win/loss), shown alongside each round's critique
      · Final scorecard now shows each side's average smack-talk rating
        across all 5 rounds
      · Last round's button now reads "Take It To The Judges" instead of
        "Start next round," signaling the battle is actually over
      · Final scorecard was getting cut off on screen — unlocked page
        scrolling specifically for the battle-complete view (the active
        battle view stays locked/no-scroll as before)
- [x] MAJOR FIX: removed ElevenLabs entirely from Smack Battle sounds.
      This was very likely the real root cause of most of the second
      playtest's problems — /api/battle-sfx was making 8 separate
      sequential ElevenLabs API calls on every cache-cold request, each
      one costing real money and, worse, likely holding a web worker
      hostage for 20-30+ seconds on a server that may only have 1-2
      workers total — which would explain the slow page loads, missing
      sounds, and probably a good chunk of the mobile update lag and
      "Battle not found" flashes too, since those all look exactly like
      what a server buried under a long-running request produces.
      Sounds now come entirely from static files under static/sfx/ (no
      API calls, no cost, instant) — user is downloading and providing:
      battle-intro.mp3, crowd-loop.mp3, new-line.mp3, countdown-tick.mp3,
      bell.mp3, cheer.mp3, boo.mp3, waiting-music.mp3. Any missing file
      just comes back as null and that sound is silently skipped.
- [x] Final scorecard no longer shows round 5's chat lines above it —
      once the battle is complete, just the scorecard, nothing else.
- [x] All 8 real sound files provided and wired in: battle-intro,
      bell, crowd-loop, countdown-tick, cheer, boo, waiting-music, and
      new-line. The waiting-music (epic rock) track now also plays
      during the final scorecard reveal, not just the pre-battle waiting
      screen.
- [x] Added no-cache headers to the battle state endpoint plus a cache-
      busting query param on the frontend poll — mobile Safari is known
      to be more aggressive about caching GET requests than desktop
      browsers, which would exactly explain "works fine on desktop,
      stuck on 'waiting for opponent' until a manual refresh on mobile."
- [x] Trimmed the AI token budget on both the round judge and the final
      recap calls (300→220, 400→250) — should meaningfully cut how long
      both take to come back, addressing the slower round 4/5 responses
      and the recap taking too long after the match ends.
- [x] Added a 9th sound — critique-reveal.mp3, layered under cheer/boo
      (lower volume) every time a round's critique appears, regardless
      of win/loss/tie.
- [x] Rebuilt the audio unlock into a genuine mute/unmute toggle. Real
      autoplay-with-sound before any interaction isn't achievable on any
      website — every browser blocks it deliberately — but now the very
      first tap/click anywhere on the page starts the music immediately,
      and every tap after that toggles mute/unmute (also fixed a bug
      where changing battle status, like the opponent joining, would
      have silently un-muted the music against the user's choice).
- [x] Reverted the mute toggle above per follow-up request — back to a
      one-way permanent unlock (first click starts it, stays on, no way
      to mute again). Same behavior on mobile and desktop since it's one
      universal click/touch/keydown listener.
- [x] Create-battle page: team and name are both now required, and
      pressing Enter in either field submits, same as clicking the
      button.
- [x] Fixed critique-reveal (and cheer/boo/bell/tick/intro/new-line)
      sounds not playing on mobile. Root cause: every one of these was
      created as a brand-new Audio object at the moment it needed to
      play, from inside a poll callback rather than a direct user
      gesture — mobile Safari specifically rejects that. Converted all
      of them to persistent, pre-existing audio elements that get
      "unlocked" via a real play-then-pause during actual clicks/taps,
      then simply replayed from poll callbacks after that — which mobile
      Safari reliably allows.
- [x] Found and fixed a serious bug likely explaining most of the
      "freezes after every round, needs a hard refresh" reports: any
      transient network error during a poll (far more common on mobile
      connections than stable desktop ones) was permanently killing
      polling for the rest of the session via clearInterval, with no way
      to recover except a hard refresh. Removed that entirely — a failed
      poll now just retries next cycle, and "Battle not found" only
      shows for a genuine 404, not a network hiccup. Also switched from
      setInterval to a self-scheduling loop (more resilient to mobile
      timer throttling) with an extra safety net so nothing can silently
      end polling again.
- [x] MAJOR FIX: found the real cause of getting permanently stuck on
      "Judging this round..." — SQLite's default driver flatly refuses
      to let a database connection be used from a different thread than
      the one that created it, and both round judging and recap
      generation run in background threads specifically so submitting a
      line responds instantly. Every database write from those threads
      was throwing, silently caught by a broad exception handler and
      logged only to server logs (never visible to the user), meaning
      the round's result genuinely never got saved — stuck forever, not
      just slow. Added check_same_thread=False to the SQLite connection
      (harmless no-op if this ever migrates to Postgres). Also added a
      20-second timeout fallback with a manual "Try again" button on the
      judging screen, as a safety net against any future issue leaving
      someone stuck with literally no way out but abandoning the battle.
- [x] Fixed hearing an audible bell blip the moment the waiting-room
      music started. Cause: the audio-unlock trick (a real, brief
      play-then-pause on every sound effect, including the bell, done
      the moment someone first taps the screen) could produce an
      audible fragment if pause() didn't land instantly. Now silences
      each sound's volume during the unlock attempt so any such delay
      can never actually be heard.
- [x] Fixed the critique-reveal track (the longer "industrial rock"
      sound that plays under every round's critique) continuing to play
      for its full length in the background even after clicking "Start
      next round" — clicking ready now cuts it off immediately before
      ringing the bell, instead of letting the two overlap.
- [x] Replaced the generic "No lines yet" message at the start of each
      round with something on-brand — now calls out whoever's actually
      on the clock by name: "[Name] is on the clock. Let's see if
      they've got anything."
- [x] Fixed the rock track bleeding over from the waiting screen into
      the final scorecard instead of starting fresh — it now always
      restarts cleanly from the beginning exactly once on the genuine
      transition into the completed battle, rather than just continuing
      wherever it happened to be (and without restarting again on every
      subsequent click, like voting, on the scorecard screen).
- [x] Redesigned the create-battle page — the hero image now carries
      through the whole page as a background (fading into the dark form
      area via a gradient) instead of stopping dead into a flat black
      void below the banner. Form restyled as a "Fight Card" — Anton
      labels, a red/gold accent stripe, a VS divider between team and
      name, stronger button glow. Button now reads "Start a Smack
      Battle."
- [x] Reverted the full-page background per follow-up — back to the
      hero image as a simple banner up top, plain dark background below.
      Kept the fight-card form styling (Anton labels, accent stripe, VS
      divider, button glow) from the redesign.
- [x] Fixed multiple sound files audibly overlapping the moment the
      waiting room loaded. Cause: the "silent unlock" trick from
      earlier — briefly playing every single sound effect (bell, cheer,
      boo, critique, intro, tick, new-line) at volume 0 to pre-unlock
      them for mobile — wasn't actually silent in practice, producing a
      burst of audible blips all firing in quick succession. Removed
      that approach entirely; only the actual background music loop
      gets started on the first tap now, and the one-shot sound effects
      just play normally when their real moment comes.
- [x] Added a retry to round judging — if the AI call or its response
      parsing fails once (a transient hiccup), it now tries a second
      time automatically before falling back to "Couldn't judge this
      round." Particularly important for round 5 specifically, since
      there's no next round to naturally give a bad result a second
      chance.
- [x] Added a personalized coach message for each side, shown while
      waiting on the opponent to respond — generated by the same round-
      judge AI call, factoring in each side's actual standing so far
      (rounds won, average score). Lights a fire under whoever's behind,
      tells whoever's ahead not to get comfortable, raises the stakes if
      it's close — grounded in the real numbers, not generic hype.
- [x] Added a "You ready for this?" hype popup that punches onto the
      screen the moment someone enters the waiting room — clicking
      "Prove It" dismisses it and, since it's a genuine click, also
      naturally triggers the browser's audio unlock and starts the
      waiting-room music as a side effect, without needing to explain
      to the person that they're "unlocking sound."
- [x] Fixed critique-reveal (and other one-shot) sounds not playing at
      all on mobile, and cutting off unreliably on desktop. Root cause:
      after removing the earlier broken "unlock everything on every
      click" approach, these sounds never got a genuine gesture-unlock
      at all — they only ever play from inside poll callbacks now, which
      strict mobile browsers reject outright, and even lenient desktop
      browsers can still interrupt since permission was never really
      granted. Used the hype popup click (a single, real, deliberate
      gesture) to properly unlock all one-shot sounds — one at a time,
      each one fully finishing before the next starts, muted+volume
      zeroed together (more reliably silent than volume alone) so there's
      no risk of the earlier overlapping-blips bug returning.
- [x] Fixed the waiting-room rock music playing during round critiques
      on mobile. Root cause: which music loop should be playing was only
      ever re-checked when a status *change* was detected via a cached
      variable — if a poll update was ever missed or delayed (known to
      happen more on mobile), that cached value went stale, so clicks
      kept incorrectly playing the waiting-room track based on outdated
      info even after the battle had actually moved into a round.
      Switched to always syncing the music against the real,
      freshly-fetched status on every single render, not a cached
      status-change flag.
- [x] Added a proper "Coach's Notes" label above the personalized
      standing-based message shown while waiting on the opponent —
      previously just floated on its own as unlabeled italic text.
- [x] Added a Smack Lab nudge on the final scorecard, shown only to
      whoever lost the battle — a small callout pointing them toward
      Smack Lab's free 1-on-1 AI coaching to sharpen up before their
      next battle. Deliberately styled small and understated (a pill
      link, not a full button) so it doesn't visually compete with the
      rematch button right below it.
- [x] Fixed the "who's up" message at the start of each round two ways:
      it now says "You're up" instead of showing the viewer's own name
      in the third person, and dropped "on the clock" (there's no clock
      anywhere in this feature) for "is up" instead — reads correctly
      whether it's referring to you or your opponent.
- [x] Made critique-reveal.mp3 loop continuously while the critique/
      ready screen is showing, instead of playing through once and
      stopping — only actually stops when "Start next round" is clicked
      (already wired correctly). Also reordered the mobile unlock
      sequence to prioritize this sound first, since it's needed almost
      immediately after round 1 finishes — minimizes any chance it's
      still mid-unlock when it's actually needed.
- [x] Changed "Start next round" to advance immediately for both sides
      the instant either person clicks it, rather than requiring both
      people to independently confirm — one click from whoever gets
      there first is enough now. Removed the now-unreachable "waiting
      for your opponent" UI state that this made obsolete. Also fixed
      the critique-reveal loop only stopping on the device that actually
      clicked — since the round can now advance from the *other*
      person's click, the stop logic had to move to wherever a round
      transition is detected (the same place the bell-per-round logic
      already lives), so it correctly stops for both people regardless
      of who triggered the advance.
- [x] Fixed two round-5 "couldn't judge this round" reports and a
      genuine judging quality bug found in the same test:
      (1) Likely root cause of the judging failures — the round judge's
      token budget was still set to 320 from before coach messages got
      added to the same call, which now has to fit two critiques, two
      coach messages, two scores, and a winner call all in one JSON
      response. Too tight, likely causing truncated/invalid JSON on some
      calls. Raised to 500.
      (2) A round of genuine (if mediocre) trash talk got called a tie
      against literal random-letter gibberish from the other side.
      Added an explicit instruction: real effort always beats a
      non-attempt outright, never a tie just because the real line
      wasn't very good, and score gibberish at or near 0.
- [x] "Judging this round..." now pulses red while it's actively
      working, instead of sitting static — makes it visually obvious
      something's happening in the background rather than looking
      frozen.
- [x] Sped up sending a smack. The content-safety check runs
      synchronously on every single line before it can be saved (can't
      be made async, since a message can't be shown and then
      retroactively censored) — but it was using the full Sonnet model
      for what's really just a binary safe/unsafe classification.
      Switched to Haiku, which should meaningfully cut the wait on every
      send without weakening the actual safety check. This is a shared
      function used everywhere on the site (Smack Chat, Smack Lab,
      Locked & Loaded, and battle lines), so the speedup applies broadly,
      not just to Smack Battle.
- [x] Found the real reason critique-reveal ("the rock music") kept not
      playing on mobile specifically while working fine on desktop: the
      one-shot sound unlock only ever happened via the hype popup, which
      only shows to whoever *creates* the battle. Whoever joins via the
      link never sees that popup at all, so their sounds never got a
      genuine gesture-unlock — explains exactly the "works for the
      creator, not for whoever joined" pattern. Added the same unlock to
      the "Accept the challenge" join button, since that's the joining
      side's equivalent deliberate click.
- [ ] Wired up infrastructure for a repeating judging beep — fires
      roughly every second while "Judging this round..." is showing,
      stops the instant the result actually arrives (or the battle
      completes, as a safety net for the edge case where that state
      gets skipped over between polls). PENDING: needs the actual sound
      file, judging-beep.mp3, dropped into static/sfx/ — everything else
      is done and wired correctly, just silently does nothing until that
      file exists (same graceful-null pattern as every other sound).
- [x] Added a tone shift to the winner's final recap — if they won but
      their own average round score was below 6.0, the recap now
      acknowledges the win while calling out that it was genuinely a
      weak, embarrassing performance to win with — 1-2 sentences of
      real constructive criticism instead of a pure victory lap. The
      "You won the battle" label stays accurate either way; the recap
      text itself is what carries the tonal shift.
- [x] Removed the public crowd-voting section from the final scorecard
      — not useful yet without real audience traffic. Left the backend
      /vote endpoint and supporting code intact (unused but harmless),
      so it's easy to bring back later once there's a real crowd to
      vote.
- [x] Added each player's actual display name (not just their team) to
      the final scorecard — sits right below the score tally, color-
      coded gold/red matching each side, "[Name A] vs [Name B]."
- [x] Made "You won the battle" / "You lost the battle" dramatically
      bigger — was using the same small generic label style as every
      other critique box, which badly undersold the actual climax of
      the whole match. Now large Anton display type, glowing gold for a
      win / red for a loss, with a punchy scale-in entrance animation.
- [x] Fixed the waiting-room music not stopping (and the crowd loop not
      starting) once the battle actually goes active, on mobile
      specifically. Root cause: waiting-room music gets a genuine
      gesture-unlock naturally (already playing during the hype-popup or
      join click), but the crowd loop never did — its first ever play()
      attempt only happens once the battle transitions to active, which
      is usually detected via a poll, not a direct click, so mobile
      rejected it outright. Added crowdLoopAudio to the same deliberate
      unlock sequence as the other sounds.
- [x] Fixed the new-line "pop" sound only playing for the second
      person's line, never the first, in every round. Root cause: a
      guard meant to stop the sound from replaying pre-existing lines on
      a page refresh was written as "skip if this is the very first line
      ever seen" — which correctly avoided the refresh-replay problem,
      but also incorrectly blocked the genuinely first new line of the
      whole battle. Fixed the same way the round-results popup was fixed
      earlier — set the starting baseline properly on first render
      instead of using a blanket "skip the first one" rule.
- [x] Redesigned the "You won/lost that round" popup — now appears dead
      center of the screen (both directions), holds there, then slides
      up and off the top of the screen as it fades out. Uses fixed
      viewport positioning, so it's identical on mobile and desktop.
- [x] Fixed critique-reveal continuing to play right through the final
      scorecard, instead of stopping and handing off to the fresh
      scorecard music. Same category of gap as the earlier judging-beep
      fix — the explicit stop only lived in the "Take It To The Judges"
      click handler and the active-status round-transition check, both
      of which miss the round 5 → complete transition specifically
      (status leaves 'active' entirely at that point), so whoever didn't
      personally click never got the stop command. Added the same
      safety-net stop where the complete-state scorecard rendering
      begins.
- [x] "You won/lost the battle" now blinks/pulses continuously after
      its entrance animation finishes, so it keeps demanding attention
      instead of settling into static text.
- [x] Added retry resilience to the final recap generation, matching
      what round judging already had — a transient AI hiccup no longer
      immediately falls back to the flat "What a battle." text.
- [x] Rebuilt the winner's recap into a proper 3-tier tone system based
      on their average round score, all in Smackagram's voice: below
      6.5 gets real savage constructive criticism (won the battle, lost
      the respect), 6.5-7.9 backs off into genuine encouragement, 8.0+
      goes full over-the-top worship mode. Replaces the earlier
      single-threshold version that only flipped tone below 6.0.
- [x] Rebuilt the chat line, considered and decided against a literal
      split-screen two-column layout — that would fight against the
      mobile viewport constraints the whole build has been optimized
      for (narrower columns force awkward text wrapping, and needs more
      vertical space for the same content). Instead pushed real
      "two fighters, two corners" energy into the existing single-feed
      layout: circular avatar badges per fighter (glowing gold/red ring
      with their initial), stronger color-washed message bubbles with a
      colored edge on the correct side, bolder uppercase name labels,
      and each message now punches in from its own side (side A slides
      from the left, side B from the right) instead of just fading in
      generically.
- [x] All 10 sound files complete — judging-beep.mp3 wired in, fires in
      sync with the pulsing "Judging this round..." text.
- [x] Fixed the header text for whoever's about to accept a challenge —
      it said "Waiting for a challenger" even from the joining side's
      own perspective, which is backwards since they ARE the challenger
      about to join. Now perspective-aware: the creator still sees
      "Waiting for a challenger," whoever's joining sees "Waiting for
      you to accept."
- [x] Fixed a large empty gap between the header and the join form on
      the waiting/accept screen. Root cause: the line-history container
      has flex:1 so it grows to fill available space during an active
      battle, but that same flex-grow was still active while completely
      empty during the waiting state, pushing the join form all the way
      down. Disabled that flex-grow specifically during the waiting
      state.
- [x] Strengthened the gibberish-vs-real-effort judging rule again —
      the earlier fix wasn't reliable enough on its own (a real line
      like "go home, loser" still tied against pure keyboard mashing).
      Added an explicit, literal test the judge has to apply (does it
      form real readable words, yes or no) plus a worked example using
      this exact scenario, instead of just describing the rule in the
      abstract.
- [x] Fixed a real layout-breaking bug: a long message typed as one
      continuous unbroken string (no spaces) had nowhere natural to
      wrap, so it just overflowed its container instead of staying
      inside it — created a full page horizontal scrollbar on mobile
      and got cut off on desktop. Added proper word-breaking to message
      bubbles and critique boxes so long unbroken text is now forced to
      wrap within its box, plus an explicit overflow-x safety net on the
      whole page as a backstop against this class of bug from any other
      source in the future.
- [x] Capped message bubbles and critique boxes at a max height with
      their own internal scroll, rather than letting a genuinely long
      (but properly wrapped, multi-line) message expand the whole bubble
      and push everything else on the page down with it.
- [x] Made "Take It To The Judges" require each person's own personal
      click, on their own device, rather than one person's click
      auto-forcing their opponent straight into the scorecard. The
      backend still finalizes the battle instantly either click (both
      people's data needs to be ready right away), but the frontend now
      gates the actual scorecard reveal behind a local, per-device flag
      — a real participant sees their own round 5 critique and has to
      click through it themselves, independent of what their opponent
      has already done server-side. Same stuck-timeout/retry protection
      applied here too, matching every other round.
- [x] Shortened the final recap text — was running 4-5 sentences per
      side, genuinely too long. Down to a hard 2-3 sentence cap, one or
      two specific real moments instead of several crammed in. Note:
      the earlier page-expansion issue from a long recap is already
      fixed separately (critique boxes got a max-height with internal
      scroll) — that fix just hasn't been deployed yet, this recap
      length trim is on top of that, not instead of it.
- [x] Tightened further per follow-up — down to a hard 2-sentence
      max, one single sharpest moment referenced instead of two.
      Token budget trimmed to match.
- [x] Fixed the boo sound firing on mobile right at round 1's start,
      completely unrelated to any actual round outcome. Root cause: the
      mobile unlock sequence muted each sound, played it silently, then
      *restored* its original volume afterward — that restore step
      could land at almost any moment, including right as the real
      round-start sequence (bell, countdown) was also firing, creating
      a race condition where a "restored to full volume" sound could
      become audible at the wrong time. Restructured so the unlock
      sequence now leaves everything muted permanently afterward (no
      restore step, no race), and moved responsibility for the correct
      volume to the actual playback functions instead — they now
      explicitly unmute and set the right volume every single time they
      genuinely play something, rather than trusting leftover state.
      Also found and fixed two other direct play() calls (the crowd
      loop and the new-line ding) that bypassed this safe handling
      entirely and would have gone silent after the mobile unlock ran.
- [x] Fixed the two-corners chat messages moving and flickering
      aggressively and continuously, instead of once when genuinely new.
      Root cause: the entire chat history was being rebuilt from scratch
      on every single poll (every 1.5s) regardless of whether anything
      actually changed, which destroyed and recreated every message
      element each time — replaying every entrance animation for every
      message, constantly. Added a signature-based guard so the chat
      only actually rebuilds when the line content genuinely changed.
      Also removed the slide-in movement entirely per follow-up
      feedback and replaced it with a subtle, finite border-blink on
      the message bubble itself instead (plays twice then settles,
      correctly only once per real new message now).
- [ ] Countdown tick sounds (3-2-1) reported not playing on mobile OR
      desktop. Traced the code path thoroughly and found no logic bug —
      it's identical to the intro/bell sound calls in the same function,
      which apparently do work. Best working theory (not confirmed,
      since I can't hear the actual audio files myself): the intro
      whoosh plays for up to 3 seconds, and the first tick was firing at
      2.2s — likely still overlapping with and getting masked by the
      still-playing intro sound's tail end, on both platforms equally
      since this is a timing/mixing issue rather than an autoplay quirk.
      Pushed the countdown start to 3.2s to give the intro sound room to
      finish first. Flagging honestly that this is a diagnosis-driven
      fix, not a confirmed root cause — worth confirming it actually
      resolves this on the next test.
- [x] Fixed having to click "Take It To The Judges" twice to actually
      reach the scorecard. Direct side effect of the manual-unlock
      feature built earlier tonight: that feature added a SECOND "Take
      It To The Judges" button (the local per-device unlock, meant for
      whoever DIDN'T click first) — but whoever DID personally click the
      original button was also being shown this second one, forcing a
      redundant confirmation of their own already-made choice. Now
      auto-unlocks the scorecard for whoever personally triggered the
      transition; the separate local confirmation only applies to their
      opponent, who didn't click and whose status just changed
      underneath them via polling.

## Future: shareable final scorecard
Saved for later per user request — a real feature, worth doing
properly rather than rushed. Key finding worth remembering: Instagram
and TikTok genuinely have no share-intent URL at all (deliberate
platform restriction, not a buildable gap) — every app that "shares to
Instagram/TikTok" is actually just handing the person a downloadable
image or using the OS-level native share sheet, not a real web link.
- [ ] Twitter/X and Facebook real one-click share buttons (both have
      genuine share-intent URLs; Facebook can't pre-fill caption text
      though, that's a platform restriction too)
- [ ] Generate a downloadable "battle card" image of the final
      scorecard — this is the actual real path for Instagram/TikTok,
      since people manually post a nice pre-made graphic themselves
- [ ] Consider the native Web Share API (navigator.share()) on mobile
      as a bonus catch-all, which can surface whatever's installed
      (possibly including Instagram/TikTok) — not guaranteed or
      controllable, just an extra option where available

---
*Last updated: 2026-07-26*

## Session addendum — four visual features added
- [x] Live typing indicator — opponent's box pings the backend
      (throttled to once every 2s) while they're actively typing;
      the waiting side sees "[Name] is typing..." with pulsing dots.
      Typing status computed server-side to avoid client/server
      clock skew.
- [x] Round-by-round momentum bar — a slim bar above the LED row
      that fills proportionally toward whichever side is winning
      based on decided rounds (ties don't push it either way).
- [x] Confetti burst for the winner — fires once when their
      scorecard appears, 60 gold/red/white pieces, self-cleans after
      ~3.5s.
- [x] Real team color theming — a new backend helper matches each
      side's free-text team name (e.g. "Cowboys") to its actual
      brand color using the existing alias-matching system, falls
      back to default gold/red for leagues without color data
      (college, soccer). Honest scope note: this re-themes solid
      colors (text/backgrounds/borders) since those use CSS
      variables directly, but glow/shadow effects throughout the
      file are hardcoded rgba values, not tied to these variables —
      those keep the original gold/red glow regardless of team
      colors unless that's expanded separately later.

## Regression found and fixed same session
- [x] The new typing indicator feature reintroduced the exact
      textarea-wiping bug from earlier tonight. Cause: is_typing_a/
      is_typing_b were included in the same signature that gates
      rebuilding the whole action area (including the textarea) — since
      a typist's own pings reflect back to their own client via polling,
      their own typing status flickering true/false every couple
      seconds kept destroying and recreating their own textarea,
      wiping whatever they'd typed. Removed typing status from that
      signature entirely, and gave the typing indicator its own
      dedicated DOM slot that updates independently on every render —
      it can never touch or rebuild the textarea now, regardless of how
      often typing status changes.

## Team color scoping fix (same session)
- [x] The team color theming was too broad — overriding the global
      --gold/--flare CSS variables affected everything (buttons, LED
      indicators, message bubbles, avatars), not just team name text as
      intended. Reverted the global override entirely; team colors now
      apply only via targeted inline styles on the specific places team
      names are displayed as text (matchup header, VS countdown screen,
      final scorecard labels, "is calling out [team] fans"). Everything
      else — buttons, LEDs, bubbles, avatars — correctly stays the
      original fixed gold/red theme regardless of team colors.

## Scorecard reveal timing fix (same session)
- [x] Clicking the final "Take It To The Judges" button was taking
      people straight to the scorecard even though the AI-generated
      final recap was still finishing in the background — landed on a
      "Writing your recap..." placeholder inside an otherwise-complete
      scorecard, rather than a clean, fully-ready reveal. Restructured
      so clicking now holds on a clear loading state ("Finishing up
      your recap...") until the recap has genuinely finished generating,
      then reveals the complete scorecard all at once. Same 20-second
      stuck-timeout/retry protection as everywhere else. Applies
      equally whether someone is the one who originally finalized the
      battle or the one confirming separately afterward.

## Main generator: roast-topic keywords (new feature)
- [x] Added an optional free-text field to the main "Send a Smack"
      generator, below the team field — user can enter up to 3
      comma-separated specific things to roast the team about (e.g.
      "Dusty Baker, trash cans, cheating" for the Astros). When
      provided, the AI weaves these in specifically rather than picking
      its own angle. When left blank, falls back to the original
      behavior — a general roast using whatever real current or
      historical material fits best. Sanitized both client and
      server-side (capped at 3 topics, 60 chars each).

## Content quality refinement — rhetorical vs declarative recipient insults
- [x] Added a specific rule distinguishing rhetorical/hypothetical framing
      about the recipient ("are you a delusional bastard?", "you'd have
      to be a dumbass to...") from flat declarative personal insults
      stated as fact ("you're a delusional bastard", "your dumbass").
      Only the former is now allowed. Uses the user's own real example
      (a Chiefs roast) as the concrete illustration in the prompt itself,
      since concrete examples land far more reliably than an abstract
      rule alone. This is the shared _HARD_LIMITS constant, so it applies
      across the main generator, game recap roasts, and the reply-smack
      feature all at once — not just the one flow that was tested.

## User accounts: SMS 2FA and screen names (same session)
- [x] Added SMS-based 2FA. A fresh 6-digit code is texted (via the same
      Twilio account already used for prank calls) at every login and
      right after registration, expires after 10 minutes. New /verify
      page for entering the code, with a resend option. The seeded
      admin test account skips 2FA entirely for frictionless testing.
      Email 2FA deliberately deferred — no email-sending infrastructure
      exists on this site at all yet (a known, pre-existing gap), so
      building it now would mean silently pretending it works.
- [x] Added a required, unique screen name to registration — this is
      what displays anywhere identity is shown (chat, battles) instead
      of the person's real name. Same content moderation check used
      everywhere else on the site (catches slurs/hate speech, not just
      an obvious-word blocklist), plus case-insensitive uniqueness so
      "CowboysHater" and "cowboyshater" can't both exist. Editable later
      from the profile page, re-checked for uniqueness/moderation only
      if actually changed.

## Gated every real feature behind login (same session)
- [x] Applied @login_required across 33 routes: main generator's
      actual generate/send/preview actions (page itself stays viewable
      per the explicit instruction — the login prompt fires only when
      actually initiating a smackogram), Locked & Loaded (full page),
      Smack Lab (page + respond/verdict), Smack Chat (page + post/rate/
      report), Smack Battle (create page, battle room itself — so
      whoever clicks a shared link while logged out gets sent to log in
      first — plus every action: create, join, submit line, ready,
      typing, vote, rematch, even the read-only status poll), and the
      whole "Did You Get Smacked" / reply / conversation flow.
      Deliberately left ungated: home page, terms/contact, Stripe/
      Twilio webhooks, cron endpoint, and pure reference-data endpoints
      (sensitivity levels, voice options, sports schedules) that don't
      let anyone actually do anything.
- [x] Updated the main generator's frontend specifically — both the
      generate call and the checkout call now redirect straight to
      /login (preserving the page as ?next=) the moment either one
      hits the new login-required response, rather than just showing a
      generic error.

## Registration crash fix (same session)
- [x] Found and fixed the actual cause of "Couldn't create your account"
      — the phone number field's own placeholder text ("(555) 555-5555")
      encouraged a format that the E.164 conversion couldn't handle; it
      only prepended a "+" rather than stripping formatting characters,
      so a real-world input like that placeholder would produce an
      invalid number Twilio rejects outright, crashing the whole
      registration request with an uncaught exception. Fixed the actual
      conversion to properly strip all non-digit characters first
      (verified against parens, dashes, and bare digits — all correctly
      normalize to the same valid number now). Also wrapped every SMS-
      send call (registration, login, resend) in proper error handling,
      so any future delivery failure fails gracefully with a specific
      message instead of a generic crash — registration specifically
      rolls back the just-created account rather than leaving an
      orphaned, unverifiable user record behind.
- [x] Fixed browser autofill showing a combined "Andy Weissberg" in
      just the first name field instead of properly split first/last —
      added explicit autocomplete hints (given-name, family-name,
      nickname, email, tel, bday, new-password/current-password) to
      every field across registration, login, and profile, so the
      browser can't guess wrong about which field is which.

## 2FA temporarily disabled (same session)
- [x] SMS 2FA showed "undelivered" in Twilio's message logs after
      registration — likely A2P 10DLC carrier filtering (US carriers
      require businesses to register their messaging campaign before
      SMS reliably delivers; without it, Twilio reports success but the
      carrier silently blocks the actual text). That's a Twilio Console
      configuration issue, not something fixable in code. Added a single
      clearly-commented toggle (TWO_FACTOR_ENABLED, top of app.py, one
      line) to skip 2FA entirely for now so testing everything else
      isn't blocked — both registration and login already check this
      flag, so flipping it back on later is a one-line change once the
      10DLC registration is sorted out in Twilio.
      IMPORTANT REMINDER: re-enable this before relying on 2FA for
      anything real.

## NEW FEATURE: Smackcast — Fantasy Football weekly recaps (major build)
Full concept: connect a fantasy league, get a weekly AI-generated,
Smackagram-toned AUDIO recap of real matchups, auto-delivered every
Tuesday at 9AM. One-time $39.99 season pass, no renewals.

Competitive research done first — audio is a genuine differentiator;
competitors found (League Rewind, SmackScript, FantasyCast, Scoutcast.ai,
FantasySportsReports) are text/podcast/strategy-focused, none combine a
consistently savage tone with phone-call delivery.

### Built and verified this session:
- [x] SmackcastSubscription + SmackcastRecap models
- [x] Sleeper integration (sleeper_service.py) — find leagues by
      username, league info, current NFL week (pulled directly from
      Sleeper's own API), full week matchup data joined from
      rosters+users+matchups
- [x] Recap script generation (smackcast_service.py) — Claude-generated,
      word count auto-scales linearly with team count (8 teams = 3 min,
      14+ teams = 5 min, verified against actual math)
- [x] Discord webhook + GroupMe bot delivery functions
- [x] New Twilio function (place_smackcast_call) — separate from the
      existing 59-second prank call limit, 6-minute cap for recaps
- [x] Public share page (/smackcast-recap/<token>) — no login required,
      universal delivery fallback
- [x] Weekly generation orchestration (scheduler.py) — follows the
      EXACT same external-cron-hits-an-endpoint pattern already proven
      reliable on this site (in-process scheduling was already tested
      and found unreliable on Render's free tier)
- [x] New cron endpoint /api/cron/generate-smackcasts, same secret-key
      protection as the existing cron endpoint
- [x] Stripe one-time $39.99 checkout + webhook handling to activate
      the subscription
- [x] Full "Connect Your League" wizard (/smackcast) — platform picker
      (Sleeper live, ESPN/Yahoo marked Coming Soon), league lookup/
      selection, delivery method picker with conditional inputs
      (phone/SMS/Discord/GroupMe, web link always on)
- [x] Success page, added to home page nav

### Explicitly NOT done yet (future phases, already scoped):
- [ ] ESPN integration — buildable now (unofficial API), private
      leagues need the owner to paste SWID/espn_s2 cookies
- [ ] Yahoo integration — blocked on user registering a Yahoo Developer
      app and providing Client ID/Secret (OAuth, can't be done without
      those credentials)
- [ ] Email delivery — blocked on the same pre-existing missing email
      infrastructure gap noted earlier in the 2FA work
- [ ] Meme generation from best lines, screenshot-upload fallback for
      unsupported platforms — good ideas from competitive research,
      not yet built
- [ ] The actual external cron job needs to be configured (e.g.
      cron-job.org) to hit /api/cron/generate-smackcasts weekly —
      same manual setup step the existing check-smackagrams cron
      required

## Smackcast Phase 2: ESPN integration (same session)
- [x] espn_service.py — uses the same unofficial, community-maintained
      ESPN fantasy API pattern the whole developer community relies on
      (no official public API exists). Public leagues work with zero
      extra setup; private leagues need the owner's SWID/espn_s2
      cookies, since ESPN has no OAuth flow for third parties.
      get_week_recap_data() returns data in the exact same shape as
      Sleeper's version, which is what lets the scheduler treat both
      platforms identically downstream.
- [x] New /api/smackcast/connect-espn-league endpoint — doubles as the
      connection test (wrong league ID or missing/bad cookies fails
      here, before any payment happens)
- [x] Subscription creation endpoint now accepts platform + ESPN cookie
      fields instead of being hardcoded to Sleeper
- [x] scheduler.py restructured to handle both platforms — key
      simplification: the actual NFL week number is universal
      regardless of which fantasy platform someone's on, so Sleeper's
      week-detection stays the single source of truth even for ESPN
      subscriptions; only the matchup data pull itself branches by
      platform
- [x] Frontend wizard — ESPN tile enabled, full connection flow with
      clear private-league cookie instructions (DevTools walkthrough),
      connection result confirms league name/team count before
      proceeding to delivery/payment

Yahoo remains blocked on the user registering a Yahoo Developer app
and providing Client ID/Secret — genuinely can't be built without
those credentials, not a scoping choice.

## Smackcast Phase 3: shareable meme generation (same session)
- [x] Restructured script generation to also extract the single best/
      most quotable line in the same API call (structured JSON output,
      2-attempt retry) — avoids a second Claude call just to pull out
      a highlight.
- [x] Built real image generation (Pillow) — 1080x1080 branded meme:
      gold/red accent bars matching the site's actual color scheme,
      auto-sizing bold Anton headline text that steps down in size
      until it fits (tested both a long line at 5 lines/82pt and a
      short line staying at max 90pt/1 line — both look genuinely
      good, not just technically functional), league/week footer.
      Bundled the actual Anton and DejaVu Sans Bold font files directly
      in static/fonts/ rather than relying on whatever's installed on
      the deployment server, since that's not guaranteed.
- [x] Wired into the pipeline — meme generates after the script/audio,
      uploads to S3, gets attached to Discord posts as a real inline
      embed image (not just a link), and displays on the public recap
      page. Meme generation failure is non-fatal — the actual recap
      (audio + script) still delivers fine even if the image step
      fails for some reason.
- [ ] GroupMe delivery does NOT include the meme yet — GroupMe bots
      only support plain text via this simple API, no rich image
      embeds the way Discord has. Could add as a follow-up using
      GroupMe's more involved image-upload API if worth the effort.

DEPLOYMENT NOTE: this needs static/fonts/Anton-Regular.ttf and
static/fonts/DejaVuSans-Bold.ttf actually present on disk to work —
these are delivered as a separate small zip alongside the main code
zip, since the main zip deliberately excludes all of static/ to avoid
the deletion issue from earlier tonight, and this is a brand new
subfolder with zero overwrite risk.

## Smackcast Phase 4: basketball + baseball support (same session)
Research done first, changed the actual scope:
- Confirmed (user directly verified) Sleeper only offers real
  season-long leagues for football and basketball — no baseball at
  all, resolving earlier uncertainty from search results.
- Confirmed via ESPN's own documentation: basketball's most common
  format is Head-to-Head Points (matches football's existing
  structure), but baseball's most common formats are Rotisserie and
  Head-to-Head Categories — NOT points. Rotisserie has no weekly
  matchups at all; Categories compares several stats separately
  instead of one combined score. Built for Head-to-Head Points only
  for now across all three sports — Roto/Categories support is a
  separate, bigger future undertaking, not silently ignored.

### Built:
- [x] Added sport field to SmackcastSubscription (was a real gap —
      previously silently assumed football)
- [x] Generalized sleeper_service.py — SUPPORTED_SPORTS = (nfl, nba),
      get_current_week(sport) and find_leagues_by_username(...sport)
      both now sport-aware
- [x] Generalized espn_service.py — GAME_CODES mapping (nfl->ffl,
      nba->fba, mlb->flb) baked into the URL, all functions sport-aware.
      Added get_current_matchup_period() using ESPN's own league status
      directly, rather than borrowing Sleeper's week-state as a
      "universal clock" — that breaks down for baseball (Sleeper has
      none) and isn't guaranteed to match ESPN's own numbering anyway.
- [x] Restructured scheduler.py's generate_weekly_smackcasts() —
      current week/period now determined per-subscription based on
      platform+sport rather than once globally; Sleeper weeks cached
      per-sport within a run (identical across every subscription for
      that sport), ESPN periods fetched per-subscription (needs that
      league's own credentials, can't be cached the same way)
- [x] All three API endpoints (find-sleeper-leagues, connect-espn-
      league, create-subscription) now accept and validate sport,
      matching each platform's actual real support
- [x] Frontend wizard — added a full sport-selection step; baseball
      tile automatically disables with an explanatory note when
      Sleeper is selected, re-enables for ESPN; a scope disclaimer
      about points-only scoring shown directly in the UI, not just
      buried in a doc

## Smackcast test tool (same session)
- [x] Admin-only test tool (/smackcast/test) — runs the entire real
      pipeline (Claude script generation, real ElevenLabs audio, real
      meme image) against realistic sample matchup data instead of a
      real league. Built specifically so the whole generation flow can
      be verified end to end without needing real fantasy accounts,
      and deliberately avoiding pulling any real person's actual league
      data for testing — even "public" league data is still a real
      stranger's identity being used to generate mocking content about
      them without consent, which doesn't become acceptable just
      because it's only for a private test.
  - generate_sample_matchups() — realistic fake team names, sport-
    appropriate score ranges (verified: NFL ~55-165, NBA ~480-920,
    MLB ~90-260), correctly pairs into matchups regardless of team count
  - Test page shows everything: the sample matchups used, the full
    script, the best line, playable audio, and the meme image

## Real bug found: sport wasn't reaching script generation (same session)
- [x] Fixed a genuine bug caught while answering "does this look the
      same for every sport" — generate_weekly_recap_script() never
      accepted a sport parameter at all, and the system prompt was
      hardcoded to say "fantasy football" regardless of which sport was
      actually being generated for. Basketball and baseball recaps
      (including in the test tool) were silently being told they were
      writing football recaps. Added a sport parameter with correct
      per-sport labeling (fantasy football/basketball/baseball), wired
      through both real call sites (the weekly scheduler and the test
      tool) that were missing it.
- [x] Also root-caused and fixed the test tool's actual crash — it
      wasn't the ffmpeg timeout (though that was a real, worthwhile fix
      too), it was gunicorn's own default 30-second worker timeout
      killing the whole process before a multi-step pipeline (Claude +
      ElevenLabs + ffmpeg + image generation, all sequential) could
      finish. Fixed via Render's Start Command setting (--timeout 180),
      not something fixable from code alone.

## Meme image broken (question mark icon) - fixed without AWS access (same session)
- [x] Meme images uploaded successfully to S3 but showed a broken
      image icon in the browser — confirmed via dev tools this was a
      403-style permission issue, not a generation failure. Root
      cause: memes were uploaded to a separate smackcast-memes/ S3
      folder, while the confirmed-working audio uploads use tts/ —
      the bucket's public-read access is almost certainly a bucket
      policy scoped to that specific path, which the new folder wasn't
      covered by. Fixed by having memes reuse the exact same tts/
      path audio already uses successfully — inherits the same public
      access automatically, zero AWS console changes needed (useful
      since account access was temporarily lost).

## Script reading bare numbers instead of "X points" (same session)
- [x] Since this audio gets read aloud (not read as text), a bare
      number like "96.2" means nothing to a listener without context —
      but the input data format (team scores in parentheses) was
      apparently getting carried straight into spoken script text
      sometimes without translation. Added an explicit instruction
      requiring "points" attached to every scoring-related number
      mentioned (team totals, margins, differentials), with concrete
      before/after examples in the prompt itself for reliability.

## Contextual sound effects (same session) - major restructuring
Restructured the entire audio pipeline from "one continuous script ->
one TTS call" to "intro/per-matchup segments/outro, each segment
tagged with a reaction -> separate TTS per piece -> stitched together
with sound effects spliced in based on tags."

- [x] generate_weekly_recap_script() now returns {intro, segments
      (each with text + reaction tag: boo/laugh/cheer/gasp/none),
      outro, best_line, full_text}. The AI tags each matchup segment
      itself based on the tone of what it just wrote about that
      matchup — not a hardcoded rule matching score thresholds.
      Malformed/unrecognized reaction tags sanitize to "none" rather
      than crashing.
- [x] New assemble_recap_audio() in smackcast_service.py — generates
      speech per-segment via a new low-level generate_speech_bytes()
      (extracted from the existing audio function, returns raw bytes
      instead of uploading), splices in a sound effect after each
      segment via _pick_random_sfx(), combines everything with pydub,
      runs the FINAL combined audio through the same loudness
      normalization every other clip gets, uploads once.
- [x] _pick_random_sfx() — randomized selection among however many
      numbered variants actually exist (smackcast-{reaction}-1.mp3
      through -10.mp3), so the same sound doesn't repeat every week.
      Verified: gracefully returns None with zero crash when no files
      exist yet for a reaction type (confirmed in isolation).
- [x] Added pydub to requirements.txt (wraps ffmpeg, already confirmed
      present and used for loudness normalization).
- [x] Exposed elevenlabs_service's loudness normalization as a public
      function (was previously private/underscore-prefixed), since
      smackcast_service now needs to call it directly on the final
      assembled audio.
- [x] Both real callers (scheduler.py's weekly generation, and the
      test tool) updated to use the new structure.

SOUND EFFECT FILES NEEDED (user is creating these, not pulling from
ElevenLabs) — drop into static/fonts/../sfx/ as: smackcast-boo-1.mp3
through smackcast-boo-N.mp3, same pattern for laugh/cheer/gasp. Fully
wired and ready — works with however many variants exist, silently
does nothing extra until at least one exists per reaction type.

HONEST FLAG: this trades one API call for several (intro + one per
matchup + outro) instead of one big call — total character count and
therefore cost should stay roughly the same, but total generation TIME
increases due to sequential network round-trips per call. For a large
league (7+ matchups), this could meaningfully eat into the 180s
gunicorn timeout already set. Worth watching once real testing happens
with sound effect files in place — if this becomes a real bottleneck,
parallelizing the TTS calls (instead of sequential) would be the fix,
not something built yet since it adds real complexity and wasn't
needed until this restructuring.

## Sound effects added, restraint guidance (same session, not deployed)
Files pulled and placed via a GitHub-based workaround for the chat's
file upload limit (repo temporarily made public for transfer, raw
content URLs pulled directly, converted to mp3, placed with correct
naming). Reaction types expanded beyond the original 4:
- trombone (6 variants) — descending brass, sad/pathetic moments
- flourish (3 variants) — rising brass, punctuates a sharp line/stat
- aww (2 variants) — sympathetic sad crowd, NOT anger (distinct from boo)
- gasp (2 variants), laugh (3 variants), boo (1 variant, more coming)
- cheer — still 0, not yet provided

Also added explicit restraint guidance to the prompt per direct
feedback: "none" is now framed as the actual default (not just one of
seven equal options), with a concrete rough ratio (~1 in 3-4 matchups
should get an actual sound effect) — the writing is already funny on
its own, effects are meant to support engagement, not replace/overtake
the content.

NOT YET DEPLOYED — holding per explicit instruction while more files
get added. Repo currently public (temporarily, for file transfer) —
needs switching back to private once done, and the temporary
sfx-uploads/ folder should be deleted from the repo at that point too.

## Real deploy bug: pydub broken on Python 3.13+ (same session)
- [x] Test tool crashed with "No module named 'pyaudioop'" — confirmed
      via research: Python 3.13+ removed the audioop stdlib module
      entirely (PEP 594), which pydub depends on internally. Render
      runs Python 3.14. Fixed by adding audioop-lts==0.2.2 to
      requirements.txt — a real, verified PyPI package (confirmed
      genuinely published, correctly restricted to Python >=3.13 only,
      which matches exactly why it's needed here) that transparently
      restores the audioop module under its original import name, so
      no code changes needed elsewhere.

## Sound effect playing on top of / drowning out voice (same session)
Genuinely could not reproduce this through isolated testing, despite
thorough attempts:
- Tested pydub concatenation (+=) with simulated silence AND real audio
  files on both sides — duration always matched expectations exactly,
  no overlap at the logical level in any test
- Tested the full export -> reload cycle — duration preserved correctly
- Tested the actual ffmpeg loudness normalization step on combined
  audio — duration preserved correctly there too
- Ruled out double-generation/multiple-tabs as the cause (confirmed
  directly with the user — this was a single generation)

Applied two defensive fixes addressing the most plausible explanations,
even without being able to definitively prove either was the exact
root cause (no ElevenLabs API access in this sandbox to generate real
speech audio and fully reproduce the exact real-world scenario):
- [x] Standardize every audio piece (speech AND sfx) to the same frame
      rate/channel count before concatenating — confirmed real,
      inconsistent properties across the actual sfx files (96000Hz vs
      44100Hz, mono vs stereo)
- [x] Force constant bitrate (192k) MP3 export instead of pydub's
      default, which can produce variable bitrate output — VBR MP3s
      are a documented source of seek/playback miscalculation in some
      browsers, which could explain garbled/overlapping playback
      without showing up as any duration mismatch in the file itself

HONEST FLAG: this is a best-effort fix based on the most likely
explanations, not a confirmed root-cause fix the way most other bugs
tonight were — worth confirming directly on the next real test whether
this actually resolved it before considering it closed.

## Sound effects too loud relative to speech (same session)
- [x] Real, separate issue from the overlap bug — the final loudness
      normalization step balances the AVERAGE loudness of the whole
      combined file, but doesn't balance the RELATIVE level between
      speech and sfx portions within it. Sound effects are
      professionally mixed/mastered clips (punchy, loud on their own);
      ElevenLabs speech sits at a more modest conversational level by
      comparison — without explicit reduction, sfx naturally overpower
      speech regardless of overall normalization. Applied a -10dB
      reduction to every sound effect specifically before splicing it
      in (verified: produces exactly the intended reduction). This
      value may need tuning after a real listen — 10dB is a reasonable
      starting point, not something tested against real speech audio
      given no ElevenLabs API access in this sandbox.

## Postgres migration (same session, not yet deployed)
Site currently runs on SQLite (wipes on restart, known issue flagged
all night). App was already architected well for this migration —
reads connection string from DATABASE_URL env var, falls back to
SQLite only if unset. Made two defensive code additions:
- [x] Fixed Render's postgres:// -> postgresql:// scheme (modern
      SQLAlchemy 1.4+ requires the newer scheme; this is a well-known
      gotcha that would crash the app on startup on first connecting
      to a real Postgres instance without this fix)
- [x] Added psycopg2-binary==2.9.12 to requirements.txt (verified real
      package/version on PyPI) - the actual Postgres driver, required
      since SQLite's driver is built into Python but Postgres needs a
      separate package

Given SQLite wipes on every restart anyway, there's no meaningful
existing data to actually migrate over - db.create_all() already runs
on startup and will automatically create all tables fresh on the new
Postgres instance the first time the app starts against it.

NEXT STEPS (Render dashboard, user's side): create a Postgres instance
on Render, link it to the web service (Render auto-sets DATABASE_URL
when you do this), deploy this code, tables get created automatically
on first startup.

## TODO before real launch: upgrade Postgres to Pro tier for HA
Currently running Basic-256mb ($6/mo instance + $4.50/mo for 15GB
storage = $10.50/mo), with Storage Autoscaling ON and High Availability
OFF. HA (automatic failover to a standby database) only unlocks on Pro
instances and higher — deliberately deferred for now since there's no
real production traffic yet to justify the extra cost. REMINDER: once
this is an actual live product with real paying users, upgrade to a
Pro-tier (or higher) Postgres instance and turn HA on — that's the
actual "system redundancy" piece of the original requirement, and it
genuinely isn't covered by the current Basic tier.

## TODO before real launch: upgrade ElevenLabs to Enterprise tier
Currently on Creator ($22/mo, 121K credits). Confirmed via math: even
the top-shown Scale tier ($299/mo, 1.8M credits) only supports roughly
225 active Smackcast subscribers/month using the site's actual Turbo
model rate (0.5 credits/character) - none of the public tiers are
built for real scale (tens/hundreds of thousands of users). REMINDER:
once there's real subscriber volume to justify it, contact ElevenLabs
about Enterprise pricing (custom, not on the public pricing page).

## Real contact emails wired in (same session)
- [x] Updated Contact page with the 2 real working @smackagram.com
      inboxes, replacing placeholder addresses. support@ stays as-is
      (already matched), report@ and billing@ both now point to
      owners@ since those categories need direct founder attention for
      a solo-operated business. Note: these are real inboxes a human
      checks manually - not the same as automated email-sending
      infrastructure (still a known, separate gap for things like
      email-based 2FA).

## Support page header image (same session)
- [x] Added header image to Contact page, pulled via the same GitHub
      public-repo workaround used for the earlier sound effect files
      (chat upload limit still in effect). Optimized before adding -
      original was 2MB PNG at 1983x793; resized to 1200px wide and
      converted to JPEG (no transparency needed, RGB not RGBA), down
      to 120KB - a 17x reduction with no visible quality loss at
      header size.

## Support header image sizing fix (same session)
- [x] Fixed the header image looking small/undersized on desktop -
      root cause was the image being trapped inside the page's narrow
      640px text-reading container (.wrap), when its actual aspect
      ratio (wide banner shape) needs real room to display properly.
      Moved it outside that container into its own wider (1400px max)
      section, letting it actually use available desktop screen space
      as a real hero-style banner instead of shrinking down small.

## Second admin account (same session)
- [x] Added admin1/admin as a second seeded admin account, same pattern
      as the original admin/admin - lets two people (founder +
      administrator) be logged in simultaneously with separate
      accounts rather than sharing one session. Verified the existing
      2FA-skip logic checks the is_admin flag generically (not
      hardcoded to a specific email), so this new account correctly
      skips 2FA automatically too, with zero additional changes needed.

## Site-wide nav consistency (same session)
The HTML structure and {% include '_nav.html' %} directives already
existed across all 21 non-index pages, but real gaps were found and
fixed:
- [x] Added @app.context_processor for current_user - without this,
      only the home page route manually passed current_user into its
      template, meaning the Login/Register vs My Profile state in the
      nav would have been broken/undefined on every other page. Now
      automatically available site-wide, no per-route changes needed.
- [x] Found and fixed: 19 of 21 pages were missing the .nav-links and
      .auth-links CSS classes entirely - the nav HTML was included
      correctly but would have rendered without proper spacing/layout,
      looking visually broken compared to the home page. Fixed via a
      systematic script insertion after each page's existing (identical
      across all 19) nav{} CSS rule.
- [x] Fixed 2 outlier "success" confirmation pages (locked_n_loaded_
      success.html, order_success.html) that had zero nav CSS at all -
      these use a centered full-screen layout for the confirmation
      message. Also caught and fixed a real layout bug here: the body's
      flex-centering would have centered the NAV ITSELF vertically
      alongside the main content, rather than keeping it as a proper
      top bar - restructured into a separate .center-wrap div so the
      nav sits correctly at top and only the confirmation content
      centers below it. order_success.html was also missing CSS
      variables entirely (hardcoded hex colors) - added the standard
      :root block to match the rest of the site.
- [x] Switched index.html itself to use the shared _nav.html partial
      too (was previously an inline duplicate) - avoids future
      divergence between the two if either gets updated separately.
- [x] Verified: full Jinja2 template syntax validation across every
      .html file (catches include/syntax errors a div-count check
      would miss), HTML div-balance check across all 21 updated files,
      full Python compile check.

## Two real bugs caught by the design project's audit (same session)
Genuine credit here - these were caught by the separate design-focused
project's headless browser audit, not found independently here. Both
verified directly against the actual files and fixed:

- [x] order_success.html and locked_n_loaded_success.html had a
      generic `a{...}` CSS selector styling EVERY link on the page as
      a big red button - written back when each page had exactly one
      link (the CTA). This was a real bug introduced by ME earlier
      tonight when adding the shared nav include to these pages,
      without noticing this pre-existing conflicting CSS - the nav's
      8 links all inherited the red button styling, causing sideways
      scrolling and broken layout, worst on the Locked & Loaded
      success page (broken at every width including desktop). Fixed
      by scoping the styling to a new .cta-btn class instead of the
      generic tag selector, applied only to the actual CTA link.
- [x] verify.html referenced 'JetBrains Mono' in its CSS but the
      Google Fonts link tag only loaded Anton and Inter - font was
      silently falling back to generic monospace. Added JetBrains
      Mono to the font link.

## Reload page navigation: clickable steps, Go Back, data preservation (same session)
Built per direct request - the step indicator ("Roast Voice Target Load
Account") was purely decorative before, with no way to go back and no
site nav on the page at all.

- [x] New GET /api/pending-action/<id> endpoint - returns a pending
      action's stored payload + action_type, scoped to the current user
- [x] /reload route now reads ?pending_action=<id>, looks up its
      action_type, and passes both through to the template so step
      labels/links adapt to whether this came from Send a Smack or
      Locked & Loaded
- [x] reload.html: added the standard site nav (_nav.html + shared
      stylesheet, including the mobile hamburger drawer - previously
      this page had neither), rebuilt the topbar with a real "<- Go
      Back" link and clickable step words, all pointing to
      /send-a-smack?resume=<id> (or /locked-n-loaded?resume=<id>)
- [x] Fixed mobile: the step row previously just vanished entirely
      below 860px (display:none) - now shows a compact wrapped version
      instead of disappearing, per direct request that mobile needs
      the same functionality, not a hidden/removed version
- [x] send_a_smack.html: built the actual resume mechanism -
      resumeFromPendingAction() fetches the stored payload and
      repopulates team, recipient name, roast text, sensitivity level,
      and voice selection on the main page; the order modal (phone,
      reply opt-in, sender phone - fields that only exist in that
      modal) gets pre-filled from the same payload when it opens.
      Added team+sensitivity to the /api/orders request body
      specifically so they'd be preserved in the stored payload for
      accurate restoration (backend ignores these extra keys otherwise)
- [x] Fixed a genuine separate bug found while working through this:
      the @app.route decorator for /api/wallet/create-payment-intent
      had gone missing entirely (function existed in the file but was
      never registered as a Flask route) - confirmed this was actually
      live in production, meaning payment completion was silently
      broken. Fixed and confirmed the route registers correctly via
      Flask's actual url_map, not just a syntax check.
- [x] VERIFIED END-TO-END, not just structurally: ran a real Flask
      server, created an actual PendingAction row with realistic test
      data, logged in via Playwright, navigated to
      /send-a-smack?resume=<id>, and confirmed every single field
      (team, recipient name, roast text, voice, sensitivity level, AND
      the three modal-only fields: phone, reply opt-in, sender phone)
      genuinely repopulated correctly - not assumed, actually tested
- [x] Verified desktop and mobile layouts programmatically (bounding
      boxes, no overlaps, no zero-size elements, no viewport overflow,
      hamburger toggle present) rather than relying only on visual
      screenshot inspection
- [x] Full verification suite: Python compile, full `import app` test,
      Jinja2 parse across every template, HTML balance, JS syntax

SCOPING DECISION (communicated to user): Locked & Loaded's page has a
substantially more complex multi-step wizard structure (dynamic game
list selection, show/hide card states with "Change" buttons) compared
to the generator's single-scroll form. Given the user's immediate,
active situation was specifically the Send a Smack flow, built and
fully verified that path end-to-end this session. Locked & Loaded
still gets a working "Go Back" link/step nav pointing back to
/locked-n-loaded?resume=<id>, but that page does not yet have the
resumeFromPendingAction() logic to actually repopulate its form fields
from the resume parameter - a real gap, flagged, not yet built.

## Payment button freezing on "Firing your Smackagram..." (same session)
User reported the final Pay button hangs indefinitely with no error.
Console showed a 400 on a Stripe internal "sessions" request (likely
background Express Checkout Element activity, inconclusive as the
direct cause) alongside otherwise-normal Stripe/Google Pay preconnect
noise.

Found and fixed a genuine, concrete bug regardless of the exact root
cause: stripe.confirmPayment() was called with no try/catch and no
elements.submit() beforehand in either the main Pay button handler or
the Apple/Google Pay express handler. Per Stripe's current documented
best practice, elements.submit() should be called first to validate
and collect data from whichever Element the user actually used - this
was skipped entirely. And critically: if confirmPayment() throws
rather than resolving with the normal {error} shape, there was nothing
to catch it - the button would freeze on "Firing your Smackagram..."
forever with zero feedback, exactly matching what was reported.

Fixed both handlers: elements.submit() now runs first (surfacing a
clear error if the form itself is invalid), and both are wrapped in
try/catch with console.error logging plus a user-facing fallback
message, so any future failure shows something instead of hanging
silently. Not able to fully reproduce the live Stripe payment flow in
this sandbox to confirm this is the exact root cause - flagged
honestly. If the freeze recurs after this fix, the browser console
should now show either Stripe's real error message or the
"Something went wrong completing payment" fallback with a caught
JS error logged above it, which will make the actual cause visible for
the first time.

## Payment freeze - diagnostic improvements round 2 (same session)
The elements.submit()/try-catch fix stopped the silent freeze (confirmed
by user - now shows the fallback error message), but the real
underlying cause still isn't confirmed. Console showed BOTH a caught
error logged as "Object" (unreadable in Safari's console as plain
text) AND a separate "Unhandled Promise Rejection" that our try/catch
could not be responsible for, since it wraps every await in the actual
click handler - strongly suggesting Stripe.js itself is internally
rejecting a promise not tied to our own awaited calls, likely related
to the persistent "sessions" 400 error that's shown up in every console
capture so far (probably Express Checkout Element / Google Pay session
setup in the background).

Changes made:
- Isolated the Express Checkout Element's creation/mounting into its
  own try/catch, separate from the main Payment Element - if wallet
  session setup fails, it now hides itself gracefully and can no
  longer take down card payments, which are the primary path
- All error logging now prints error.message/type/code/name as
  separate readable arguments instead of a single Object reference,
  which Safari's console was collapsing to just "Object" when copied
  as text
- Added a window 'unhandledrejection' listener as a last-resort net,
  since Stripe.js can reject promises internally in ways no try/catch
  in our own code can intercept - this at least surfaces what it
  actually is in the console instead of the opaque default message

STILL NOT CONFIRMED: the exact root cause of the "sessions" 400 itself.
If isolating the Express Checkout Element doesn't resolve the freeze
on its own, the next round of console output (with the improved
logging) should finally show readable error text rather than "Object",
which should make the actual cause diagnosable for the first time.

## Payment freeze - actual root cause found (same session)
With readable error logging finally in place, got the real error:
"Could not retrieve elements store due to unexpected error" - a known
Stripe.js internal-state error.

Root cause identified: initPaymentForPack() runs again every time a
user clicks a different tier card (starter/loaded/arsenal), and it was
creating a brand new stripe.elements() instance and mounting brand new
Payment/Express Elements into the SAME DOM containers every single
time, without ever destroying the previous instances first. Mounting
a new Element on top of an old one that was never unmounted is a known
way to corrupt Stripe.js's internal state - and switching tiers before
paying is completely normal, expected user behavior on this page, not
an edge case.

Fix: paymentElementInstance and expressElementInstance are now tracked
at module scope (previously local variables re-created and discarded
on every call, with no way to reference the old ones). initPaymentForPack()
now calls .destroy() on both before creating anything new, wrapped
defensively in case destroy() itself throws on an already-broken
instance.

Higher confidence than the previous two rounds, since this is a
specific, verifiable cause matching a well-documented Stripe.js failure
pattern rather than a defensive/diagnostic-only change - but still
flagging honestly that it hasn't been confirmed working in the live
payment flow, since that requires an actual browser + Stripe test
session this sandbox can't fully replicate.

## Payment freeze - Express Checkout Element disabled (same session)
The Elements-cleanup fix did not resolve the issue - same exact error
recurred: "Could not retrieve elements store due to unexpected error".
The "sessions" 400 error has now appeared in every single console
capture across all attempts, and appeared 3 times in the latest one,
strongly implicating Express Checkout Element's (Apple/Google Pay)
background session setup specifically.

Given Payment Element and Express Checkout Element share the same
underlying Stripe.js store when tied to one PaymentIntent, a
synchronous try/catch around Express Checkout's setup (the prior fix)
cannot protect against an async internal failure inside Stripe.js's
own code corrupting that shared state - which appears to be exactly
what's happening.

DECISION: temporarily disabled Express Checkout Element entirely
(commented out, not deleted, with a clear note on why and how to
re-enable). The Apple/Google Pay button and "or pay with card" divider
are hidden; only the card Payment Element shows now. This is a real
regression in checkout options (no more one-tap Apple/Google Pay) but
prioritizes getting the core, primary card payment path working
reliably, which is what almost every user will use regardless.

NOT YET RESOLVED: why Google Pay's session setup returns a 400 in the
first place. This needs separate investigation (possibly: Google Pay
merchant configuration in the Stripe dashboard is incomplete even
though Apple Pay/domain verification was done; Google Pay may have
distinct setup requirements). Flagged for follow-up once card payments
are confirmed working again.

## ACTUAL root cause found: test/live Stripe key mismatch (same session)
After 4 rounds of code-level fixes (elements.submit(), error handling,
proper Elements cleanup on tier switch, temporarily disabling Express
Checkout Element entirely) all failed to resolve the payment freeze,
confirmed the real cause was environmental, not code: STRIPE_SECRET_KEY
on Render was sk_test_... while STRIPE_PUBLISHABLE_KEY was pk_live_....
Test and live mode are two entirely separate, walled-off environments
on Stripe's side - a PaymentIntent created server-side in test mode
does not exist from the perspective of a frontend initialized with a
live-mode publishable key. This explains "Could not retrieve elements
store due to unexpected error" precisely, and why it persisted through
every code change: the code was never the actual problem.

User is confirmed intentionally in Stripe test mode (not accidental) -
fix is updating STRIPE_PUBLISHABLE_KEY on Render to a pk_test_... key
matching the existing sk_test_... secret key.

Re-enabled Express Checkout Element (Apple/Google Pay) - it was never
actually the cause, despite 3 rounds of investigation pointing at it
(the persistent "sessions" 400 error was a red herring, or itself a
symptom of the same key mismatch). Kept the defensive try/catch
isolation around it regardless, as reasonable practice for a
background wallet-session setup, but the temporary full removal has
been undone now that the real cause is understood.

STILL TO CONFIRM: full payment flow working end to end once the
publishable key is corrected on Render - not yet verified live, since
this requires the user's own Render/Stripe dashboard changes outside
what could be fixed in code alone this session.

## Payment success page frozen - "attempts" ReferenceError (same session)
After the key mismatch fix resolved actual payment processing (test
card 4242... succeeded), the destination page (reload_success.html)
got stuck on "Finishing up..." forever. Console showed:
"ReferenceError: Can't find variable: attempts" - a real JS bug, not a
webhook/backend issue.

Rewrote the polling logic using an explicit IIFE wrapper instead of a
bare if-block for scoping, converted the async/await + try/catch
pattern to plain .then()/.catch() promise chaining, and added a
console.error on the catch path (previously silent). The original
code was arguably valid JS on paper, but rather than debug an
ambiguous scoping edge case blind, moved to an unambiguous, explicit
function-scope pattern instead.

VERIFIED with real browser tests (not just syntax checks) using
Playwright with a mocked pending-action-status endpoint:
- Confirmed zero page errors and correct ~1 request/second polling
  cadence while status stays "pending" (1 request at 0.5s, 4 requests
  by 3.5s, heading correctly stuck on "Finishing up..." throughout -
  matching the real user's report before the fix, minus the actual bug)
- Confirmed the "completed" path: heading changes to "All set!" and
  the page genuinely redirects to the server-provided redirect URL

Also re-enabled Apple/Google Pay (Express Checkout Element) in
reload.html per direct request, now that the root cause (test/live key
mismatch) is confirmed and fixed - it was never actually the problem.

## Smack Inbox privacy/security fix - phone ownership verification (same session)
Built per direct request: the existing check_if_smacked() endpoint's own
docstring already flagged the vulnerability - any logged-in user could
search ANY phone number and read the actual message content, with zero
proof they owned that number.

Decided against waiting on SMS specifically being blocked by A2P 10DLC
carrier filtering (still true - TWO_FACTOR_ENABLED = False site-wide).
Proposed voice-call verification as an alternative that would work
today, but per direct instruction, built with SMS as originally
requested - user will handle Twilio A2P 10DLC registration separately
on their end.

- [x] New models: VerifiedPhone (proof of ownership, supports multiple
      verified numbers per user over time) and PhoneVerificationCode
      (tracks an in-progress code, separate from the existing account-
      level two_factor_code/two_factor_expires_at fields used for
      login/registration - this verifies an arbitrary searched number,
      not necessarily the account's own registered phone)
- [x] Rewrote check_if_smacked(): removed @login_required from the API
      itself (though note: the PAGE route /did-you-get-smacked already
      had its own @login_required, discovered during testing - so in
      practice this page has always required login to even reach the
      search form; the API-level change is still correct defense in
      depth). Returns only a count (no content) unless the requester
      has a matching VerifiedPhone record for that exact number.
- [x] Two new endpoints: /api/verify-phone/send (texts a 6-digit code,
      simple abuse guard - 60 second cooldown between requests per
      user+number) and /api/verify-phone/confirm (validates the code,
      creates the VerifiedPhone record on success)
- [x] Rewrote did_you_get_smacked.html frontend: blurred/locked teaser
      cards with fake placeholder text (not real content) when a match
      exists but isn't verified, inline "text me a code -> enter it"
      flow for logged-in users, login/signup CTA for logged-out
      visitors (currently unreachable in practice given the page-level
      gate, but correct if that ever changes)

VERIFIED END-TO-END with a real running server (not just code review):
- Confirmed real message content is NOT leaked on an unverified search
- Confirmed wrong code is correctly rejected with an error
- Confirmed correct code unlocks the real content
- Confirmed verification PERSISTS across subsequent searches (no
  re-verification needed once done)
- Confirmed the critical security boundary: verifying one number does
  NOT unlock a different number for the same logged-in user - a second
  real test record was created specifically to test this, and it
  correctly stayed locked
- Confirmed zero JS errors throughout the full flow
- Confirmed database migration safety: the two new tables are created
  automatically by db.create_all() on both a fresh Postgres database
  and an existing one with data already in it (unlike the earlier
  balance_cents column issue, these are brand new tables, not
  alterations to existing ones, so no manual migration step is needed)

NOT YET DONE: user needs to complete Twilio A2P 10DLC registration on
their end before real SMS codes will actually deliver in production -
until then, the send-code endpoint will fail with the same "couldn't
send a verification text" error the existing registration/login 2FA
flow already surfaces for the same underlying reason.

## Meet Smacky mascot page (same session)
Built the brand/mascot introduction page per direct request - "loud,
hype-man energy, always talking trash" personality, added to main nav
(both desktop and mobile drawer versions).

- [x] New route /meet-smacky (no login required - pure marketing
      content). Checks whether static/img/smacky-hero.png actually
      exists on disk and passes this to the template, so the page
      shows a clean placeholder box with instructions until the real
      generated image is dropped in - swaps over automatically with no
      further code changes needed once that file exists.
- [x] Full page: hero with placeholder/portrait, "Who Is This Guy" bio
      section, 6-quote "Smacky-isms" wall, 5-item "Smacky's Rules"
      code section, CTA linking to /send-a-smack. Matches the site's
      existing black/red/gold design system and Anton/Inter/JetBrains
      Mono font stack (same pattern as did_you_get_smacked.html) rather
      than introducing a new visual style.
- [x] Advised against a full-bleed background photo (text legibility,
      responsive cropping issues, harder to extend down a long page) -
      recommended a contained hero character illustration instead,
      matching how most mascot pages actually work. Gave the user a
      concrete image-generation prompt (transparent/solid background,
      comic-book style, dynamic trash-talking pose) to go generate the
      actual art themselves.
- [x] Added "Meet Smacky" to both the desktop nav-links and the mobile
      nav-drawer in _nav.html, placed right after "How it works" since
      it's also brand-introduction content.
- [x] Verified: full Python compile, full app import with the route
      confirmed actually registered in Flask's url_map (not just
      assumed from the decorator), all templates parse, actual
      rendered screenshots taken on both desktop (1280px) and mobile
      (393px) with zero layout issues (no zero-size elements, no
      horizontal overflow, mobile hamburger toggle present), and
      programmatic confirmation all 6 quote cards and all 5 rule rows
      actually render.

NOT YET DONE: the actual Smacky artwork itself - user is generating
this separately using the prompt guidance given. Once generated, just
needs to be saved as static/img/smacky-hero.png and the placeholder
disappears automatically.

## Smacky portrait added + optimized (same session)
User generated and uploaded the real Smacky portrait. Original upload
was 2.4MB PNG - heavy for an image displaying at max 340px wide,
especially given the site has a documented history of caring about
exactly this (an earlier commit optimized site images from 61MB to 3MB
total). A single 2.4MB image would have undone a meaningful chunk of
that effort on its own.

Optimized following the exact same pattern already used for the site
logo (WebP primary + PNG fallback via <picture>, not just swapping
formats blindly):
- Resized to 700x769 (roughly 2x the 340px max display width, for
  retina sharpness without carrying full original resolution nobody
  can actually see)
- WebP: 2.4MB -> 157KB (93% reduction)
- PNG fallback: 2.4MB -> 953KB (60% reduction, for older browsers
  that don't support WebP)
- Updated meet_smacky.html to use <picture><source webp>+<img png>,
  matching _nav.html's existing logo pattern exactly

VERIFIED: dimensions and pixel content spot-checked to confirm no
corruption during resize, and - critically - confirmed via a real
browser (not just assumption) that it actually requests/loads the tiny
WebP file rather than the larger PNG fallback, displaying at the
correct 340px width with correct 700x769 natural (2x) resolution
behind it.

## Site-wide Smacky branding pass (same session)
Went through the site page by page, weaving Smacky's name into the
branding as "the voice and roaster" behind the generators, per direct
request. Deliberately NOT forced everywhere - skipped Smack Chat
entirely since that's genuine user-generated content, not AI-voiced,
so attributing it to Smacky would be inaccurate.

- [x] services/voice_options.py: the "default" voice is now literally
      labeled "Smacky (Classic)" - a structural change, not just copy,
      making him the actual named, selectable default voice across
      both the main generator and Locked & Loaded
- [x] Homepage: "We make the call" -> "Smacky makes the call" (How It
      Works step 3), Step 1 credits him with reading the line too, and
      both the main hero paragraph and the mini-generator card now
      name him as the one writing AND voicing the roast
- [x] Send a Smack (main generator): Step 1/Step 3 copy renamed
      ("Smacky's first draft", "preview it in Smacky's voice"), all 3
      meta tags (search/social preview) updated to match
- [x] Locked & Loaded: meta tags updated, the auto-generated post-game
      roast now credits Smacky by name. Also found and fixed something
      real: an existing sidebar mascot image on this page had no name
      attached (alt="") - named it Smacky in the alt text (left the
      actual image file untouched since I couldn't fully confirm its
      exact visual content matches the new portrait art)
- [x] Smack Lab: full pass - every visible "coach"/"Coach" reference
      (there were ~9) renamed to Smacky by name, matching the user's
      own example almost verbatim ("Smack Lab - 1-on-1 coaching with
      Smacky"). Left the internal .coach-label CSS class name as-is
      since it's not user-visible.
- [x] Smack Battle + Battle Room: investigated the actual backend
      logic before editing (found BOTH an AI judge scoring each
      individual round AND genuine crowd voting deciding the overall
      winner - two different real mechanisms). Credited Smacky
      precisely for the part that's actually his (per-round scoring:
      "each one scored live by Smacky" / "Smacky judges every round"),
      left "the crowd decides who wins" untouched since that's
      accurately describing real community voting, not AI.
- [x] Smackcast: meta tags updated ("hosted by Smacky"), and the hero
      paragraph's "in Smackagram's voice" changed to "in his own
      voice" - directly naming him as the voice, per the user's
      specific request wording.
- [x] Smack Chat: deliberately left alone - real fan-posted trash
      talk, not AI-generated, so a Smacky attribution would misrepresent
      the feature.

VERIFIED: full Python compile, full app import (with voice_options
output directly checked to confirm "Smacky (Classic)" actually shows
up first), every touched template parses via Jinja2, HTML balance
checked on every file, JS syntax validated on every file with scripts.

## Smack Lab hero image simplified (same session)
Per direct request to get a new photo in quickly without dealing with
the full responsive setup right now: simplified from a 4-file
<picture> element (3 WebP breakpoints + JPG fallback) down to a single
plain <img> pointing at static/img/smack-lab-hero.jpg. Works
everywhere immediately with just one file upload. Flagged as a
deliberate, temporary simplification - the multi-size responsive
version can be rebuilt later the same way the Locked & Loaded hero
still works, once there's time to do the full WebP/srcset treatment
properly.

## Smack Battle: Intensity System (Phase 1 of matchmaking work, same session)
Built the intensity/tone system for Smack Battle, per direct request -
first phase of the broader Battle matchmaking overhaul, reusing the
site's existing 4-level Clean/Mild/Aggressive/Savage scale rather than
inventing a new one.

- [x] New `intensity` column on the Battle model (1-4, default 4 to
      match prior always-Savage behavior), with a real Postgres
      migration added to the startup migration block
- [x] Battle creation now accepts and validates intensity (reusing the
      same SENSITIVITY_LEVELS validation used elsewhere)
- [x] Rebuilt the battle judge's system prompt to be genuinely
      intensity-aware - built a parallel _BATTLE_JUDGE_TONE_BY_LEVEL
      set (separate from the main generator's _TONE_BY_LEVEL, since
      this shapes the JUDGE's own critique/coach-message voice, not
      AI-generated battle lines - those are typed by real people).
      Hard safety limits (no personal attacks, no protected-characteristic
      content, etc.) are identical at every level and never scale down,
      matching the same pattern already used for the main generator.
- [x] Intensity selector added to the battle creation page, populated
      from the same /api/sensitivity-levels endpoint the main generator
      already uses (one shared system, not a duplicate)
- [x] Battle room page shows the intensity level in three places: to
      the creator while waiting, to the joining side BEFORE they accept
      (the actual core requirement - they need to know what they're
      agreeing to), and throughout the entire active battle in the header

VERIFIED thoroughly, not just written and assumed:
- Tested the Postgres migration against an existing database with real
  data already in it, not just a fresh one
- Directly tested _build_battle_judge_system_prompt() across all 4
  levels: confirmed each produces genuinely distinct output, confirmed
  hard limits are present at every single level, confirmed an invalid
  level safely falls back to Savage rather than crashing
- Full live-server, real-browser end-to-end test: created an actual
  battle at a deliberately non-default intensity (Clean, not Savage),
  confirmed the database genuinely stored the selected level (not
  silently defaulting), then confirmed the badge displays correctly to
  the creator while waiting, to a separate browser context simulating
  a stranger who clicked the link fresh (before they'd accepted
  anything), and in the active battle header after they joined

NOT YET BUILT (Phase 2, still to come): the actual matchmaking queue
itself - async pairing segmented by sport/league, and the AI-persona
fallback (openly labeled, not disguised as a real person) when no real
opponent is waiting. This session only covered the intensity system
that Phase 2 will build on top of.

## Smack Battle: 18+ age confirmation for non-Clean intensity (same session)
Per direct request: any intensity other than Clean requires an active
"I confirm I am 18 years of age or older" checkbox before continuing -
on BOTH the creation side (selecting Mild/Aggressive/Savage) and the
joining side (accepting a battle someone else already set to a
non-Clean level, since they're about to participate in that content
too even though they didn't choose it).

- Checkbox is hidden entirely and not required when Clean is selected/
  set - only appears for Mild, Aggressive, Savage
- Both the "Start a Smack Battle" and "Accept the challenge" buttons
  are blocked with a clear error message if the relevant intensity is
  non-Clean and the box isn't checked
- Purely a frontend confirmation gate (no backend enforcement) -
  worth knowing if a stricter/server-verified version is ever wanted

VERIFIED with a real live-server test, not just reading the code:
confirmed the gate genuinely shows/hides based on the actual selected
intensity, confirmed creation is genuinely blocked without the checkbox
checked, confirmed it succeeds immediately after checking it, and
confirmed the exact same behavior independently on the join side using
a real Savage battle a separate account had to actually join.

## Smack Battle: team must be selected from dropdown, not just typed (same session)
Per direct request: the "your team" field on both the creation and
joining sides now requires an actual click/selection from the
team-search autocomplete dropdown - typing a team name (even a
perfectly valid, correctly-spelled one) is no longer sufficient on its
own.

Implementation: extended the shared, site-wide static/js/smackagram.js
autocomplete (used on multiple pages) with a new data-smk-selected
marker - set to 'true' only when choose() fires from an actual
dropdown click/Enter-key selection, and cleared the moment the user
types anything afterward (leveraging the existing suppress guard that
already distinguishes real keystrokes from the autocomplete's own
synthetic events). This is purely additive - nothing else on the site
reads this marker, so no other page's behavior changes.

Smack Battle's own JS (both create and join flows) now checks this
marker before allowing submission, with a clear error message if it's
missing.

VERIFIED with real live-browser tests, not just reading the logic:
- Typing a team name with no selection: confirmed blocked, both create
  and join sides
- Actually clicking a real suggestion from the dropdown: confirmed the
  marker gets set and creation succeeds
- The critical edge case - manually editing the text AFTER a valid
  selection (e.g. selecting "Dallas Cowboys" then typing an extra
  character): confirmed the marker correctly clears and submission is
  blocked again, not left in a stale "selected" state

## Battle waiting room: "Waiting for opponent" - larger, blinking red (same session)
Per direct request, referencing a live battle URL: the creator's
waiting-room text ("Waiting for a challenger") is now "Waiting for
opponent", styled larger than any other visible text on the page and
blinking red - dedicated new CSS class (.waiting-pulse) with its own
keyframe animation, kept separate from the shared .round-indicator
class so the active battle's "Round X of 5" text is unaffected.
Applies only to the creator's side (mySide 'a') - the joining side's
"Waiting for you to accept" text is unchanged, since that's a
different message for a different person in a different situation.

VERIFIED live in a browser, not just visually assumed: confirmed the
exact text, confirmed the computed color is the site's red (--flare),
confirmed the blink animation is genuinely applied and running (not
just present in CSS but unused), and specifically checked computed
font sizes against every OTHER visible element on the actual waiting
screen (filtering out a couple of much larger but entirely hidden
intro-animation elements that would have given a false negative) to
confirm 32px really is the largest visible text on that screen, not
just assumed from the stylesheet.

## Smack Battle: fixed backwards "calling out" copy on the join screen (same session)
Per direct request, but this was also a genuine logical bug, not just a
wording preference: the join screen said "[Creator] is calling out
[Creator's own team] fans" - which doesn't make sense, since a Cowboys
fan wouldn't be calling out Cowboys fans. The creator's team was never
meant to be who they're challenging - it's just who THEY are, since no
specific opponent/team is chosen until someone actually joins.

Fixed to: "[Creator], a [their team] fan, is calling out [LEAGUE] fans.
Step up?" - shows their team as context (who you're about to face),
and correctly says they're calling out fans of the whole league
(anyone in that sport can join), not fans of their own team.

Added a small LEAGUE_LABELS lookup local to battle_room.html, matching
exactly Smack Battle's own 8 league dropdown options (nfl/nba/mlb/nhl/
wnba/ncaaf/ncaab/soccer) - didn't reuse services/team_display.py's
existing LEAGUE_LABELS dict since its keys are built around a
different, more granular league taxonomy (individual soccer leagues,
etc.) that doesn't line up with Smack Battle's simpler league picker.

VERIFIED with real live-server tests: created an actual battle as
"Cowboy Guy" with Dallas Cowboys in the NFL, confirmed a separate
browser context (simulating a fresh visitor) sees the exact corrected
copy: "Cowboy Guy, a Dallas Cowboys fan, is calling out NFL fans. Step
up?" - then repeated with an MLB battle (Yankees) to confirm the
league label mapping works correctly across leagues, not just NFL.

## Battle room: exit confirmation + choppy crowd audio fix (same session)
Two fixes per direct request:

1. Exit confirmation while a battle is in progress. Warns via the
   browser's native beforeunload dialog while status is 'waiting' or
   'active', not once 'complete' (nothing left to lose leaving then).
   Important honest limitation flagged: modern browsers (Chrome,
   Firefox, Safari) block custom text in this dialog for security
   reasons and always show their own generic wording - this can
   trigger the dialog, but not control what it says. Verified by
   directly testing the actual event-handling logic (dispatching real
   beforeunload events and checking defaultPrevented) across all three
   battle states, confirming it correctly arms for waiting/active and
   correctly stays off for complete.

2. Choppy/breaking-up crowd audio "in between rounds" - investigated
   rather than guessed at. Root cause found: judgingBeepAudio (the
   beep during "Judging this round...") restarts itself every second
   via playAudioElement()'s currentTime=0 reset, while crowdLoopAudio
   continues playing simultaneously throughout - since battle.status
   stays 'active' during judging (awaiting_next_round is a separate
   flag, not a status change), the existing background-music logic
   never paused the crowd loop for this window. Two audio elements
   sharing playback resources, one of them restarting every second,
   is a well-known cause of audible stutter on the other. Fixed by
   pausing the crowd loop for the duration of the judging beep and
   resuming (not restarting) it once judging completes.

VERIFIED with real runtime tests, not just code reading: confirmed no
reference/timing errors calling the modified functions in the actual
page context, then set real .src values on both audio elements and
directly observed the crowd track genuinely pause when the beep starts
and genuinely resume after it stops - not just that the code looks
right, but that the actual audio-element state changes as intended.

## Smack Battle: 60-second per-turn timer with auto-submit (same session)
Per direct request: each side gets 60 seconds per turn. When it expires,
whatever's typed gets auto-submitted - still checked against the site's
real safety guardrails, and if it fails (or nothing was typed at all),
the round is awarded to the other side (as long as they submit
something real), with a clear "did not enter in time" message instead
of AI judging.

- [x] New `turn_started_at` on Battle (server-side timer anchor - reset
      whenever the turn changes, including a fresh round) and
      `timed_out` on BattleLine (marks a missed/unsafe placeholder,
      message always empty - unsafe text is never stored or displayed
      even under a timeout). Both migrated, tested against a real
      Postgres DB with existing data.
- [x] Reused the site's own existing, already-live safety gate
      (content_moderation.check_message_safety) rather than building a
      new one - discovered while surveying that this already exists
      and already fails closed (blocks) on any error.
- [x] submit_battle_line() now accepts is_timeout - on a normal manual
      submission, behavior is completely unchanged (empty/unsafe are
      still hard rejections). Under is_timeout, empty or unsafe both
      become a "timed_out" placeholder instead of an error, so the
      round can still move forward.
- [x] New _resolve_timeout_round() - when either side timed out, skips
      the AI judge entirely (nothing valid to compare) and awards the
      round directly: the other side wins if only one side timed out,
      a tie if both did, with fixed (not AI-generated) critique text
      and scores.
- [x] Frontend: real 60-second countdown anchored to the server
      timestamp (not client-side drift), urgent pulsing animation in
      the final 10 seconds, auto-submits whatever's typed the moment
      it hits zero. Timer is properly cleared whenever it's no longer
      that side's turn, so it can't keep running/firing in the
      background after the turn moves on.

FOUND AND FIXED A SEPARATE, PRE-EXISTING BUG while building this: the
"must select team from dropdown" feature (built earlier this same
session) never actually worked on the joining side. teamBInput is
inserted into the page dynamically after someone's battle state loads,
but the team-search autocomplete's attach logic only ever scans the
page once, on initial load - before that field exists. The dropdown
itself likely never even appeared there. Fixed by exposing a
window.smkAttachTeamSearch() re-scan function from the shared
autocomplete script, called right after the join form's HTML is
inserted. Confirmed fixed with a real test: dropdown now appears, and
clicking a real suggestion correctly sets the selection marker.

VERIFIED thoroughly with a real live server, not just reading the code:
- Timer genuinely counts down over real elapsed time (confirmed two
  separate readings a few seconds apart actually differ correctly)
- All 4 backend timeout scenarios tested directly against the API:
  side A times out then B submits a real line (B wins, correct
  critique text); reverse order (A submits then B times out - A wins);
  both time out (tie); and unsafe content submitted right at timeout
  (correctly treated as timed_out, with the actual unsafe text
  confirmed NEVER stored - message comes back empty, not the flagged
  content)
- Confirmed the frontend auto-submit is real, not just theoretical: set
  a battle's turn_started_at to 61 seconds in the past directly in the
  database, loaded the page fresh with zero manual interaction, and
  confirmed the turn correctly auto-advanced and was marked timed_out
  within about a second - the client-side timer genuinely detected
  expiry and fired on its own

## Smack Battle: music mute toggle + configurable 5/10 rounds (same session)
Two of the five backlog items from this thread, fully built and verified.

### Music mute toggle
- Fixed-position button, top-right corner, toggles both background music
  tracks (waiting-room music + active-battle crowd loop)
- Preference persisted via localStorage so it sticks across battles/visits
- Properly integrated into the existing music engine rather than bolted
  on top - the old code's own comment said "no mute toggle" explicitly;
  this closes that.

### Configurable 5/10 rounds
- New `max_rounds` column on Battle (default 5, migrated, tested against
  both a fresh DB and an existing one with real data already in it)
- Rounds selector added to battle creation, validated server-side (must
  be exactly 5 or 10)
- All hardcoded "5" references replaced with the battle's own
  max_rounds: the round-completion check in ready_for_next_round(), the
  "Round X of Y" display, and the "final round" button-label logic
- Also fixed a related, smaller issue found while doing this: the AI
  battle-recap prompt had "5 rounds" hardcoded directly into its system
  prompt text, which would have given the AI wrong context on a 10-round
  battle. Now generic, with the actual round count passed dynamically.
- Updated all marketing copy (meta tags, hero text) that previously
  assumed "five rounds" specifically

VERIFIED with real live-server tests, not just reading the code:
- Created an actual 10-round battle, confirmed max_rounds=10 stored
  correctly and displayed correctly ("Round 1 of 10", not "of 5")
- Simulated being at round 5 in a 10-round battle and advancing forward -
  confirmed it correctly continues to round 6 (status stays "active"),
  rather than prematurely completing the way the old hardcoded check
  would have
- Confirmed the reverse: a genuine default 5-round battle still
  correctly completes at round 5 - full backward compatibility verified,
  not just assumed
- Confirmed the Postgres migration itself works both against a fresh
  database and one with existing battle data already in it

STILL TO BUILD (same backlog thread, not started yet):
- Round transition sync - require BOTH sides ready before advancing
  (currently either side alone still advances both immediately)
- Live viewer count, including both participants
- Smacky decorative graphic in the waiting room
