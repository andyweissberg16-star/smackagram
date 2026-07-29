# Smackagram — design & data notes

A record of what was changed, why, and what is deliberately still open. Written so that anyone
picking this codebase up — including future-you — does not have to re-derive the reasoning or
repeat the mistakes.

Covers three rounds of work: a full design/accessibility audit (`8b698b3` → `53f434b`), error pages
and site-wide team search (`8b28384` → `06e6d6a`), and full NCAA Division I coverage (`51c2d72`).

---

## 1. Things that will mislead you if you don't know them

### The site is password-gated, and that breaks naive `curl`

`@app.before_request` enforces `SITE_PASSWORD` on **everything** except `/webhook/stripe`,
`/call-instructions/`, `/call-status/`, `/recording-ready/`, `/recording-done/`, `/static/` and
`/api/cron/`.

An unauthenticated request to a page or an API route returns `Authentication required.` — which
looks exactly like "my change isn't deployed" if you only grep for the string you expected.

This produced two separate wrong diagnoses ("Render is two commits behind", "nothing is deploying").
Both were false; both were built on curls the gate had bounced.

**The one command worth memorising.** `/static/` is exempt, so grep a static asset for a string that
only exists in the new build:

```bash
curl -s https://smackagram.com/static/js/smackagram.js | grep -o "teams/all?v=[0-9]"
```

To inspect a gated API response, open the URL in a browser where you're already signed in.

### HTTP caching: a `max-age` you already handed out cannot be taken back

The team list first shipped with `Cache-Control: max-age=3600`. Lowering it to 300 afterwards did
nothing for anyone who already had a copy — they stayed stale for the full original hour. Changing
the response header cannot retract a promise the browser already holds.

**Only changing the URL reliably works.** Hence `fetch('/api/teams/all?v=3')` in
`static/js/smackagram.js`. **Bump that number whenever the team data changes.**

What makes this work is an asymmetry worth understanding:

- `SEND_FILE_MAX_AGE_DEFAULT` is unset, so Flask serves `/static/*` with `Cache-Control: no-cache`
  plus an ETag. Browsers **must** revalidate before reusing — so a new `smackagram.js` reaches
  people on an ordinary reload.
- That new JS then requests a `?v=` URL nobody has ever cached.

So no user ever has to hard-reload. The one caveat: bumping `?v=` protects future loads, but someone
still holding the *previous* `?v=` response waits out its original max-age.

### Local development gotchas

- **`debug=False` caches Jinja templates.** Template edits won't appear until you restart. A fix has
  looked broken more than once when it was just a stale render.
- **Killing the dev server:** `pkill -f run.py` can match the invoking shell's own command line.
  Kill by scanning `/proc/*/cmdline` instead.
- **A stale server may already own the port** and will answer `curl` with *old* data while your new
  process silently exits. Check the served payload, not just the HTTP status.
- **The nav hamburger is now the first `<button>` in the DOM.** Any browser test doing
  `click("button")` hits the drawer toggle, not the form button. Use explicit IDs.

Local run:

```bash
export DATABASE_URL="sqlite:////tmp/smack.db" SECRET_KEY=dev BASE_URL="http://127.0.0.1:5001"
python3 -c "import app as A; A.app.run(host='127.0.0.1', port=5001, threaded=True)"
```

The app self-seeds admin accounts on import. Log in via
`POST /api/login {"email":"admin","password":"admin"}` — the field is **email**, value literally
`admin`. 2FA is bypassed for admins. Test fixtures: battle code `TESTBATTLE`, order reply_token
`TESTREPLYTOKEN`, conversation id 2, Smackcast recap share_token `TESTRECAP`.

---

## 2. Team data — how it is put together

Three files, in dependency order.

### `services/chat_team_lists.py` — `CHAT_LEAGUES`

The original list. Pro leagues and soccer, keyed by an **internal chat-room code**, storing the
mascot alone (`"NYY": "Yankees"`). Still the source of truth for Smack Chat league rooms
(`app.py`, the `/api/chat/teams` route) and for pro teams in search.

