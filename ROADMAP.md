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

## Smack Battle: moved age gate directly under intensity dropdown (same session)
Per direct request - the rounds selector added last session had gotten
inserted between the intensity dropdown and the age confirmation
checkbox, pushing them apart. Reordered so the age gate sits
immediately under intensity (where it logically belongs, since it's
tied to intensity, not round count), with the rounds selector now
below it instead.

Verified live: confirmed the age gate still correctly shows for
non-Clean intensities and hides for Clean, and confirmed via actual DOM
position checking that the order is now intensity -> age gate -> rounds.

## Smack Battle: centered the intensity badge on the waiting screen (same session)
Per direct request - the intensity badge was sitting off to the side.
Root cause: it used display:inline-block, which only centers the TEXT
inside the badge (via text-align:center on itself), not the badge
element's own position within its container. Fixed to display:table
with margin:0 auto, which centers the badge itself while still
shrinking to fit its content (preserving the pill shape).

Verified with actual bounding-box measurements, not visual assumption:
confirmed the gap between the badge and its container's left edge
exactly equals the gap on the right (208px each in the test), proving
genuine centering rather than just eyeballing a screenshot.

## Smack Battle: larger, mobile-friendly age confirmation checkbox (same session)
Per direct request - the checkbox had no explicit size at all
(width:auto), leaving it at the browser's tiny default (~13px), a
known mobile tap-target problem. Fixed in both places it appears
(create form and join form) to a proper 24x24px with accent-color
matching the brand red, flex-shrink:0 so it can't get squished in the
label's flex layout, and cursor:pointer.

Verified with real measurements on an actual mobile viewport (390px
wide, iPhone-sized), not assumed from the CSS alone - confirmed both
the create-side and join-side checkboxes genuinely render at 24x24px.

## Smack Battle: "Respond Now" gate + fixed mobile line-covering issue (same session)
Per direct request - the 60-second timer was starting the INSTANT the
opponent submitted their line, giving zero time to actually read what
was just said before being rushed into typing a response. On mobile
specifically, the response box + timer popping up immediately also
visually crowded out the opponent's line, making it hard to even see.

Root fix, not just a layout tweak: turn_started_at is no longer set
automatically when side A submits and it becomes side B's turn - it's
now explicitly left null. The frontend detects this and shows a
"Respond Now" button instead of the response box/timer, with the
opponent's line fully visible and completely unobstructed. Only when
the user clicks that button does the timer actually start (via a new
POST /api/battles/<code>/start-turn endpoint) - at that point they've
already read the line, so the box/timer appearing is no longer a
problem, and it also directly fixes the "can't see it" mobile issue
raised, since nothing covers the line until the user chooses to move
on.

Side A's turn at the very start of a fresh round is intentionally
UNCHANGED - it still starts immediately (no gate), since there's
nothing from this round to read yet at that point. Only the
"just-received-a-response-within-the-same-round" transition needed
gating. Confirmed both remaining immediate-start locations (join_battle
and ready_for_next_round) were untouched by this change.

VERIFIED with a real, full live-server test, not just reading the
code:
- Confirmed submitting side A's line leaves turn_started_at genuinely
  null in the actual API response
- Confirmed side B's real rendered page shows the Respond Now button,
  NOT the text input or timer, with the opponent's line fully visible
  and readable in the history above it
- Simulated actual reading time (waited several real seconds) before
  clicking Respond Now, then confirmed the timer displayed exactly 60
  right after clicking - proving the clock genuinely starts fresh at
  the moment of the click, not counting down from whenever the
  opponent originally submitted
- Confirmed turn_started_at is now set server-side after the click
- Confirmed the join-time and new-round-start immediate-timer behaviors
  were both left completely untouched by this change

## Smack Battle: round transitions now require BOTH sides ready (same session)
Per direct request - the "Start next round" button was previously
advancing BOTH players the instant either one clicked it, dragging the
other person into the next round before they'd necessarily even
finished reading their own critique. This was also the exact "round
transition sync" item flagged as still-to-build from earlier in this
same session.

Fixed at the source: /api/battles/<code>/ready no longer immediately
advances the round on any single click. It now just records that side's
own readiness (ready_a or ready_b), and the round only actually
advances once BOTH are true. Whoever clicks first sees their button
replaced with "Waiting for [opponent] to be ready too..." instead of
silently assuming the round moved on.

No changes needed to the polling/rebuild mechanism itself -
ready_a/ready_b were already part of the existing render signature from
earlier work, so both sides' pages already correctly detect and react
to this change via normal polling.

VERIFIED with a real, full live-server test, not just reading the
code:
- Confirmed side A clicking ready alone leaves round_number and
  awaiting_next_round completely unchanged (round genuinely does NOT
  advance) - this is the exact bug fixed, confirmed via the real API
  response, not assumed
- Confirmed side A's actual rendered page correctly shows "Waiting for
  B to be ready too..." with the button gone, while side B's page
  still shows their own ready button since they haven't clicked yet
- Confirmed that once side B also clicks ready, the round genuinely
  advances - both ready flags reset, round_number increments, and
  current_turn resets to 'a' for the new round

## Smack Battle: fixed music button overlapping the nav bar (same session)
Per direct request - the button used position:fixed with top:16px,
which is well within the site nav's actual height, overlapping the
Login/Register links. Measured the real nav height on this page
(85px) rather than guessing, and moved the button to top:101px (85px
nav + the same 16px visual gap it originally had from the viewport
edge, just shifted to start below the nav instead of overlapping it).

Verified with real bounding-box measurements on both desktop and
mobile viewports (nav height is identical at both sizes on this page):
confirmed the button's top edge now sits at or below the nav's bottom
edge in both cases, with zero overlap.

## Smack Battle: music now reliably starts on entering the waiting room (same session)
Per direct request from live testing - the waiting-room music was
relying on the hype popup's ("Are you ready?"/"Prove It") click event
bubbling up to a separate, page-wide click listener to actually start
playing, rather than being started directly at the moment of that
click. Made this explicit and direct: the hype button's own click
handler now calls updateBackgroundMusic() itself, guaranteed to fire
at that exact moment rather than depending on event propagation.

VERIFIED with a real browser test, not just reasoning about event
bubbling: confirmed the music is genuinely paused before the hype
button is clicked (correctly blocked by the browser's autoplay policy,
since no gesture has happened yet), then confirmed it's genuinely
playing afterward - not just a flag, but actual currentTime advancing
in real time. Also confirmed the mute button's icon correctly shows
unmuted at that point, and that clicking it genuinely silences the
now-playing track (muted:true, still playing underneath) rather than
stopping playback outright.

## Smack Battle: fixed the 60-second timer silently starting during the intro countdown (same session)
Per direct request from live testing - the timer was starting the
moment the battle went active (when side B joins), but the frontend
then plays a ~5.9-second team-names + 3-2-1 countdown intro before
side A's actual input box appears for round 1. That entire animation
was silently burning into side A's 60 seconds before they could even
see or use the response box.

Fix: join_battle() no longer sets turn_started_at when the battle goes
active - left null instead. playIntro()'s own final setTimeout (the
exact moment the overlay clears and bell rings) now automatically
calls the existing /start-turn endpoint for side A specifically. Side
B's own page runs the same intro but has nothing to start, since it
isn't their turn. If this automatic call ever somehow failed, the
existing "Respond Now" gate (shown whenever turn_started_at is null)
is still there as a manual fallback rather than leaving side A stuck.

Rounds 2+ were confirmed unaffected and don't need this - playIntro()
is explicitly gated to only ever play for round_number === 1, so
ready_for_next_round()'s existing immediate-start behavior for later
rounds was already correct (no animation delay exists there).

VERIFIED with a real live-server test spanning the actual full
timing, not a shortcut: confirmed turn_started_at is genuinely null
immediately after side B joins, confirmed the intro overlay is visible
early and the input box is NOT, then waited the actual ~6.5 real
seconds for the intro to genuinely finish, and confirmed both that the
input box appeared with a fresh ~59-60 second timer (not something
already ticked down to ~54) AND that turn_started_at was now set
server-side. Also confirmed side B's own experience during this same
window was correct and unaffected.

## Smack Battle: round 1's turn timer no longer burns time during the intro animation (same session)
Per direct request from live testing - the 60-second clock was
starting the moment the battle went active server-side (when side B
joins), but the frontend then plays a ~5.9 second team-names + 3-2-1
countdown intro before side A's actual input box appears. That entire
animation was silently eating into side A's response window before
they could even see the text field.

Fixed the same way as the earlier mid-battle "Respond Now" gate:
join_battle() no longer sets turn_started_at at all (left null). The
frontend's existing turn_started_at===null gating already covers this
correctly - but rather than showing a manual button here (there's
nothing to read yet at the very start of a battle, unlike mid-battle),
playIntro() now automatically calls the existing /start-turn endpoint
itself the instant its own countdown finishes, only from side A's
browser. If that automatic call somehow failed, the existing "Respond
Now" button would still be there as a manual fallback rather than
leaving side A stuck.

VERIFIED with a real, full live-server test: confirmed turn_started_at
is genuinely null immediately after joining, confirmed the intro
overlay is genuinely visible right after loading and genuinely cleared
after waiting through its full real duration, confirmed the text input
appears at that point, and confirmed the timer displayed 59 (not
appreciably less) - the clock is now starting right as the intro ends,
not counting down from several seconds earlier.

## Smack Battle: music mute button repositioned on mobile only (same session)
Per direct request from live testing - the fixed-position mute button
(top:101px, right:16px) was overlapping the team name text in the
matchup header on narrow mobile screens. Confirmed the actual overlap
with real measurements before fixing (button sat inside the header's
own bounding box).

Fixed with a mobile-only media query, matching the site's own existing
nav-drawer breakpoint (max-width:1180px) rather than inventing a new
one - below that width, the site already hides both the desktop
nav-links and auth-links, leaving the entire center of the nav bar
empty. Moved the button there on mobile: centered horizontally, sitting
at the very top inside the nav itself. Desktop is completely
unaffected - this only applies below the same breakpoint the site
already uses for its own mobile nav.

VERIFIED with real bounding-box measurements, not visual assumption:
confirmed the button now sits exactly horizontally centered in a real
390px mobile viewport, with zero vertical overlap with the team-name
header, and specifically confirmed it doesn't collide with either the
logo (top-left) or the hamburger menu toggle (top-right) on that same
mobile view. Also confirmed desktop's position (top:101, right side)
is completely unchanged.

## Smack Battle: fixed clipped between-round lines + LED row not scaling to 10 rounds (same session)
Two related visibility bugs found during live testing.

### LED row hardcoded to 5
buildLedRow() looped `round <= 5` regardless of the battle's actual
max_rounds, so a 10-round battle only ever showed 5 win/loss/tie
circles - another spot missed when the configurable-rounds feature was
built. Fixed to loop against battle.max_rounds instead. Verified live:
a real 10-round battle now genuinely renders 10 LED elements.

