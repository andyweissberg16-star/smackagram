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

---
*Last updated: 2026-07-26*