Its college section is no longer used for search — it only ever had the four power football
conferences and a hand-picked 45-school basketball list.

### `services/ncaa_d1.py` — every Division I school

Added in `51c2d72`. One pipe-separated row per school:

```
key | school shown | mascot | football conf | FBS/FCS | m. hoops conf | baseball conf
```

An empty field means the school doesn't play that sport. Parsed once at import into `SCHOOLS`,
`FOOTBALL_FBS`, `FOOTBALL_FCS`, `BASKETBALL`, `BASEBALL` and `FEED_CODES`.

It's a text block rather than nested dicts on purpose: this file has to survive being pasted into a
terminal, and 365 flat rows survive that far better than 1,500 lines of Python punctuation.

**Where the data came from:**

| Sport | Source | Count |
|---|---|---|
| Men's basketball | `ncaa.com/standings/basketball-men/d1` | 365 schools, 31 conferences |
| Football FBS | `ncaa.com/standings/football/fbs` | 136 |
| Football FCS | `ncaa.com/standings/football/fcs` | 128 |
| Baseball | ncsasports.org, cross-checked against Warren Nolan's 2026 conference standings | 307 across 30 conferences |
| Mascots + canonical names | Per-school verification against school athletics sites | 365 |

**The NCAA baseball standings page is empty out of season.** In July it returns nothing at all —
that's why baseball came from elsewhere. Don't conclude the page is broken.

**Adding or moving a school:** edit the one row. Conference realignment is a text edit, not a code
change. If the school is new, also add a `_FEED_ROWS` line if you know the code SportsDataIO uses
for it — without one it's searchable but can't be matched to a live game.

**Conference genuinely varies by sport.** This is the most common thing to "fix" by mistake:

- Hawaii — Mountain West football, **Big West** baseball
- UMass — MAC football, **MAC** baseball (moved from the Atlantic 10 in 2025)
- Army — AAC football, **Patriot League** everything else
- Cal Poly — Big Sky football, **Big West** hoops and baseball
- Notre Dame — **independent** in football, ACC in everything else
- Oregon State — played 2026 baseball as an independent

**75 of the 365 schools sponsor no D1 baseball** (Wisconsin, Colorado, Syracuse, SMU, Temple,
Marquette and others). They simply have no baseball row. That's correct, not missing data.

### `services/team_display.py` — what search actually sees

Turns the two sources above into the list served by `/api/teams/all`. Pro leagues come from
`CHAT_LEAGUES`; college comes from `ncaa_d1`. A school appears **once per sport it plays**, because
"Florida Gators / SEC Football" and "Florida Gators / SEC Baseball" are different things to trash
talk about.

Design decisions worth keeping:

- **Names must carry the city.** `CHAT_LEAGUES` stores mascot-only for pro and school-only for
  college — neither is findable by typing "new", and "Florida" says nothing about which sport.
  `_derive_pro()` recovers the city from the alias table.
- **Take the longest alias that *ends with* the current mascot.** Taking the shortest gave
  "NY Yankees"; taking the longest of all aliases resurrected a stale "Utah Hockey Club" entry. The
  endswith constraint fixes both at once.
- **Only consult college alias tables for college leagues.** Codes collide across leagues — La
  Liga's Alavés is `ALA`, the same code as Alabama, so searching "crimson" was returning Deportivo
  Alavés.
- **`_trim()` drops aliases already contained in the name, short name or code.** The client's
  `score()` already has a bare `name.indexOf(q) > -1` fallback, so those aliases could only ever
  duplicate a match it would make anyway. This cut 3,742 aliases to 312 and took ~23% off the
  payload. What survives is genuinely different phrasing: "vols", "terps", "niners",
  "runnin rebels", "southern california".

**Payload:** 1,205 teams is 177 KB of JSON, which gzips to about 18 KB.

### ⚠️ Two code schemes exist for the same schools

This is the sharpest edge in the whole system.

