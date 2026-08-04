"""
Smackcast — weekly fantasy football recap generation. Pulls real
matchup data (via sleeper_service for now; espn_service/yahoo_service
follow the same shape once built) and turns it into a savage,
Smackagram-toned script covering every matchup in the league, sized to
the league's team count.
"""
import os
import tempfile
import re
import json
import anthropic
import requests
from services import smackology

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_HARD_LIMITS = """Hard limits — never cross these:
- Roast the TEAM PERFORMANCE (the score, the blowout, the bad bench
  decision, the specific players who did or didn't produce) — never
  invent personal details about the actual human behind a team name
  beyond what's in the data you were given.
- No slurs of any kind, no hate speech, no content targeting race,
  religion, gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- Only use the scores and team names you were actually given — never
  invent a stat, score, or player performance that wasn't provided.
- Output ONLY the script to be read aloud. No preamble, no labels, no
  stage directions, no markdown."""


# MEASURED, not assumed. The original code assumed 150 words/minute, which
# is a conversational-reading pace. Smacky's delivery is slower than that:
# a 600-word target came back as 5 minutes 12 seconds of audio, which works
# out to ~115 wpm. Every target was therefore ~30% optimistic.
#
# This is the single knob for recap runtime. If audio still lands long,
# lower this number - don't touch the per-band minutes, which express the
# product decision. Sound effects and the 200ms pauses around them add a
# few seconds on top, so treat this as a floor rather than exact.
SPOKEN_WORDS_PER_MINUTE = 115


def _target_word_count(team_count: int) -> int:
    """
    Scales the target script length with league size — an 8-team league
    has less ground to cover than a 14-team one, so the recap runtime
    scales roughly linearly between ~3 minutes (8 teams) and ~5 minutes
    (14+ teams), at a natural spoken pace of ~150 words/minute.
    """
    if team_count <= 9:
        minutes = 3.0
    elif team_count <= 12:
        minutes = 4.0
    else:
        minutes = 6.0
    return round(minutes * SPOKEN_WORDS_PER_MINUTE)


_SPORT_LABELS = {"nfl": "fantasy football", "nba": "fantasy basketball", "mlb": "fantasy baseball"}


_REACTION_TYPES = ("boo", "laugh", "cheer", "gasp", "trombone", "flourish",
                   "aww", "crickets", "boom", "ring", "none")


def league_colour(sub) -> str:
    """
    Everything that makes one league different from every other league.

    A box score is identical everywhere. "You lost by forty" is a joke that
    works in every league in the country, which is another way of saying it
    lands in none of them. "You lost by forty to the man who sits two desks
    away" only works in one - and that is the one somebody screenshots.

    All fields optional. A commissioner who filled in nothing gets a normal
    recap; there is simply less to work with.
    """
    if sub is None:
        return ""

    def g(attr):
        v = getattr(sub, attr, None)
        return v.strip() if isinstance(v, str) and v.strip() else None

    bits = []

    known = g("how_they_know_each_other")
    if known:
        bits.append(f"How they know each other: {known}")
    age = g("league_age")
    if age:
        bits.append(f"The league has been running: {age}")

    buy_in = g("buy_in")
    if buy_in:
        bits.append(f"Buy-in: {buy_in}")

    trophy = g("trophy")
    if trophy:
        bits.append(f"The trophy: {trophy}")
    punishment = g("last_place_punishment")
    if punishment:
        bits.append(f"What last place has to do: {punishment}")

    for attr, label in [
        ("commissioner_name", "Commissioner"),
        ("reigning_champion", "Won it last season"),
        ("runner_up", "Came second last season"),
        ("perennial_winner", "Wins constantly"),
        ("perennial_loser", "Has never won"),
        ("biggest_talker", "Talks the most"),
        ("most_absent", "Barely pays attention"),
        ("newest_member", "New this season"),
        ("worst_at_lineups", "Always leaves points on the bench"),
    ]:
        v = g(attr)
        if v:
            bits.append(f"{label}: {v}")

    chat = g("group_chat")
    if chat:
        bits.append(f"They all talk in a group chat on: {chat}")

    for attr, label in [("running_jokes", "Running jokes"),
                        ("rivalries", "Rivalries"),
                        ("anything_else", "Other")]:
        v = g(attr)
        if v:
            bits.append(f"{label}: {v}")

    if not bits:
        return ""

    return (
        "\n\nWHAT MAKES THIS LEAGUE THIS LEAGUE\n\n  "
        + "\n  ".join(bits)
        + "\n\n"
        "  USE THIS. It is the entire difference between a recap that could "
        "belong to anybody and one that could only belong to them. Work at "
        "least two of these details in.\n\n"
        "  BUT AIM IT AT THE FANTASY, NOT THE PERSON. These are real people "
        "and a commissioner wrote this about their friends. 'Kyle started a "
        "man on bye, and Kyle is the commissioner' is the joke. Anything "
        "about how Kyle looks, what Kyle earns, or Kyle's marriage is not, "
        "however it was phrased in the form.\n\n"
        "  INVENT NOTHING. If it is not written above, it did not happen. "
        "You do not know that the trophy is ugly unless somebody said so, "
        "and a detail you made up about a real person is the one thing here "
        "that could genuinely upset somebody.\n\n"
        "  THE REIGNING CHAMPION IS THE BEST TARGET IN THE LEAGUE. Last "
        "season's winner losing this week is worth more than anybody else "
        "losing, and the runner-up is the person most likely to enjoy it. "
        "If either shows up in the results, lead with them.\n\n"
        "  MONEY CHANGES THE TONE. A free league is a laugh. A league with "
        "real money in it means the man who lost on a bad start actually "
        "minds, and that is funnier - lean into what it cost him.\n"
    )


def weekly_notes_block(note, past_notes=None) -> str:
    """
    What the commissioner said happened this week, plus older weeks for
    callbacks.

    This is the material a box score cannot give you. A score says somebody
    lost; a note says he lost by half a point to a man who started a player
    on a bye, and that is the difference between a recap and a roast.
    """
    lines = []

    if note is not None:
        for attr, label in [
            ("big_trade", "A trade people are still talking about"),
            ("brutal_loss", "A loss somebody has not recovered from"),
            ("loudest_in_chat", "Loudest in the group chat"),
            ("anything_else", "Also"),
        ]:
            v = getattr(note, attr, None)
            if v and v.strip():
                lines.append(f"{label}: {v.strip()}")

    older = []
    for p in (past_notes or []):
        bits = [getattr(p, a, None) for a in
                ("big_trade", "brutal_loss", "loudest_in_chat", "anything_else")]
        bits = [b.strip() for b in bits if b and b.strip()]
        if bits:
            older.append(f"Week {p.week_number}: " + " / ".join(bits))

    if not lines and not older:
        return ""

    out = "\n\nWHAT ACTUALLY HAPPENED THIS WEEK\n\n"
    if lines:
        out += "  " + "\n  ".join(lines) + "\n\n"
    else:
        out += "  Nothing was submitted for this week.\n\n"

    if older:
        out += "  EARLIER IN THE SEASON\n  " + "\n  ".join(older[:6]) + "\n\n"
        out += (
            "  Those older weeks are for CALLBACKS. 'Three weeks ago somebody "
            "told me Dave made a terrible trade, and Dave has now lost four in "
            "a row' is the single best thing you can do with them - it makes "
            "the show sound like it has been paying attention all season, "
            "which nothing else achieves.\n\n")

    out += (
        "  LEAD WITH THIS WEEK'S ITEMS where they fit the results. Somebody "
        "took the trouble to write them down, which means they matter to the "
        "league far more than any scoreline does.\n\n"
        "  Same rules as everything else: aim at the FANTASY, invent nothing, "
        "and if it was not written above it did not happen.\n"
    )
    return out


