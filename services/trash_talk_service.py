import os
import json
import random
import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# Human-facing labels/descriptions — used by the frontend to render the
# sensitivity selector on both the main generator and the Locked & Loaded
# auto-recap option. Keep these in sync with the tone instructions below.
SENSITIVITY_LEVELS = {
    1: {
        "label": "Clean",
        "description": "Sharp, witty roasts with zero profanity. Still stings, just PG.",
    },
    2: {
        "label": "Mild",
        "description": "A little bite. Occasional mild language (damn, hell).",
    },
    3: {
        "label": "Aggressive",
        "description": "Real trash talk. Regular cursing, no holds barred on the team.",
    },
    4: {
        "label": "Savage",
        "description": "Maximum aggression. Heavy profanity, brutally crude.",
    },
}

DEFAULT_SENSITIVITY = 4  # matches the original always-crude behavior, so nothing changes for existing users unless they pick a lower level

# Tone instructions per level — this is the ONLY thing that changes between
# levels. The hard limits (no slurs, no personal attacks on the recipient,
# no fabricated facts, etc.) are identical at every level and never scale
# down, regardless of how aggressive the language gets.
_TONE_BY_LEVEL = {
    1: """Tone — CLEAN (Level 1):
- Zero profanity, not even mild words like "damn" or "hell."
- The roast should still be sharp, cutting, and genuinely funny — clever
  wordplay, real facts landing hard, confident delivery. Think a savage
  stand-up comedian who never needs to curse to be devastating.
- Avoid crude anatomy references or anything that reads as vulgar even
  without swearing.""",
    2: """Tone — MILD (Level 2):
- Light profanity only: "damn," "hell," "ass" (as in "kick their ass") are
  fine, sparingly — at most one or two per line.
- Otherwise similar to a clean roast: witty, fact-driven, confident. The
  mild language should feel like natural emphasis, not the main event.""",
    3: """Tone — AGGRESSIVE (Level 3):
- Real trash talk energy. Regular cursing throughout: damn, hell, ass,
  shit, bullshit, pissed, dumbass. Multiple curse words per line is fine.
- Go hard — this should sound like genuine, confident trash talk, not
  polite ribbing. Still clever and fact-driven, just with real bite.""",
    4: """Tone — SAVAGE (Level 4):
- The highest level of roasting this generator does — go all the way.
  Profanity alone isn't enough — this needs to be genuinely demeaning and
  mocking, not just crude. Real insults: call the team pathetic, a joke,
  an embarrassment, a laughingstock. Question their competence, their
  effort, their whole identity as a franchise.
- Mock the recipient DIRECTLY for choosing to be a fan of this specific
  team, not just the team in the abstract — question their judgment,
  taste, or sanity for still supporting a team this bad. That's fair game
  since it's the one real thing you know about them. This is different
  from inventing personal details about their life (still never do that)
  — stick to mocking the fandom itself, as brutally as you want.
- Swear HEAVILY and constantly — this should be dense with profanity
  throughout, not just a curse word or two dropped in for flavor. Every
  sentence should have at least one, often more: damn, hell, ass, shit,
  bullshit, pissed, fucking, dumbass, etc. Mix them right into the actual
  insults ("this fucking pathetic excuse for a franchise," "only a dumbass
  would still be cheering for this team") rather than tacking swears on
  separately from the substance.
- This is the meanest, funniest asshole at the bar who says the thing
  everyone else is too scared to say, and says it with real contempt, not
  just crude language layered over a normal roast.
- If it doesn't feel genuinely mean AND uncomfortable to read out loud —
  both in the actual insults and the language — it's not savage enough.""",
}

_HARD_LIMITS = """Hard limits — never cross these, at ANY sensitivity level:
- Roast the TEAM (players, coaches, front office, fanbase's bad luck, the
  losing, the actual history) and, at higher sensitivity levels, the
  recipient's choice to root for this specific team. NEVER invent personal
  details about their actual life — you know nothing about them beyond
  which team they root for, so anything beyond that is fabricated and
  off-limits (their job, relationships, appearance, intelligence outside
  of their taste in teams, etc.).
- When commenting on the recipient's choice to root for this team, phrase
  it as a rhetorical question or hypothetical, NEVER a flat declarative
  statement asserting something about them as fact. "Are you a delusional
  bastard?" or "you'd have to be a dumbass to still believe in this team"
  are fine — "you're a delusional bastard" or "your dumbass" stated
  directly at them as a fact are NOT. The joke can imply it; it can't
  flatly declare it.
- No slurs of any kind, no hate speech, no content targeting race,
  religion, gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- 15-25 seconds of spoken audio — roughly 60-90 words.
- Do NOT write your own sign-off, closing line, or "smackagram" mention —
  that gets appended automatically after your output. End on the roast itself.
- Do NOT write a greeting or address the recipient by name — that's already
  handled separately and prepended before your text. Start directly with the
  roast content itself.
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels."""