- `CHAT_LEAGUES` uses **internal chat-room codes** — Auburn is `AUB`, Florida is `FLA`
- `TEAM_ALIASES` / `DISPLAY_NAMES` use the codes **SportsDataIO actually sends** — `AUBRN`, `FL`

They line up 100% for NFL / NBA / MLB / NHL. They diverge for **61 of 116** college teams.

`sports_service.py` calls `matches_search(sport, home_code, query)` with `home_code` taken straight
from the feed's `HomeTeam` field. So a display name registered under a chat-room code is invisible
to the game lookup. That was a real production bug: picking "Auburn Tigers" from search found no
games, because the name had been filed under `AUB` while the feed says `AUBRN`.

`register_aliases()` in `team_display.py` now writes **only** to codes that already exist in the
feed's alias table, and skips anything else rather than inventing a bucket. If you extend this, keep
that rule.

### Known limits of the team data

- **There is no college baseball feed.** `SPORT_PATHS` in `sports_service.py` has `cfb`, `cbb` and
  `cwbb` only. Baseball teams are searchable everywhere, but Locked & Loaded can never find a live
  baseball game. Its sport tabs are hardcoded and have no baseball tab, so the `ncaabase` league key
  never reaches `sports_service` — safe, not a latent crash.
- **Only 87 football and 85 basketball schools have a known SportsDataIO code.** Everything else
  falls back to `matches_search`'s plain substring test against whatever code the feed sends.
- **Women's basketball is still the old 24-school list** from `CHAT_LEAGUES`. Its badges borrow the
  men's conference so they read "SEC Women's Basketball" rather than "NCAAWB", but the roster hasn't
  been expanded. Building it out is the same pattern as the other three sports.
- **`"utah hockey club"` is a stale alias** in `services/team_aliases.py` — the team is now the Utah
  Mammoth. Harmless today because `_derive_pro` requires an alias to end with the current mascot,
  but it will mislead whoever reads that table next.

---

## 3. Front-end architecture

### `static/css/smackagram.css`

All site-wide chrome: brand variables, nav, mobile drawer, focus rings, type scale, loading spinner,
reduced-motion rules, invalid-field styling, the team autocomplete.

Linked from every template **before** its inline `<style>`, so page-level rules still win by source
order. When it was introduced, an inline block was only removed if it was byte-identical to the
shared version — anything different stayed inline and kept overriding. That's what made a 108-rule
deduplication a visual no-op.

### `static/js/smackagram.js`

Loaded from `_nav.html`, so every page gets it. Holds `smkInvalid()` (field-level error marking) and
the team autocomplete, including the `?v=` cache-buster described above.

One subtlety: selecting a suggestion used to reopen the dropdown, because `choose()` dispatches an
`input` event to notify page code and that retriggered the search. There's a `suppress` flag around
the dispatch — don't remove it.

### Images

`static/img/` holds 780w / 1560w / 1983w WebP with JPEG fallbacks (the heroes are opaque, so PNG
fallbacks were 8× larger), plus a 204px logo with a PNG fallback. Served via `<picture>` + `srcset`
with explicit `width`/`height` to prevent layout shift.

This took all 19 pages from **60.99 MB to 2.98 MB** over the wire. `logo.png` alone was 1536×1024 /
2.1 MB, displayed at 51×34 px, on every page.

When adding a `height` attribute, check the template's inline style has `height:auto` — omitting it
distorted the contact header to 479px tall.

### Accessibility decisions

- **Contrast.** `--flare-text:#FF3B50` (5.55:1) is for text under 18px; `--flare` is untouched for
  buttons and display type, so the brand look is unchanged. Use the right one.
- **Battle-room team colours** go through `readableColor()`, which keeps the hue and raises
  lightness until AA passes — computed at render time, so it works for any team. Eagles went 1.85 →
  4.74, Cowboys 1.66 → 4.85.
- **Focus rings.** `html body :focus-visible` at specificity (0,1,2) beats `input:focus{outline:none}`
  at (0,1,1); an `:is(...)` variant at (0,2,2) beats class-level suppressors. No `!important`
  anywhere — please keep it that way.