def generate_weekly_recap_script(league_name: str, week: int, matchups: list, team_count: int, sport: str = "nfl", subscription=None, note=None, past_notes=None) -> dict:
    """
    matchups: list of {team_a, team_a_score, team_b, team_b_score}
    Returns {"intro": str, "segments": [{"text": str, "reaction": str}],
    "outro": str, "best_line": str, "full_text": str}. Segments are
    per-matchup, each tagged with a reaction type (boo/laugh/cheer/
    gasp/none) — this is what lets assemble_recap_audio() splice in the
    right sound effect after each one, based on what the AI itself
    judged that matchup's tone to be while writing about it, rather
    than a hardcoded rule. full_text is intro+segments+outro joined
    together, for display/storage purposes (the public recap page, etc)
    — the audio assembly step uses the segmented structure directly
    instead, since that's what it needs for splicing in sound effects.
    """
    target_words = _target_word_count(team_count)
    sport_label = _SPORT_LABELS.get(sport, "fantasy football")

    # A per-piece budget, because a single total proved too abstract to hold
    # to once the prompt grew - real output ran 7+ minutes on a 12-team
    # league against a 650-word target.
    segment_count = max(1, len(matchups))
    intro_words, outro_words = 55, 45
    per_segment_words = max(40, round((target_words - intro_words - outro_words) / segment_count))
    target_minutes = round(target_words / SPOKEN_WORDS_PER_MINUTE, 1)

    matchup_lines = []
    for m in matchups:
        winner = m["team_a"] if m["team_a_score"] > m["team_b_score"] else m["team_b"]
        margin = abs(m["team_a_score"] - m["team_b_score"])
        line = (
            f"{m['team_a']} ({m['team_a_score']:.1f}) vs {m['team_b']} ({m['team_b_score']:.1f}) "
            f"— {winner} won by {margin:.1f}"
        )
        # Real player detail when the platform gave us any. Absent for
        # leagues/platforms where the roster fetch came back empty, so the
        # prompt has to cope with some matchups having it and some not.
        for side, label in ((m.get("team_a_standouts"), m["team_a"]),
                            (m.get("team_b_standouts"), m["team_b"])):
            if not side:
                continue
            bits = []
            if side.get("top"):
                bits.append(f"best starter {side['top']['name']} {side['top']['points']:.1f}")
            if side.get("bust"):
                bits.append(f"worst starter {side['bust']['name']} {side['bust']['points']:.1f}")
            if bits:
                line += f"\n    {label} — " + "; ".join(bits)
        matchup_lines.append(line)
    matchups_block = "\n".join(matchup_lines)

    system_prompt = f"""You write the weekly Smackcast — a savage, heavily
profane {sport_label} recap read aloud to an entire league. This is
Smackagram's established voice: real cursing throughout, genuinely
brutal, but funny and specific rather than mean for its own sake.

Structure your response as an intro, one segment PER MATCHUP given to
you (every single one, not just the most dramatic), and an outro. For
EACH segment, also tag it with the single reaction that best fits the
tone of what you just wrote about that matchup — this tag controls a
real sound effect that gets spliced in right after your words, so pick
whichever one actually matches:
- "boo" — a blowout loss, a genuinely bad performance the crowd would
  be angry about
- "laugh" — a genuinely funny/savage line you wrote landed hard
- "cheer" — an impressive win, a nail-biter finish — the OUTCOME itself
  is exciting
- "gasp" — a shocking upset, a surprising stat
- "trombone" — a comedic, pathetic, "well that's just sad" moment —
  an embarrassing stat, a terrible bench decision, a low/losing score
  that's more sad-funny than blowout-bad. Different feel from "boo":
  boo is the crowd genuinely mad, trombone is a "womp womp" gag
- "flourish" — a rising brass sting used to punctuate a particularly
  sharp, well-delivered line or a "mic drop" stat reveal — this is
  about how SHARP the line itself landed, not about the matchup's
  outcome the way "cheer" is
- "aww" — a sad, sympathetic crowd sound — genuine disappointment or
  bad luck, NOT anger like "boo" and not comedic like "trombone." Use
  this for a close, unlucky loss or a rough break that deserves
  sympathy rather than mockery or anger
- "none" — nothing about this matchup calls for a sound effect

IMPORTANT — "none" should be your DEFAULT, not just one option among
several. The writing itself is already funny; sound effects are
support to keep a listener engaged, not something to lean on for every
single matchup. Reserve an actual reaction tag for the moments that
genuinely earn it — the biggest blowout, the single funniest line, the
one real gut-punch loss — not routinely for every matchup in the
league. As a rough guide: in a typical week, only about 1 in every 3-4
matchups should get an actual sound effect — the rest should be
"none." If you're tagging most segments with something other than
"none," you're overdoing it.

CRITICAL — this gets read aloud by text-to-speech, not displayed as
text: every single time you mention a number tied to scoring — a
team's total, a margin of victory, a point differential, anything —
you MUST say the word "points" (or "pts" spoken as "points") right
after it, never just state a bare number on its own. Say "96.2
points," never just "96.2"; say "won by 14.7 points," never just "won
by 14.7." A listener hearing a random number with zero context has no
idea what it means, since they can't see parenthetical score data the
way a reader could. This applies throughout, every time, not just the
first mention.

{smackology.render(4)}

LENGTH — a hard constraint, not a suggestion. This instruction was
missing entirely and scripts ran nearly double their intended runtime.
Total budget: {target_words} words across intro, ALL segments and outro
combined, which is about {target_minutes} minutes spoken.

Because a single total is easy to lose track of, budget per piece:
  intro: about {intro_words} words
  EACH matchup segment: about {per_segment_words} words
  outro: about {outro_words} words
There are {segment_count} matchups this week. Every segment gets roughly
the same share — don't spend 200 words on the blowout and 40 on the rest.

The vocabulary and smackology sections above are a PALETTE, not a
checklist, and you do not need to demonstrate all of it. Three sharp
words inside {per_segment_words} words beats cramming in ten and running
to double the length. If you're over budget, cut the coinages first — the
scores and player callouts are the content, the invented language is
seasoning.

REAL PLAYERS — some matchups come with a best and worst starter named,
with their actual fantasy points. When they do, use them every so often:
a named player is far more cutting than another abstract team total.
Roughly one matchup in three is about right — leaning on it every
segment turns the recap into a stat sheet read aloud.

The bust is usually the better material. A starter who put up 2.1 points
is the whole joke; you don't have to build one. A monster game from the
top starter works too, especially when the team lost anyway — starting a
30-point player and still losing is its own kind of pain.

Absolute rule: you may ONLY name a player who was explicitly given to
you above, and you may ONLY cite the exact points listed next to their
name. Do not mention any other real player, do not reference a real NFL,
NBA or MLB game, injury, headline or news story, and do not invent or
round a stat. You have no information about the real season beyond these
numbers. If a matchup lists no players, write it from the totals and say
nothing about players at all.

Roast the PERFORMANCE, not the human — "2.1 points from your starting
running back is a war crime" is the job. Real players are working
professionals, so keep it about the box score.

{_HARD_LIMITS}

After writing everything, pull out the single most quotable, savage
line from anywhere in it verbatim (word-for-word as it appears) — this
gets used on its own as a shareable image, so it needs to land
completely out of context, not rely on the rest of the recap to make
sense. Because of that, avoid picking a line whose punch depends on a
coined word the reader hasn't had explained — "that's a Smackquake"
means nothing on a graphic by itself. Either pick a line that works
cold, or pick one where the coinage is explained inside that same line.

Respond with ONLY a JSON object, nothing else:
{{"intro": "...", "segments": [{{"text": "...", "reaction": "boo|laugh|cheer|gasp|trombone|flourish|aww|none"}}], "outro": "...", "best_line": "..."}}"""

    user_content = (
        f"League: {league_name}\n"
        f"Week: {week}\n\n"
        f"This week's matchups:\n{matchups_block}\n"
        + league_colour(subscription)
        + weekly_notes_block(note, past_notes)
        + f"\nWrite the recap."
    )

    last_error = None
    for attempt in range(2):
        try:
            message = _get_client().messages.create(
                model="claude-sonnet-4-6",
                # Raised from 1800. The prompt now asks for considerably
                # more (score registers, losing vocabulary, smackology,
                # named players), and a truncated response is invalid JSON,
                # which silently burns the retry and doubles the wait.
                max_tokens=3000,
                # Without this the SDK waits up to 600s. Gunicorn kills the
                # worker at 180s, so a slow call became a request that never
                # returned at all rather than a clean error.
                timeout=90.0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            segments = result.get("segments") or []
            if result.get("intro") and segments:
                # Sanitize reaction tags — an unrecognized value falls back
                # to "none" rather than crashing the whole pipeline over one
                # bad tag on one segment.
                for seg in segments:
                    if seg.get("reaction") not in _REACTION_TYPES:
                        seg["reaction"] = "none"

                full_text = " ".join(
                    [result["intro"]] + [seg["text"] for seg in segments] + [result.get("outro") or ""]
                ).strip()

                return {
                    "intro": result["intro"],
                    "segments": segments,
                    "outro": result.get("outro") or "",
                    "best_line": result.get("best_line") or "",
                    "full_text": full_text,
                }
        except Exception as e:
            last_error = e
            print(f"[smackcast] script generation attempt {attempt + 1} failed: {e}")

    # Both attempts failed to produce valid structured output — this is
    # a genuine failure the caller needs to know about, not something to
    # paper over with fallback text the way the battle recap does,
    # since there's no sensible generic fallback for an entire league's
    # weekly recap.
    raise RuntimeError(f"Failed to generate Smackcast script after 2 attempts: {last_error}")

def deliver_to_discord(webhook_url: str, league_name: str, week: int, audio_url: str, share_url: str, meme_url: str = None) -> bool:
    """
    Posts a message into a Discord channel via a webhook the league
    owner set up themselves (Discord doesn't let third parties post
    into a server without the owner explicitly creating a webhook for
    that specific channel). Returns True on success, False on failure —
    delivery failures shouldn't crash the whole weekly generation run
    for every other league. Includes the meme as a rich embed image
    when available, which displays inline in Discord rather than as a
    plain clickable link.
    """
    try:
        payload = {
            "content": (
                f"🔥 **Smackcast — {league_name}, Week {week}** 🔥\n"
                f"Your league just got roasted. Listen here: {audio_url}\n"
                f"Full recap page: {share_url}"
            )
        }
        if meme_url:
            payload["embeds"] = [{"image": {"url": meme_url}}]
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"[smackcast] Discord delivery failed: {e}")
        return False