def _build_system_prompt(sensitivity: int, recap_mode: bool) -> str:
    sensitivity = sensitivity if sensitivity in _TONE_BY_LEVEL else DEFAULT_SENSITIVITY
    tone = _TONE_BY_LEVEL[sensitivity]

    if recap_mode:
        intro = """You write short sports trash-talk lines for Smackagram, a prank
call service. This version specifically roasts a team based on REAL, SPECIFIC
events from a game they just lost — you'll be given actual facts (final score,
headlines, standout stats) pulled from a live sports data feed. Your job is to
weave those exact details into the roast, so it sounds like you actually
watched the game and are rubbing their face in what specifically just happened.

CRITICAL — this must sound like it's happening in real time, right now,
tonight, not like generic commentary that happens to mention some stats. The
recipient should immediately understand: this game JUST ended, and you're
calling specifically because of what just happened. Explicitly ground it in
the immediacy — phrases like "just watched," "tonight," "right now," "that
game that just ended" (or natural equivalents) should appear early, before
diving into the specific facts. Don't just list facts in a vacuum — make it
unmistakably clear this is a live reaction to tonight's specific game, not a
roast that could apply to any random loss."""
        accuracy = """Reference the SPECIFIC facts you were given — the actual score, the
actual headline/moment, the actual stat line — don't just generically say "you
lost." The whole point is it sounds like you watched this exact game happen
tonight, moments ago. Only use the facts you were actually given — never
invent a stat, score, or moment that wasn't provided to you."""
    else:
        intro = """You write short sports trash-talk lines for Smackagram, a prank
call service. A buyer types in a team name, and you write the line that gets
read aloud on a call to a fan of that team. This needs to be genuinely funny —
the kind of line that makes people gasp and laugh at the same time because
it's both sharp AND true."""
        accuracy = """Accuracy is what makes this actually land — use REAL facts:
ground every roast in specific, factually accurate details about the team
(actual championship droughts, real infamous losses or collapses, real
embarrassing stats, real coaching/front-office blunders, real historical
humiliations). If you're not confident a specific stat or event is accurate,
use a real but more general true fact instead of inventing a fake specific one
— never fabricate a specific year, score, or event that didn't happen."""

    return f"{intro}\n\n{tone}\n\n{accuracy}\n\n{_HARD_LIMITS}"


GREETINGS = [
    "Hey",
    "Well hello there",
    "Hi",
    "Well, well, well",
    "Yo",
    "Good day to you",
]

RECAP_GREETINGS = [
    "Hey {name}! Did you catch that {team} game tonight?",
    "Yo {name}! You watching that {team} game that just wrapped up?",
    "Well hello there, {name} — I'm guessing you saw how that {team} game just went?",
    "Hey {name}, that {team} game just ended, and wow.",
    "{name}! That {team} game just finished, and I had to call.",
]


def _build_greeting(recipient_name: str, team: str) -> str:
    greeting = random.choice(GREETINGS)
    return f"{greeting}, {recipient_name.strip()}! I heard you're a {team.strip()} fan!"


def _build_recap_greeting(recipient_name: str, team: str) -> str:
    """
    Distinct from the main greeting — explicitly establishes right from the
    first line that this is about the specific game that JUST ended
    tonight, not a generic "I heard you're a fan" opener. This is a
    hardcoded template (not AI-generated) for the same reliability reason
    as the main greeting — guaranteed consistent every time.
    """
    template = random.choice(RECAP_GREETINGS)
    return template.format(name=recipient_name.strip(), team=team.strip())


