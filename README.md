# Smackagram — backend scaffold

## What's here

- `app.py` — Flask routes: landing page, immediate orders, locked-and-loaded
  smackagrams, Twilio callbacks
- `models.py` — `Scenario`, `Order` (send-now flow), `Smackagram` (conditional
  game-outcome flow)
- `services/twilio_service.py` — places calls, builds the TwiML script
- `services/stripe_service.py` — immediate charges + the authorize-now,
  capture-later flow used for locked smackagrams
- `services/sports_service.py` — upcoming games (48h window) and game results
- `scheduler.py` — background job that checks armed smackagrams every 3
  minutes and fires or releases them once a game goes final
- `templates/index.html` — the landing page

## What's stubbed and needs real wiring before this runs

1. **`services/sports_service.py`** — now wired to ESPN's free unofficial
   API (`site.api.espn.com`). No key needed. Worth verifying the exact
   status string ESPN uses for "game is over" (`STATUS_FINAL`) against a
   real completed game before relying on it — this was written from
   documented behavior, not tested against a live response, since this
   environment can't reach espn.com.

2. **`services/elevenlabs_service.py`** — generates TTS for custom
   messages and uploads to S3. Needs a real `ELEVENLABS_API_KEY`,
   `ELEVENLABS_VOICE_ID`, and an S3 bucket (`AUDIO_S3_BUCKET`) with public
   read access on the `tts/` prefix. Uses the `turbo` model for lower
   per-character cost — fine for short prank lines.

3. **`.env.example`** — copy to `.env` and fill in real Twilio, Stripe,
   ElevenLabs, and AWS keys.

4. **Stripe webhook signature verification** — the current webhook routes
   don't verify the Stripe signature header yet. Add that before going live
   (`stripe.Webhook.construct_event`) so you're not trusting unverified
   POST bodies.

5. **Scenario library** — the `scenarios` table is empty. Needs seeding with
   your actual pre-recorded clips (audio_url) and the "write your own"
   entry.

## Running locally (once .env is filled in)

```bash
pip install -r requirements.txt --break-system-packages
python app.py
```

This starts Flask on :5000 and the background scheduler in-process. For
production, run the scheduler as a separate worker process rather than
in-process with the web server — otherwise a web dyno restart kills your
polling job mid-cycle.

## Key design decisions baked into this scaffold

- **Locked smackagrams use `capture_method: manual`** on the Stripe
  PaymentIntent — the card is authorized when armed, captured only if the
  target team loses, released (canceled) if they win. Nothing is charged
  until the outcome is known.
- **48-hour arming window** is enforced server-side in `arm_smackagram()`,
  not just in the UI — this keeps every hold comfortably inside Stripe's
  7-day authorization expiry.
- **Recording consent line is baked into the TwiML script itself**
  (`twilio_service.build_twiml`) since FL is a two-party consent state for
  call recording.

## Docs

`docs/design-notes.md` is the record of what has been changed and why — how the team data is put
together, front-end architecture decisions, accessibility choices, what is deliberately left alone,
and the traps that have burned past debugging sessions. Worth reading before touching team data or
`static/css/smackagram.css`.

Pointers it expands on:

- `services/ncaa_d1.py` — every NCAA Division I school (365) with the conference it plays each sport
  in: football, men's basketball, baseball. One pipe-separated row per school, so conference
  realignment is a text edit rather than a code change.
- `services/team_display.py` — builds the list served by `/api/teams/all` that feeds the site-wide
  team autocomplete. 1,205 teams across pro leagues, soccer and college.
- `services/chat_team_lists.py` — `CHAT_LEAGUES`, still the source of truth for Smack Chat rooms.
  Note it uses internal chat-room codes, which differ from the codes SportsDataIO sends.
- The site is password-gated except `/static/`, which is why an unauthenticated `curl` against a
  page returns `Authentication required.` instead of your change. Check a static asset instead.
- Bump the `?v=` number in `static/js/smackagram.js` whenever team data changes, or browsers keep
  serving the old list.
