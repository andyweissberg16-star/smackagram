"""
Smackcast — weekly fantasy football recap generation. Pulls real
matchup data (via sleeper_service for now; espn_service/yahoo_service
follow the same shape once built) and turns it into a savage,
Smackagram-toned script covering every matchup in the league, sized to
the league's team count.
"""
import os
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


_REACTION_TYPES = ("boo", "laugh", "cheer", "gasp", "trombone", "flourish", "aww", "none")


def generate_weekly_recap_script(league_name: str, week: int, matchups: list, team_count: int, sport: str = "nfl") -> dict:
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
        f"This week's matchups:\n{matchups_block}\n\n"
        f"Write the recap."
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
    filename = f"tts/{uuid.uuid4()}.png"
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
    for i in range(1, _MAX_SFX_VARIANTS + 1):
        path = os.path.join(_SFX_DIR, f"smackcast-{reaction}-{i}.mp3")
        if os.path.exists(path):
            existing_paths.append(path)

    if not existing_paths:
        return None

    chosen_path = random.choice(existing_paths)
    try:
        return AudioSegment.from_mp3(chosen_path)
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
    for acronym, spoken in SPEECH_PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(acronym)}\b", spoken, text)

    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# A music bed shorter than the read gets looped - but only if the gap is
# large enough that a loop sounds intentional. Anything smaller and the
# restart reads as a glitch, so the bed is padded with silence and faded out
# instead. 4s is roughly the shortest repeat that still sounds like music
# rather than a mistake.
MUSIC_LOOP_MIN_GAP_MS = 4000


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

    combined = AudioSegment.empty()

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
    combined += _standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[0])))

    for i, seg in enumerate(segments):
        # A real beat before each new matchup. Spoken transitions carry most of
        # the work, but back-to-back speech with no gap still runs together to
        # the ear. Skipped before the first segment, which follows the intro
        # and already has the intro's own trailing pause.
        if i > 0:
            combined += AudioSegment.silent(duration=450)

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

                if shortfall > 0:
                    # Only loop when the gap is big enough to be worth it. A
                    # bed a second or two shorter than the read would
                    # otherwise restart for that last second - a very audible
                    # jump right at the end of the ad, and worse than simply
                    # running out. Below the threshold the bed is padded with
                    # silence instead and the fade carries it out.
                    if shortfall >= MUSIC_LOOP_MIN_GAP_MS:
                        loops = (len(spoken) // max(1, len(bed))) + 1
                        bed = bed * loops
                    else:
                        bed = bed + AudioSegment.silent(duration=shortfall)

                bed = bed[: len(spoken)]
                fade = int(seg.get("music_fade_ms", 600))
                bed = bed.fade_in(fade).fade_out(fade) + float(seg.get("music_gain_db", -20.0))
                spoken = spoken.overlay(bed)
            except Exception as e:
                print(f"[audio] music bed failed ({e}); running the read dry", flush=True)
        elif bed_path:
            print(f"[audio] music bed not found at {bed_path}; running the read dry", flush=True)

        combined += spoken

        sfx = _pick_random_sfx(seg.get("reaction", "none"))
        if sfx is not None:
            # A brief pause before the effect so it doesn't feel like it's
            # cutting off the last word of the segment.
            combined += AudioSegment.silent(duration=200)
            combined += _standardize(sfx) + SFX_VOLUME_REDUCTION_DB

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

        combined += signoff
        del hit_clip, tail_clip, signoff
    elif outro:
        combined += _standardize(AudioSegment.from_mp3(io.BytesIO(speech_bytes[-1])))

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
    buffer = io.BytesIO()
    combined.export(buffer, format="mp3", parameters=["-b:a", "192k"])
    combined_bytes = buffer.getvalue()
    normalized_bytes = elevenlabs_service.normalize_loudness(combined_bytes)

    s3_bucket = os.environ["AUDIO_S3_BUCKET"]
    s3_region = os.environ.get("AWS_REGION", "us-east-1")
    filename = f"tts/{uuid.uuid4()}.mp3"
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(Bucket=s3_bucket, Key=filename, Body=normalized_bytes, ContentType="audio/mpeg")

    return f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"