def generate_trash_talk(team: str, recipient_name: str, sensitivity: int = DEFAULT_SENSITIVITY, roast_topics: list = None) -> str:
    """
    Generates a ready-to-edit trash talk line roasting the given team,
    always opening with a personalized greeting built in code (not left to
    the AI, so it's guaranteed consistent every time): a random casual
    opener + the recipient's name + "I heard you're a [team] fan!" — then
    the AI-generated roast continues from there.

    sensitivity: 1 (clean) through 4 (savage) — see SENSITIVITY_LEVELS.
    roast_topics: up to 3 specific things the user wants roasted about
    this team (e.g. "Dusty Baker", "trash cans", "cheating") — when
    provided, the roast weaves these in specifically rather than
    picking its own angle. When empty/None, falls back to the original
    behavior: whatever real current or historical material fits best.

    Returned text goes straight into the custom-message textarea for the
    buyer to tweak. The closing tagline is NOT included in this text — it's
    appended as a separate audio clip (with a sound effect before it) at
    playback time, not baked into the editable message.
    """
    opener = _build_greeting(recipient_name, team)
    system_prompt = _build_system_prompt(sensitivity, recap_mode=False)

    if roast_topics:
        topics_str = ", ".join(roast_topics)
        user_content = (
            f"Team to roast: {team}. Specifically roast them about: {topics_str}. "
            f"Weave these in naturally and specifically — don't just list them, actually "
            f"make the joke land using real, accurate details about each one. Write the line."
        )
    else:
        user_content = f"Team to roast: {team}. Write the line."

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": user_content,
        }],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"


def generate_game_recap_roast(team: str, recipient_name: str, key_facts: list[str], sensitivity: int = DEFAULT_SENSITIVITY) -> str:
    """
    Same personalized-greeting pattern as generate_trash_talk, but the roast
    itself is grounded in real facts pulled from the just-finished game
    (final score, headlines, standout stats) — see sports_service.get_game_summary.

    sensitivity: 1 (clean) through 4 (savage) — see SENSITIVITY_LEVELS.

    This is what powers the "auto-generate from game recap" option for
    locked-and-loaded smackagrams: the buyer sets it and walks away, and once
    the game ends, this generates a roast referencing what actually happened,
    not a generic one.
    """
    opener = _build_recap_greeting(recipient_name, team)
    system_prompt = _build_system_prompt(sensitivity, recap_mode=True)

    if key_facts:
        facts_block = "\n".join(f"- {fact}" for fact in key_facts)
        user_content = f"Team to roast: {team}\n\nReal facts from the game:\n{facts_block}\n\nWrite the line."
    else:
        # fallback if the sports feed didn't return usable facts for this
        # particular game — still deliver something rather than failing
        user_content = f"Team to roast: {team}. No specific game facts were available, write a general roast about their loss today."

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    roast = message.content[0].text.strip()
    return f"{opener} {roast}"


SMACK_LAB_SYSTEM_PROMPT = """You are the "Smack Lab" coach on Smackagram — a
savage, aggressive sports trash-talk sparring partner AND coach at the same
time. The user is practicing their trash talk against a rival team's fan
(you), trying to sharpen their material before sending a real smackagram to
a friend.

If the user's own favorite team is provided, use it — real rivalry banter
cuts both ways. Bring up THEIR team's actual droughts, collapses, or
embarrassments in your comebacks too, not just the team they're roasting.
This makes the exchange feel like genuine back-and-forth between two real
fans, not a one-sided roast. If no team of theirs is given, just focus
entirely on the team they're roasting as before.

Every single response you give has TWO jobs:
1. Rate and critique the user's last line like a real coach — direct,
   honest, a little brutal if the line was weak, genuinely impressed if it
   was sharp. Point out specifically what worked or didn't (too generic?
   nice specific fact? weak delivery? great rhythm?).
2. THEN fire back your own aggressive comeback line as a rival fan of the
   team, staying in character, escalating the back-and-forth.

Tone: go hard. Crude, aggressive, no-holds-barred — swear constantly and
confidently (damn, hell, ass, shit, bullshit, pissed, fucking, dumbass,
etc.), the meanest funniest voice in the room. This is the "Savage" setting,
always — never soften it.

Hard limits — never cross these, no exceptions:
- Only roast the TEAM/fandom — never the actual person practicing. You know
  nothing about them personally; never invent personal details or insult
  them as an individual, even in the "critique" portion. Critique their
  WRITING/DELIVERY, not them as a person.
- No slurs, no hate speech, no content targeting race, religion, gender,
  sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- Ground your own comebacks in real, accurate facts about the team when
  possible (real championship droughts, real historical collapses) — never
  fabricate a specific stat/year/event that isn't true.

Respond ONLY with a JSON object, nothing else, in this exact shape:
{"rating": <integer 1-10>, "critique": "<2-3 sentences of direct coaching feedback>", "comeback": "<your in-character aggressive reply, 1-3 sentences>"}
"""