### Lines getting clipped during the between-rounds critique screen
Root cause, confirmed with real DOM measurements: #lineHistory uses
flex:1 + overflow-y:auto inside a viewport-height-constrained flex
column layout. Whenever the round's two lines together were taller
than the space left over after the critique card (#actionArea, which
doesn't shrink) took its share, the second line got silently clipped
by the internal scroll area - not visible without scrolling a small,
easy-to-miss internal box, exactly matching the report of not being
able to read what was said.

Fixed using the same pattern the codebase already applies to the
battle-complete scorecard screen: added a new awaiting-round body/html
class, toggled whenever the between-rounds critique is showing, that
switches the whole page to natural height:auto scrolling instead of
being squeezed into the fixed viewport-height flex box. Both lines and
the critique card are now always fully reachable by scrolling the
actual page, not a hidden inner scrollbox.

VERIFIED with real, precise DOM measurements before and after, not
assumption: confirmed before the fix that the second line's bottom
edge (675px) extended well past the visible clipped area's bottom
edge (644px) - a genuine ~31px cutoff. After the fix, confirmed the
page's actual scroll height now correctly grows past the viewport
height, and confirmed the previously-clipped line becomes fully
visible after a normal page scroll.

## Smack Battle: mute scope confirmed correct + rematch UI finished + carryover bug fixed (same session)
Two items from the same request.

### Mute button scope (verified, no code change needed)
Per direct request - confirmed empirically, not just by reading the
code, that the existing mute toggle already does exactly what was
asked: it silences background music (waiting-room track) and crowd
noise, while the round-start bell and the "message sent" sound stay
completely unaffected and always audible regardless of mute state.
playAudioElement() (which plays both of those) already force-unmutes
every time it actually plays something, independent of the music mute
toggle. Tested all four cases directly against a live page rather than
assuming from the source.

### Rematch: 2-button final scorecard + a real bug fix
Discovered while investigating that a full rematch backend/frontend
flow already existed (both-sides-must-agree gate, auto-redirect via
polling, brand new Battle created with the same teams). Extended it
per direct request:
- Renamed the single existing button from "Start New Smack Battle" to
  "Rematch"
- Added a distinct "Accept Rematch" label specifically for whichever
  side sees their opponent already requested it - previously both
  sides saw identical generic button text with no indication a request
  was already waiting on them
- Added the second button: "Start a New Battle", linking to the
  create-a-battle page, for starting a fresh matchup instead of
  rematching the same opponent

Found and fixed a real bug along the way: the new rematch Battle never
carried over the original's intensity or round count, silently
resetting every rematch to Savage/5-rounds regardless of what the
original battle actually used.

VERIFIED with a real, full live-server test end to end: created an
original battle at a deliberately non-default Mild/10-round
combination, fast-forwarded it through a properly simulated 10-round
completion (real round results, not just flipping the status flag),
confirmed both buttons render correctly on the scorecard, confirmed
side A requesting shows the correct waiting text AND correctly flips
side B's own button to "Accept Rematch", confirmed side B accepting
creates a real new battle and redirects both browsers there (side A's
via the existing polling-based redirect, side B's directly), confirmed
the new battle genuinely shows the 1-2-3 intro countdown again, and
confirmed the new battle's intensity (2/Mild) and max_rounds (10)
correctly match the original instead of reverting to defaults.

## Twilio work package: ID collision diagnostic endpoint (David's handoff, item #1)
David's Twilio handoff flagged a potential production bug: Order and
Smackagram are separate tables with separate autoincrementing primary
keys, but every Twilio webhook URL carries only the bare integer id,
resolved by guessing (Order.query.get(id) or Smackagram.query.get(id)),
with Order always winning. Any Smackagram whose id also exists in
Orders would silently get served the wrong record's audio - no error
logged, call completes normally with wrong content.

Needed to verify against the live production database before building
any fix. Hit real friction trying to do this via psql from a separate
Windows PC (no psql installed, Render's free tier blocks the web
shell) - rather than fighting further with local tool installation,
built a small, safely-gated diagnostic endpoint directly into the app
itself, matching the exact pattern already established for
check-team-codes (protected by the same CRON_SECRET query-string key,
not linked from the UI, visit-to-run).

New route: GET /api/admin/check-id-collisions?key=...
Runs 3 read-only queries (MIN/MAX/COUNT on both tables, plus a JOIN to
find actual overlapping ids) directly through the app's own live DB
connection - no separate database client needed at all, just a
browser.

VERIFIED against a real Postgres database with a deliberately inserted
collision (id=42 present in both tables) before considering this ready
to deploy: confirmed the endpoint correctly reports collision_count=1,
correctly identifies the specific colliding id, and correctly flags
the verdict as broken. Also confirmed the auth gate correctly rejects
both a missing key and a wrong key with 401.

NEXT STEP: deploy this, then visit the URL against the real production
database to get the actual answer for David's item #1.

## Twilio work package: ID collision bug FIXED (David's handoff, item #1)
Verified via the diagnostic endpoint that current production has 0
collisions - but only because smackagrams currently has ZERO rows.
Since both tables use independent auto-increment counters starting at
1, the very first Locked & Loaded smack ever created would get id=1,
which already collides with an existing Order. This was not a distant
future risk - it was effectively guaranteed on the next Locked &
Loaded smack, whenever that happened to be sent. Built the real fix
rather than just monitoring.

Namespaced every Twilio webhook URL by record type instead of a bare
integer, per David's recommended approach:
- place_prank_call() now takes record_type ("order" or "smackagram")
  as an explicit parameter and builds namespaced URLs:
  /call-instructions/{type}/{id}, /call-status/{type}/{id}
- All 3 call sites updated (2 in app.py for Order, 1 in scheduler.py
  for Smackagram)
- New namespaced routes for all 4 webhook endpoints
  (call-instructions, call-status, recording-ready, recording-done),
  backed by a shared _resolve_record(record_type, record_id) helper
- The OLD bare-int routes are kept alive as explicit fallbacks
  (call_instructions_legacy, call_status_legacy, etc.) specifically
  for calls already in flight when this deploy lands - those calls
  have the old-style URL already baked into Twilio's call
  configuration and can't be redirected. Safe to remove later once
  enough time has passed that no in-flight call could still exist.
- _pending_call_audio now keyed by (record_type, record_id) tuples
  instead of a bare id, fixing the same collision in the in-memory
  cache itself

NOTE for item #2 (dead air): found while working on this that
scheduler.py's call site (the Locked & Loaded path) never used
_pending_call_audio at all - it has no import path to app.py's dict.
Every Locked & Loaded call was therefore already hitting the "generate
audio live inside the webhook while the customer holds the phone"
delay this whole caching mechanism exists to avoid. Flagging this
specifically for the item #2 diagnosis, not fixed as part of this
change.

VERIFIED with a real, direct test simulating the exact broken
scenario: inserted an Order and a Smackagram both at id=42 with
different recipient info and different scenario audio. Confirmed:
- /call-status/order/42 updates ONLY the Order, Smackagram untouched
- /call-status/smackagram/42 updates ONLY the Smackagram, Order
  untouched (both directions tested, not just one)
- /recording-ready/order/42 and /recording-ready/smackagram/42 each
  correctly stored their own recording URL with zero cross-contamination
- /call-instructions/order/42 correctly played the Order's own audio;
  /call-instructions/smackagram/42 correctly played the Smackagram's
  own, different audio - including confirming the generated <Record>
  action/callback URLs inside that TwiML were themselves correctly
  namespaced
- The legacy bare-int fallback routes (/call-status/42,
  /call-instructions/42) still work exactly as before, correctly
  favoring Order per the old guess logic - confirming backward
  compatibility for any calls already in flight at deploy time

## Twilio work package: dead-air-on-answer fix for Locked & Loaded calls (David's handoff, item #2)
Diagnosed by first checking the actual Render start command
(gunicorn app:app --timeout 180 - no --workers flag, so gunicorn
defaults to 1 worker). This RULES OUT David's "Candidate 1" (different
worker process handling the webhook than the one that placed the
call) as the cause for the main "Send a Smack" immediate flow - with a
single process, that in-memory cache was already reliably shared.

But it surfaced something more significant, found earlier while
working on item #1: scheduler.py (the Locked & Loaded call path) had
NO import path at all to app.py's cache dict - not a cross-process
timing issue, but a "never even attempts to cache" gap. This meant
EVERY Locked & Loaded call was unconditionally generating its audio
live inside the /call-instructions webhook while the customer was
already holding the phone - constant, not intermittent, for that call
type specifically.

Fixed by moving the pending-audio cache out of app.py and into
services/call_audio_service.py (a module both app.py and scheduler.py
already import), then updating scheduler.py's actual call-placement
code to populate it before placing the call - the same
resolve-then-cache-then-call pattern the immediate Order flow already
used. Also added David's suggested cache-miss instrumentation logging
to /call-instructions, so a genuine cache miss (e.g. from a rare
deploy/restart racing an in-flight call) is now directly visible in
Render's logs going forward, for both call types.

VERIFIED thoroughly, not just reasoned about:
- Confirmed at the Python object level that app.py, scheduler.py, and
  call_audio_service.py are all now genuinely sharing the exact same
  dict object (identical id()), not separate copies
- Ran a real live-server test proving an actual cache MISS correctly
  fires the new instrumentation log line
- Ran a real live-server test proving a cache HIT works correctly
  within the same process: populated the cache with a deliberately
  fake, unmistakable value, then confirmed /call-instructions served
  THAT exact fake value (not a fresh database-resolved one) - direct,
  unambiguous proof the shared cache is actually being read, not just
  present
- Re-confirmed the pre-existing Order ("Send a Smack") cache-hit
  behavior still works correctly after moving the dict - no regression

## Twilio work package: call flow changes (David's handoff, item #3)
All sub-items marked "code ready" in the handoff, built and directly
verified. Skipped 3e (machine_detection_speech_end_threshold tuning)
per David's own explicit guidance to leave it at default until dead
air is fixed and real remaining latency can be observed - that
hasn't happened yet (needs an actual production call + Twilio Console
timeline check).

3a - Fixed the "unknown" bug: the old check
(answered_by.startswith("machine")) let AnsweredBy="unknown" silently
pass through as a confirmed live human, since "unknown" doesn't start
with "machine". Inverted to fail-safe: only answered_by == "human"
counts as live. Anything else (unknown, fax, any machine_* value) is
treated as not-confirmed-human.

3b - Welded the recording disclosure to the recording decision itself
in build_twiml() - the <Say> disclosure now only plays when record is
True, one boolean controlling both, so an AMD misfire can never
produce an undisclosed recording (Florida two-party consent).
Voicemail/unknown: no disclosure, message only, no recording. Live
human: disclosure, message, recording.

3c - Extended call length from 0:59 to 1:59 (time_limit=119 in
place_prank_call, max_length=115 on <Record> in build_twiml - stays
under the hard cap so Twilio's own connection-level cutoff remains
what actually ends the call, not an independent Record timer).

3d - Reverted machine_detection_timeout from 15 back to Twilio's
default of 30. Corrected the previous code comment's misdiagnosis:
this timeout is a CEILING on AMD analysis, not a wait - a live "Hello?"
resolves in ~2-3s regardless of this value, so it never approached 15s
anyway. The ceiling only engages on genuinely ambiguous/long voicemail
greetings; setting it too low meant AMD would give up and return
AnsweredBy="unknown" mid-greeting, causing the smack to play over the
tail of the greeting instead of landing after it. The actual
live-answer lag this comment blamed on the timeout was the dead-air
caching bug (item #2), a separate and already-fixed issue.

3f - Added answered_by column to both Order and Smackagram (migrated).
Previously print()ed and discarded; now persisted on every call. Gives
a real, queryable answer to "did my smack land?" instead of just
call_status="completed" regardless of whether it was a live reaction
or a voicemail. Also the only way to later check whether
machine_detection_timeout is calibrated correctly (a high share of
"unknown" would mean the ceiling needs raising further).

VERIFIED thoroughly with direct tests, not just code review:
- Mocked the actual Twilio client and captured the real parameters
  passed to calls.create() - confirmed time_limit=119 and
  machine_detection_timeout=30 are genuinely what gets sent, not just
  what's written in the source
- Tested build_twiml() directly for both record=True and record=False:
  confirmed the disclosure and <Record> verb appear together or not at
  all, never independently, and confirmed max_length=115 is correctly
  set when recording
- Ran a real live-server test against an actual database record for
  all three answer scenarios: AnsweredBy=human (disclosure + recording,
  as before), AnsweredBy=unknown (the actual bug being fixed - now
  correctly produces NO disclosure and NO recording, unlike the old
  behavior which would have wrongly included both), and
  AnsweredBy=machine_end_beep (real voicemail, confirmed still
  correctly skips both) - and confirmed answered_by was correctly
  persisted to the database in all three cases

## Smack Battle: live viewer count + Smacky waiting-room graphic (same session)
Completes the 3-item backlog thread. Round transition sync (both sides
must be ready) turned out to already be fully built and working from
earlier in this session - verified it live rather than assuming, then
built the two genuinely-new items.

### Live viewer count
New BattleViewer table (one row per distinct browser, upserted on a
periodic heartbeat rather than inserted fresh each time). Every
visitor's page pings a new /viewer-ping endpoint every 8 seconds,
participant and spectator alike - no special-casing needed to include
participants in the count, since they ping the exact same way anyone
else does. Battle state now includes viewer_count (distinct viewer_ids
seen in the last 20 seconds), displayed in the header on both the
waiting screen and the active/complete battle screen.

VERIFIED with real multi-browser tests, not just reading the code:
confirmed a single viewer shows count=1, confirmed opening a genuinely
second, separate browser correctly bumps it to 2 (and both browsers'
own pages agree on that same number), confirmed repeated pings from
the same already-counted browsers across multiple full ping cycles
does NOT inflate the count, and confirmed stale viewers (browser
closed) correctly age back out of the count rather than accumulating
forever.

### Smacky graphic in the waiting room
Added the site's existing Smacky portrait (same file already used on
the Meet Smacky page) to both waiting-screen views - the creator
waiting for an opponent, and the joining side before they accept.
Purely decorative, as requested. Confirmed via a real browser check
that the image genuinely loads (not broken/404) with correct
dimensions.

## Smack Battle: "opponent left" notification + round-review music mute fix (same session)
Two additional items per direct request.

### Critique-reveal music now respects mute
The looping "rock music" track during between-round critique review
(critiqueRevealAudio) was always forced unmuted every time it played,
via the shared playAudioElement() helper that also handles one-shot
SFX like the bell and new-line sound (which correctly should always
stay on regardless of mute, per earlier direction). Gave this one
track specifically its own behavior: it now checks musicMuted just
like the waiting-room/crowd-loop background tracks do, while every
other sound routed through playAudioElement() is unchanged. Also
updated the mute button's click handler to immediately mute/unmute
this track if it's already playing when toggled, not just on its next
start.

VERIFIED with real live-server tests: confirmed the track plays
audibly (muted:false) when the mute button is off, confirmed it plays
silently (muted:true, still actually running underneath) when mute is
on, and reconfirmed the bell sound is completely unaffected either way.

