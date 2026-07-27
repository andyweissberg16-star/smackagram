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

---
*Last updated: 2026-07-26*