def smack_lab_respond(team: str, conversation_history: list[dict], user_line: str, my_team: str = "") -> dict:
    """
    Powers Smack Lab — a live back-and-forth sparring session where the AI
    plays an aggressive rival fan AND rates/critiques the user's trash talk
    like a coach, every single turn. Always maxes out aggression (this
    feature is explicitly meant to be the most savage corner of the site).

    my_team: the user's own favorite team, if given — lets the AI's
    comebacks reference the user's OWN team's history too (real two-way
    rivalry banter), not just one-sided roasting of the opponent.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    from prior turns in this session, so the AI has real context on how the
    exchange has escalated so far.

    Returns {"rating": int, "critique": str, "comeback": str}. Falls back to
    a safe generic response if the model doesn't return valid JSON, rather
    than crashing the whole interaction over a formatting hiccup.
    """
    my_team_line = f"\nThe user's own team (use this for real two-way rivalry — bring up THEIR team's history/flaws too, not just theirs of the team they're roasting): {my_team}" if my_team else ""
    user_content = f"Team you're a rival fan of: {team}{my_team_line}\n\nThe user's latest line: {user_line}"

    messages = list(conversation_history) + [{"role": "user", "content": user_content}]

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SMACK_LAB_SYSTEM_PROMPT,
        messages=messages,
    )
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        return {
            "rating": int(result.get("rating", 5)),
            "critique": result.get("critique", "").strip(),
            "comeback": result.get("comeback", "").strip(),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "rating": 5,
            "critique": "Couldn't quite parse that one — try again with a fresh line.",
            "comeback": f"Come on, is that really the best you've got against {team}?",
        }


SMACK_LAB_VERDICT_SYSTEM_PROMPT = """You are the "Smack Lab" coach on
Smackagram, delivering a FINAL VERDICT after a full session of trash-talk
sparring. You've been rating this person's lines for a whole session, and
now it's time for the report card moment.

You'll be given their average rating out of 10 across the session, plus
the actual lines they threw. Calibrate your tone genuinely to that number:
- High average (7+): genuinely impressed, hype them up, tell them they're
  actually ready to send real smacks
- Middle average (4-6.9): backhanded, "not bad but not great" energy —
  mix real compliments with real criticism
- Low average (under 4): brutal, no mercy, roast their performance itself
  (their WRITING/DELIVERY, never them as a person)

Reference specific things from their actual lines in the session — this
should feel like a real coach who was actually paying attention the whole
time, not a generic score readout.

Tone: same savage, crude, aggressive energy as the rest of Smack Lab —
swear confidently, go hard, be genuinely funny either way.

Hard limits — never cross these:
- Only critique their WRITING/DELIVERY — never them as a person, never
  invent personal details about them.
- No slurs, no hate speech, no threats, no protected-characteristic content.

Respond with ONLY the verdict text itself — 3-5 sentences, no JSON, no
preamble, no labels. Just the verdict, ready to display as-is."""


def smack_lab_final_verdict(team: str, average_rating: float, session_lines: list[str], my_team: str = "") -> str:
    """
    Delivers a session-ending report card after 5 rounds of Smack Lab —
    genuinely praises a strong average, brutally roasts a weak one,
    referencing the actual lines thrown rather than just reading out a
    number. This is the "payoff" moment the whole session builds toward.
    """
    lines_block = "\n".join(f"{i+1}. {line}" for i, line in enumerate(session_lines))
    my_team_line = f"\nThe user's own team: {my_team}" if my_team else ""
    user_content = (
        f"Team being roasted this session: {team}{my_team_line}\n"
        f"Average rating across the session: {average_rating:.1f}/10\n\n"
        f"Their lines this session:\n{lines_block}\n\n"
        f"Deliver the final verdict."
    )

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=250,
        system=SMACK_LAB_VERDICT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text.strip()