- **Loading spinners** are pure CSS keyed on `:disabled`. That's only safe because `disabled` is
  used exclusively for in-flight operations here — never for validation, never set in markup at
  load. If that ever changes, this breaks. Escape hatch: `.no-spinner`.
- **Reduced motion.** Three animations could not use the usual "finish instantly" pattern, because
  their end state isn't their resting state: the ticker ends `translateX(-50%)` (frozen half
  off-screen), and the round-result popup and battle countdown both end at `opacity:0` — the
  animation *is* how they become visible. A reduced-motion user would never have seen who won a
  round. All three are handled explicitly.
- **The ticker pause button exists to satisfy WCAG 2.2.2**, which applies to everyone — not only
  users who set the OS reduced-motion preference. Don't remove it as redundant.
- **Error pages.** `templates/500.html` deliberately omits `_nav.html`, and the handler has a
  plain-text fallback, because the `current_user` context processor hits the database on every
  render — rendering the branded page during a database outage would raise a second exception
  inside the error handler.

---

## 4. Still open

Needs a person, not a code change:

- **Real iOS Safari check** of `100dvh` and the drawer's touch/scroll-lock behaviour. Chromium
  cannot reproduce Safari's address-bar behaviour.
- **`static/support-header.jpg` needs a ~2400px re-export.** It's 1200px wide and displayed at
  1352px on desktop; it can't be fixed from the existing file.
- **Confirm four hand-filled WNBA names** — Connecticut Sun, Golden State Valkyries, Phoenix Mercury,
  Washington Mystics had no derivable alias and were typed by hand into `_EXPLICIT`.

Known gaps, deliberately left:

- Women's basketball roster (see above).
- Per-feature social share cards, blocked on hero art with feature names baked into the image.
- The live battle room under real two-player load — fixtures are static, so the momentum bar and
  typing indicators mid-battle are untested.
- The ticker pause button is 44×40; a 4px bump would make it a full 44×44.

Deliberately **not** changed, so nobody "fixes" them again:

- **Empty states** are already handled everywhere with human-written copy. Minor inconsistency in
  class names and font size, nothing broken.
- **10 sub-44px tap targets** remain on purpose: 5 are inline links inside sentences (WCAG 2.5.8
  exempts these), 4 are checkboxes inside label rows that are already ≥44px, and 1 is a 16px info
  "i" that would break its row if stretched.
- **`h1` sizes were not collapsed to one value** — three tiers is deliberate hierarchy.

---

## 5. Verification practices that actually caught bugs

- **Establish a noise floor before pixel-diffing.** Render the same code twice and diff it first.
  The battle room varies ~8,000 px run to run and the home ticker ~5,000 px, all from animation.
  Without that baseline you will chase phantom regressions.
- **`scrollWidth` 778 vs `docWidth` 768 at tablet is the scrollbar**, not overflow.
- **Test interaction with real input.** Calling `.focus()` from a script does not trigger
  `:focus-visible` the way pressing Tab does — the first focus audit reported the wrong number
  because of this. Drive the real autocomplete with keystrokes rather than reasoning about the
  scoring function.
- **Check the state a page loads in, not just the state you're changing.** The loading-spinner rule
  would have made conversation.html's "Audio unavailable" buttons spin forever; only a sweep of
  every page at rest caught it.
- **Join on a controlled vocabulary and assert zero unmatched rows.** Every sports data source names
  schools differently ("Florida St." / "Florida State" / "Florida State University"). Fixing NCAA.com's
  abbreviation as the key, and making every source map back to that exact string, is what let the
  football, basketball and baseball tables join with zero misses.
- **Boot a clean clone to rule out the code.** When a deploy looks broken, `git clone` the pushed
  commit and import the app. One command distinguishes "my code is bad" from "the deploy pipeline
  didn't run", and it has redirected an entire investigation.
- **Verify against `origin`, not memory.** `git fetch && git log origin/main` settles whether a push
  actually landed.
