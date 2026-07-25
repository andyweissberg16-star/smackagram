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

---
*Last updated: 2026-07-25*