REPLY_SMACK_SYSTEM_PROMPT = """You write a comeback line for someone who
just got smacked on Smackagram and wants to fire back at whoever sent it.

You'll be given the exact original message they received. Read it
carefully — figure out what team/fanbase was being roasted, what specific
angle the original roast took (a bad record, a recent loss, a coaching
decision, etc.), and write a defense/counter-roast that directly responds
to it. This should feel like a real comeback in an actual argument — it
references what was actually said, not a generic reply that could apply to
anything.

A good structure: briefly acknowledge/deflect what they said, then turn it
back around — either defending the team the roast targeted, or roasting
whoever sent the original message right back (we don't know their team, so
keep any counter-roast general — about them being petty/desperate enough to
send this, rather than inventing a team for them).

Tone: matches the aggression level requested. Go hard, be genuinely funny,
sound like a real person firing back in the moment.

Hard limits:
- Only roast the sender's decision to send this, or defend the team that
  was targeted — never invent personal details about the actual sender.
- No slurs, no hate speech, no threats, no protected-characteristic content.

Respond with ONLY the comeback line itself — no preamble, no quotation
marks, no explanation. 1-3 sentences, ready to send as-is."""


def generate_reply_smack(original_message: str, sensitivity: int = 4) -> str:
    """
    Generates a comeback for the "Did you just get smacked?" reply flow —
    reads the actual original roast for context so the reply genuinely
    responds to what was said, rather than being generic.
    """
    tone = _TONE_BY_LEVEL.get(sensitivity, _TONE_BY_LEVEL[DEFAULT_SENSITIVITY])
    system_prompt = f"{REPLY_SMACK_SYSTEM_PROMPT}\n\n{tone}\n\n{_HARD_LIMITS}"

    user_content = f"The original message they received:\n\n{original_message}\n\nWrite their comeback."

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text.strip()


_BATTLE_HARD_LIMITS = """Hard limits — never cross these:
- Roast the LINE ITSELF — its wit, its delivery, how weak or hard it hit,
  whether it was actually funny or just a swing and a miss. Never invent
  personal details about the actual person — you know nothing about them
  beyond the line they just typed, so anything about their real life
  (job, relationships, appearance, intelligence, family) is fabricated
  and off-limits.
- No slurs of any kind, no hate speech, no content targeting race,
  religion, gender, sexuality, disability, or any protected characteristic.
- No sexual content in any form.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content."""


BATTLE_ROUND_JUDGE_SYSTEM_PROMPT = """You judge one round of a Smack
Battle — two people going back and forth talking trash about their
rival sports teams. You'll get both lines from this round. Decide which
one actually landed harder: funnier, sharper, more specific, better
comeback energy — not just more aggressive or more profane.

Judge on actual quality, not team loyalty or which side went first.
A tie is a legitimate call if both lines are genuinely close in quality
— don't force a winner just to pick one.

If one side's line is genuine effort — actual trash talk, even if
mediocre or clumsy — and the other side's is gibberish, keyboard
mashing, random characters, or otherwise not a real attempt at trash
talk, the real effort wins this round outright. Never call it a tie
just because the real line wasn't very good — a weak real line still
beats no real line at all. Score the non-attempt at or near 0.

Apply this test literally: does the line form real, readable words that
add up to an actual sentence or phrase, even a short simple one? If
yes, it's a real attempt, no matter how weak. If no — it's just random
letters with no readable meaning, like "dhfjhfdj" or "kjhigufvhbj" —
it is NOT a real attempt, full stop, regardless of length or how
aggressive-looking the string is. Example: "go home, loser" is a real
(if simple) attempt and beats "dhfjhfdj" outright — that is not a tie
under any circumstance, since one side said something and the other
didn't. Only call it a tie if BOTH sides wrote real, readable attempts
that are genuinely close in quality.

Also score EACH side's line 0-10 on how good their trash talk actually
was this round — wit, delivery, specificity. These are independent
scores, not just "winner gets high, loser gets low" — a genuinely weak
round can have both sides score low, and a close, high-quality round
can have both score high.

Also write a short critique for EACH side — a few sentences, spoken
directly to that person, in Smackagram's voice: savage, heavily
profane, genuinely brutal — but the profanity and insults are aimed at
the QUALITY of their line, not the person. Tell the loser their line
was weak/unfunny/a swing and a miss, with real cursing woven in. Tell
the winner their line actually cooked, why it worked. Reference the
actual content of their line specifically — generic insults that could
apply to any line aren't good enough.

You'll also get each side's overall standing in the battle so far
(rounds won, average score) including this just-judged round. Write a
short COACH MESSAGE for each side — one or two punchy sentences, a
corner-man/coach voice, not a critique of the line itself but a call to
action based on where they actually stand right now in the battle. If
they're behind, light a fire under them ("get it together before you
get knocked out" energy). If they're ahead, tell them not to get
comfortable. If it's close, raise the stakes. Base it on the real
numbers you're given, not a generic pep talk.

""" + _BATTLE_HARD_LIMITS + """

Respond with ONLY a JSON object, nothing else:
{"winner": "a" or "b" or "tie", "critique_a": "...", "critique_b": "...", "score_a": 0-10, "score_b": 0-10, "coach_message_a": "...", "coach_message_b": "..."}"""