def deliver_to_groupme(bot_id: str, league_name: str, week: int, share_url: str) -> bool:
    """
    Posts into a GroupMe chat via a bot the league owner registered
    themselves at dev.groupme.com. GroupMe bots can only post plain
    text (no rich embeds like Discord), so this leans on the share link
    for the audio player rather than linking the raw file directly.
    """
    try:
        resp = requests.post(
            "https://api.groupme.com/v3/bots/post",
            json={
                "bot_id": bot_id,
                "text": f"🔥 Smackcast — {league_name}, Week {week} 🔥 Your league just got roasted: {share_url}",
            },
            timeout=10,
        )
        return resp.status_code in (200, 202)
    except Exception as e:
        print(f"[smackcast] GroupMe delivery failed: {e}")
        return False


def _wrap_text(draw, text, font, max_width):
    """Manual word-wrap since Pillow doesn't do this automatically —
    greedily packs words onto each line until adding the next one
    would exceed max_width."""
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        candidate = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current_line:
            current_line = candidate
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def generate_meme_image(best_line: str, league_name: str, week: int) -> str:
    """
    Turns the week's single best/most savage line into a shareable,
    Smackagram-branded square image (1080x1080 — works fine for
    Discord/GroupMe embeds and any social sharing). Returns the
    uploaded S3 URL. Fonts are bundled directly in static/fonts/ rather
    than relying on whatever happens to be installed on the deployment
    server, since that's not guaranteed to include Anton at all.
    """
    from PIL import Image, ImageDraw, ImageFont
    import boto3
    import uuid

    INK = (13, 13, 13)
    CHALK = (245, 245, 243)
    GOLD = (255, 212, 0)
    FLARE = (232, 20, 44)

    size = 1080
    img = Image.new("RGB", (size, size), INK)
    draw = ImageDraw.Draw(img)

    fonts_dir = os.path.join(os.path.dirname(__file__), "..", "static", "fonts")
    anton_path = os.path.join(fonts_dir, "Anton-Regular.ttf")
    dejavu_path = os.path.join(fonts_dir, "DejaVuSans-Bold.ttf")

    # Accent bar across the top, same gold-to-red brand pairing used
    # throughout the rest of the site.
    draw.rectangle([(0, 0), (size, 14)], fill=GOLD)
    draw.rectangle([(0, 14), (size, 20)], fill=FLARE)

    label_font = ImageFont.truetype(dejavu_path, 32)
    draw.text((size / 2, 90), "SMACKCAST", font=label_font, fill=FLARE, anchor="mm")

    # Main quote — starts large and steps down in size until it
    # actually fits within the available height, since a short savage
    # one-liner and a longer one need very different type sizes to
    # both look intentional rather than either tiny or overflowing.
    max_text_width = size - 160
    max_text_height = 620
    quote_font_size = 90
    quote_lines = []
    while quote_font_size > 36:
        quote_font = ImageFont.truetype(anton_path, quote_font_size)
        quote_lines = _wrap_text(draw, f'"{best_line}"', quote_font, max_text_width)
        line_height = quote_font_size * 1.25
        if line_height * len(quote_lines) <= max_text_height:
            break
        quote_font_size -= 4

    quote_font = ImageFont.truetype(anton_path, quote_font_size)
    line_height = quote_font_size * 1.25
    total_height = line_height * len(quote_lines)
    start_y = (size - total_height) / 2 + 40

    for i, line in enumerate(quote_lines):
        draw.text((size / 2, start_y + i * line_height), line, font=quote_font, fill=CHALK, anchor="mm")

    footer_font = ImageFont.truetype(dejavu_path, 26)
    draw.text((size / 2, size - 70), f"{league_name} — Week {week}", font=footer_font, fill=(154, 154, 150), anchor="mm")

    draw.rectangle([(0, size - 20), (size, size - 14)], fill=FLARE)
    draw.rectangle([(0, size - 14), (size, size)], fill=GOLD)

    buffer_path = f"/tmp/{uuid.uuid4()}.png"
    img.save(buffer_path, "PNG")

    s3_bucket = os.environ["AUDIO_S3_BUCKET"]
    s3_region = os.environ.get("AWS_REGION", "us-east-1")
    # Reusing the same "tts/" path the confirmed-working audio uploads
    # use, rather than a separate folder — the bucket's public-read
    # access is almost certainly scoped to this specific path via a
    # bucket policy, and a separate smackcast-memes/ folder wouldn't be
    # covered by that same policy, which is exactly what caused the
    # meme images to upload successfully but return a broken image icon
    # (no public read access) when the browser tried to load them.
    from datetime import datetime as _dt
    filename = ("memes/" + _dt.now().strftime("%Y-%m-%d")
                + f"-{uuid.uuid4().hex[:6]}.png")
    s3 = boto3.client("s3", region_name=s3_region)
    with open(buffer_path, "rb") as f:
        s3.put_object(Bucket=s3_bucket, Key=filename, Body=f.read(), ContentType="image/png")
    os.remove(buffer_path)

    return f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"


_SAMPLE_TEAM_NAMES = [
    "Gridiron Ghosts", "Waiver Wire Warriors", "Fumble Bunch", "Bench Press Kings",
    "The Injured Reserve", "Sunday Scaries", "Trade Deadline Villains", "Zero Dark Thirty",
    "Blowout Brigade", "Last Place Legends", "The Comeback Kids", "Championship Dreams",
    "Point Differential", "The Bye Week Crew", "Draft Day Disasters", "Undefeated Underdogs",
    "Playoff Bound", "Streak Breakers", "The Sleeper Picks", "Overtime Heroes",
]


# Deliberately awkward names, for exercising the read-aloud handling. Real
# fantasy leagues are full of these and each one probes a different rule:
_TRICKY_TEAM_NAMES = [
    "topdogdaddypants",          # real words, no spaces - IS sayable, should be said in full and mocked
    "thewaiverwirekings",        # same, longer
    "THEREALCHAMPS",             # long caps run - sanitizer title-cases so it isn't spelled out
    "xXx_L33T_xXx",              # leetspeak and symbols - genuinely unsayable, should be nicknamed
    "Ftghjklmn United",          # no vowel structure - unsayable
    "🔥🔥 Fire Squad 🔥",          # emoji - sanitizer strips them, the words survive
    "Saquon The Barbarian",      # player-name pun - perfectly sayable, good material
    "2 Chainz 2 Furious",        # leading digit - reads fine, tests number handling mid-name
    "AAAAAAAAA",                 # caps run with no word structure at all
    "Ctrl+Alt+Defeat",           # symbols mid-name - engines may read "plus" aloud
    "iiiiiiii",                  # repeated single letter, lowercase
    "Da 12th Man",               # ordinal inside a name
    "🏈🏈🏈",                      # emoji ONLY - nothing left after sanitizing, needs a nickname
    "Mr. Fantasy Pants Jr.",     # periods mid-name - abbreviation handling
]


def generate_sample_matchups(sport: str, team_count: int, stress: bool = False) -> list:
    """
    Realistic-but-entirely-fake matchup data for testing the generation
    pipeline without needing a real league or touching any real
    person's actual data. Score ranges are rough approximations per
    sport (points-format weekly totals), not meant to be precise —
    good enough to give the script generator something plausible to
    react to.
    """
    import random

    score_ranges = {
        "nfl": (55, 165),
        "nba": (480, 920),
        "mlb": (90, 260),
    }
    low, high = score_ranges.get(sport, (55, 165))

    names = random.sample(_SAMPLE_TEAM_NAMES, min(team_count, len(_SAMPLE_TEAM_NAMES)))
    while len(names) < team_count:
        names.append(f"Team {len(names) + 1}")

    # Swap two entries for deliberately awkward names. Two rather than all of
    # them on purpose: a generation needs some ordinary names alongside, so we
    # can see both that the tricky ones are handled AND that Smacky doesn't
    # start refusing perfectly sayable names now that he has the option.
    # stress=True replaces EVERY name with an awkward one, for deliberately
    # hammering the read-aloud handling. Default is two, which is closer to a
    # real league and also checks the opposite failure - that Smacky doesn't
    # start refusing ordinary names now that he can.
    if stress:
        pool = list(_TRICKY_TEAM_NAMES)
        random.shuffle(pool)
        for i in range(len(names)):
            names[i] = pool[i % len(pool)]
    else:
        for t in random.sample(_TRICKY_TEAM_NAMES, min(2, len(names))):
            names[random.randrange(len(names))] = t

    # Obviously-fictional player names. Deliberately NOT real players -
    # the test page runs the real pipeline, and inventing stat lines for
    # actual professionals is exactly what the prompt forbids in
    # production. Fake names keep the preview honest.
    fake_players = {
        "nfl": ["Dex Hollaway (QB)", "Ronnie Stackhouse (RB)", "Trey Milbourne (WR)",
                "Cal Vensetti (TE)", "Duke Farrady (RB)", "Ozzie Brantwood (WR)",
                "Rube Castellan (QB)", "Miles Trepper (K)"],
        "nba": ["Jace Kimbrough", "Ade Fontanel", "Rudy Vashenko", "Terrance Pell",
                "Ori Lindqvist", "Bo Chatham", "Nash Everly", "Kip Solano"],
        "mlb": ["Rocco Delmar", "Sy Hatterly", "Junior Vasquez-Poe", "Wes Kirkbride",
                "Ollie Mancuso", "Rafe Dunleavy", "Cy Portelli", "Gus Havemeyer"],
    }
    pool = fake_players.get(sport, fake_players["nfl"])
    # Per-player scale, derived from the team total so a "bust" reads as a
    # bust relative to that sport's scoring rather than an absolute number.
    p_low, p_high = low / 12, high / 5

    matchups = []
    for i in range(0, len(names) - 1, 2):
        def standouts():
            picks = random.sample(pool, 2)
            top = round(random.uniform(p_high * 0.6, p_high), 1)
            bust = round(random.uniform(p_low * 0.1, p_low), 1)
            return {"top": {"name": picks[0], "points": top},
                    "bust": {"name": picks[1], "points": bust}}
        matchups.append({
            "team_a": names[i],
            "team_a_score": round(random.uniform(low, high), 1),
            "team_b": names[i + 1],
            "team_b_score": round(random.uniform(low, high), 1),
            "team_a_standouts": standouts(),
            "team_b_standouts": standouts(),
        })
    return matchups