### "Opponent left the battle" notification
New per-side presence tracking: Battle.last_seen_a/last_seen_b, updated
by the same viewer-ping heartbeat the live viewer count already uses,
now also tagged with which side (if any) the pinging browser
represents. If one side's presence goes stale for more than 30 seconds
while the battle is still active, the OTHER side's screen shows "[Name]
left the battle" with a "Start New Smack Battle" button back to the
create page - this overrides whatever else would normally be showing
(mid-turn, awaiting round, anything), since the battle is effectively
over the moment one side is actually gone. Deliberately only triggers
on a stale timestamp, never a null one, since null just means "hasn't
had a chance to ping yet" (e.g. right after joining), not "has left."

VERIFIED with a real, full bidirectional live-server test: created an
actual battle with both sides genuinely present and pinging, then
actually closed one side's browser tab, aged their last-seen timestamp
to simulate real elapsed time, and confirmed the OTHER side's page
correctly showed the exact right opponent name and the correct button
- then repeated the test in the reverse direction (the other side
leaving instead) to confirm both directions work, not just one.

## Smack Battle: mobile waiting-room scroll fix + new wider waiting image (same session)
Per direct request from live mobile testing - adding the Smacky image
last session pushed the waiting/join screen's total content (image +
text + team/name fields + age gate + button) past the .wrap
container's fixed height:calc(100dvh - var(--nav-h)) on mobile, with
no way to scroll down and reach anything below the "Your team" field.
This is the exact same class of bug already fixed twice before for
battle-complete and awaiting-round; applied the identical fix here:
body.waiting-room/html.waiting-room now gets overflow:auto and
height:auto, letting the whole page scroll naturally instead of being
clipped. Also found and fixed a related inconsistency: the
'waiting-room' class was only ever toggled on <body>, not <html> like
the other two states - added the missing html toggle so the CSS
selector (which targets both) actually works.

Also swapped the waiting-room image to point at a new filename,
battle-waiting-smacky.png/.webp, since the user has a new, wider
replacement image to drop in (following the same "rename and drop into
static/img/" pattern already used for smacky-hero.png). Widened the
image's CSS sizing (max-width 180px->340px, width 60%->90%) to suit a
wider aspect ratio instead of the roughly-square sizing that fit the
original portrait.

VERIFIED the scroll fix with a real mobile-viewport test, not just
reading the CSS: created an actual battle with Savage intensity
(maximizing content height via the age-gate checkbox too), loaded the
joining side's view at a real 390x700 mobile size, confirmed the
page's actual content height (797px) genuinely exceeds the viewport
(700px) - proving this scenario really does overflow - confirmed
overflow is now "auto" not clipped, and confirmed that after actually
scrolling to the bottom, the join button is genuinely reachable within
the viewport, not just present in the DOM.

NEXT STEP: user needs to rename their new wider image to
battle-waiting-smacky.png (and ideally also produce/rename a
battle-waiting-smacky.webp) and drop both into static/img/ before
deploying, or the waiting screen will show a broken image icon until
then.

## Smack Battle: flashing red border around the waiting-room photo card (same session)
Per direct request - added a pulsing red border animation to the
card containing the waiting-room Smacky/photo image, on both the
creator's waiting view and the joining side's accept-challenge view.
Scoped to a new waiting-photo-card class rather than the base .card
style, so this doesn't affect any other card on the page.

VERIFIED with a real live-server test, not just checking the CSS
exists: confirmed the animation is genuinely applied (animationName
computed as "flashRedBorder"), and confirmed the border's actual
rendered color genuinely differs between two samples taken 600ms
apart, proving it's really cycling in the browser rather than sitting
static.

## Smack Battle: fixed broken waiting-room image + chat background not rendering (same session)
Two bugs found during live testing, both mine.

### Broken image icon in the waiting room
I'd wrapped the waiting-room image in a <picture> element with a
<source type="image/webp"> pointing at battle-waiting-smacky.webp,
while telling the user the .webp was optional. It isn't: a modern
browser sees the webp <source>, treats it as authoritative, tries to
load it, gets a 404, and shows a broken-image icon rather than falling
back to the <img> PNG. Confirmed directly - the .png returned HTTP 200
(1.6MB, present) while the .webp returned 404. Removed the <picture>
wrapper and webp <source> entirely from both waiting views; now just a
plain <img> pointing at the PNG, so the .webp really is optional as
described.

### Chat input background not showing
The .chat-input-card rule was originally declared BEFORE .card in the
stylesheet. .card sets the shorthand `background:` property, which
resets background-image - so at equal specificity, the later .card
rule silently wiped the background image out. Moved .chat-input-card
to after .card so the override actually applies.

VERIFIED with a real live test using the user's actual uploaded images
(both present locally at full size): confirmed the waiting-room image
genuinely loads (naturalWidth 1752 x 897, matching the real wide
image, complete=true) and confirmed zero image-related 404s in the
page's network activity.

## Smack Battle: broken waiting image, "calling YOU out" copy, league-filtered team search (same session)
Three fixes from live testing.

### Broken waiting-room image (my bug)
The waiting-room image rendered as a broken-image box. Root cause: the
<picture> element listed a .webp <source> FIRST, but only the .png was
ever actually created - and a <source> that 404s doesn't fall back to
the <img>, it just fails. Confirmed by direct HTTP checks: the .png
returned 200 (1.6MB, real file) while the .webp returned 404. Fixed by
dropping the <picture>/<source> wrapper entirely and using a plain
<img> pointing at the .png that genuinely exists. Verified with a real
browser test checking naturalWidth > 0 (a broken image reports
naturalWidth 0 even when "complete"), plus zero failed /static/
requests.

### Chat-input background wasn't applying (my bug)
The .chat-input-card rule was declared BEFORE .card in the stylesheet.
Since .card uses the shorthand `background:` property (which resets
background-image) and both rules have equal specificity, the later
.card rule silently won and wiped the background image out entirely.
Moved .chat-input-card to immediately after .card and left a comment
explaining why the order matters. Verified via computed style that both
the gradient overlay AND the image URL are now present, and the image
loads (HTTP 200).

### "is calling YOU out" copy
Per direct request, changed the joiner's prompt from "...is calling out
[LEAGUE] fans. Step up?" to "...is calling YOU out. Step up?" - the
league callout made sense for a broad open challenge, but reads oddly
to someone who was personally sent the link.

### Team search now filtered by league
Per direct request: searching for a team on the join screen was
returning every team across all leagues, when it should only offer
teams from the battle's own league. Added optional league filtering to
the shared site-wide autocomplete via a data-team-league attribute
(comma-separated league keys, read at search time so it can change
dynamically). Absent/empty = no restriction, so every other page using
this autocomplete is completely unaffected.

Applied it to BOTH the join screen (restricted to the battle's stored
league) and the create form (restricted to whatever league is currently
picked, updating live when the dropdown changes, and clearing any
already-picked team since it may not belong to the new league). Needed
a mapping layer because Smack Battle's dropdown value "soccer" spans
five separate league keys in the actual team data (mls, epl, laliga,
bundesliga, seriea); the rest are 1:1.

VERIFIED with a deliberately tricky real test: searched "giants",
which genuinely exists in BOTH the NFL (New York) and MLB (San
Francisco). Confirmed an NFL battle returns only the NFL Giants, then
switched the create form to MLB and confirmed it returns only the MLB
Giants - proving the filter is real and not coincidental. Also
confirmed the join side's attribute is correctly populated from the
battle's league, and that changing league on the create form clears
the previously-typed team.

## Smack Battle: removed the redundant round box squeezing the chat (same session)
Per direct request from live mobile testing - each round rendered TWO
stacked boxes: a top one containing just "Round 3" plus a "You're up.
Let's see what you've got." prompt, and below it the actual action card
("Your turn - round 3" + timer + input + send). Both pieces of the top
box were already shown elsewhere: the round number in the page header
("Round 3 of 5") and the turn prompt in the action card immediately
below. So it was a full-height box duplicating information while
stealing vertical space from the actual chat, which on mobile left the
responses barely visible.

Fixed so the history area renders nothing at all until someone has
actually said something in the round (instead of a box holding only
redundant text), and dropped the now-duplicate "Round N" label from
the lines card so the lines themselves get the full space.

VERIFIED on a real 390x844 mobile viewport: confirmed the history area
goes from 1 box down to 0 while it's your turn with nothing said yet
(leaving a single box on screen), confirmed the lines card correctly
DOES appear once a real line is submitted and shows the actual message
text, and confirmed the duplicate "Round N" label is gone.

Note: hit and fixed a test-harness bug while verifying this - one of my
test server scripts was missing the content-moderation mock, so the
safety check was failing closed against a dummy API key and silently
rejecting every submitted line. That was my test setup, not product
code, but it briefly looked like a real bug.

## Smack Battle: moved chat background to the shared roast history + lightened overlay (same session)
Two corrections from live testing.

1) The background image was on the wrong box. It had been applied to
each player's own individual typing card (.chat-input-card). What was
actually wanted is the box holding BOTH players' roasts for the round -
the shared conversation history that accumulates during the battle.
Moved the background to that card (renamed the rule to
.chat-history-card) and removed it from the typing box entirely.

2) Lightened the dark overlay from rgba(...,0.82) to 0.55. At 82%
opaque black over a detailed image, the image was very likely present
but almost entirely hidden - which would present exactly as "not
showing at all." 55% keeps the roast text clearly readable while
letting the image actually come through.

Also removed a stale duplicate CSS comment left over from the rename,
and preserved the critical ordering requirement (the rule must stay
declared after .card, since .card's shorthand `background:` property
resets background-image and would otherwise silently override it).

Note for future debugging: my sandbox's copies of the user's uploaded
images (static/img/battle-chat-bg.png, battle-waiting-smacky.png) were
cleaned up mid-session, so local browser tests of these specific images
will 404 and can't verify them - that's a sandbox artifact, not a
production issue. Both files are confirmed present in the repo on
GitHub. Verified what IS verifiable locally: the CSS computes correctly
(confirmed the actual computed backgroundImage property resolves to the
gradient + correct image URL with background-size:cover).

## Smack Battle: roast-history box reworked - fixed size, full transcript, auto-scroll
Four issues from live testing, all in the history box.

1) BOX RESIZED ITSELF as roasts came in - tiny after the first line,
   bigger after the second, revealing only a fraction of the background
   image. Now a fixed 400px on desktop (300px under 620px wide), so it
   holds a stable size from the first line and scrolls internally.

2) EVERY ROUND WIPED THE PREVIOUS ROUND'S CHAT. History was filtered to
   the current round only. Now renders every line from every round as a
   running transcript, with a "Round N" divider whenever the round
   changes. Timed-out turns (real lines with deliberately empty
   messages) render as an italic "Ran out of time" note, not a blank.

3) NO AUTO-SCROLL. Now jumps to the newest roast at the bottom when new
   content lands. Tied to the content-changed check, so it re-anchors
   only on genuinely new lines and never yanks the view from someone
   who scrolled up to re-read earlier rounds.

4) OVERLAY NOT SHADED ENOUGH - raised 0.55 to 0.7. (0.82 hid the image
   entirely, 0.55 read as unshaded; 0.7 is the middle ground.)

Supporting layout change: .wrap moved from fixed height:calc(100dvh -
nav) to min-height, and #lineHistory from flex:1/overflow-y:auto to
flex:none. The card owns its own height and scrolling now; the old
flex+overflow on the wrapper caused a nested double-scroll and stopped
the card holding a stable size.

Also caught my own error mid-build: I first wrote
background-attachment:local, which scrolls the image away WITH the
content - opposite of the intent. Corrected to scroll, pinning it.