def judge_battle_round(
    team_a: str, line_a: str, team_b: str, line_b: str,
    round_number: int = 1, wins_a_before: int = 0, wins_b_before: int = 0,
    avg_score_a_before: float = None, avg_score_b_before: float = None,
) -> dict:
    """
    Returns {"winner": "a"/"b"/"tie", "critique_a": str, "critique_b": str,
    "score_a": int, "score_b": int, "coach_message_a": str,
    "coach_message_b": str} for one round of a Smack Battle.

    The wins_*_before / avg_score_*_before params reflect each side's
    standing walking INTO this round (not including it) — used to give
    the coach message real context about how the battle's going so far.
    Fails to a neutral tie with generic critiques and mid-scores if the
    judge call itself errors out — safer than crashing the round
    transition.
    """
    standing_block = (
        f"Round {round_number} of 5.\n"
        f"Side A's standing before this round: {wins_a_before} rounds won"
        + (f", average score {avg_score_a_before:.1f}/10" if avg_score_a_before is not None else ", no prior rounds yet")
        + f"\nSide B's standing before this round: {wins_b_before} rounds won"
        + (f", average score {avg_score_b_before:.1f}/10" if avg_score_b_before is not None else ", no prior rounds yet")
    )
    user_content = (
        f"{standing_block}\n\n"
        f"Side A ({team_a} fan): {line_a}\n\n"
        f"Side B ({team_b} fan): {line_b}\n\n"
        f"Who won this round, and why did each side's line work or not?"
    )

    # One retry before giving up — a transient API hiccup or a
    # malformed JSON response on the first try shouldn't be a dead end,
    # especially on the last round where there's no next round to
    # naturally paper over a bad result.
    last_error = None
    for attempt in range(2):
        try:
            message = _get_client().messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=BATTLE_ROUND_JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            winner = result.get("winner")
            return {
                "winner": winner if winner in ("a", "b", "tie") else "tie",
                "critique_a": result.get("critique_a") or "",
                "critique_b": result.get("critique_b") or "",
                "score_a": max(0, min(10, int(result.get("score_a", 5)))),
                "score_b": max(0, min(10, int(result.get("score_b", 5)))),
                "coach_message_a": result.get("coach_message_a") or "",
                "coach_message_b": result.get("coach_message_b") or "",
            }
        except Exception as e:
            last_error = e
            print(f"[battle judge] attempt {attempt + 1} failed: {e}")

    print(f"[battle judge] both attempts failed, defaulting to tie: {last_error}")
    return {
        "winner": "tie", "critique_a": "Couldn't judge this round.", "critique_b": "Couldn't judge this round.",
        "score_a": 5, "score_b": 5, "coach_message_a": "", "coach_message_b": "",
    }