_SFX_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "sfx")
_MAX_SFX_VARIANTS = 10  # checks smackcast-{reaction}-1.mp3 through -10.mp3


def _pick_random_sfx(reaction: str):
    """
    Randomly picks one variant of a given reaction's sound effect, so
    the same "boo" or "laugh" clip isn't used every single week for
    every single subscriber. Checks however many numbered variants
    actually exist on disk (1 through _MAX_SFX_VARIANTS) rather than
    requiring a fixed count — gracefully returns None if none exist yet
    for that reaction, same pattern as every other optional sound on
    this site (silently does nothing until the file is actually there).
    """
    import random
    from pydub import AudioSegment

    if reaction == "none":
        return None

    existing_paths = []
    # Accept wav as well as mp3. Sound libraries hand out wav far more
    # often, and a conversion step before every new effect is friction
    # that ends with effects simply not being added.
    for i in range(1, _MAX_SFX_VARIANTS + 1):
        for ext in ("mp3", "wav"):
            path = os.path.join(_SFX_DIR, f"smackcast-{reaction}-{i}.{ext}")
            if os.path.exists(path):
                existing_paths.append(path)
                break          # one file per variant number; mp3 wins

    if not existing_paths:
        return None

    chosen_path = random.choice(existing_paths)
    try:
        # from_file reads the format off the file rather than being told.
        return AudioSegment.from_file(chosen_path)
    except Exception as e:
        print(f"[smackcast] failed to load sound effect {chosen_path}: {e}")
        return None


# Deliberately narrow. An earlier version also caught "period", "dash",
# "quote", "colon" and friends, which broke real sentences - "dominated
# every period" became "dominated every", and "that's it, period" lost its
# emphasis. Those words have legitimate uses in a sports recap; "comma"
# spoken aloud does not, and it's the one actually observed in output.
# Semicolon and ellipsis are included on the same reasoning - nobody says
# them out loud on purpose.
#
# Also requires the word to be sitting BETWEEN punctuation or spaces the way
# a dictated punctuation mark would be, rather than matching the bare word
# anywhere, so a sentence that legitimately discusses commas survives.
_PUNCT_NAME_RE = re.compile(
    # Widened after it kept slipping through. The previous version required
    # the word to be FOLLOWED by a comma, space or end of string, so
    # "comma." with a period after it never matched - and it also couldn't
    # match at the very start of a segment, since there was nothing before
    # it to look behind at. Now anchored on word boundaries and allowed to
    # be followed by any punctuation.
    # Widened AGAIN after "dot" was spoken aloud in the first daily show.
    # The list was only ever the names that had been caught in the wild, which
    # meant every new one cost a broken episode to discover. This is now the
    # full set of punctuation names an engine might verbalise.
    # Two names were removed or guarded because they are ordinary English
    # words as well as punctuation names, and stripping them unconditionally
    # broke real output:
    #
    #   "dot"    - the sign-off "Smackagram dot com" became "Smackagram com",
    #              which the engine reads as one blurred word. Heard in a
    #              real episode. Now protected before a TLD.
    #   "period" - dropped from the list entirely. "They're done. Period."
    #              lost the word and left a doubled full stop, and NHL
    #              segments would lose it as a unit of play ("second
    #              period"). It was speculative anyway: the list started as
    #              names caught in the wild and was later widened to every
    #              name an engine MIGHT verbalise, which is how both of
    #              these got in. Hearing a stray "period" once is a far
    #              smaller failure than silently deleting a real word.
    #
    # The rest have no ordinary use in a sports recap and stay unconditional.
    r"(?:^|(?<=[\s,.!?;:]))\s*("
    r"comma|semicolon|colon|ellipsis|"
    r"dot(?!\s+(?:com|net|org|io|co|tv|gg)\b)|"
    r"full stop|exclamation mark|exclamation point|question mark|"
    r"apostrophe|quote|quotation mark|hyphen|dash|underscore|asterisk|"
    r"ampersand|slash|backslash|parenthesis|bracket|tilde)\b[\s]*",
    re.IGNORECASE | re.MULTILINE,
)


# Broadened to cover essentially any emoji or pictograph, not just the common
# blocks. Fantasy team names use all of it - flags, arrows, stars, keycaps,
# trademark symbols, compound emoji joined with zero-width joiners.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # all pictographs, emoji, symbols, supplemental
    "\U00002190-\U000021FF"   # arrows
    "\U00002300-\U000023FF"   # misc technical (watches, hourglasses, keyboard)
    "\U00002460-\U000024FF"   # enclosed alphanumerics (circled letters/numbers)
    "\U00002500-\U00002BFF"   # box drawing, block elements, misc symbols, dingbats, arrows
    "\U00002E00-\U00002E7F"   # supplemental punctuation
    "\U00003000-\U0000303F"   # CJK symbols and punctuation
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\U000000A9\U000000AE"    # copyright, registered
    "\U00002122"               # trademark
    "\U0000200D"               # zero-width joiner (compound emoji)
    "\U000020E3"               # combining keycap enclosure
    "]+",
    flags=re.UNICODE,
)


# Acronyms this TTS engine mispronounces, mapped to spellings that force the
# letter names. Confirmed in real output: "WNBA" came out with a gargled,
# slurred W followed by a clean "NBA" - the engine treats the leading W as
# part of a pronounceable token and tries to make a syllable of it, then
# recovers for the remaining three letters.
#
# "double you" rather than "W" because a lone W is exactly what it already
# fails on. NOT "W-N-B-A": a hyphen is read as a PAUSE by this engine (the
# same reason coinages avoid them), which would fix the mangling but destroy
# the fluency - four separated letters instead of one natural run.
#
# Case-sensitive and word-bounded deliberately. A lowercase "era" is an
# ordinary English word and must never be rewritten; only an uppercase
# acronym would be. Add entries here as more surface - this is the single
# place pronunciation is corrected for every spoken product.
SPEECH_PRONUNCIATIONS = {
    "WNBA": "double you N B A",
}