VERIFIED by playing two full rounds through a live server: card
computes to exactly 400px with overflow-y:auto and
background-attachment:scroll; all four messages from BOTH rounds
present simultaneously (old code would show only round 2's two); both
"Round 1" and "Round 2" dividers render; box genuinely scrolled to
bottom on load (scrollTop 31 + clientHeight 398 = scrollHeight 429).

## Smack Battle: fixed locked/unscrollable page during an active battle
Regression from the fixed-size history box. The base rule
`html, body{height:100%; overflow:hidden}` locked page scrolling, and
only three state classes overrode it (battle-complete, awaiting-round,
waiting-room). The ACTIVE battle state had no override - it never needed
one before, because .wrap was a fixed viewport height and the history
scrolled internally, so nothing exceeded the viewport. With the history
box now a fixed 400px, content legitimately overflows on desktop and
mobile, and overflow:hidden clipped it with no way to scroll down to
the typing area.

Fixed by making vertical scrolling the global default
(min-height:100%; overflow-y:auto) rather than locking it and patching
per-state. Horizontal scroll stays locked exactly as before.

VERIFIED on both viewports in the actual typing state of a real live
battle: desktop (1280x900) content height 1022 > 900 viewport, mobile
(390x700) content 980 > 700 - both genuinely overflow - and in both
cases body computes overflow-y:auto, the page reports scrollable, and
the textarea was confirmed reachable within the viewport.

## Smack Battle: roast bubbles made nearly opaque for readability
The gold (side A) and red (side B) message bubbles were only 12% opaque
tints, so the detailed background image behind the history box cut
straight through them and made the roast text hard to read.

Rebuilt both as a near-opaque dark base (rgba(26,26,26,0.92)) with the
coloured tint layered on top via background-image (which paints above
background-color), rather than a single very transparent coloured wash.
Net ~93% opaque - still faintly see-through as the user explicitly
wanted, but the image no longer bleeds through the text. Also raised the
border tints 0.3 -> 0.45 so the gold/red identity stays clear now that
the fills are darker.

VERIFIED with a live battle: computed styles confirm both bubbles resolve
to background-color rgba(26,26,26,0.92) with their respective
linear-gradient colour tint on top, and borders at ~0.46 alpha.

## Smack Battle: 3-2-1 countdown before every round + reduced audio churn

### Round countdown (built and verified)
Added playRoundCountdown(), modelled on the battle intro: reuses the same
full-screen overlay, the same intro whoosh + tick sounds + closing bell,
and the same 900ms-per-tick 3-2-1 cadence, but announces "ROUND N"
instead of the team-vs-team reveal. Shorter lead-in (1200ms vs 3200ms)
since there are no team names to read. Total ~3.9s.

Fires off round_number ticking up, which BOTH players see from their own
poll, so neither can start typing before the other. Hooked in where a
bare ringBell() previously fired the instant the round advanced; the bell
now rings at the END of the countdown so it lands on the actual round
start rather than ~4s early. The shared overlay's "VS" element is hidden
during a round countdown and restored afterwards, since a rematch reuses
the same element for the full team-vs-team intro.

Backend: ready_for_next_round no longer sets turn_started_at (left null),
so the countdown can't burn seconds off side A's 60 - the exact bug
already fixed for round 1's intro. The countdown calls /start-turn on
completion, and the existing "Respond Now" gate stays as the fallback if
that call ever fails.

VERIFIED with a real two-player live battle: confirmed BOTH sides show
the overlay reading "ROUND 2" with the countdown running simultaneously,
confirmed the overlay clears afterwards, and confirmed the turn timer
then reads a full 60 (not reduced by the ~3.9s animation) with
turn_started_at set server-side.

### Choppy music - partial, unverified
Reduced redundant audio property writes: updateBackgroundMusic() runs on
every 1.5s poll and was blindly re-assigning .muted and .volume on
already-playing media elements each time, which is a known cause of
audible stutter (mobile Safari especially). Now only writes when the
value actually differs.

HONEST CAVEAT: this is a plausible contributor, not a confirmed
diagnosis. Audio smoothness cannot be verified in a headless sandbox
with no real audio output. Other candidates not ruled out: a hard seam
in the looping crowd-loop.mp3 itself, or the 1-per-second judging beep
reading as choppiness. If it persists after this, the next step is to
narrow down WHICH sound is choppy (crowd loop during play vs the
between-rounds track vs the judging beep).

## Smack Battle: final scorecard redesigned as a fight-night judge's card
The old scorecard was a generic centred stack: big "3 – 2" numeral, names
row, five round chips showing only "R1".."R5", two averages. Dull, and it
threw away the best data on the card - score_a/score_b per round already
existed in the API response and were never shown.

Redesigned around the real-world artifact the feature is imitating: an
official boxing judge's scorecard. Worked entirely within the site's
established identity (Anton display, JetBrains Mono for data, gold/red on
ink) rather than inventing a new palette.

- Document header: "Official scorecard" / "Bout <challenge_code>" as a
  mono eyebrow over a hairline rule. The bout code is a real detail the
  data already had.
- Bout line: each fighter's name + team flanking the rounds tally, so the
  matchup reads left-to-right like a card, instead of a giant lone number.
- SIGNATURE - the judge's grid: rounds across the top, one row per
  fighter, the actual per-round score in each cell, and the winner's cell
  marked (tinted + ruled + bold) the way a judge marks a card. This is now
  the hero of the card because the scores ARE the information. Columns
  capped at 50px so numerals sit in tight cells rather than stretching.
  Honours max_rounds, which also fixes a real bug: the old loop was
  hardcoded to 5, so a 10-round battle only ever showed five rounds.
- Verdict as a rubber stamp: off-axis (-3.5deg), double-ruled, wide
  letter-spacing, slamming in with a scale-down animation. One loud
  moment; everything around it stays quiet. prefers-reduced-motion
  respected.
- 10-round grids scroll horizontally rather than crushing columns
  unreadably on a phone.

VERIFIED by rendering a real completed battle and reviewing screenshots
at 1280x900 and 390x800: 21 grid cells (3 rows x 7 cols) for a 5-round
bout, all 5 winning cells marked, stamp confirmed rotated via computed
transform, and on mobile the 300px grid fits inside the 342px card with
no overflow. Confirmed zero orphaned references to the removed CSS
classes (final-round-chip / final-score-tally / final-players-row /
final-avg-row).

## Smack Battle: shareable portrait card (/battle/<code>/card)
User wanted a single-page scorecard sized for IG Stories, explicitly NOT
boxing/fighting themed - Smackagram/Smack Battle themed instead.

Built as its own route and template rather than resizing the in-page
scorecard: the playing view wants a wide card in a 620px column, a
shareable graphic wants tall and self-contained, and one layout doing
both compromises both. Rendered fully server-side so there's no empty
flash or half-built state to catch in a screenshot.

Design direction - a post-game result card you'd screenshot and post,
grounded in the product's own world (sports fandom + social sharing)
rather than boxing. SIGNATURE: the two fanbases' real brand colours cut
across the card at an angle and meet in the middle, so every battle's
colour identity comes from the actual matchup. Those colours were already
in the data (_lookup_team_color) and previously only used for small text
accents. Added _readable_on_dark() since several real team colours are
near-black and would vanish on this background - falls back to the brand
gold/red.

Contents: Smackagram wordmark + SMACK BATTLE kicker, team-vs-team, a meta
strip (rounds / intensity / final), big rounds-won score with both
handles, a round strip colour-coded by who took each round, the verdict,
per-team averages, and bout code + domain in the footer. Added a "Get
shareable card" link on the in-page scorecard.

CAUGHT MY OWN FALSE POSITIVE: an early measurement said content
overflowed the card by ~92px, so I shrank the score numerals and trimmed
spacing throughout. Re-measuring properly showed the real content was
710px inside a 762px box - it always fitted. The apparent overflow was
the decorative .clash gradients (deliberately positioned past the card
edges) inflating scrollHeight. The test server had also been serving a
cached template, so the "fix" was never even live. Reverted all of it and
kept the bold sizing.

VERIFIED by measurement (image viewing was not working this session, so
this is measured rather than eyeballed - user should eyeball it):
5-round phone 616px content in 652px box (36px headroom), 5-round desktop
710/762 (52px), and worst case 10-round battle with long handles 612/634
(22px). All exactly 9:16 (ratio 0.563), footer inside bounds, no page
errors.

## Smack Battle share card: deeper Smackagram theming (2nd pass)
First pass was a competent scoreboard but thin on brand. Two big misses
fixed:

1) SMACKY WAS ABSENT. He judges every round and is the brand character,
   yet the card read as a neutral scoreboard. Now presented as his
   ruling: his portrait (circular, gold-ringed) with "Judged by Smacky"
   sitting above the score. Uses the same smacky_image_exists check the
   Meet Smacky page uses, so a missing portrait degrades to text rather
   than a broken image.

2) THE AI RECAP WASN'T ON IT. recap_winner_text is the savage one-liner
   the app already generates and is by far the most shareable thing on
   the card - a scoreboard is information, the roast is what someone
   actually wants to post. Now the hero: attributed "Smacky to <winner>"
   (which makes its second-person voice read correctly), in the only
   italic treatment on the card, in a gold-tinted panel.

Copy moved into the product's own register throughout: "Rounds taken"
not "Rounds won", "Reppin'" not "Side A", and the footer is now the
taunt "Think you talk better? / smackagram.com" instead of a bout code.

FIT WORK - real overflow this time, not the earlier false positive:
adding the roast genuinely pushed content past the box (measured -106px
on a 10-round card with a long recap). Fixed properly rather than by
shrinking type:
- .inner was locked to height:100%, which meant content could never
  expand the card - it could only be clipped. Changed to min-height:100%
  with height:auto on the card, so 9:16 is the target and long content
  expands it slightly instead of being cut off. A card that's
  occasionally 9:18 still posts fine to a story; clipped content never
  does.
- overflow:hidden moved off the card onto the decorative .clash layer,
  which is the only thing that actually needs clipping.
- Roast clamped to 3 lines, team names to 2, and the round strip
  tightened when max_rounds > 5 (ten chips wrapped to two rows at the
  five-chip size).

VERIFIED by measurement across five cases - 5-round at phone/desktop/340px
narrow, and a worst-case 10-round battle with long team names, long
handles and a long recap at phone and desktop: nothing clipped in any
case, footer inside bounds in all five, no page errors.

STILL UNREVIEWED VISUALLY: image viewing was unavailable this session, so
none of this has been eyeballed - only measured. Needs a human look.

## Smackcast: subscriber library + sales page step-numbering fix
Surveyed Smackcast before touching it. It's already a real product:
$39.99 one-time season pass, Sleeper/ESPN connected (Yahoo stubbed),
NFL/NBA (MLB ESPN-only), weekly auto-generation on a cron, and each
recap produces script text, ElevenLabs audio in Smacky's voice, a meme
image, a "best line" and a share token. Delivery is web link (always),
phone call, SMS, plus Discord/GroupMe columns already in the schema.

FOUND A REAL PRODUCT HOLE: SmackcastRecap was only ever queried by
share_token (or by recap_id for the Twilio call). There was no way for a
paying subscriber to see their own recaps. The share link arrives once by
text or call and is easy to lose - so someone buys a full season and then
has no route back to week 3. Nothing in the app listed a user's recaps at
all.

Built /smackcast/library (login required):
- Groups by subscription, since one person can run Smackcast on several
  leagues at once and weeks would otherwise interleave