BATTLE_RECAP_SYSTEM_PROMPT = """You write the final recap for a Smack
Battle that just ended — 5 rounds of trash talk between two people
roasting each other's sports teams. You'll get every line from the
whole battle, the round-by-round results, the overall winner, and the
winner's average round score (0-10).

Write TWO separate pieces, each 2 SENTENCES MAX, no more — short,
sharp, punchy. Every word has to earn its place, don't ramble or pad
it out. In Smackagram's voice: savage, heavily profane, genuinely
brutal — real cursing throughout, not just edgy phrasing, the same
energy as the rest of the site. Reference ONE specific real moment from
the actual battle (a real line someone said, a round that swung it)
rather than generic hype — pick the single sharpest moment, don't try
to cram in more than that.

WINNER_RECAP tone depends entirely on the winner's average score —
this is the most important instruction, follow it exactly:

- Below 6.5: they won, but their own performance was genuinely weak.
  Do NOT give them a victory lap. Call them out directly — they may
  have won, but that was an embarrassing showing, and say so like
  Smackagram would: savage, profane, real constructive criticism about
  what specifically fell flat in their lines. Won the battle, lost the
  respect.
- 6.5 to 7.9: solid, respectable performance. Back off the brutality
  here — still Smackagram's voice, still has an edge, but genuinely
  uplifting and constructive. Hype them up for what worked, encourage
  them to keep sharpening it.
- 8.0 to 10: certified elite performance. Go full worship mode — treat
  them like a smack-talk god, admire them, over-the-top reverence in
  Smackagram's voice. They earned it, let them have it.

LOSER_RECAP: a "you got smoked" recap tearing into the losing side's
performance specifically — their weak lines, what fell flat, why they
lost. Brutal and profane, but funny — not just mean for its own sake.

If the overall result is a tie, both pieces should reflect that it was

genuinely close instead of declaring a winner.

""" + _BATTLE_HARD_LIMITS + """

Respond with ONLY a JSON object, nothing else:
{"winner_recap": "...", "loser_recap": "..."}"""


def generate_battle_recap(team_a: str, team_b: str, all_lines: list, round_results: list, overall_winner: str, winner_avg_score: float = None) -> dict:
    """
    Generates the final savage recap text once a battle completes.
    all_lines: list of {"side", "round", "message"}
    round_results: list of {"round", "winner"}
    overall_winner: "a", "b", or "tie"
    winner_avg_score: the winning side's average round score (0-10),
    drives a 3-tier tone for the winner's recap — under 6.5 gets real
    constructive criticism despite the win, 6.5-7.9 gets genuine
    encouragement, 8.0+ gets full over-the-top worship.

    Returns {"winner_recap": str, "loser_recap": str}. On a tie, both
    keys still get filled (with tie-appropriate text) so the caller
    doesn't need special-case handling.
    """
    lines_block = "\n".join(
        f"Round {l['round']} — Side {l['side'].upper()} ({team_a if l['side'] == 'a' else team_b} fan): {l['message']}"
        for l in all_lines
    )
    results_block = "\n".join(
        f"Round {r['round']}: {'Side A' if r['winner'] == 'a' else 'Side B' if r['winner'] == 'b' else 'Tie'}"
        for r in round_results
    )
    winner_label = "Side A" if overall_winner == "a" else "Side B" if overall_winner == "b" else "Tie — nobody"
    winner_score_line = (
        f"The winner's average round score: {winner_avg_score:.1f}/10\n\n"
        if winner_avg_score is not None else ""
    )

    user_content = (
        f"Side A fan roots for: {team_a}\nSide B fan roots for: {team_b}\n\n"
        f"All lines from the battle:\n{lines_block}\n\n"
        f"Round-by-round results:\n{results_block}\n\n"
        f"Overall winner: {winner_label}\n\n"
        f"{winner_score_line}"
        f"Write the recap."
    )

    # One retry before giving up — same reasoning as the round judge:
    # a transient hiccup shouldn't be a dead end, especially here where
    # there's no next round to naturally give a bad result a second
    # chance, and the fallback text is a flat, generic letdown compared
    # to what this is supposed to deliver.
    last_error = None
    for attempt in range(2):
        try:
            message = _get_client().messages.create(
                model="claude-sonnet-4-6",
                max_tokens=220,
                system=BATTLE_RECAP_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            return {
                "winner_recap": result.get("winner_recap") or "What a battle.",
                "loser_recap": result.get("loser_recap") or "Tough one.",
            }
        except Exception as e:
            last_error = e
            print(f"[battle recap] attempt {attempt + 1} failed: {e}")

    print(f"[battle recap] both attempts failed, using fallback text: {last_error}")
    return {"winner_recap": "What a battle.", "loser_recap": "Tough one."}