def sanitize_for_display(text: str) -> str:
    """
    Clean text for a transcript somebody READS, as opposed to one the engine
    speaks.

    The speech sanitizer respells things for the ear - "WNBA" becomes
    "double you N B A", ".500" becomes "five hundred", "16/25" becomes "16
    of 25". All correct out loud and all wrong on a page. A real episode
    stored "double you N B A" in its transcript because both uses shared one
    pass.

    So this does only the parts that are wrong in BOTH forms: emoji, and
    punctuation names the model wrote out as words.
    """
    if not text:
        return text
    text = _PUNCT_NAME_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = re.sub(r"[_~^|`]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Team abbreviations, spelled out as the club a person would actually say.
#
# A belt-and-braces pass. The real fix is upstream - the show now hands the
# writer nicknames rather than ESPN's abbreviation field - but a stray code
# from any other source would still be read aloud as letters, and "P.I.T."
# instead of "Pittsburgh" is the kind of thing a listener notices instantly.
_ABBR_SPOKEN = {
    "ARI":"Arizona","ATL":"Atlanta","BAL":"Baltimore","BOS":"Boston",
    "CHC":"the Cubs","CHW":"the White Sox","CIN":"Cincinnati","CLE":"Cleveland",
    "COL":"Colorado","DET":"Detroit","HOU":"Houston","KC":"Kansas City",
    "LAA":"the Angels","LAD":"the Dodgers","MIA":"Miami","MIL":"Milwaukee",
    "MIN":"Minnesota","NYM":"the Mets","NYY":"the Yankees","OAK":"the Athletics",
    "PHI":"Philadelphia","PIT":"Pittsburgh","SD":"San Diego","SEA":"Seattle",
    "SF":"San Francisco","STL":"St. Louis","TB":"Tampa Bay","TEX":"Texas",
    "TOR":"Toronto","WSH":"Washington",
    # WNBA codes are DELIBERATELY ABSENT.
    #
    # They collide with baseball and with ordinary text. "NY" mapped to the
    # Liberty turned "the NY Yankees" into "the the Liberty Yankees"; IND is
    # Indiana in four sports and DAL is Dallas in three. A wrong expansion is
    # far worse than an unexpanded code, because at least a code sounds like
    # a code.
    #
    # The real fix is upstream anyway: winner and loser now carry nicknames
    # rather than abbreviations, so basketball codes should not reach the
    # voice at all. This pass is a safety net for baseball, not a translator.
}


def _spell_out_abbreviations(text: str) -> str:
    """Swap any bare team code for the name a human would say."""
    import re as _re
    def _sub(m):
        return _ABBR_SPOKEN.get(m.group(0).upper().replace(".", ""), m.group(0))
    # Whole tokens in caps only, and never one immediately followed by
    # another capitalised word - "NY Yankees" is a team NAME being used
    # correctly, not a bare code needing expansion.
    return _re.sub(r"\b[A-Z]{2}[A-Z.]{0,3}\b(?!\s+[A-Z][a-z])", _sub, text or "")


def sanitize_for_speech(text: str) -> str:
    """
    Cleans script text before it goes to text-to-speech.

    Two separate problems, both confirmed in real output:

    1. The engine spoke the word "comma" aloud instead of treating it as
       punctuation. Any punctuation NAME appearing as a word gets stripped -
       there is no legitimate reason for a recap to say "comma" out loud,
       and leaving one in is jarring enough to ruin a segment.

    2. Typographic punctuation the model picks up from the prompt's own
       writing style. Em and en dashes, ellipses and smart quotes are read
       inconsistently across engines - sometimes as a pause, sometimes
       spoken literally as "dash". They're normalised to plain commas,
       periods and straight quotes, which every engine handles predictably.

    Deliberately conservative: it does not touch wording, only punctuation
    and stray punctuation names.
    """
    if not text:
        return text

    # Typographic characters the model tends to mirror from the prompt.
    # Team codes first, before anything else touches the text.
    text = _spell_out_abbreviations(text)

    replacements = {
        "\u2014": ", ",   # em dash
        "\u2013": ", ",   # en dash
        "\u2026": ". ",   # ellipsis
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u00a0": " ",    # non-breaking space
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Underscores and similar separators read as a silent gap rather than a
    # word break - confirmed in a real generation, where xXx_L33T_xXx came out
    # as a stutter, dead air, "L33T", dead air, stutter. Converting them to
    # spaces keeps the name awkward enough to mock (which is the point) without
    # the broken-sounding pauses. Deliberately does NOT try to smooth the name
    # out further: stumbling over a genuinely stupid name is good material, and
    # over-sanitising would remove the joke along with the noise.
    text = re.sub(r"[_~^|`]+", " ", text)

    # A spoken punctuation name is always a mistake here.
    text = _PUNCT_NAME_RE.sub(" ", text)

    # Leading-decimal sports figures: ".500", ".289", ".311". The engine reads
    # the decimal point aloud - a real episode said "above dot five hundred".
    # Spelled out in WORDS because "289" would be read "two hundred eighty
    # nine" when a broadcaster says "two eighty nine".
    _ONES = ("zero", "one", "two", "three", "four", "five",
             "six", "seven", "eight", "nine")
    _TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen",
              "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
    _TENS = ("", "", "twenty", "thirty", "forty", "fifty",
             "sixty", "seventy", "eighty", "ninety")

    def _two_digit(n):
        if n < 10:
            return "oh " + _ONES[n] if n else "hundred"
        if n < 20:
            return _TEENS[n - 10]
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])

    def _lead_dec(m):
        d = m.group(1)
        lead, rest = int(d[0]), int(d[1:])
        return f" {_ONES[lead]} {_two_digit(rest)}"

    text = re.sub(r"(?<![\d.])\.(\d{3})\b", _lead_dec, text)
    text = re.sub(r"\b(\d+)\.(\d+)\b",
                  lambda m: f"{m.group(1)} point {' '.join(m.group(2))}", text)

    # Football notation. Read literally these all come out wrong: "16/25"
    # becomes "sixteen slash twenty five", "3-34" becomes "three minus
    # thirty four", and a QBR of "16.3" hits the same decimal problem that
    # made a real episode say "above dot five hundred".
    #
    # Ordered longest-pattern-first so the sack line is consumed before the
    # bare hyphen rule can get to it.
    text = re.sub(r"\b(\d+)-(\d+)\s+sacks?\b",
                  lambda m: f"{m.group(1)} sacks for {m.group(2)} yards", text)
    text = re.sub(r"\bsacked\s+(\d+)-(\d+)\b",
                  lambda m: f"sacked {m.group(1)} times for {m.group(2)} yards", text)
    text = re.sub(r"\b(\d+)/(\d+)\b",
                  lambda m: f"{m.group(1)} of {m.group(2)}", text)

    for abbr, spoken in (
        ("St. Louis", "Saint Louis"), ("St. John", "Saint John"),
        ("Ft. ", "Fort "), ("Mt. ", "Mount "),
    ):
        text = text.replace(abbr, spoken)
    # Removing a punctuation NAME leaves the punctuation around it butted
    # together - "lost.Again", "bad,really" - which TTS runs straight through
    # with no pause, and a stranded leading period at the start of a segment.
    # Cheap to repair here, jarring to hear.
    text = re.sub(r"([.,!?;:])(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"^[\s.,;:]+", "", text)

    # Emoji and pictographs. Fantasy team names are full of them, and engines
    # either skip them or read the character's DESCRIPTION out loud
    # ("fire emoji"), neither of which is wanted mid-sentence.
    text = _EMOJI_RE.sub(" ", text)

    # Long all-capital runs. Engines spell capitals out letter by letter, so a
    # team called THEREALCHAMPS becomes "T-H-E-R-E-A-L...". Anything 5+ letters
    # gets title-cased; shorter runs are left alone because they're usually
    # genuine acronyms (NFL, QB, RB, TE) that SHOULD be spelled out.
    text = re.sub(r"\b[A-Z]{5,}\b", lambda m: m.group(0).title(), text)

    # Collapse the artefacts the above can leave behind - doubled commas,
    # a comma butted against a period, runs of whitespace.
    text = re.sub(r"\s*,\s*,+", ",", text)
    # A stripped punctuation name can leave a comma stranded against the next
    # mark ("disaster,! Unreal") or at the very start of a line. Both are read
    # oddly aloud, so collapse them.
    text = re.sub(r",\s*([.!?;:])", r"\1", text)
    text = re.sub(r"^[\s,;:]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+([,.!?])", r"\1", text)

    # Pronunciation corrections. Applied AFTER the cleanup above so that
    # nothing upstream has split an acronym apart before it can be matched,
    # but BEFORE the final whitespace collapse so any spacing this
    # introduces gets tidied by it.
    # The engine ran "Smackagram dot com" together into something that
    # sounded like "detached com" - heard in a real episode. Breaking the
    # brand into syllables forces articulation, and this is the one line
    # that has to be understood: it is where people are told to go.
    #
    # Done as a regex rather than a dict entry because by this point earlier
    # cleanup may have turned "Smackagram.com" into "Smackagram. com", and a
    # literal lookup misses that.
    text = re.sub(r"\bsmackagram\s*(?:\.|\s+dot\s+)\s*com\b",
                  "Smack a gram dot com", text, flags=re.IGNORECASE)

    for acronym, spoken in SPEECH_PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(acronym)}\b", spoken, text)

    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# A music bed shorter than the read gets looped - but only if the gap is
# large enough that a loop sounds intentional. Anything smaller and the
# restart reads as a glitch, so the bed is padded with silence and faded out
# instead. 4s is roughly the shortest repeat that still sounds like music
# rather than a mistake.
# Kept for reference; the bed now always loops to cover the read.
MUSIC_LOOP_MIN_GAP_MS = 4000
MUSIC_LOOP_CROSSFADE_MS = 900
MUSIC_TAIL_FADE_MS = 2200


def _trim_trailing_silence(seg, silence_thresh_db: float = -45.0, chunk_ms: int = 10):
    """
    Removes the silence a TTS clip leaves on its end.

    This matters for anchoring a sound effect. The whole point of splitting
    the sign-off so a clip ENDS on the word "you" is that the clip's end is
    then exactly where the word finishes - but only if the trailing silence
    is gone. Left in, it can be a few hundred ms, and the effect lands late
    on empty air rather than over the tail of the word.
    """
    trim = 0
    while trim < len(seg):
        window = seg[len(seg) - trim - chunk_ms: len(seg) - trim]
        if len(window) == 0 or window.dBFS > silence_thresh_db:
            break
        trim += chunk_ms
    return seg[: len(seg) - trim] if trim else seg


# Reaction tag -> the file that actually exists.
#
# The writer is asked for burn / laugh / shock / groan, and only ONE of those
# had a matching file in static/sfx. The other three resolved to nothing, so
# even once playback worked they would have been silent. Mapped explicitly
# rather than assuming the names line up.
_REACTION_FILES = {
    "burn":    ["boo.mp3", "smackcast-boo-1.mp3"],
    "laugh":   ["smackcast-laugh-1.mp3", "smackcast-laugh-2.mp3"],
    "shock":   ["smackcast-gasp-1.mp3", "smackcast-boom-1.wav"],
    "groan":   ["smackcast-aww-1.mp3", "smackcast-aww-2.mp3"],
    "boo":     ["boo.mp3", "smackcast-boo-1.mp3"],
    "cheer":   ["cheer.mp3"],
    "gasp":    ["smackcast-gasp-1.mp3"],
    "trombone":["smackcast-trombone-1.mp3"],
}

_SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "sfx")

# Long enough to land, short enough not to become a pause in the show.
REACTION_MAX_MS = 1200