- Newest week first, with each recap showing its best line as the lead
  (that's the part someone actually remembers from a given week), then
  audio, meme, share/copy-link buttons and a collapsed transcript
- Handles the mixed-status reality: still-generating weeks show a waiting
  note instead of a dead audio element, failed weeks say so explicitly
  and reassure that the season pass is unaffected
- Copy-link button falls back to a hidden textarea + execCommand where
  the async clipboard API isn't available (older iOS Safari, non-HTTPS),
  so it never silently does nothing
- Empty state points a non-subscriber at setup

Entry points: mobile nav drawer (not the desktop row - that already needs
~1250px to stay on one line per the existing CSS comment, so another item
would make it worse) plus a prominent "Already set up? Open your library"
link in the sales page hero.

ALSO FIXED: the sales page numbered its steps 1, 2, 2 - "Step 2 - Pick
Your Sport" and "Step 2 - Choose Delivery". Delivery is now Step 3.

VERIFIED against a real seeded league with three recaps in mixed states
(two ready, one still generating): confirmed correct league name/platform/
sport/season header, weeks ordered newest-first (4, 3, 2), correct
statuses, best lines and transcripts only on recaps that have them, audio
players only on ready ones, copy buttons on all three, no page errors.
Confirmed the auth gate redirects an anonymous request (302), and
confirmed the empty state renders for a logged-in user with no
subscriptions.

STILL OPEN (biggest remaining Smackcast gap): there is no sample recap
anywhere on the sales page. It asks $39.99 for an audio product with
nothing to listen to. A real generator exists at /smackcast/test but it's
admin-only. Highest-value next step, needs a hosted sample audio file.
Also still on the page: emoji platform/sport icons, which read cheap next
to the rest of the site's typography.

## Smackcast: real product page + buy-first checkout with multi-league pricing
Restructured the funnel. /smackcast was the league-connection form, which
meant someone had to hook up a fantasy league before ever seeing a price.
Now:
  /smackcast          -> public product page (marketing + pricing + checkout)
  /smackcast/connect  -> league hookup, AFTER payment (was /smackcast)
  /smackcast/library  -> their recaps

PRICING (constants live in stripe_service so page, server total and Stripe
line items can't drift):
  $7.99  single recap, any league, one week
  $39.99 season pass, weekly all season, one league
  +$29.99 per additional league, season pass only

New SmackcastPurchase model. The old flow could only create a
SmackcastSubscription after league details were known; buy-first needs the
entitlement to exist beforehand, so a purchase now holds league_slots and
subscriptions attach to it as leagues get connected. slots_used /
slots_remaining are computed properties, so they can't fall out of sync
with the actual subscription rows.

- Stripe: create_smackcast_purchase_session handles the variable amount,
  itemising extra leagues as their own line with a quantity so the receipt
  shows what was bought rather than one opaque total
- Total is computed server-side from the constants; the browser sends a
  plan and a league count, never a price
- Webhook marks purchases paid on smackcast_purchase_id metadata
- create-subscription no longer routes to Stripe at all - it claims a slot
  on the oldest open paid purchase (so a single recap bought before a
  season pass gets consumed first rather than orphaned) and returns a
  redirect to the library. Returns 402 + needs_purchase if there's no open
  pass, which the page turns into a bounce to #pricing.
- Migration for smackcast_subscriptions.purchase_id and .plan; the
  purchases table is new so create_all handles it

PRODUCT PAGE: hero with Smacky, three-step how-it-works, platform tiles
(Sleeper/ESPN live, Yahoo coming, each with its supported sports), pricing
with a live-updating league stepper, and honest fine print about what
happens post-payment and what mid-season buying means. Replaced the emoji
platform/sport icons with typographic tiles - zero emoji on the page now.

CAUGHT A REAL FLAW MID-BUILD: the product page inherited @login_required
from the old connect form, so the pricing page demanded a login. Made it
public; checkout still requires an account and the page bounces to login
and returns to #pricing.

SAMPLES: the "hear it" section is data-driven off SMACKCAST_SAMPLES,
deliberately empty. The section shows a "being cut right now" placeholder
rather than a dead audio player. Filling that list is the only change
needed - generate at /smackcast/test, then paste audio_url, best_line,
league_name, sport and week.

VERIFIED: purchases table and both new subscription columns created
correctly; pricing math exact at 1/2/3/5 and 10 leagues ($7.99, $39.99,
$69.98, $99.97, $159.95, $309.90); slot entitlement decrements 3->0 as
leagues connect against real rows; product page returns 200 anonymously
while /smackcast/connect still 302s; stepper totals match the server
exactly; caps enforced at 1 and 10 on both client and server; no page
errors.

STILL TO DO: publish real samples; the connect page is functional but
still styled as the old sales page and could use a pass.

## Smackcast product page: fixed white background + added hero banner
The new product page rendered with a WHITE background. Cause: static/css/
smackagram.css supplies the :root colour variables and .btn, but NOT a body
background - every page on the site sets its own (smackcast_connect.html,
smack_lab.html etc all do). The product page linked the stylesheet and
assumed the theme came with it, so the gold/red accents were rendering on
white. Added the body background/colour, box-sizing reset and link colour
the other pages declare.

Added a full-width hero banner directly under the nav, matching the
existing pattern used by smack_lab.html and did-you-get-smacked
(single image, width:100%, height:auto). Guarded behind a
hero_image_exists check so the page renders cleanly before the file is
dropped in rather than showing a broken image - same approach already used
for smacky-hero.png.

Expected filename: static/img/smackcast-hero.png (follows the
smack-lab-hero.jpg / did-you-get-smacked-hero.png single-file convention
rather than the multi-size -780/-1560/-1983 responsive sets).

VERIFIED: body computes to rgb(13,13,13) (--ink) with rgb(245,245,243)
text, featured plan border / price / step borders all resolve to gold
rgb(255,212,0), Inter loading, no page errors, and the hero block
correctly stays hidden while the image is absent.

## Smackcast pages: design audit against the site's own stylesheet
Audited the three Smackcast pages against static/css/smackagram.css rather
than by eye. Findings and what was / wasn't changed:

FIXED - real problems:
1. Duplicated reset. The product page re-declared
   *{margin:0;padding:0;box-sizing:border-box} which smackagram.css already
   declares at line 26. Removed.
2. Sub-scale type. Four labels were at 9px - below --fs-2xs (10px), the
   smallest token the site defines - and 9px uppercase mono with
   letter-spacing is genuinely hard to read. Raised to --fs-2xs. Verified
   nothing on the page now computes under 10px (was 4 elements).
3. TWO REAL WCAG VIOLATIONS. smackagram.css states outright that --flare
   (#E8142C) only reaches 4.23:1 on --ink, failing AA (4.5:1) for anything
   under 18px, and that --flare-text (#FF3B50) exists for exactly that
   case. Both were mine:
     - connect page: 15px "No open passes" notice using --flare
     - library page: .recap-status.failed at 10px using --flare
   Both moved to --flare-text. Checked every other --flare use on the three
   pages: all are borders, backgrounds, .btn-flare, or the hero's display-
   size <em> - all legitimate per the stylesheet's own rule.
4. Hand-rolled heading clamps sitting just off the established ones -
   clamp(34px,8.5vw,60px) vs --h1-hero, clamp(24px,6vw,36px) vs --h1-page.
   Now use the tokens.
5. Converted the mapping raw sizes (10/11/12/13/14px) to their scale tokens
   on the product and library pages.

DELIBERATELY NOT CHANGED:
- Did not mass-convert every remaining raw px size to tokens. The scale
  exists but is NOT the de facto convention: smack_lab.html and index.html
  use zero scale tokens, smack_battle.html uses two. Converting wholesale
  would match the stylesheet's intent while diverging from every actual
  page. Left the off-scale display sizes (17/19/23/24/44px Anton headings)
  as-is for the same reason.
- Each page defining its own .card/.hero/.wrap/.label is correct - the
  shared CSS defines none of those (only .btn min-height), so there's no
  shadowing conflict.
- Each page loading its own font <link> is also correct; the shared CSS
  imports no fonts.
- body styles staying per-page is explicitly intended - smackagram.css has
  a comment saying body is deliberately excluded because line-height
  genuinely varies per page.

VERIFIED in a browser that every token resolves to a real pixel value (a
var() referencing a nonexistent token silently collapses, so this is the
only way to be sure): --h1-hero -> 60px, --h1-page -> 36px, --fs-2xs ->
10px, --fs-md -> 14px, --fs-base -> 13px, body -> rgb(13,13,13), and zero
elements under 10px.

## Smackcast product page: matched to reload.html's checkout design + 2 bug fixes
User pointed at /reload (the Smackagram pricing page) as the design to
match. Read the template rather than the rendered page (smackagram.com is
outside the sandbox's allowed domains), which was better anyway - got the
real tokens instead of eyeballing colours.

That page runs its OWN token names layered over smackagram.css: --punch
(#E01B24) for the accent, --surface (#141414) for cards, --line (#3A1416)
as a red-tinted hairline, --ivory/--muted/--muted-2 for text, --radius:14px.
Redeclared the same set here so the two checkout surfaces share one palette.

Adopted its tier pattern wholesale: click-to-select cards with a radio dot
and ONE confirm button below, instead of a button per card. Anchor tier gets
the gradient + scale(1.04) + ribbon treatment. Keyboard accessible
(tabindex, role, aria-pressed, Enter/Space, focus-visible), matching the
original. Removed the circular Smacky portrait - the hero banner already
carries him.

TWO REAL BUGS FIXED:
1. FROZEN LEAGUE SELECTOR. smackagram.css auto-applies a spinner to ANY
   disabled button, and explicitly documents the exception: add .no-spinner
   to buttons disabled to express a permanent state rather than a wait. The
   stepper disables minus at 1 and plus at 10 - permanent states - so both
   spun forever and looked stuck loading. Added .no-spinner. I'd missed
   that rule when writing the stepper.
2. CHECKOUT BUTTON STUCK SPINNING. Two causes, both mine:
   - The success path assigned window.location.href unconditionally, so a
     response without a checkout_url navigated to "undefined" and the
     button just sat there disabled (and therefore spinning). Now guarded
     with an explicit failure message.
   - A 500 returns an HTML error page, and resp.json() threw on it, landing
     in the generic catch with no clue what broke. Now reads the body as
     text first, then parses, and surfaces the actual status code.
   Every failure path now restores the button rather than leaving it
   disabled.

Also: stepper clicks stopPropagation so adjusting leagues doesn't
re-trigger tier selection, and adjusting leagues while Single is selected
now switches to Season rather than silently changing a number that doesn't
apply.

VERIFIED in a browser: initial state Season/$39.99/1 league with minus
correctly disabled AND carrying .no-spinner; clicking Single swaps to
$7.99 and updates the label; Season +2 gives $99.97 (3 leagues); using the
stepper while Single is selected correctly switches to Season and shows
$129.96 (4 leagues); anchor border and plan name both compute to
rgb(224,27,36); zero remaining gold (255,212,0) references; circular
portrait gone; no page errors.

NOTE: --punch on sub-18px text (.plan-name at 14px, .choose at 13px) is
about 3.6:1 on --surface, under WCAG AA. Matched reload.html deliberately
since consistency was the ask and that page does the same, but flagging it
- if it matters, those two could take --ivory with red reserved for
borders and the large price type.

## Smackcast product page: red checkout button + Smacky in accent red
The checkout button rendered as a plain white browser button. Cause: the
page used class="btn btn-flare" but never DEFINED those classes.
smackagram.css only sets min-height on .btn/.btn-flare/.btn-play/.btn-ghost -
the actual colours live per-page (smackcast_connect.html defines them at
lines 73-75). With no definition it fell back to the UA default. Added .btn
and .btn-flare using --punch to match the reload palette, plus hover and
disabled states.

Also wrapped "Smacky" in a .smacky span (accent red) in the two places it
appears as visible copy - the hero subheading and the samples heading. Left
the three meta/alt-text occurrences alone since they never render.

VERIFIED: checkout button computes to rgb(224,27,36) with white text; both
.smacky spans resolve to rgb(224,27,36).

## Smackcast pricing: Season Pass moved to the left
Swapped tier order so Season Pass leads and Single Recap follows. The grid
was 1fr 1.12fr to widen the anchor column (originally the second one), so
that flipped to 1.12fr 1fr - otherwise Season would have kept the
scale/gradient treatment while sitting in the narrower column.

VERIFIED by actual rendered position rather than DOM order: season at x106
(415px wide), single at x529 (357px). Season remains the anchor and the
default selection, and both tier switching and the league stepper still
work after the move ($7.99 on Single, $69.98 at 2 leagues).

## Smackology: Smacky's language directory (new services/smackology.py)
Consolidated everything from this session's vocabulary work into one
shared module instead of three inline prompt blocks.

WHY CURATED, NOT EXHAUSTIVE: the raw input was several hundred terms.
Pasting all of it in backfires - past a certain prompt length a model
starts working through the list rather than writing, and output gets MORE
mechanical. Cut to ~130, chosen to be distinct from each other rather
than near-synonyms ("destroyed/annihilated/obliterated/demolished/
decimated" is one idea, not five), TTS-safe, and in Smacky's register.

TTS FILTERING (all read-aloud, so these were real problems):
- Dropped "L-ified" - a bare letter plus suffix mangles in speech.
  Kept "L Collector", which reads as an ordinary two-word phrase.
- De-hyphenated "Turbo-smack"/"Mega-smack" - a hyphen is read as a pause
  or spoken as "dash".
- Added a rule against writing coinages in CAPS. The source examples used
  SMACKAGEDDON and FUMBLETRON; speech engines read capital runs letter by
  letter, so that becomes "S-M-A-C-K-A-G-E-D-D-O-N". Emphasis now has to
  live in the sentence, not the casing.

SENSITIVITY TIERING: terms carry the LOWEST level they may appear at
(matching trash_talk_service.SENSITIVITY_LEVELS 1-4). Anything above the
requested level is omitted entirely, not softened. Verified at Clean:
"ass-kicking", "dog-walked", "Cope Captain", "torched them for" all
absent - but Smackquake, Smack Meter, Cry Mode and the catchphrases all
survive, so a Clean generation still sounds like Smacky rather than a
generic announcer. That distinction is the point of tiering.

CONTEXT SPLIT: render(level, context) changes which SECTIONS appear,
because the two places Smacky speaks are different jobs.
  recap  - Smackcast. Long spoken script about game scores. Everything.
  battle - the Smack Battle judge's critiques and coach messages. Omits
           score phrasing (its scores are 0-10 ratings, and those rules
           would push it to invent point totals), omits the read-aloud
           rules (critiques are displayed text, never spoken), and omits
           the explain-a-word mechanic (a 20-word aside would consume a
           short critique whole).
Verified all four combinations: recap lvl1 5063ch / lvl4 5598ch, battle
lvl1 2755ch / lvl4 3122ch, with the right sections present in each.

UNIFIED THE TWO VOICES: the battle judge now calls
smackology.render(battle.intensity, "battle"), so it speaks the same
language as the Smackcast host at whatever intensity that specific battle
was created with. Previously it had an entirely separate voice.

Also in this session's prompt work (all now inside the directory):
- Score phrasing by register, with energetic named as the home register
  and neutral demoted to a sparing rhythm break
- Losing vocabulary as a palette with honest escalation
- best_line guarded against picking a line whose punch depends on an
  unexplained coinage - "that's a Smackquake" means nothing on a
  shareable graphic

VERIFIED: all Python compiles, full app imports, all templates parse, and
the assembled Smackcast prompt (11,377 chars) contains every section with
player standouts flowing into the user content.

## Smackcast: moved generation off the web worker (site-outage fix)
Reported symptom: test generator button spun forever, then the WHOLE SITE
stopped loading any page, then recovered on its own.

ROOT CAUSE: Render runs `gunicorn app:app --timeout 180` with no --workers
flag, so a single worker serves every request on the site. Both the test
generator and the weekly cron ran their full pipeline INLINE in the
request: a Claude call, one ElevenLabs call per matchup, sfx splicing, an
S3 upload and a meme generation - minutes of work. While that ran, the one
worker was blocked and nothing else on the site could be served. At 180s
gunicorn killed and restarted the worker, which is exactly why it appeared
to recover by itself.

The cron was the serious half. generate_weekly_smackcasts() loops over
EVERY subscription doing the full pipeline each time. Inline on a single
worker with a 180s ceiling, the worker would be killed partway through
every Tuesday - so most paying subscribers would never get a recap at all,
and the site would be down while it tried. That breaks the paid product,
not just an admin tool.

FIXED - both now use the same background-thread pattern already
established by _judge_round_async:
- Cron: fires a thread and returns immediately. Safe to fire and forget
  because generate_weekly_smackcasts already skips subscriptions that
  already have this week's recap, so an interrupted run resumes rather
  than duplicating on the next hit.
- Test generator: returns a job id immediately; new
  /api/smackcast/test-status/<job_id> endpoint is polled every 3s. Results
  are held in memory and popped on collection - they're disposable
  previews and the audio itself lives on S3. Page shows elapsed seconds
  instead of an indefinite spinner, with an 8 minute ceiling so a stalled
  job reports rather than hanging, and a clear message if the job id is
  lost to a worker restart.

ALSO FIXED while diagnosing:
- The Anthropic call had NO timeout, so the SDK default of 600s applied
  while gunicorn kills the worker at 180s - a slow call became a request
  that never returned at all rather than a clean error. Now 90s.
- max_tokens raised 1800 -> 3000. The prompt now asks for considerably
  more (score registers, losing vocabulary, smackology, named players),
  and a truncated response is invalid JSON, which silently burned the
  retry and doubled the wait.

NOTE: adding --workers 2 would also have relieved the blocking, but was
deliberately NOT done - it breaks the in-memory _pending_call_audio cache
fixed earlier for Twilio, which is exactly the dead-air bug from David's
handoff item #2.

## Smackcast: parallelized speech generation (the actual slowness)
After the background-thread fix the site stayed responsive, but generation
itself still took minutes. Found the real bottleneck: assemble_recap_audio
made every ElevenLabs call STRICTLY SEQUENTIALLY. A 10-team league is
intro + 5 segments + outro = 7 separate calls, each 10-25 seconds for a
paragraph, each waiting for the previous one to finish. That sequencing was
essentially all of the runtime.

The calls are completely independent - only the assembly needs to be in
order - so they now run through a ThreadPoolExecutor. Expected effect on a
10-team league: roughly 105s of speech generation down to roughly 30s.

Two deliberate choices:
- Concurrency capped at 4, not unbounded. A 14-team league would otherwise
  fire a dozen simultaneous requests at ElevenLabs and risk rate limiting,
  which would end up slower than sequential.
- pool.map rather than as_completed, because map preserves input order.
  Assembling on completion order would shuffle the segments, which is a
  genuinely nasty bug - a recap where the outro lands mid-way and the
  matchups are out of sequence.

VERIFIED the ordering specifically, since that's the real risk: ran the
same indexing against a stub with jittered delays so fast calls finish
first, and confirmed output order still matches input order exactly and
that intro/segment-N/outro all map to the right slots.

## Smackcast: audio CPU waste (bottleneck moved after parallelizing TTS)
Render logs from a real run told the story precisely: job returned
instantly, polling worked, site stayed responsive, NO error logged. Claude
took ~44s (pydub's import warnings mark the handoff at 04:21:13), then
audio assembly ran 96+ seconds and was still going when the page was
reloaded. So the architecture fix worked and generation was still
progressing - it hadn't failed.

Also visible in the logs: "Setting WEB_CONCURRENCY=1 by default, based on
available CPUs." Single CPU. Parallelizing the ElevenLabs calls removed
the network wait and exposed a CPU-bound audio bottleneck underneath.

FIXED real waste in _standardize: it called
.set_frame_rate(44100).set_channels(2) on every piece unconditionally, and
both of those resample the entire segment even when it's already at the
target. Its own docstring says the mismatch it guards against was the SFX
FILES disagreeing with each other (some 96000Hz, some 44100, some mono) -
ElevenLabs speech all comes from one API at one setting and is already
correct. So seven multi-minute speech segments were being resampled for
nothing, on a single-CPU box. Now converts only when a property actually
differs.

Verified the guarantee is unchanged: speech at 44100/2 does zero work,
96000/mono sfx still gets both conversions, 44100/mono sfx gets only the
channel conversion, and everything still leaves at 44100/stereo.

REMAINING inherent cost (not bugs, just the shape of the work): one mp3
decode per segment, the ffmpeg loudness normalization pass over the whole
multi-minute file, and the final mp3 export. All CPU-bound on one core.
If it needs to get materially faster than this, the options are a bigger
Render instance or dropping the normalization pass - not more code
tricks.

## Smackcast: OOM regression from my own parallelization — FIXED
Render event: "Instance failed. Ran out of memory (used over 512MB) while
running your code." This was the real cause of the failed runs, not
slowness, and it was caused by MY parallelization change.

WHAT I GOT WRONG: parallelizing the ElevenLabs calls was correct, but I
also changed the assembly to decode every segment up front into a list
(`rendered = [_standardize(AudioSegment.from_mp3(...)) for b in
speech_bytes]`). The original code decoded ONE segment, appended it, and
let it be freed. Mine held all of them decoded simultaneously.

That distinction matters enormously: mp3 bytes are compressed and cheap
(~1MB per segment), but a DECODED AudioSegment is raw PCM at roughly
176KB per SECOND — 44100Hz x 2 channels x 2 bytes. A four-minute recap is
~40MB decoded. Holding all seven segments decoded at once, plus the
growing combined track, plus pydub's copy-on-append, went straight past
512MB and the instance was killed.

FIX: keep the parallel network win (still ThreadPoolExecutor, still
order-preserving) but hold only the COMPRESSED bytes, and decode one
segment at a time immediately before appending it, so each is freed right
after use. Also explicitly frees the compressed blobs before the export
and ffmpeg normalization pass, both of which need headroom on a 512MB box.

Net memory profile is now the same as the original working code, with the
parallel speed benefit retained.

LESSON WORTH KEEPING: on this instance size, anything touching decoded
audio must be streamed one piece at a time. Bulk-decoding a multi-minute
recap will always OOM. Concurrency on the DOWNLOADS is fine (a few MB);
concurrency on DECODED segments is not.

## Smackcast: I DELETED the length instruction — 7-minute recaps
Reported: a 12-team recap came out over 7 minutes, when earlier ones were
3-4. Something changed with the smackology work.

ROOT CAUSE, and it was my error: the length instruction was GONE from the
prompt entirely. target_words was still being computed and then referenced
nowhere. When I consolidated the vocabulary into smackology.render(), I
replaced everything between "SCORE PHRASING" and "REAL PLAYERS" - and the
"Target length: approximately {target_words} words" line sat inside that
range. I swallowed it. So the model had no length guidance at all, which is
exactly why output nearly doubled. Raising max_tokens 1800 -> 3000 removed
the incidental ceiling that had been masking it.

FIXED:
1. Restored the instruction, and made it enforceable. A single total proved
   too abstract to hold to in a 12,000-character prompt, so it now gives a
   PER-PIECE budget: intro ~55 words, each matchup segment ~N words (total
   divided by the actual matchup count), outro ~45. A 12-team league now
   reads "about 83 words per segment, there are 6 matchups this week",
   which is concrete enough to write against.
2. Recalibrated to the requested runtimes, banded rather than a linear
   ramp: up to 9 teams -> 450 words (~3 min), 10-12 -> 600 (~4 min), 13+ ->
   900 (~6 min). Previously a linear 450-750 topping out at 5 min.
3. Added an explicit instruction that the vocabulary is a palette, not a
   checklist, and that if it's over budget the COINAGES get cut first - the
   scores and player callouts are the content. The length overrun was
   partly the model trying to demonstrate all the new vocabulary.

Verified the rendered prompt shows real numbers: 600 words / 4.0 minutes /
83 words per segment / 6 matchups for a 12-team league.

## Smackcast: cursing vanished — clean vocabulary crowded out the profanity
Reported: no cursing at all in a 7-minute generation, when the product has
always been heavily profane.

CAUSE: the instruction was still there ("heavily profane... real cursing
throughout", line 110) — but everything I added in the smackology work was
CLEAN. Zero instances of any real profanity across ~12,000 characters of
concrete word lists. Given that much specific vocabulary, the model writes
FROM the list, so one line of instruction lost against a wall of clean
words. A crowding-out effect I should have anticipated when adding a
vocabulary that large.

FIX: put the profanity into the vocabulary itself, at tier 4, so the
concrete list the model draws from actually contains it — profane verbs,
intensifiers meant to sit in front of the existing adjectives/nouns
("fucking pathetic", "a goddamn shitshow"), nouns, and names for people.
Plus an explicit statement that the coinages go WITH the profanity rather
than instead of it, and that the target register is both in one breath:
"that was a goddamn Smackocalypse."

Tiering verified: level 1 and level 3 render zero profanity terms, level 4
renders 15. So Clean and Aggressive battles stay clean while Smackcast
(always 4) and Savage battles curse.

Still bound by the existing hard limits — no slurs, nothing targeting
protected characteristics, aimed at team performance.

## Smackcast: recap runtime — speaking pace was measured wrong
12-team recap came back at 5:12 against a 4:00 target. The word budget was
being honoured; the ASSUMPTION converting words to minutes was wrong. The
code assumed 150 words/minute, a conversational reading pace. Smacky's
delivery is slower: 600 words produced 312 seconds of audio, which is
~115 wpm. Every target was therefore ~30% optimistic.

Replaced the buried assumption with a single named constant,
SPOKEN_WORDS_PER_MINUTE = 115, measured from that run. The per-band values
are now expressed as MINUTES (the product decision) and the word count is
derived, so runtime is tuned by adjusting one number rather than
recalculating three word counts by hand.

New targets: up to 9 teams 345 words (3 min), 10-12 460 words (4 min),
13+ 690 words (6 min). Previously 450/600/900 at the wrong pace.

Note the 13+ band is flat all the way to 32 teams, so a 32-team league gets
~43 words per matchup. That is likely too thin to be a good product
regardless of price — worth deciding before selling large-league tiers.

## Smackcast: TTS spoke the word "comma" out loud
Observed around 2:58 and 3:05 in a real generation: the voice said "comma"
instead of treating it as punctuation.

Added sanitize_for_speech(), applied to the intro, every segment and the
outro immediately before synthesis - NOT to the stored transcript, which
keeps its original punctuation for display on the recap page.

Handles two separate problems:
1. Spoken punctuation names. Strips "comma", "semicolon" and "ellipsis"
   when they appear the way a dictated punctuation mark would.
2. Typographic punctuation the model mirrors from the prompt's own writing
   style - em dashes, en dashes, ellipses and smart quotes get normalised
   to plain commas, periods and straight quotes, which every engine reads
   predictably. Em dashes were a likely contributor: the prompt is full of
   them, so the model reproduces them, and engines read them
   inconsistently (sometimes a pause, sometimes the word "dash").

CAUGHT MY OWN OVER-REACH: the first version also stripped "period",
"dash", "quote", "colon" and others. That broke real sentences - "dominated
every period" became "dominated every", and "that's it, period" lost its
emphasis. Those words have legitimate uses in a sports recap. Narrowed to
the three that never legitimately appear spoken, and required them to sit
between punctuation or spaces the way a dictated mark would, so a sentence
that genuinely discusses commas survives.

Verified across eight cases: both bug forms stripped, and "period" as
emphasis, "period" as a game period, "dash" as a verb and ordinary commas
all preserved.

## Smackcast: team-name roasting + stronger profanity
Two notes from listening to a real generation: not enough roasting aimed at
the specific fantasy team, and still not swearing enough.

TEAM NAME AS THE PERSONAL ANGLE. There are no owner names anywhere in the
data - only team names. But a fantasy team name is something the owner
CHOSE, which makes mocking it land personally without ever being about the
human, and keeps it inside the existing hard limit (roast the team, never
invent personal details). New prompt section instructs: say the team name
often rather than "they", treat the name as a promise and hold them to it
(Undefeated Underdogs losing by 40 writes its own joke), mock names that
try too hard or are lazy, coin a nickname from it and reuse it, and play
the two names in a matchup off each other. Framed as the difference
between a scoreboard read aloud and a roast aimed at somebody. Renders at
every sensitivity level since none of it depends on profanity.

PROFANITY STRENGTHENED. The previous tier-4 set was too polite and output
came back under-sworn. Added the specific vocabulary requested - fucking,
fuck, bullshit, what the fuck, what the hell - plus a reactions category
for opening a segment on one. Density instruction hardened from "most
segments" to "EVERY segment, more than once where it fits", with an
explicit note that a segment containing no profanity is off-voice.
Profanity terms in the rendered vocabulary went from 15 to 28.

Still bound by the hard limits: no threats, no slurs, nothing targeting
protected characteristics, no sexual content, and aimed at team
performance rather than the person.

## Smackcast: roasting the unseen manager (safely)
User's framing, and it's genuinely safer than what was there: Smacky can go
after whoever runs a team, but only ever as a stranger judging their
DECISIONS. He has never met them, knows nothing about them, and the only
evidence is the lineup they set and what it scored. Phrasing it that way -
"whoever is setting this lineup needs to get a fucking clue" - structurally
prevents inventing anything personal, because the framing itself
acknowledges he doesn't know who they are.

Reuses the pattern already established in trash_talk_service's hard limits:
criticism that reaches toward a person stays hypothetical or rhetorical
rather than a flat declarative statement of fact. "Whoever set this lineup
has lost their mind" is fine; asserting things about them as a person is
not - and couldn't be accurate anyway.

The named starters and their points are what make this land: a bust in the
STARTING lineup is a decision somebody made, which is as personal as it
ever needs to get. Explicitly out of bounds: their job, looks,
intelligence, family, anything about their actual life, anything sexual,
any threat.

SCOPED TO RECAP CONTEXT ONLY. Both this and the team-name section are
recap-only concepts - a Smack Battle has a live opponent typing lines, not
an absent fantasy manager, and no fantasy team name to work with. Verified
all four combinations: recap gets both sections at levels 1 and 4, battle
gets neither, and smackology's own vocabulary still renders in all four.

## Smackcast: team names Smacky can't pronounce
Raised as a hypothetical, but it's a real hole - fantasy team names are
routinely unsayable (leetspeak, emoji, mashed player names, keyboard
nonsense, all-caps) and nothing handled it. It would have produced garbage
audio silently.

Fixed in two places, because the prompt alone isn't enough:

1. PROMPT (recap context only): instructed NOT to attempt an unpronounceable
   name and never to read it character by character. Instead say plainly
   he's not trying it, coin a nickname, use that for the rest of the recap,
   and mock the choice - somebody typed that on purpose, which says
   something about how their lineup decisions go. Turns a failure mode into
   material, which is more in-voice than a workaround.

2. SANITIZER (defensive, so bad audio is impossible even if the model
   ignores the instruction):
   - Emoji and pictographs stripped. Engines either skip them or read the
     character's description aloud ("fire emoji") mid-sentence.
   - All-capital runs of 5+ letters title-cased, because engines spell
     capitals out letter by letter - THEREALCHAMPS would become
     "T-H-E-R-E-A-L...". Deliberately only 5+: shorter runs are usually
     genuine acronyms (NFL, QB, RB, TE) which SHOULD be spelled out, and
     title-casing those would be the wrong fix.

Verified: emoji removed, THEREALCHAMPS -> Therealchamps, while QB/RB/NFL
survive untouched in the same sentence.

## Smackcast test generator: deliberately awkward team names
Added _TRICKY_TEAM_NAMES so the read-aloud handling actually gets exercised
instead of only showing up by luck with a real league. Each entry probes a
different rule:
  topdogdaddypants / thewaiverwirekings - real words run together. SAYABLE;
    should be said in full and mocked, not refused.
  THEREALCHAMPS - long caps run; sanitizer title-cases it so it isn't
    spelled out letter by letter.
  xXx_L33T_xXx / Ftghjklmn United - genuinely unsayable; should trigger the
    "not attempting that, we'll call them X" nickname path.
  emoji name - sanitizer strips the pictographs, words survive.
  Saquon The Barbarian / 2 Chainz 2 Furious - sayable puns and a leading
    digit; both should be read normally.

TWO are swapped in per generation, not all of them, deliberately. A sample
needs ordinary names alongside so a test shows both that tricky names are
handled AND that the "can't pronounce it" escape hatch does not start
over-triggering on perfectly sayable names now that the model has it.

Verified a real sample: drew the emoji name and topdogdaddypants alongside
ten normal ones, and confirmed the emoji name sanitizes to "Fire Squad"
while topdogdaddypants passes through untouched.

## Smackcast test page: stress-test toggle for read-aloud handling
Two tricky names per generation was hardcoded, so hitting the genuinely
unsayable cases was down to luck - and after several runs the refuse-and-
nickname path still hadn't been exercised.

Added a "Stress test read-aloud handling" checkbox to /smackcast/test which
replaces EVERY team name with a deliberately awkward one. Expanded the pool
from 8 to 14 so a 12-team stress run has no repeats, adding: a caps run with
no word structure (AAAAAAAAA), symbols mid-name (Ctrl+Alt+Defeat), a
repeated lowercase letter (iiiiiiii), an ordinal (Da 12th Man), an
EMOJI-ONLY name (nothing survives sanitizing, so it must be nicknamed), and
periods mid-name (Mr. Fantasy Pants Jr.).

Default stays at two tricky names, deliberately. That's closer to a real
league AND it tests the opposite failure - that Smacky doesn't start
refusing perfectly sayable names now that he has the option. The stress
toggle is for probing the handling, not the normal case.

Confirmed a 10-team stress run produces all-awkward names including both
refusal cases (xXx_L33T_xXx, Ftghjklmn United) and the emoji-only name.

## Smackcast: emoji team names — locked in the behavior that emerged
A stress-test run produced, unprompted: "Three football emojis in a row.
There's nothing I respect about that team name." That's better than what was
designed for - the plan was strip-then-nickname, and instead it DESCRIBED
the name and made the description the insult.

That worked because of a split built for a different reason: the model reads
the RAW text (emoji included) in the prompt, while only the SANITIZED text
reaches text-to-speech. So it knows exactly what the name is without having
to pronounce it. Emergent, not instructed - so now made explicit rather than
left to luck. Prompt instructs: count them, name them, let how stupid it
sounds out loud do the work, and note that an emoji-ONLY name is the best
version since there's literally nothing to read.

Also broadened _EMOJI_RE well beyond the common blocks, since fantasy names
use all of it: flags (regional indicators), arrows, stars, hearts, keycap
sequences, enclosed alphanumerics, CJK symbols, trademark/copyright, and
zero-width joiners for compound emoji like family groupings.

Verified across ten cases - fire, football-only, star, flag, keycap, heart,
compound family, trademark, arrows - all stripped correctly, with an
ordinary team name left untouched.

## Smackcast: underscores in names produced dead air
Real stress-test observation on xXx_L33T_xXx: stutter on the x run, then a
SILENT GAP where the underscore was, "L33T", another silent gap, then the
stutter again. The stumble is fine - it's the joke, and Smacky weaponised it
- but the gaps just sound broken.

Underscores, tildes, carets, pipes and backticks now become spaces before
synthesis, so they read as word breaks. Common in gamertag-style names, so
this generalises beyond the one case.

Deliberately NOT smoothing further. Stumbling over a genuinely stupid name
is good material; over-sanitising would strip the joke out along with the
noise. Left "+" alone in Ctrl+Alt+Defeat pending a listen - if the engine
speaks "plus" aloud that's a separate call, and it might well be funnier
than silence.

Verified nothing else regressed: THEREALCHAMPS still title-cases, the
Mr./Jr. periods survive, emoji-only still empties, ordinary names untouched.

## Session status — Smackcast read-aloud handling, all paths confirmed
Every case verified in real generations, not just unit tests:
  AAAAAAAAA           said aloud and mocked ("a name like that tells me
                      everything I need to know about you")
  topdogdaddypants    said in full, not refused - the escape hatch is not
  thewaiverwirekings  over-triggering on sayable names
  2 Chainz 2 Furious  digits spoken as words ("two chains two furious")
  football emoji only DESCRIBED rather than attempted, and the description
                      became the insult
  xXx_L33T_xXx        stumbled, then turned the stumble into the joke
  Ftghjklmn United    attempted it, degraded into gibberish, then self-
                      rescued: "ahhh I'm just going to call you Fudge" - and
                      used Fudge for the rest of the recap
ALL SIX PATHS NOW CONFIRMED in real audio.

REFINEMENT from that last one: he built the nickname OUT OF the name's own
sounds (Ftghjklmn -> Fudge) rather than describing it from outside, which is
better than the generic "Alphabet Soup" example the prompt gave. It reads as
his genuine attempt at saying it. Written into the prompt as the preferred
approach: grab the first syllable or two and run with it.

RESOLVED - the refuse-and-nickname instruction STAYS, and I was about to
recommend cutting it, which would have been wrong. Real output:
  stumbles on xXx_L33T_xXx, then "I'm just going to call you L33T for now so
  I don't have to do that again."
The nickname comes from the instruction, but he EARNS it in the moment by
reacting to his own struggle. That's better than either half alone: a clean
upfront refusal reads as a workaround, and stumbling with no resolution just
sounds broken. The stumble becoming the REASON for the nickname is the
pattern, and it's now written into the prompt as the preferred handling
rather than left to chance.

## Smackcast: manager criticism wasn't firing
Noted after the stress run - no shots taken at the people running the teams,
despite the unseen-manager section being in the prompt.

TWO CAUSES, one of them a testing artifact:
1. The stress run had all TWELVE team names deliberately awkward. At ~60
   words per segment, handling a bizarre name consumed the entire budget,
   leaving nothing for manager criticism. A normal league with one or two odd
   names would not squeeze it out the same way - so this is partly an
   artifact of an unfair test.
2. But the section was also too passive. It described what was ALLOWED
   without ever saying how often to do it, in a prompt now well over 16,000
   characters competing for attention.

Made it directive and tied it to the evidence: any segment with a bust
starter should question whoever chose to start them, targeting at least a
third of segments, with an explicit note that a recap discussing only scores
and never questioning anybody's judgement has left the best angle unused.
Pairing the manager criticism with the bust data is what moves it from "the
team scored badly" to "a person made this happen on purpose".

Worth re-testing on a NORMAL generation (stress off) rather than another
all-awkward run, since the name handling competes directly with this for
segment budget.

## Smackcast: no audible break between matchups
Segments ran straight into each other with nothing signalling a new matchup.
In text you can see a paragraph break; in audio there's nothing, so a
listener loses track of who's even being discussed.

Fixed in two places, because either alone is insufficient:

1. SPOKEN TRANSITIONS. Every segment after the first opens with a short
   handoff - moving on, next up, elsewhere, meanwhile, which brings me to -
   with an explicit instruction to VARY them, since the same phrase six times
   is worse than none. Better still, make the transition carry contempt or
   connect to the previous segment ("if you thought that was bad", "somehow
   it gets worse"). Naming the teams immediately after the handoff is what
   actually orients the listener. No transition on the first segment (it
   follows the intro) and the outro closes rather than transitions.

2. A 450ms SILENCE before each new matchup in the audio assembly. Spoken
   transitions do most of the work, but back-to-back speech with no gap still
   runs together to the ear. Skipped before the first segment, which already
   follows the intro's trailing pause.

Costs a few seconds of runtime on a 6-matchup recap - worth it for being able
to follow what's happening.

## TODO (MANDATORY, not yet built): download generated audio locally
Raised while collecting sample recaps. Not implemented - this is a note.

THE PROBLEM: every generated file lands in S3 under tts/ with a random UUID
filename (a3f9c2e1-....mp3), in one flat folder, mixed in with prank call
audio and every test generation. Nothing indicates which recap, league,
sport or week a file belongs to. Sorting by Last Modified in the AWS console
is currently the only way to find anything, which does not scale and makes
collecting samples for the product page tedious.

PREFERRED FIX: a download button on /smackcast/test (and probably on the
library page too) that serves the file with a sensible name derived from the
database rather than the S3 key - e.g. smackcast-nfl-week7-2026-07-30.mp3.
One click, no CLI, no bucket hunting. Estimated small.

SECOND OPTION: a script that syncs recent files down and renames them by
joining S3 keys against SmackcastRecap rows for league/week/sport. Useful
for bulk, but doesn't fix the underlying naming problem.

WORTH CONSIDERING AT THE SAME TIME: storing a human-readable S3 key at
upload time instead of a bare UUID. That fixes this at the source rather
than papering over it afterwards, and would make every future file
self-describing. Larger change since the key format is shared with the
prank-call audio path.

RELATED RISK already noted elsewhere: samples published to the product page
live under the same tts/ path as everything else, so any future S3 lifecycle
cleanup rule would delete them. Namespacing samples separately would need
its own bucket policy - see the note in smackcast_service.generate_meme_image
about public-read being scoped to tts/.

## CRUCIAL TODO (not built): the weekly delivery loop has never actually run
Clarified while walking through the customer workflow. The pipeline IS fully
automated - customer buys, connects a league, and every Tuesday the cron
generates and DELIVERS with no manual step (phone call via Twilio, SMS with
the share link, Discord/GroupMe webhooks, plus the library). Nobody needs to
be awake for it.

But three things make the first real Tuesday risky, and none are built:

1. FAILURES ARE SILENT. Each subscription is wrapped in its own try/except -
   correct, so one bad league can't kill the run - but a failure only prints
   to the log and moves on. Nobody is notified. At two subscribers you would
   not notice a missing recap for a week, and the customer paid for it. THIS
   IS THE MOST IMPORTANT ONE. Needs at minimum a failure count surfaced
   somewhere you'd actually see, ideally per-subscription failure state on
   SmackcastRecap (status="failed" already exists as a value) plus an admin
   view or an alert.

2. THE PATH HAS NEVER RUN FOR REAL. Everything to date has been the
   admin-only test generator against generate_sample_matchups() - fake data.
   The real path (sleeper_service/espn_service fetch -> generate -> deliver)
   has never been exercised against a live league. First paying customer is
   currently also the first integration test. Worth connecting a real
   personal league and letting one genuine Tuesday run before selling.

3. SMS DELIVERY IS BLOCKED. Twilio A2P 10DLC still pending, so the text
   option silently won't send even though it's offered at signup. Either gate
   that option in the UI until approval lands, or make the failure visible.

Related, already logged separately: chunked cron becomes necessary somewhere
around 10-15 subscribers, since the run is sequential at ~2-3 min each and a
restart mid-run currently loses the remainder until the following week.

## SMACKCAST TODO LIST — consolidated (as of end of this session)
Everything outstanding in one place. Ranked within each group.

### A. BEFORE SELLING TO ANYONE
A1. THE REAL DATA PATH HAS NEVER RUN. Every generation to date used the
    admin test page against generate_sample_matchups() - fake data. The live
    chain (sleeper_service/espn_service fetch -> generate -> deliver) has
    never touched a real league. Right now the first paying customer is also
    the first integration test.
    BEST SINGLE TEST: connect one real Sleeper league AND one real ESPN
    league of your own, then hit the cron endpoint manually. That exercises
    every item in group B at once.

A2. FAILURES ARE SILENT. Per-subscription try/except is correct (one bad
    league can't kill the run) but a failure only prints to a log nobody
    reads. At two subscribers a missing recap would go unnoticed for a week,
    and they paid for it. Needs failure state surfaced - status="failed"
    already exists on SmackcastRecap, so at minimum write it and show it,
    ideally alert.

A3. NO SAMPLE ON THE SALES PAGE. Asking $39.99 for an audio product with
    nothing to listen to. SMACKCAST_SAMPLES in app.py is deliberately empty
    and the section renders a placeholder. One-line fix once real samples
    exist: audio_url, best_line, league_name, sport, week per sample.

A4. SMS DELIVERY IS OFFERED BUT BLOCKED. A2P 10DLC still pending, so the
    text option silently won't send even though signup presents it. Gate it
    in the UI until approval, or make the failure visible.

### B. LIVE-DATA RISKS (all untested, ranked by likelihood of biting)
B1. Sleeper player-name dump on a 512MB instance. Fetching real player names
    downloads Sleeper's full player file (several MB) and holds ~11,000
    players in memory for the process lifetime. This box already OOM'd once
    tonight. Fires on the FIRST real recap. Most likely thing to break.
B2. ESPN box score shape. The view param was changed to mBoxscore and
    _standouts() written against an ASSUMED response structure. Best case no
    player callouts, worst case it throws. Never seen a real ESPN response.
B3. ESPN private-league cookies expire. SWID/espn_s2 captured once at
    signup, no refresh, no notification. Recaps would quietly stop working.
B4. Tuesday 9am timing. If a Monday night game hasn't finalised, the recap
    could generate off incomplete scores. Confirm both platforms have
    settled by then.
B5. Rotisserie / category leagues are documented unsupported - but is that
    caught at SIGNUP or only at generation? Difference between a clear error
    and a customer paying for nothing.
B6. Non-English team names. Sanitizer leaves them intact (correct), but TTS
    handling is unknown.
CONFIRMED FINE: bye weeks / odd team counts are skipped cleanly.

### C. SCALE (not needed yet, thresholds noted)
C1. Chunked cron. Run is sequential at ~170s per recap. 10 subscribers is
    ~30 min, 100 is ~5 hours, and a restart mid-run loses the remainder
    until the following week. Build around 10-15 subscribers.
C2. ElevenLabs cost. ~2,700-4,500 characters per recap. At 100 subscribers
    that's well over a million characters a month against a plan including
    ~100k. Price the overage before selling volume - this bites at a much
    lower subscriber count than the infrastructure does.
C3. Pricing tiers for larger leagues. Requested, never built. Needs bands
    and prices. Note the 13+ band is flat to 32 teams, so a 32-team league
    gets ~43 words per matchup, which may be too thin to sell at any price.

### D. TOOLING
D1. Local audio download / S3 filenames. Every file is a random UUID in one
    flat tts/ folder mixed with prank-call audio. Preferred fix: download
    button with a database-derived filename. Better long-term: store a
    human-readable S3 key at upload.
D2. Connect page still wears the old sales-page styling, unchanged since it
    became the post-checkout step.

## Smackcast: download button in the subscriber library
Subscribers could already stream every recap from /smackcast/library, but
saving one meant right-clicking and hunting for "Save Audio As". Added a
proper Download button per recap.

PROXIED through the app rather than linking straight to S3, for one concrete
reason: the S3 object key is a bare UUID, so a direct link saves as
"a3f9c2e1-....mp3". Going through the app allows Content-Disposition with a
real filename - smackcast-the-dynasty-disasters-week7-2026.mp3. This also
covers the tooling TODO logged earlier about unusable S3 filenames.

Streamed in 64KB chunks rather than read into memory - a multi-minute recap
is several MB and this instance has already hit its ceiling once tonight.

OWNERSHIP IS CHECKED. Recap IDs are sequential integers, so without it any
logged-in user could walk the range and pull down other subscribers' audio.
Returns 404 rather than 403 for a non-owner, so it doesn't confirm that a
recap with that id exists.

Filename generation verified against awkward league names: punctuation and
symbols collapse to hyphens, and an emoji-only or missing league name falls
back to "league" rather than producing an unusable filename.

Access verified three ways: owner reaches the fetch (502 only because the
test row pointed at an unreachable URL, which also confirms the upstream
error path), non-owner gets 404, anonymous gets redirected to login.

CAUGHT MID-BUILD: my edit script appended the anchor twice, producing
@app.route("/smackcast/library")@app.route("/smackcast/library") on one line
and a TypeError on boot. Fixed; full app import and both route registrations
now verified.

## Smackcast library: rethemed to match the product page
The library was built before the red palette was settled, so it was still on
gold with the base smackagram.css look while /smackcast had moved to the
reload-style tokens. Brought fully in line rather than approximately:
  - Same token block (--punch, --surface, --hairline, --radius) as
    smackcast_product.html and reload.html
  - Same full-width hero banner under the nav, behind the same
    hero_image_exists guard
  - Hero typography lifted verbatim - label, --h1-hero heading with a red
    <em>, sub paragraph, .smacky accent
  - Same .btn / .btn-flare definitions rather than a bespoke button style
  - Copy rewritten into the product page's voice ("Every week you got
    roasted") instead of a flat description
  - Card surfaces moved from --ink-2 to --surface, borders to the red-tinted
    --hairline, radius to --radius
Zero gold references remain.

VERIFIED by comparing COMPUTED styles between the two pages rather than
eyeballing: 7 properties checked, and the only difference turned out to be
the PRODUCT page using --flare on its hero <em> while everything else on it
used --punch - a leftover from the palette swap. Fixed the outlier rather
than degrading the library to match it. Both pages now identical on body
background, label colour, heading font/size, em colour, sub size and the
smacky accent.

NOTE on the empty library: that's correct behaviour, not a bug. There are no
paid Smackcast purchases in production yet, so no subscriptions and no
recaps. It populates once a real league is connected.

## Smackcast test page: save a generation into the admin library
Asked for a recap to exist in the admin library for testing. Rather than
hand-seeding a database row (which also wouldn't have had real audio), added
a "Save to my Smackcast library" checkbox to /smackcast/test.

When ticked, the generated recap is persisted as a real SmackcastRecap
against a self-created "__admin_test__" subscription owned by the admin - so
it shows up in the library with a working player, a share link and a
download, exercising the whole surface end to end.

Useful beyond testing: this is also how samples for the product page get
produced. The audio already lives on S3 either way; saving just gives it a
row, a share token and a proper download filename.

Save failure is caught and rolled back separately from the generation, so a
database problem can never lose audio that has already been generated and
paid for.

Reuses one subscription per admin rather than creating a new one per run, so
repeated test generations stack up as weeks under a single league heading
instead of littering the library.

## Smackcast: THEREALCHAMPS came out as "Theral Champs"
Caught in live testing. The sanitizer title-cases long capital runs so they
aren't spelled out letter by letter - THEREALCHAMPS becomes Therealchamps -
but the voice engine then read that single long word as "Theral Champs",
dropping syllables entirely. So the caps fix solved one problem and created
another.

WRONG LAYER. The sanitizer is a regex; it cannot know that THEREALCHAMPS is
"the real champs" with the spaces removed. The MODEL can see that trivially.

Fixed in the prompt instead: when a team name is words run together, with or
without capitals, write it SPACED OUT in the script - "The Real Champs",
"top dog daddy pants" - so it reads correctly aloud, then mock them for not
bothering with the spacebar. Gets the joke AND correct pronunciation, where
the sanitizer approach could only ever get one.

This also explains why topdogdaddypants worked earlier: it happens to be
made of short common syllables the engine guessed right. That was luck, not
handling. Now it's instructed.

Sanitizer title-casing stays as the fallback for when the model doesn't
split a name - it still prevents letter-by-letter spelling, which is the
worse failure.

## Smackcast: transitions dropped in a stress run
Live testing: several segments moved to a new matchup with no spoken handoff
at all, leaving the listener no cue that the subject had changed.

CAUSE: the instruction was phrased as a stylistic preference ("open each
segment with a short transition") sitting among a dozen other rules in a
14,000-character prompt. Under pressure - every segment in a stress run has
an unpronounceable name to deal with inside ~60 words - it was the first
thing dropped.

FIXED by making it STRUCTURAL rather than stylistic. A segment is now
defined as an ordered shape: handoff, then both team names, then everything
else. Explicitly states the handoff is not optional and is not the first
thing to cut when crowded - if short on room, cut a coinage or trim the
roast instead. Also states that a segment opening straight into a joke about
a stupid team name has failed however good the joke is, which is exactly the
failure that occurred.

Ordering matters as much as presence: the handoff has to come BEFORE the
name mockery, since orienting the listener is the whole point.

Possibly aggravated by the stress run specifically - a normal recap has
spare budget per segment, and the earlier non-stress generation sounded
correct. Worth confirming on both.

## Smackcast: slang spellings read as initials, and Smackocalypse removed
Two from the same live listening session.

1. "Da 12th Man" came out as "Dee-Ay 12th Man" - the engine read the short
   non-standard word as INITIALS, the same instinct that correctly spells out
   QB and NFL. Right rule, wrong case, and the sanitizer can't distinguish
   them. Same fix as run-together names: the MODEL can tell it's slang, so it
   now writes such words PHONETICALLY in the script ("Duh 12th Man") and can
   still mock the spelling. Covers Da, Tha, Dem, Ova and similar, which are
   common in fantasy team names.

2. Smackocalypse removed from the invented vocabulary - didn't sound right
   read aloud. Also had to be replaced in TWO worked examples in the prompt,
   which would otherwise have kept reintroducing it despite the list entry
   being gone. Wins vocabulary is now Smackageddon, Smackquake, Smacknado,
   Smackzilla. Verified it appears nowhere in the rendered prompt.

Pattern worth noting across all three read-aloud fixes tonight
(THEREALCHAMPS, Da, and run-together names generally): the sanitizer is the
wrong layer for anything requiring comprehension. A regex cannot know that
THEREALCHAMPS is three words or that Da is slang. The model can, trivially.
The sanitizer's job is mechanical hazards only - emoji, separators, caps runs
- and everything requiring understanding belongs in the prompt.

## Smackcast: fixed branded opener
Every episode now opens with three beats in a fixed order before anything
about the league:

1. A greeting that VARIES week to week - eight supplied to rotate through
   ("What's up, degenerates", "Rise and shine, losers", "Well, well, well.
   Look who showed up", etc), or he can coin his own in the same register.
   The only rule is that it can't be the same one every week.

2. Then, WORD FOR WORD:
   "Welcome to this week's brand new episode of the Smackcast, brought to you by
   Smackagram! I'm your host, Smacky. Everybody gets smacked. No exceptions."
   Explicitly flagged as fixed text rather than something to reword in his
   own voice - it's a sponsor read plus a signature line, and both only work
   as branding if they're identical every week.

3. Then the WEEK NUMBER said out loud, plainly, and the league name. Recaps
   are filed weekly, so the number is the only thing distinguishing one from
   the next, and a listener opening a link needs to know what they're
   hearing. The week is already passed in as data, so it's accurate rather
   than invented.

Also instructed NOT to restate the sponsor or tagline later or close on
them - they open the show, that's it.

TAGLINE NOTE: "Everybody gets smacked. No exceptions." was chosen over
several alternatives because it states a rule rather than making a joke -
the same shape as taglines that last - and is built from the brand's own
word, so no competitor could use it. Written as its own sentence rather than
joined with "and", so it lands as a declaration rather than a trailing
clause. Provisional; easy to swap.

## WATCH: recap prompt is now 23,261 characters
Grew from ~16,000 over this session as vocabulary, read-aloud handling and
the branded opener were added. Crowding has ALREADY caused two regressions
tonight - the manager criticism faded, then the segment transitions did -
and both were fixed by making the instruction structural rather than adding
more text.

If something that previously worked starts slipping (score-phrasing variety,
coinage frequency, player callouts), assume crowding before assuming the
instruction is wrong, and TRIM rather than add. Candidates to cut first if it
comes to that: the losing-vocabulary word lists are the longest section and
the most redundant, since the model reliably generates that register without
being handed a list.
