# Smackagram — Future Roadmap

Saved for reference. Not yet started. Revisit and prioritize when ready.

## Prerequisites (needed before most of this becomes buildable)
- [ ] **Postgres database** — currently on SQLite, which wipes on every Render
      redeploy. Accounts, purchase history, and admin reporting all need
      data that survives deploys.
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