def _reaction_audio(tag):
    """
    The sound for a reaction tag, or None.

    Returns None for anything unrecognised or missing rather than raising -
    a missing sound effect should cost a sound effect, not an episode.
    """
    import random as _r
    # Imported here rather than at module scope: pydub is a heavy import and
    # the rest of this module is used by paths that never touch audio.
    from pydub import AudioSegment

    if not tag or str(tag).lower() in ("none", "burn_none", ""):
        return None
    names = _REACTION_FILES.get(str(tag).lower().strip())
    if not names:
        return None
    existing = [n for n in names if os.path.exists(os.path.join(_SFX_DIR, n))]
    if not existing:
        print(f"[audio] no file on disk for reaction {tag!r}", flush=True)
        return None
    try:
        sfx = AudioSegment.from_file(os.path.join(_SFX_DIR, _r.choice(existing)))
    except Exception as e:
        print(f"[audio] could not load reaction {tag!r}: {e}", flush=True)
        return None

    # TRIMMED HARD. These files run four to five seconds each, and nineteen
    # segments of that is well over a minute of the show spent on sound
    # effects - a five-second cheer after every line stops being a punchline
    # and becomes a wait.
    #
    # A punch of about a second is the joke; the rest is the file's tail.
    if len(sfx) > REACTION_MAX_MS:
        sfx = sfx[:REACTION_MAX_MS].fade_out(180)
    return sfx


def assemble_recap_audio(intro: str, segments: list, outro: str,
                         outro_tail: str = None, hit_sfx_path: str = None,
                         hit_lead_ms: int = 120, hit_beat_ms: int = 350,
                         hit_gain_db: float = 0.0) -> str:
    """
    Generates speech for the intro, each segment, and the outro
    separately, splicing in a randomly-chosen sound effect after each
    segment based on its reaction tag, then combines everything into
    one final audio file — normalized for consistent loudness the same
    way every other spoken audio on this site is — and uploads it to
    S3. Returns the final public URL.

    segments: list of {"text": str, "reaction": str}
    """
    from pydub import AudioSegment
    import io
    import uuid
    import boto3
    from services import elevenlabs_service

    def _mem():
        try:
            with open("/proc/self/status") as fh:
                for ln in fh:
                    if ln.startswith("VmRSS:"):
                        return int(ln.split()[1]) / 1024
        except Exception:
            return None

    def _memlog(where):
        m = _mem()
        if m is not None:
            print(f"[audio {m:5.0f}MB] {where}", flush=True)

    _memlog("assembly starting")

    # Pieces are written to disk as they are finished rather than being
    # accumulated in memory.
    #
    # The old approach built the entire episode as one AudioSegment. Decoded
    # audio is raw PCM - roughly 88KB a second at 44.1kHz mono - so a five
    # minute show is about 26MB, and pydub COPIES on every append, so the
    # peak is far higher than the final size. Production logs showed it
    # climbing ~10MB a segment and a run was killed at segment six on a
    # 512MB instance.
    #
    # Writing each piece out and letting ffmpeg concatenate at the end means
    # at most two pieces are ever held - the current one, and the previous
    # one when an interruption needs to mix across their boundary.
    _tmpdir = tempfile.mkdtemp(prefix="smackcast-")
    _parts = []

    def _flush(audio):
        """
        Write a finished piece to disk and release it.

        Every piece is forced to the SAME format first. ffmpeg's concat
        demuxer does not resample - it assumes every input matches, and if
        one piece is at a different sample rate the output plays that
        section at the wrong speed. Heard in a real episode: a minute of
        garbled, slow audio in the middle of an otherwise clean show.
        """
        if audio is None or len(audio) == 0:
            return
        audio = audio.set_frame_rate(44100).set_channels(1).set_sample_width(2)
        path = os.path.join(_tmpdir, f"part-{len(_parts):03d}.wav")
        audio.export(path, format="wav")
        _parts.append(path)

    def _total_ms():
        """Rough running length, for the logs - reads headers, not audio."""
        import wave
        total = 0
        for pth in _parts:
            try:
                with wave.open(pth) as w:
                    total += (w.getnframes() / w.getframerate()) * 1000
            except Exception:
                pass
        return total

    def _standardize(segment):
        """
        Forces consistent audio properties before concatenation.
        Mismatched sample rates/channel counts between pieces (real,
        confirmed here — some sfx files are 96000Hz, others 44100Hz;
        some mono, some stereo) is a known source of corruption when
        concatenating with pydub, which could plausibly explain audio
        overlapping or playing incorrectly instead of sequentially.

        Only actually converts when something differs. set_frame_rate and
        set_channels resample the whole segment every time they're called,
        even when the segment is already at the target — which on a
        single-CPU instance was real, wasted time across seven multi-minute
        speech segments. Note the original problem this guards against was
        specifically the SFX FILES disagreeing with each other; ElevenLabs
        speech all comes from one API at one setting, so it's already
        correct and needs no conversion at all. Same guarantee as before -
        everything leaves here at 44100/stereo - just without the no-op
        resamples.
        """
        if segment.frame_rate != 44100:
            segment = segment.set_frame_rate(44100)
        if segment.channels != 1:
            segment = segment.set_channels(1)
        return segment

    # Sound effects were coming through louder than the speech — the
    # final loudness normalization step balances the AVERAGE loudness
    # of the whole combined file, but doesn't balance the RELATIVE
    # level between speech and sfx portions within it. These sound
    # effects are professionally mixed/mastered clips, punchy and loud
    # on their own; ElevenLabs' speech output sits at a more modest,
    # conversational level by comparison. Without this explicit
    # reduction, the sfx will naturally overpower the speech regardless
    # of the overall normalization pass.
    SFX_VOLUME_REDUCTION_DB = -10

    # Every piece of speech is generated in PARALLEL rather than one after
    # another. This was the whole reason a recap took minutes: a 10-team
    # league is intro + 5 segments + outro = 7 separate ElevenLabs calls,
    # each 10-25 seconds for a paragraph, run strictly in sequence. The
    # calls are completely independent of each other - only the assembly
    # below needs to happen in order - so waiting for each one before
    # starting the next was pure dead time.
    #
    # Concurrency is capped rather than unbounded: a 14-team league would
    # otherwise fire a dozen simultaneous requests at ElevenLabs and risk
    # rate limiting, which would be slower than doing it sequentially.
    from concurrent.futures import ThreadPoolExecutor

    # Sanitised before synthesis, never after - the transcript keeps its
    # original punctuation for display on the recap page.
    texts = [sanitize_for_speech(intro)] + [sanitize_for_speech(seg["text"]) for seg in segments]
    if outro:
        texts.append(sanitize_for_speech(outro))
    # The tail is synthesised SEPARATELY, not because it sounds different,
    # but because splitting here is what makes the sound effect placeable:
    # the clip before it ends on the exact word the effect has to land on.
    if outro and outro_tail:
        texts.append(sanitize_for_speech(outro_tail))

    with ThreadPoolExecutor(max_workers=4) as pool:
        # .map preserves input order, which is what keeps the recap from
        # being assembled with its segments shuffled.
        speech_bytes = list(pool.map(elevenlabs_service.generate_speech_bytes, texts))

    # Decode ONE segment at a time and append it, rather than decoding all of
    # them up front. This caused a real out-of-memory kill (Render limit is
    # 512MB): mp3 bytes are compressed and cheap to hold, but a DECODED
    # AudioSegment is raw PCM at ~176KB per second, so a four-minute recap
    # is ~40MB decoded. Holding every segment decoded simultaneously, on top
    # of the combined track and pydub's copy-on-append, exceeded the limit.
    # Keeping only the compressed bytes gives us the parallel-network win
    # without the memory cost - each decoded segment is freed once appended.
    _flush(_standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[0]))))

    # At most one ambient bed per episode - it is texture, not a feature.
    _ambient_used = False

    # The previous piece, held back one beat. An interruption has to mix its
    # ring across the boundary into the tail of the line before it, so that
    # line cannot be written to disk until we know what follows.
    _pending = None

    for i, seg in enumerate(segments):
        # A real beat before each new matchup. Spoken transitions carry most of
        # the work, but back-to-back speech with no gap still runs together to
        # the ear. Skipped before the first segment, which follows the intro
        # and already has the intro's own trailing pause.
        lead_gap = AudioSegment.silent(duration=450) if i > 0 else None

        spoken = _standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[1 + i])))

        # A segment can carry a music bed - used for the commercial break,
        # where the ad is read over ambience rather than dry. The bed is
        # looped to cover the read (a short loop would otherwise stop dead
        # halfway through) and faded at both ends so it doesn't click in.
        bed_path = seg.get("music_bed")
        if bed_path and os.path.exists(bed_path):
            try:
                bed = _standardize(AudioSegment.from_file(bed_path))
                shortfall = len(spoken) - len(bed)

                # The bed always covers the whole read. Padding a short bed
                # with silence left the drums stopping dead partway through
                # the ad - heard in a real episode, the loop ran out before
                # "ring, roast, repeat". The seam is hidden with a crossfade
                # rather than avoided.
                if shortfall > 0:
                    seam = min(MUSIC_LOOP_CROSSFADE_MS, len(bed) // 3)
                    looped = bed
                    while len(looped) < len(spoken):
                        looped = looped.append(bed, crossfade=seam)
                    bed = looped

                bed = bed[: len(spoken)]
                fade = int(seg.get("music_fade_ms", 600))
                bed = (bed.fade_in(fade)
                          .fade_out(min(MUSIC_TAIL_FADE_MS, len(bed) // 2))
                       + float(seg.get("music_gain_db", -20.0)))
                spoken = spoken.overlay(bed)
            except Exception as e:
                print(f"[audio] music bed failed ({e}); running the read dry", flush=True)
        elif bed_path:
            print(f"[audio] music bed not found at {bed_path}; running the read dry", flush=True)

        # An interruption mixes ACROSS the boundary - the ring starts while
        # he is still talking on the previous line - so it is merged into
        # the piece that is still pending rather than becoming its own.
        if seg.get("interruption"):
            base = _pending if _pending is not None else AudioSegment.silent(duration=1)
            if lead_gap is not None:
                base = base + lead_gap
            _pending = lay_in_interruption(
                base, spoken, _standardize,
                sound=seg.get("interrupt_sound") or "phone")
            del spoken, base
            continue

        # Background noise, sometimes, under one segment. Never on the
        # commercial break - the ad has its own bed.
        if not seg.get("music_bed") and i > 0 and not _ambient_used:
            before = spoken
            spoken = maybe_ambient(spoken, _standardize)
            if spoken is not before:
                _ambient_used = True

        # If an interruption follows this segment, do NOT put a reaction
        # sound on the end of it.
        #
        # The ring is meant to start while he is still TALKING - that is the
        # whole point of the bit. But a reaction sound extends the segment
        # with its own tail, so the ring ended up mixing over a decaying
        # sound effect instead of over speech. Heard in a real episode: an
        # explosion, then a phone ringing into silence, with no voice
        # underneath either.
        _next_interrupts = (i + 1 < len(segments)
                            and segments[i + 1].get("interruption"))

        sfx = None if _next_interrupts else _pick_random_sfx(seg.get("reaction", "none"))
        if sfx is not None:
            # _standardize is nested inside this function, so it is passed
            # in rather than reached for - a module-level helper cannot see
            # it, which is exactly how the first version of this failed.
            spoken = _lay_in_sfx(spoken, sfx, len(spoken), _standardize,
                                 kind=seg.get("reaction"))

        piece = (lead_gap + spoken) if lead_gap is not None else spoken

        # The reaction, at last.
        #
        # Every episode so far has had these tagged by the writer, stored by
        # the parser, and then silently dropped - the docstring above promised
        # them, nothing played them. Appended AFTER the speech with a short
        # beat, so it reads as a response to the line rather than talking over
        # it.
        _rx = _reaction_audio(seg.get("reaction"))
        if _rx is not None:
            piece = piece + AudioSegment.silent(duration=180) + _standardize(_rx) - 3
            print(f"[audio] reaction {seg.get('reaction')!r} after segment {i}",
                  flush=True)

        # The previous piece is safe to write now: nothing after it needs to
        # reach back into it.
        _flush(_pending)
        _pending = piece
        del spoken, piece

        if i % 3 == 0:
            _memlog(f"segment {i} written, {_total_ms()/1000:.0f}s on disk")

    _flush(_pending)
    _pending = None
    _memlog(f"all segments written ({_total_ms()/1000:.0f}s)")
    if outro and outro_tail:
        # speech_bytes[-2] ends on the word the hit lands on; [-1] is the tail.
        hit_clip = _trim_trailing_silence(
            _standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[-2]))))
        tail_clip = _standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[-1])))

        signoff = hit_clip + AudioSegment.silent(duration=hit_beat_ms) + tail_clip
        hit_point = len(hit_clip)

        # Overlaid AFTER the tail is appended, deliberately. pydub's overlay
        # does not extend the track it is laid onto, so doing this earlier
        # would clip the effect's decay at whatever the end happened to be.
        # With the tail already in place the effect is free to ring out over
        # it, which is also how it would sound if a person did it live.
        if hit_sfx_path and os.path.exists(hit_sfx_path):
            try:
                smack = _standardize(AudioSegment.from_file(hit_sfx_path))
                if hit_gain_db:
                    smack = smack + hit_gain_db
                signoff = signoff.overlay(smack, position=max(0, hit_point - hit_lead_ms))
                del smack
            except Exception as e:
                print(f"[audio] smack sfx failed to load ({e}); continuing without it", flush=True)

        _flush(signoff)
        del hit_clip, tail_clip, signoff
    elif outro:
        _flush(_standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[-1]))))

    # Compressed source blobs are no longer needed, and the export plus the
    # ffmpeg normalization pass below both need headroom on a 512MB box.
    del speech_bytes

    # Export the fully-assembled audio back to raw mp3 bytes, then run it
    # through the same loudness normalization every other spoken clip on
    # the site gets, so the overall recap doesn't sound quieter/louder
    # than everything else.
    #
    # Explicit constant bitrate (not pydub's default, which can produce
    # variable bitrate output) — VBR MP3s are a known source of seek/
    # playback miscalculation in some browsers, which could plausibly
    # explain garbled or overlapping-sounding playback without showing
    # up as any duration mismatch in the file itself.
    # ffmpeg concatenates the pieces. It STREAMS - it reads and writes a
    # buffer at a time and never holds the episode - which is the entire
    # point of writing the pieces out in the first place.
    # Confirm every piece really does match before handing them to ffmpeg.
    # A mismatch here is silent - the output is simply wrong - so it is
    # worth a line in the log rather than a listener finding it.
    try:
        import wave
        rates = set()
        for pth in _parts:
            with wave.open(pth) as w:
                rates.add((w.getframerate(), w.getnchannels(), w.getsampwidth()))
        if len(rates) > 1:
            print(f"[audio] WARNING mixed formats across pieces: {rates}", flush=True)
        else:
            print(f"[audio] all {len(_parts)} pieces at {rates.pop()}", flush=True)
    except Exception as e:
        print(f"[audio] could not verify piece formats: {e}", flush=True)

    _memlog(f"concatenating {len(_parts)} pieces")

    import subprocess
    listfile = os.path.join(_tmpdir, "parts.txt")
    with open(listfile, "w") as fh:
        for pth in _parts:
            fh.write(f"file '{pth}'\n")

    outpath = os.path.join(_tmpdir, "show.mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", listfile,
             "-b:a", "192k", outpath],
            check=True, capture_output=True, timeout=300)
        with open(outpath, "rb") as fh:
            combined_bytes = fh.read()
    except Exception as e:
        # If ffmpeg is unavailable or fails, fall back to doing it in memory
        # rather than losing the episode. Slower and heavier, but it works.
        print(f"[audio] ffmpeg concat failed ({e}); falling back to in-memory",
              flush=True)
        merged = AudioSegment.empty()
        for pth in _parts:
            merged += AudioSegment.from_file(pth)
        buffer = io.BytesIO()
        merged.export(buffer, format="mp3", parameters=["-b:a", "192k"])
        combined_bytes = buffer.getvalue()
        del merged

    _memlog("concatenated, normalising")
    normalized_bytes = elevenlabs_service.normalize_loudness(combined_bytes)

    # Temp files are not small - a five minute show is roughly 26MB of wav.
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

    s3_bucket = os.environ["AUDIO_S3_BUCKET"]
    s3_region = os.environ.get("AWS_REGION", "us-east-1")
    # Its own folder and a readable name, same reasoning as the daily show:
    # a bucket of tts/<uuid>.mp3 tells you nothing about what any file is.
    #
    # datetime is imported HERE because this module has no module-level
    # import of it - only two other functions import it locally, and using
    # it without that would have crashed every recap upload.
    from datetime import datetime as _dt
    filename = ("smackcast/" + _dt.now().strftime("%Y-%m-%d")
                + f"-smackcast-{uuid.uuid4().hex[:6]}.mp3")
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(Bucket=s3_bucket, Key=filename, Body=normalized_bytes, ContentType="audio/mpeg")

    return f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"


# How far INTO the tail of a segment an effect starts. A sound that waits
# politely for the voice to finish sounds bolted on; one that starts while
# the last word is still ringing sounds like it is happening in the room.
# Mirrors the value inside the assembler. Kept here as its own constant
# because this helper lives at module scope and cannot see the nested one -
# the third scope mistake in a row while building this.
SFX_VOLUME_DB = -10

# Some effects are mastered far hotter than others. Sound libraries normalise
# an explosion to the same peak as a laugh, so it lands about twice as loud
# in context - it was noticeably too loud in a real episode. These take an
# extra trim on top of the shared level.
SFX_EXTRA_TRIM_DB = {
    "boom": -7,        # explosions are always the loudest thing in a library
    "alarm": -4,
    "carhorn": -4,
    "siren": -3,
}
SFX_OVERLAP_MS = 420
# Effects that hard-stop sound like files. A fade gives them somewhere to go.
SFX_FADE_OUT_MS = 600
SFX_FADE_IN_MS = 40


def _lay_in_sfx(spoken, sfx, spoken_ms, standardize, kind=None):
    """
    Place a sound effect so it feels played rather than pasted.

    Two things do the work. It starts BEFORE the voice has quite finished -
    overlapping the tail of the last word, the way a real reaction would -
    and it fades out rather than stopping dead. A hard cut is the single
    biggest tell that something was assembled rather than performed.
    """
    clip = standardize(sfx) + SFX_VOLUME_DB + SFX_EXTRA_TRIM_DB.get(kind, 0)

    # A short fade in stops the attack clicking, a longer one out gives it
    # somewhere to land.
    fade_out = min(SFX_FADE_OUT_MS, max(0, len(clip) // 2))
    clip = clip.fade_in(min(SFX_FADE_IN_MS, len(clip) // 4)).fade_out(fade_out)

    # Start it inside the tail of the read, but never so early that it steps
    # on words that carry meaning - capped at a third of the segment.
    # Imported locally: pydub is not available at module scope here, and
    # reaching for it globally is the same class of mistake as reaching for
    # _standardize was.
    from pydub import AudioSegment

    overlap = min(SFX_OVERLAP_MS, max(0, spoken_ms // 3))
    if overlap <= 0:
        return spoken + AudioSegment.silent(duration=180) + clip

    # Overlay onto THIS SEGMENT, not the whole show assembled so far.
    #
    # The first version took the accumulated audio and overlaid onto that,
    # which meant every sound effect copied the entire episode - by the last
    # segment that is a 26 MB copy for a two second noise, and roughly
    # 155 MB of churn across one show. It ran the instance out of its 512 MB
    # and killed a production run.
    start = max(0, len(spoken) - overlap)

    tail_needed = max(0, (start + len(clip)) - len(spoken))
    if tail_needed:
        spoken = spoken + AudioSegment.silent(duration=tail_needed)

    return spoken.overlay(clip, position=start)


# An interruption only works if the phone starts while he is STILL TALKING.
# A ring that waits for a gap sounds like a cue; one that arrives mid-thought
# sounds like an interruption, which is the entire point of the bit.
RING_LEAD_IN_MS = 2600      # how far into the previous line the ring starts
RING_MAX_MS = 3400          # long rings get cut - nobody needs a full cycle
RING_FADE_IN_MS = 350       # comes up rather than appearing
RING_FADE_OUT_MS = 500      # he answers it; it does not just stop
RING_UNDER_DB = -14         # sits under the voice, not over it
HANGUP_GAP_MS = 260         # beat between his last word and the beep


def lay_in_interruption(prev_audio, bit_audio, standardize, sound="phone"):
    """
    Stitch a phone interruption so it sounds like it happened rather than
    like it was assembled.

    Four things do the work:

      the ring starts BEFORE he stops talking, buried under the end of the
      previous line, so the listener hears it a moment before he reacts -
      exactly the order it happens in a real room

      it is trimmed. Ring files run five or ten seconds and a full cycle
      under a five minute show is interminable

      it fades in and out rather than switching on and off, and it fades
      DOWN as he starts speaking, because he has answered it

      a hang-up beep closes the bit, since otherwise he simply stops talking
      and the call never visibly ends
    """
    from pydub import AudioSegment

    # Which sound this bit needs. Not every interruption is a phone call -
    # the baby ones want a crying baby underneath, and a phone ring over
    # "he's up, we're all up" would make no sense at all.
    ring = _pick_random_sfx(sound)
    if ring is None:
        # No file yet - the bit still works, it just has no phone in it.
        return prev_audio + AudioSegment.silent(duration=300) + bit_audio

    ring = standardize(ring)
    if len(ring) > RING_MAX_MS:
        ring = ring[:RING_MAX_MS]
    ring = (ring.fade_in(min(RING_FADE_IN_MS, len(ring) // 3))
                .fade_out(min(RING_FADE_OUT_MS, len(ring) // 2))
            + RING_UNDER_DB)

    # Where the ring begins, measured back from the end of the line he is
    # currently speaking. Never more than a third of that line, so it does
    # not step on a score.
    lead = min(RING_LEAD_IN_MS, max(0, len(prev_audio) // 3))
    start = max(0, len(prev_audio) - lead)

    # Only the TAIL of the previous line is needed, not the whole show.
    #
    # Building a canvas from the entire accumulated episode and overlaying
    # onto that copies everything assembled so far - which on a five minute
    # show is tens of megabytes for one phone ring, and is what ran the
    # instance out of memory mid-production.
    #
    # So: slice off just the tail, mix the ring into that, and hand back the
    # untouched head plus the mixed tail.
    head = prev_audio[:start]
    tail = prev_audio[start:]

    canvas = tail + AudioSegment.silent(duration=260) + bit_audio
    if len(ring) > len(canvas):
        canvas += AudioSegment.silent(duration=len(ring) - len(canvas))

    out = head + canvas.overlay(ring, position=0)

    # Only a phone call gets hung up.
    hangup = _pick_random_sfx("hangup") if sound == "phone" else None
    if hangup is not None:
        clip = standardize(hangup) + RING_UNDER_DB
        clip = clip.fade_out(min(200, len(clip) // 2))
        out = out + AudioSegment.silent(duration=HANGUP_GAP_MS) + clip

    return out


# Background, not interruption. A dog somewhere, a siren going past, a
# neighbour mowing at five in the morning - things Smacky never acknowledges
# and simply talks over. They cost nothing in pacing because nothing stops,
# and they do more for the sense of a real room than any scripted bit.
#
# Deliberately much quieter than a reaction sound. If the listener CONSCIOUSLY
# notices it, it is too loud - the effect wanted here is "something is off
# about this room" rather than "a sound effect just played".
AMBIENT_TYPES = ("dog", "siren", "mower", "carhorn", "baby", "alarm")
AMBIENT_CHANCE = 0.45          # in an episode, not per segment
AMBIENT_UNDER_DB = -26
AMBIENT_FADE_MS = 900


def maybe_ambient(spoken, standardize):
    """
    Lay a background sound under one segment. Returns the audio unchanged if
    nothing is available or the roll fails.
    """
    import random
    from pydub import AudioSegment

    if random.random() > AMBIENT_CHANCE:
        return spoken

    kind = random.choice(AMBIENT_TYPES)
    bed = _pick_random_sfx(kind)
    if bed is None:
        return spoken

    bed = standardize(bed) + AMBIENT_UNDER_DB

    # Continuous sounds get looped to sit under the whole line. One-off
    # events do not - a car horn repeated on a loop for nine seconds is a
    # traffic jam, which is a different joke and not a good one.
    # One-off events rather than continuous washes. Looping a car horn for
    # nine seconds is a traffic jam; looping a smoke alarm chirp is a fire.
    # Neither is the joke.
    ONE_SHOT = ("carhorn", "alarm")

    if kind in ONE_SHOT:
        # Drop it somewhere in the middle of the line rather than at the
        # start, so it interrupts rather than announces.
        import random as _r
        at = _r.randint(len(spoken) // 4, max(len(spoken) // 4, len(spoken) - len(bed) - 200)) \
            if len(spoken) > len(bed) + 400 else 0
        bed = bed.fade_in(80).fade_out(min(400, len(bed) // 2))
        print(f"[audio] ambient one-shot: {kind}", flush=True)
        return spoken.overlay(bed, position=at)

    if len(bed) < len(spoken):
        reps = (len(spoken) // max(1, len(bed))) + 1
        bed = bed * reps
    bed = bed[:len(spoken)]
    bed = (bed.fade_in(min(AMBIENT_FADE_MS, len(bed) // 3))
              .fade_out(min(AMBIENT_FADE_MS, len(bed) // 3)))

    print(f"[audio] ambient bed: {kind}", flush=True)
    return spoken.overlay(bed)


# ---------------------------------------------------------------------------
# Which week are we collecting for?
# ---------------------------------------------------------------------------
# Notes are stamped when they are SAVED, not when the recap runs. A note at
# 11:58pm Monday belongs to the week that just finished and goes into
# tomorrow's episode; a note at 12:01am Tuesday belongs to the week now
# starting and waits seven days.
#
# Everything is Eastern, because the deadline is stated to subscribers as
# 11:59pm Monday and a deadline that means different things in different
# places is not a deadline.

NOTES_DEADLINE_WEEKDAY = 0     # Monday, in Python's Monday=0 numbering
SEASON_TZ = "America/New_York"


def _eastern_now():
    """Now, in the timezone the deadline is quoted in."""
    from datetime import datetime, timezone as _tz
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(SEASON_TZ))
    except Exception:
        # Falls back to UTC rather than failing. The window shifts by a few
        # hours, which is wrong but survivable; raising here would take the
        # page down.
        return datetime.now(_tz.utc)


def current_notes_week(season_start=None, now=None):
    """
    The week notes are currently being collected for, and when it closes.

    Returns (week_number, season_year, closes_at). The week rolls at
    midnight Eastern on Tuesday - the moment the Monday deadline passes.

    season_start is the date of the season's first game week. Without one
    the week number is derived from the NFL's usual early-September start,
    which is right for the overwhelming majority of leagues and adjustable
    per subscription later.
    """
    from datetime import datetime, timedelta, date

    now = now or _eastern_now()
    today = now.date()

    # The most recent Tuesday midnight. Anything after it belongs to the new
    # week; anything before belongs to the week that is still open.
    days_since_tue = (today.weekday() - 1) % 7
    week_opened = today - timedelta(days=days_since_tue)

    # Closes at the end of the following Monday.
    closes = datetime.combine(week_opened + timedelta(days=6),
                              datetime.max.time())

    if season_start is None:
        # First Tuesday on or after 1 September - close enough to the NFL's
        # opening week for a default, and overridable per league later.
        sep = date(today.year if today.month >= 3 else today.year - 1, 9, 1)
        season_start = sep + timedelta(days=(1 - sep.weekday()) % 7)

    week = ((week_opened - season_start).days // 7) + 1
    season_year = season_start.year

    # Before the season opens the counter would go negative or zero.
    week = max(1, week)

    return week, season_year, closes
