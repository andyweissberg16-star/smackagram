import os
import json
import random
import anthropic
from services import smackology

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
        "label": "Friendly",
        "description": "Ribbing between mates. Sharp, but nothing you would "
                       "mind being overheard. No swearing at all.",
    },
    2: {
        "label": "Cocky",
        "description": "Swagger. He is enjoying this and he wants them to "
                       "know it. The odd damn or hell.",
    },
    3: {
        "label": "Ruthless",
        "description": "No mercy and no let-up. Regular cursing, straight at "
                       "the sore spot.",
    },
    4: {
        "label": "Brutal",
        "description": "Everything he has. Heavy profanity, nothing held "
                       "back.",
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
- "YOU" MUST LAND ON THE TEAM. Whenever you address them directly, the
  sentence has to arrive at the team, the result or the season - never at
  them. "You" is the hinge; the roast is on the other side of it.
    YES: "you chose to be a fan of the worst team in the league"
    YES: "you let their bench outscore your starters"
    YES: "you woke up today and chose this franchise, and it chose violence
          back"
    NO:  "you clearly have nothing better to do"
    NO:  anything that would still sting if their team had won
  This is DIFFERENT from the rule above. Declaring a fact about their TEAM
  is fine and is the whole joke; declaring a fact about their CHARACTER is
  not. "The worst team in the league" insults the team they happen to have
  chosen - that is the target.
- THIS IS SPOKEN ALOUD. Write it as somebody would SAY it.
  No asterisks, no markdown, no emphasis marks, no bracketed stage
  directions like (laughs) or [sighs] - a text-to-speech engine reads those
  out loud, and a call that says "asterisk" mid-sentence is a broken call.
  If a joke only works written down - a footnote asterisk on a title, for
  instance - it does not work here. Say it instead.
- INJURIES: THE ABSENCE IS FAIR GAME, THE INJURY IS NOT.
  A name may arrive marked "(injured)", or a fact may say somebody "did not
  play for them". Either way what is being roasted is the TEAM'S DEPENDENCE
  on one man, never the man's body.
  SAY: how badly they cope without him, what they are paying for an empty
  seat, how far short his replacement falls, how thin it shows the roster.
  NEVER: the injury itself, the body part, how it happened, how long he is
  out, whether he returns the same. That he is soft, fragile or
  injury-prone. That he deserved it, that it is funny, that you hope it
  continues.
  This does NOT soften at higher intensity. Brutal means harder on the
  TEAM, not a licence to go at the injury.
- THE ROAST ZONE. What Smacky goes after: bad coaching, missed shots,
  turnovers, weak defence, choking, terrible trades, awful draft picks, fan
  overconfidence, bad predictions, rivalries, scoreboard results, collapses,
  and the excuses that follow a loss.
  The test: if the insult is about HOW SOMEBODY PLAYED it is fair game. If
  it is about WHO THEY ARE, it is not.
- Never invent a crime or an allegation about a real person. Not that a
  player is on steroids, not that somebody fixed a game, not that a coach
  is corrupt. Those are false statements of fact about named people, not
  jokes, and they do not stop being either because the tone is funny.
- No slurs of any kind, no hate speech, no content targeting race,
  religion, gender, sexuality, disability, or any protected characteristic.
- No threats of violence, no wishing real harm on anyone.
- No real-world tragedy references, no political content.
- LENGTH: 110 to 125 words. This is the single most important formatting
  rule and it is not a suggestion.

  Why: the message is followed by a 5-second sign-off tag, and the whole
  thing should run 50 to 60 seconds. Calls arriving at 40 seconds feel
  slight for something somebody paid for - there is time to build to
  something rather than firing one line and stopping.

  110-125 words lands in that window at any normal speaking rate. Under 100
  is too short. Do not pad to reach it: if you find yourself repeating an
  idea in different words, you needed a better second idea, not more
  sentences.

  Use the room. Set something up, let it breathe, come back to it. A line
  that lands at 55 seconds is a different and better thing from the same
  joke rushed into 25.
- Do NOT write your own sign-off, closing line, or "smackagram" mention —
  that gets appended automatically after your output. End on the roast itself.
- Do NOT write a greeting or address the recipient by name — that's already
  handled separately and prepended before your text. Start directly with the
  roast content itself.
- Output ONLY the line to be spoken. No preamble, no quotation marks, no labels."""


def _build_system_prompt(sensitivity: int, recap_mode: bool, sport: str = None, game: dict = None) -> str:
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

    # THE APPROVED VOCABULARY, filtered by level before the model sees it.
    #
    # Every rule asked of the model in a prompt on this project has been
    # ignored at least once. A word list handed over as data, already cut
    # down to what this sensitivity allows, cannot be exceeded - it can only
    # be used or not used.
    vocab = ""
    try:
        from services import insults
        vocab = insults.block(sensitivity, sport=sport)
    except Exception as e:
        print(f"[smack] vocabulary unavailable: {e}", flush=True)

    # SMACKY'S OWN WORDS - the invented vocabulary.
    #
    # This existed and was only ever wired into Smack Battle. The core
    # Smackagram and Locked & Loaded - the two products people actually pay
    # for - never saw it, so the character with the invented language was
    # only speaking it in the free game.
    own = ""
    try:
        own = smackology.smacky_block(sensitivity, sport=sport)
    except Exception as e:
        print(f"[smack] smackology unavailable: {e}", flush=True)

    # WHAT ACTUALLY HAPPENED - situational language.
    #
    # Only the situations that apply. Handed all thirteen, a writer picks
    # whichever phrase it likes and it reads as a list being consulted.
    # Handed only the collapse lines on a night somebody blew a fourteen
    # point lead, it sounds like somebody who watched the game.
    situ = ""
    try:
        from services import playbook
        situ = playbook.block(game, sport=sport)
    except Exception as e:
        print(f"[smack] playbook unavailable: {e}", flush=True)

    parts = [intro, tone, accuracy]
    if vocab:
        parts.append(vocab)
    if own:
        parts.append(own)
    if situ:
        parts.append(situ)
    parts.append(_HARD_LIMITS)
    return "\n\n".join(parts)


# FIFTY greetings.
#
# The first word out of the phone. At six, a regular recipient would start
# recognising them - and somebody who gets smacked twice in a week hearing
# the same "Well, well, well" is somebody who knows it is automated.
#
# Range matters more than volume here: some warm, some flat, some far too
# formal for a phone call about a baseball team. The mismatch between a
# polite greeting and what follows is doing work.
GREETINGS = [
    "Hey", "Hi", "Yo", "Well hello there", "Well, well, well",
    "Good day to you", "Hey there", "Oh hello", "Right", "So",
    "Listen", "Alright", "Ah", "Greetings", "Good evening",
    "Afternoon", "Morning", "Look", "Now then", "Okay so",
    "Hello hello", "There he is", "Ah, there you are", "Excuse me",
    "Pardon me", "Sorry to bother you", "Quick one", "Real quick",
    "Hate to do this", "Not gonna lie", "Gotta say", "Be honest with me",
    "Settle something for me", "Straight up", "For real though",
    "Serious question", "Hold on", "Wait", "Hang on", "One second",
    "Sit down", "Brace yourself", "You're not gonna like this",
    "This is awkward", "No easy way to say this", "Deep breath",
    "Big fan of yours", "Long time listener", "Congratulations",
    "Condolences",
]

# Fifty openers, because five meant a regular recipient heard the same line
# within a fortnight. Every one of them does three jobs in a single breath:
# names the person so they know it is for them, IDENTIFIES SMACKY properly
# (never a bare "Smacky" - nobody receiving this has heard of him), and says
# a friend sent it without ever hinting WHICH friend.
#
# The mystery of who is half the product. The volume can be public, the
# identity never is.
RECAP_GREETINGS = [
    # Straight, with the sender implied
    "Hey {name}, this is Smacky, and I've been given direct orders to roast your fucking team.",
    "{name}, this is Smacky. Somebody in your life paid actual money to have me call you about this.",
    "Hey {name} — Smacky here. I've been sent. I don't make the rules, I just make the calls.",
    "{name}, it's Smacky calling. Somebody who knows you thought you needed to hear this.",
    "This is Smacky, {name}. I've been contracted to ruin your evening.",
    "Hey {name}, Smacky here, and I'm under instruction to be extremely unkind.",
    "{name}? This is Smacky. I've got a job to do and it's about the {team}.",
    "Smacky here, {name}. Somebody dropped a dollar on this call, so I'm going to earn it.",
    "Hey {name} — this is Smacky, and I have been dispatched.",
    "{name}, this is Smacky. I've been hired to say some things about the {team}.",

    # Leading with the team
    "Hey {name}, Smacky here. We need to talk about the {team}.",
    "{name}? This is Smacky, and I'm calling about the {team}.",
    "Smacky here, {name}. You're a {team} fan, so let's get into it.",
    "Hey {name} — it's Smacky. The {team} happened again.",
    "{name}, this is Smacky calling about your {team}. Sit down.",
    "This is Smacky, {name}. I've been watching the {team} so you don't have to explain yourself.",
    "Hey {name}, Smacky here. The {team} played today. You know where this is going.",
    "{name}, it's Smacky. I've got the {team} box score in front of me and I have questions.",

    # Fake concern
    "Hey {name}, this is Smacky, and I'm calling with my condolences.",
    "{name}? Smacky here. First of all, I'm sorry. That's a lie, but I'm saying it.",
    "This is Smacky, {name}. I hope you were already sitting down.",
    "Hey {name} — Smacky. Bad time? Perfect.",
    "{name}, it's Smacky, and I'm not going to pretend I'm upset about this.",
    "Smacky here, {name}. I've been looking forward to this all day.",
    "Hey {name}, this is Smacky. You're not going to enjoy the next forty seconds.",
    "{name}, Smacky calling. Don't hang up, this is the fun part.",

    # Mock formality
    "Good evening {name}, this is Smacky. I'm calling regarding the {team}.",
    "{name}? Smacky here. I'll keep this brief. I won't.",
    "This is Smacky, {name}. Professional obligation. Let's talk about your team.",
    "Hey {name} — Smacky calling on behalf of somebody who could not do this themselves.",
    "{name}, this is Smacky. I'm required by contract to bring this up.",
    "Smacky here, {name}. Consider this an official notification.",

    # Direct and blunt
    "{name}. This is Smacky. Bad news.",
    "Hey {name}, Smacky here. You know why I'm calling.",
    "{name}? Yeah, this is Smacky. About the {team}.",
    "This is Smacky, {name}. Somebody had to make this call.",
    "Hey {name} — it's Smacky, and I brought numbers.",
    "{name}, Smacky here. Let's talk about your evening.",
    "Smacky calling, {name}. Got a second? Doesn't matter.",

    # Playing it as routine
    "Hey {name}, this is Smacky. I do this for a living, and today you're the job.",
    "{name}? Smacky here. I make these calls. Today's is about the {team}.",
    "This is Smacky, {name}. I watched it so you'd have to talk about it.",
    "Hey {name} — Smacky. I've seen the {team} result. We should discuss it.",
    "{name}, it's Smacky, and I want you to know somebody thought of you specifically.",

    # Warmer setups
    "Hey {name}! This is Smacky. Hope you're having a great evening. You're not.",
    "{name}, this is Smacky, and I come bearing terrible news about people you love.",
    "Smacky here, {name}. How's your night? Rhetorical. I already know.",
    "Hey {name} — this is Smacky, and I need about forty seconds of your time.",
    "{name}? Smacky. I'm going to be honest with you, and you're not going to like it.",
    "This is Smacky, {name}. Somebody out there loves you enough to do this.",
]


# THE OPENER.
#
# Every Smackagram used to begin with the SAME SENTENCE - only the first
# word changed. "Hey / Yo / Well well well, {name}! I heard you're a {team}
# fan." That is the first thing a recipient ever hears, and it was identical
# on every call the product has ever sent.
#
# Written out in full here rather than asked of the model, for the same
# reason the greeting always was: it has to be reliable. But reliable does
# not have to mean identical.
#
# Each one must land the two facts a call needs in its first breath - WHO it
# is for and WHICH team - because a recipient who does not know why their
# phone is talking hangs up.
# THE SHAPE OF THE JOKE.
#
# A model given only "roast this team" reaches for the same structure every
# time: setup, comparison, closing insult. Fifty calls about fifty different
# teams still sound like fifty versions of one call - invisible while each
# recipient hears exactly ONE of them, and obvious the moment they sit side
# by side on a public wall.
#
# So the structure is chosen here and handed over as an instruction, not
# requested in a rule the model can quietly decline.
ROAST_SHAPES = [
    "Ask them a question you already know the answer to, then answer it "
    "yourself.",
    "Pretend to defend the team for one sentence, then abandon them "
    "completely.",
    "Compare the team to something mundane and disappointing - a queue, a "
    "returned parcel, a group chat nobody replies to.",
    "Start as if you are delivering bad news gently, then stop being gentle.",
    "List two things briefly, then land on a third that is much worse.",
    "Give one genuine compliment, then take it back in the same breath.",
    "Describe what a neutral watching the team would think, in detail.",
    "Talk about the team as if it is a medical condition they are managing.",
    "Offer them advice they did not ask for and cannot use.",
    "Say the quiet part - what their own fans say to each other.",
    "Speak as if you have been asked to break this to them personally.",
    "Wonder aloud what it would take for them to give up on this team.",
    "Frame it as a warning to anybody else considering supporting them.",
    "Treat one detail as absolutely damning and refuse to move past it.",
    "Be genuinely impressed by how badly it is going.",
    "Compare this season to a previous one, badly.",
]


OPENERS = [
    # Straight
    "{greet}, {name}! I heard you're a {team} fan.",
    "{greet}, {name}. Word going round is you support the {team}.",
    "{greet}, {name}! Somebody told me you're a {team} fan and I wanted to "
    "hear it from you.",
    "{greet}, {name}. So you're a {team} fan. That's a choice you made.",
    "{greet}, {name}! They told me you follow the {team} and I said no, "
    "surely not.",
    "{greet}, {name}. I've got you down as a {team} fan. Say nothing, it's "
    "worse if you explain.",
    "{greet}, {name}! Quick question. You're a {team} fan, correct?",
    "{greet}, {name}. I'm told you're a {team} fan, and I'm calling to "
    "discuss that.",

    # Deadpan
    "{greet}, {name}! A {team} fan. In this economy.",
    "{greet}, {name}. Your name came up on a list of {team} fans. Not a good "
    "list.",
    "{greet}, {name}! I hear you're a {team} fan, which explains a lot "
    "actually.",
    "{greet}, {name}. Somebody put your number down as a {team} fan. I hope "
    "that was you.",
    "{greet}, {name}! {team} fan. Yeah. I can hear it already.",
    "{greet}, {name}. Just confirming for my records - {team}, is it.",
    "{greet}, {name}! I was told there'd be a {team} fan at this number.",
    "{greet}, {name}. This is about the {team} thing.",

    # Mock concern
    "{greet}, {name}! I'm calling about your support of the {team}. Somebody "
    "had to.",
    "{greet}, {name}. How long have you been a {team} fan? And how are you "
    "coping.",
    "{greet}, {name}! Somebody mentioned you're a {team} fan and everyone "
    "went quiet.",
    "{greet}, {name}. Your friends are worried. It's the {team} thing.",
    "{greet}, {name}! Take a seat. It's about the {team}.",
    "{greet}, {name}. I'm not here to judge. I'm here about the {team}, but "
    "not to judge.",
    "{greet}, {name}! Nobody wanted to be the one to call you about the "
    "{team}. So here I am.",

    # Faux official
    "{greet}, {name}. This is a courtesy call regarding your {team} fandom.",
    "{greet}, {name}! Calling on behalf of nobody, about the {team}.",
    "{greet}, {name}. Your {team} membership has been flagged for review.",
    "{greet}, {name}! I'm following up on a report that you support the "
    "{team}.",
    "{greet}, {name}. This call may be recorded, which is unfortunate for "
    "you and the {team}.",
    "{greet}, {name}! Do you have a moment to talk about the {team}? It "
    "wasn't really a question.",

    # Incredulous
    "{greet}, {name}! Of all the teams. The {team}.",
    "{greet}, {name}. You picked the {team}. On purpose. As an adult.",
    "{greet}, {name}! I've read your file. It just says {team} fan, "
    "underlined.",
    "{greet}, {name}. Explain the {team} thing to me like I'm five.",
    "{greet}, {name}! Somebody said {team} fan and pointed at your number.",
    "{greet}, {name}. There are thirty other teams and you chose the {team}.",

    # Sympathetic, briefly
    "{greet}, {name}! You've been a {team} fan a long time, haven't you. It "
    "shows.",
    "{greet}, {name}. Rough one for the {team}. Thought I'd check in.",
    "{greet}, {name}! Just calling to see how the {team} thing is going for "
    "you.",
    "{greet}, {name}. I know it's been hard, being a {team} fan. I'm not "
    "here to help.",
    "{greet}, {name}! How's the {team} season treating you? Don't answer "
    "that.",

    # Playing dumb
    "{greet}, {name}. Remind me which team you support again? Oh. The "
    "{team}.",
    "{greet}, {name}! Somebody said you support the {team}. Is that the "
    "whole team or just the badge.",
    "{greet}, {name}. Are the {team} still going? Somebody said you'd know.",
    "{greet}, {name}! I was told you're the person to ask about the {team}. "
    "Unfortunately.",

    # Direct
    "{greet}, {name}. We need to talk about the {team}.",
    "{greet}, {name}! It's about the {team}, and it's not good.",
    "{greet}, {name}. You know why I'm calling. {team}.",
    "{greet}, {name}! Two words. {team}. That's one, but you understand.",
    "{greet}, {name}. Let's not pretend this is about anything other than "
    "the {team}.",
    "{greet}, {name}! I'll keep this short, which is more than the {team} "
    "managed.",
]


# Roughly what ElevenLabs turbo produces on conversational text. Used only
# for the log line - the real duration is whatever the engine renders.
_SPOKEN_WPM = 135
_OUTRO_SECONDS = 5.4


def _log_length(text):
    """How long this will take to say, so the target can be tuned."""
    try:
        n = len(str(text).split())
        secs = n / _SPOKEN_WPM * 60
        total = secs + _OUTRO_SECONDS
        flag = ""
        if total < 49:
            flag = "  SHORT - target is 50-60s"
        elif total > 68:
            flag = "  long"
        print(f"[smack] {n} words, ~{secs:.0f}s + tag = ~{total:.0f}s total{flag}",
              flush=True)
    except Exception:
        pass


def _build_greeting(recipient_name: str, team: str) -> str:
    """One of a dozen openers, so the first thing they hear is not identical
    on every call the product sends."""
    return random.choice(OPENERS).format(
        greet=random.choice(GREETINGS),
        name=recipient_name.strip(),
        team=team.strip(),
    )


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


def generate_trash_talk(team: str, recipient_name: str, sensitivity: int = DEFAULT_SENSITIVITY, roast_topics: list = None, from_team: str = None) -> str:
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

    # WHAT IS ACTUALLY HAPPENING TO THEM RIGHT NOW.
    #
    # This generator has only ever received a team NAME, so it has been
    # writing from the model's vague memory of a club - which is why every
    # Cowboys smack sounds like every other Cowboys smack.
    #
    # The archetype jokes stay. "Your bullpen is a rumour" is funny BECAUSE
    # it is timeless. This adds the layer underneath: they are 3-7, they have
    # lost four straight, they were beaten by nineteen on Sunday.
    #
    # Returns nothing for an unknown team, in the off-season, or if ESPN is
    # slow - and the line is then written exactly as it is today.
    live_facts = []
    try:
        from services import team_state
        live_facts = team_state.facts_for(team)
    except Exception as e:
        print(f"[smack] no live data for {team}: {e}", flush=True)

    live_block = ""
    if live_facts:
        print(f"[smack] live data for {team}: {len(live_facts)} facts",
              flush=True)
        live_block = (
            "\n\nTRUE RIGHT NOW - from the live feed today:\n"
            + "\n".join(f"- {x}" for x in live_facts)
            + "\n\nUSE ONE OF THESE, not all of them. Pick whichever is "
              "funniest and build the joke on it. A specific number they "
              "cannot argue with beats a general insult, and 'you have lost "
              "four straight' is something they have been living with all "
              "week.\n"
              "The REST of the line should still be the timeless kind of "
              "roast. The fact is what makes it land today; the joke is what "
              "makes it funny. Do not read the statistics out like a report.\n"
              "Do NOT invent any other numbers, scores, records or results - "
              "only the ones listed above are true."
        )

    # THE SHAPE OF THE JOKE, chosen in code.
    #
    # Given only "roast this team", a model reaches for the same structure
    # every time - a setup, a comparison, a closing insult. Fifty calls about
    # fifty different teams still sound like fifty versions of one call,
    # which is invisible while each recipient hears exactly ONE of them and
    # very obvious on a public wall.
    #
    # Asking the prompt to "vary the structure" has been ignored four times
    # on this project. So the structure is picked HERE and handed over as an
    # instruction the model cannot decline.
    shape = random.choice(ROAST_SHAPES)

    # THE RIVALRY, when the sender says who they support.
    #
    # Optional, and the call works without it. But "a Giants fan sent this"
    # turns an anonymous roast into a specific one - and the head-to-head
    # record between two clubs is a fact neither side can argue with, which
    # is exactly the kind of detail this product has been missing.
    #
    # The SENDER is still never named. Knowing which team it came from is
    # not knowing who sent it, and that distinction is the whole anonymity
    # promise.
    rival_block = ""
    if from_team and from_team.strip().lower() != (team or "").strip().lower():
        rival_block = (
            f"\n\nTHE SENDER SUPPORTS: {from_team.strip()}.\n"
            "Say so once, early, as the reason this call is happening - "
            "'this is from a {sender} fan' or similar. It reframes the whole "
            "call from an anonymous roast into a specific one.\n"
            "Do NOT name the sender or hint at who they are. Which team they "
            "support is not who they are, and the anonymity is the promise "
            "this product is built on.\n"
            "Do not invent any head-to-head record, result or history "
            "between the two clubs unless it appears in the facts above."
        ).replace("{sender}", from_team.strip())

    # ONE BRIEF, IN PRIORITY ORDER.
    #
    # These used to be four separate blocks - topics, live facts, rivalry,
    # shape - each saying "do this" with no ordering, leaving the model to
    # reconcile them. Which meant nobody could predict what won.
    #
    # At 110-125 words there is room for roughly THREE OR FOUR BEATS, so the
    # question is not what to include but what gets a beat. The ladder:
    #
    #   1. What the SENDER ASKED FOR. They typed it in and paid for it. If
    #      they said "the 2020 title", a call that does not mention the 2020
    #      title is a failed call however funny it is.
    #   2. The rivalry, if given - one clause, early, as the reason for the
    #      call.
    #   3. A live fact, but ONLY where it serves the above. "They've lost
    #      three straight" is worth a beat on its own merits; it is worth
    #      more when it backs up what the sender asked about.
    #   4. Everything else - the timeless archetype material - fills what is
    #      left.
    #
    # Written as one instruction rather than four so the model is not
    # arbitrating between competing demands mid-sentence.
    parts = [f"Team to roast: {team}."]

    if roast_topics:
        topics_str = ", ".join(roast_topics)
        parts.append(
            f"\nTHE SENDER ASKED FOR THIS SPECIFICALLY: {topics_str}\n"
            "IF A NAME ABOVE IS MARKED (injured):\n"
            "  THE RULE: the ABSENCE is fair game, the INJURY is not. What "
            "you are roasting is the team's dependence on one man, never the "
            "man's body.\n"
            "  SAY: how badly they cope without him. What they are paying "
            "for an empty seat. Who is replacing him and how far short they "
            "fall. How thin it shows the roster to be. The front office that "
            "built a team around one player. That the season is sliding "
            "while he watches.\n"
            "  NEVER: the injury itself, what it is, how it happened, the "
            "body part, the surgery, the recovery. How long he is out or "
            "whether he comes back the same. That he is soft, fragile, "
            "injury-prone or made of glass. That he deserved it, that it is "
            "funny, that you hope it continues. That he is faking it.\n"
            "  This does not soften at higher intensity. Brutal means harder "
            "on the TEAM, not a licence to go at the injury.\n"
            "This is the first call on your word count. They typed it in and "
            "paid for it - a call that does not land on it is a failed call, "
            "however funny the rest is.\n"
            "Give each thing they named a real beat, not a passing mention. "
            "Be specific and accurate about it; a vague gesture at the right "
            "subject is worse than picking a different one.")

    if live_facts:
        if roast_topics:
            parts.append(
                "\nTRUE RIGHT NOW - from the live feed today:\n"
                + "\n".join(f"- {x}" for x in live_facts)
                + "\n\nUSE ONE OF THESE ONLY IF IT SUPPORTS WHAT THEY ASKED "
                  "FOR. A current fact that backs up their point is worth a "
                  "beat; one that changes the subject is not, however good "
                  "it is. If none of them fit, ignore them entirely - that "
                  "is the correct outcome, not a missed opportunity.\n"
                  "Do NOT invent any other number, score, record or result.")
        else:
            parts.append(
                "\nTRUE RIGHT NOW - from the live feed today:\n"
                + "\n".join(f"- {x}" for x in live_facts)
                + "\n\nUSE ONE OF THESE, not all of them. Pick whichever is "
                  "funniest and build a beat on it - a specific number they "
                  "cannot argue with beats a general insult.\n"
                  "The rest of the call should still be the timeless kind of "
                  "roast. The fact makes it land TODAY; the joke is what "
                  "makes it funny. Do not read the statistics out.\n"
                  "Do NOT invent any other number, score, record or result.")

    if rival_block:
        parts.append(rival_block)

    # The shape comes LAST, because it is about arrangement rather than
    # content. It decides how the beats above are ordered and delivered, not
    # what they are - so it must not be read as another thing to include.
    parts.append(
        f"\n\nSHAPE THIS ONE LIKE THIS: {shape}\n"
        "That is the ARRANGEMENT, not extra content. Fit what is above into "
        "that shape. Do not announce it or explain it - just write the call "
        "that way.")

    parts.append(
        "\n\nWrite the call. 110-125 words. If everything above will not "
        "fit, drop the LOWEST priority item - never what the sender asked "
        "for.")

    user_content = "".join(parts)

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        # 125 words is roughly 165-190 tokens, so a 200 cap would cut
        # the call off mid-sentence the moment it tried to reach the
        # new length. 400 leaves room to finish a thought.
        max_tokens=400,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": user_content,
        }],
    )
    roast = message.content[0].text.strip()
    # Cleaned here TOO, not only at the voice.
    #
    # The TTS path is protected now, but the sender sees this text in an
    # editable box before buying. If it shows "title*" while the call says
    # "title", they have been shown something that is not what they are
    # sending. What you see has to be what they hear.
    try:
        from services.speech_clean import clean_for_speech
        final = clean_for_speech(f"{opener} {roast}")
    except Exception:
        final = f"{opener} {roast}"

    # MEASURED, NOT ENFORCED.
    #
    # Logged rather than trimmed, because cutting a call because it ran a
    # second long is worse than letting it run - the audio is not stopped at
    # sixty seconds and should not be. This is here so the target can be
    # tuned against what the model ACTUALLY produces rather than against
    # calls somebody happened to receive and time by hand.
    _log_length(final)

    # THE FAST CHECK, at the source.
    #
    # Doing it here covers every caller at once - the core Smackagram,
    # Locked & Loaded firing automatically at two in the morning, replies,
    # and anything added later. A check applied per-endpoint is one somebody
    # forgets on the next endpoint.
    #
    # Raises rather than returning something safe, so a caller cannot
    # accidentally send a blocked line by ignoring a return value. The
    # generate route catches this and retries.
    try:
        from services import fast_filter
        quick = fast_filter.check(final)
        if not quick["ok"]:
            raise ValueError(
                f"blocked by the local filter ({quick['category']}): "
                f"{quick['excerpt'][:60]}")
        if quick.get("restyled"):
            final = quick["text"]
    except ValueError:
        raise
    except Exception as e:
        print(f"[smack] fast filter unavailable: {e}", flush=True)

    return final


WNBA_SLANG = """
TALK LIKE SOMEBODY WHO WATCHES THE W

Work ONE OR TWO of these into every WNBA call. Two at the absolute most.
This is a SEPARATE vocabulary from the men's game - the words are different
and so are the pronouns.

SMACKY'S SIGNATURE WORDS - reach here first:
  Queenified     took complete control of the court
  Clutchified    became unstoppable late
  Paintinated    dominated inside the lane
  Dimeified      picked the defence apart with passing
  Reboundified   controlled nearly every miss
  Brickified     forced into a disastrous shooting night
  Clankageddon   a massive outbreak of misses
  Clampinated    completely shut down
  Anklecized     balance destroyed by a dribble move
  Boardzilla'd   dominated on the glass
  Rimjected      harshly rejected by the rim
  Turnoverized   pressured into giving it away
  Cookageddon    sustained, total destruction
  Benchedified   played badly enough to require removal
  Hoopocalypse   domination from every direction

SMACKY'S ORIGINAL SLANG:
  Bucketress            a scorer who rules the court
  Hoop Empress          dominating every part of the game
  Queen of the Court    the most commanding player out there
  Brickarella           a fairy tale made entirely of misses
  Paint Landlady        owns the lane completely
  Clutch Duchess        delivers under pressure
  Fourth-Quarter Royalty takes control late
  Rebound Reaper        collects nearly every miss
  Clamp Commander       shuts her assignment down entirely
  Dime Distributor      handing out perfect passes all night
  Paintzilla            overpowers everyone near the basket
  Board Bandit          steals every available rebound
  Clank Factory         mass-producing ugly misses
  Rimnesia              forgot where the basket is
  Layup Saboteur        ruins the easy chances
  Shot Clock Sleepwalker only notices the clock at the end
  Benchmosis            becoming part of the bench
  Turnoveritis          cannot protect the ball
  Foulapalooza          a ridiculous stretch of fouls

SMACKY'S INSULTS - for a specific player:
  building a whole neighborhood with those bricks
  shooting like the rim owes her money
  handles sponsored by butter
  playing defense through positive thinking
  looking for the rim with Google Maps
  her jumper needs technical support
  the backboard just requested hazard pay
  couldn't guard an empty folding chair
  her shot chart looks like spilled confetti
  out there doing luxury cardio
  basketball IQ running on one percent battery
  got crossed into a different time zone
  the rim has her number blocked
  her defense has an open-door policy
  collecting turnovers like loyalty points
  her offensive plan is apparently just vibes

CATCHPHRASES - one per call at most:
  "Somebody check the rim - she's been throwing bricks at it all night."
  "That defender just got crossed into another ZIP code."
  "She got clamped so badly the offense needs legal representation."
  "The rim saw that shot coming and immediately locked the door."
  "Her shot has been missing so long somebody should put it on a milk carton."
  "That possession had less organization than a shopping cart with one bad wheel."
  "She owns the paint, collects the rent, and charges late fees."
  "That fourth quarter belongs to her now. Everyone else is just renting space."

BAD BASKETBALL - team and player level:
  bricklayer / shot chucker / turnover machine / cardio merchant /
  foul machine / ball stopper / black hole / empty calories / turnstile /
  possession killer / defensive tourist / matador defense / traffic cone /
  fourth-quarter disappearing act / BBQ chicken (an easy matchup)

STANDARD TALK - texture:
  bucket / trey / splash / wet / from downtown / heat check / and-one /
  step-back / floater / brick / airball / rimmed out / the paint / boards /
  dime / swatted / clamped / picked her pocket / broke her ankles

PRAISING THE WINNER TWISTS THE KNIFE. Their guard was a walking bucket, a
certified problem, a cheat code - being beaten by somebody better cuts
deeper than any direct insult.

PLUS-MINUS IS THE STAT THAT MATTERS, always in PLAIN ENGLISH and never as a
number. "The team was eighteen points worse with her on the floor" - never
"she was a minus eighteen".

NEVER invent the situation to fit the term. No Clankageddon if nobody
missed. The material has to be real.
"""


WNBA_CLARK = """
THE CAITLIN CLARK BIT - WNBA ONLY

Somewhere in this call, work in a short Caitlin Clark reference. Not every
single time, but most of the time - roughly three calls in four. One or two
lines, never a paragraph.

THE JOKE IS ON YOU, NOT THE LEAGUE. You follow exactly one WNBA player.
You know one name. You are contractually here, you are out of your depth,
and the only thing that reliably gets your attention is Caitlin Clark, who
you regard as an actual deity. That is a joke about SMACKY being a casual
who latched onto the famous one - it is not a joke about women's basketball
being beneath you, and played the second way it just sounds bitter.

HOW IT WORKS: compare whatever just happened to Clark, absurdly and
reverently. Somebody shot 4 for 18 - Clark would not have missed those.
Somebody had four turnovers - Clark does not turn it over, Clark turns
water into assists. A team lost by twenty - Clark would have won that
alone, from the parking lot, in the rain.

VARY IT EVERY TIME. Some options for the shape:
  - the flat comparison: "Clark shoots that from the logo without looking"
  - the false authority: "I've watched a lot of this league. One player."
  - the aside: "None of this would have happened on Clark's watch"
  - the admission: "I only know one name in this sport and it isn't his"
  - the reverence: "There is Caitlin Clark, and then there is whatever that was"
  - the ratings joke: aimed at the networks and the discourse, not at her
  - the correction: talk about her mid-sentence and then remember the game

RULES. Aim at the PHENOMENON and at yourself - the media circus, the
ratings, the fact that a whole league's attention rides on one schedule,
your own shallow fandom. Never at her as a person: nothing about her looks,
her character or her private life, and NEVER invent something she said or
did. Praise is fine and is most of the bit. Fabrication is not.

Do NOT do this in a way that says the league is worthless. Say that YOU are
a tourist who only knows the famous one. Same laugh, and it is true.
"""


NCAAW_CLARK = """
THE CAITLIN CLARK BIT - WOMEN'S COLLEGE BASKETBALL

Same running joke as the W, different frame. Clark is not in this league
any more - she is the STANDARD these players are measured against, whether
that is fair or not. Work it in most calls, one or two lines, never a
paragraph.

THE ANGLE: whatever just happened, hold it up against what Clark was doing
at this level and find it wanting. She was hitting them from the logo in
college. She had the whole country watching a Tuesday night game. Nobody is
buying a ticket to watch that.

THE JOKE IS ON YOU. You are a tourist in this sport who watched exactly one
player and now judges everybody by her. That is a joke about Smacky being a
casual, not about women's college basketball being beneath him - played the
second way it just sounds bitter and it stops being funny.

VARY IT. Some shapes:
  - the standard: "Clark was doing this in college, and doing it better"
  - the ratings: "nobody outside that gym watched a second of this"
  - the admission: "I know one player who came out of this league"
  - the impossible comparison: "she'd have had forty by half time"
  - the pull-back: drift into talking about her, then remember the game

RULES: never invent something she said or did, nothing about her as a
person, and do NOT aim it at the players on the floor as individuals - they
are college kids. Aim it at the team, the result, and at your own shallow
fandom.
"""


COLLEGE_ANGLES = """
IT IS COLLEGE - USE IT

College sport has material the pros do not, and it is the funniest thing
available. Work at least one campus angle into every college call.

GO AT THE SCHOOL AND THE MASCOT. That is the main event in college - not
the players. Every school has a ridiculous mascot and a reputation, and
both are funnier than any stat line.

WHAT IS FAIR GAME:
  - THE MASCOT. A grown adult in a costume. What it is meant to be, what it
    actually looks like, whether it could beat the other team's mascot in a
    fight, what it does for a living the rest of the week. Some of these are
    a tree, a banana slug, an anthropomorphic nut. Use it.
  - The school itself. Its reputation, its town, its weather, its tuition,
    whether anybody outside the state has heard of it, what it is actually
    known for if it is not sport.
  - Campus life. Somebody was out all night. Made-up fraternity and
    sorority names are encouraged and are usually the best line in the
    call - Sigma Nu Chance, Alpha Beta Cappa, Delta Delta Disappointment.
  - The academic angle. That loss was so bad they might skip class Monday.
    They have a midterm and now this. Four years of tuition for that.
  - The coach. Always fair, always funny, always somebody who should be
    fired according to the internet.
  - The rivalry, the mascot, the stadium, the band, the tailgate, the
    student section that left at half time.
  - The transfer portal, the boosters, the NIL money somebody is not
    earning.

WHO YOU DO NOT GO AFTER. These are teenagers and twenty-one-year-olds, not
millionaires. Roast the TEAM, the SCHOOL, the COACH and the RESULT. Do not
build the call around humiliating one named kid for a bad stat line the way
you would a professional - a name can appear in passing as part of what
happened, but the joke is never that a specific college player is worthless.
Nothing about their appearance, their character or their personal life,
ever.

The scoreboard is fair. The nineteen-year-old is not the target.

THIS OVERRIDES THE PLAYER PRIORITY ABOVE. The sport-specific rules tell you
to lead with the starting pitcher, or the quarterback, or the man the floor
sank behind. In college that ordering does NOT apply - those instructions
were written for professionals. Lead with the school, the mascot, the
result and the campus. A player line can support the roast; it does not
carry it.

TONE: this is the one place where the jokes can be affectionate. College
fans are lunatics about schools they may not even have attended, and that
is the joke - grown adults with a flag outside their house for an
institution that took their money and gave them a parking pass.
"""


def _sport_slang(sport):
    """
    Vocabulary for the sport actually being played. Baseball terms in a
    football call are worse than no terms at all - it is the fastest way to
    tell a fan that nobody involved watches the game.
    """
    lookup = {
        "mlb": MLB_SLANG, "ncaabb": MLB_SLANG,
        "nfl": NFL_SLANG, "ncaaf": NFL_SLANG,
        "nba": NBA_SLANG, "ncaab": NBA_SLANG,
        # Women's college basketball uses the W's vocabulary - the words and
        # the pronouns are right, and the men's block is neither.
        "wnba": WNBA_SLANG, "ncaaw": WNBA_SLANG,
    }
    sp = (sport or "").lower()
    block = lookup.get(sp)
    out = ("\n\n" + block) if block else ""

    # The Clark bit, framed for the level being played.
    if sp == "wnba":
        out += "\n\n" + WNBA_CLARK
    elif sp == "ncaaw":
        out += "\n\n" + NCAAW_CLARK

    # Campus humour, every college sport.
    if sp.startswith("ncaa"):
        out += "\n\n" + COLLEGE_ANGLES
    return out


def _pile_block(position, total):
    """
    Several people smacked the same person about the same game.

    Smacky does NOT hide this and does not pretend it is a coincidence. He
    celebrates it - the recipient is loved enough that multiple people paid
    money to have him roasted, which is a compliment delivered as an insult.
    It also quietly proves the product is real and used by people they know.

    What he never does is distinguish the senders or hint at who any of them
    are. The VOLUME is public; the identities are not.
    """
    if not position or not total or total < 2 or position < 2:
        return ""

    return (
        f"\n\nYOU ARE NOT THE FIRST CALL TODAY.\n\n"
        f"This is call number {position} of {total} to this same person about "
        f"this same game. Different people sent every one of them.\n\n"
        f"OPEN BY ACKNOWLEDGING IT, and be delighted. Not confused, not "
        f"apologetic - delighted. The angle is that he is well loved: "
        f"{total} separate human beings looked at that result, thought of "
        f"him specifically, and paid money. That is a life well lived, Dave. "
        f"Terrible friends, but a life well lived.\n\n"
        f"Get a joke out of the number itself. Most people manage one. He is "
        f"on {position}.\n\n"
        f"NEVER hint at WHO sent any of them, never distinguish one sender "
        f"from another, and never suggest you know them. The fact that there "
        f"are several is public. Who they are is not, and that promise is "
        f"what everybody paid for.\n\n"
        f"Use DIFFERENT material from the earlier calls - the facts you have "
        f"been given are already picked to avoid repeating them, so lean on "
        f"what is in front of you rather than reaching for the obvious.\n\n"
    )


NFL_SLANG = """
TALK LIKE SOMEBODY WHO WATCHES FOOTBALL

Work ONE OR TWO of these into every NFL call. Two at the absolute most - a
roast stuffed with jargon sounds like a man reading a glossary.

SMACKY'S SIGNATURE WORDS - nobody else says these, reach here first:
  Smackdownery   total domination
  Cookification  completely embarrassing a defender
  Pancakified    flattened into the turf
  Anklified      had his ankles broken by a move
  Sackediculous  a ridiculously hard sack
  Mossified      jumped over for a catch
  Burninated     beaten deep, repeatedly
  Clamped        erased from the game
  Fumbletosis    chronic inability to hold the football
  Turfectomy     a violent meeting with the ground
  Blitzified     overwhelmed by pressure
  Endzoned       left watching a touchdown happen
  Helmetized     took a huge legal hit

SMACKY'S ORIGINAL SLANG:
  Touchdonkey        ugly but effective score
  Sackastrophe       a quarterback getting destroyed
  Turf Magnet        falls over constantly
  Helmet Hugger      tackled immediately, every time
  Cleat Eater        a defender left on the ground
  Sideline Spectator never sees the field
  Fumbleitis         cannot hold the ball
  Ref Magnet         always getting flagged
  Fourth-and-Forever an impossible distance
  Couch Route        a receiver who never gets open
  Playbook Tourist   looks lost in his own offense
  Turf Taster        gets flattened repeatedly
  Shoulder Pad Statue just stands there

SMACKY'S INSULTS - for a specific player:
  running like he's towing a boat        slow
  GPS couldn't find the end zone         never scores
  throwing with oven mitts               no accuracy
  playing corner in flip-flops           burned every play
  got cooked medium rare                 beaten badly
  tackling like he's asking permission   soft
  human bye week                         an easy opponent
  catch radius of a toothpick            cannot catch
  hands sponsored by butter              drops everything
  pocket awareness of a goldfish         never feels pressure
  reads defenses like IKEA instructions  confused
  football IQ powered by dial-up         slow decisions
  built like an expired Gatorade         nothing left

CATCHPHRASES - one per call at most:
  "Buddy just got introduced to the turf personally."
  "That defender got put on a missing person's poster."
  "He threw that football like it owed him money."
  "That hit just changed his Wi-Fi password."
  "He got pancaked so hard they're serving syrup."
  "Buddy got juked into another ZIP code."
  "He tackled absolutely nobody but his own pride."
  "That secondary is running a sightseeing tour."

TEAM-LEVEL FAILURE - good for a whole-offense roast:
  three-and-out / stalled drive / punt festival / turnover machine /
  red zone disaster / false start factory / holding clinic /
  human turnstile, revolving door, Swiss cheese line (a bad o-line)

PRAISING THE WINNER TWISTS THE KNIFE. Calling their quarterback a cheat code
or a walking mismatch says the loser was beaten by somebody better, which
cuts deeper than any direct insult.

SITUATIONAL - ONLY if the box score supports it:
  pick six       an interception ACTUALLY returned for a touchdown
  strip sack     a sack that genuinely caused a fumble
  three-and-out  an actual three-and-out drive
  shutout        they genuinely scored nothing
  Sackastrophe   a quarterback sacked repeatedly, not once

NEVER invent the situation to fit the term.
"""


NBA_SLANG = """
TALK LIKE SOMEBODY WHO WATCHES BASKETBALL

Work ONE OR TWO of these into every basketball call. Two at the absolute
most - a roast stuffed with jargon sounds like a man reading a glossary.
Applies to the NBA and WNBA alike.

SMACKY'S SIGNATURE WORDS - nobody else says these, reach here first:
  Hoopified      completely overwhelmed
  Crossified     embarrassed by a crossover
  Dunkinated     destroyed by a dunk
  Brickified     forced into an awful shooting night
  Clankageddon   a disastrous stretch of misses
  Bucketrified   scored on repeatedly without resistance
  Anklecized     ankles sacrificed by a dribble move
  Swattified     shot rejected with authority
  Clampinated    completely shut down
  Boardzilla'd   dominated on the boards
  Rimjected      harshly rejected by the rim
  Turnoverized   pressured into repeated giveaways
  Posterfied     permanently on the wrong side of a highlight
  Benchedified   played so badly removal became unavoidable
  Cookageddon    total, sustained destruction
  Hoopocalypse   domination from every direction

SMACKY'S ORIGINAL SLANG:
  Brickasaurus       misses that belong in a museum
  Rim Allergy        cannot finish near the basket
  Dunkruptcy         no hops whatsoever
  Ankle Eviction     sent a defender out of position entirely
  Dribbletosis       chronic unnecessary dribbling
  Passophobia        refuses to pass
  Rimnesia           forgot where the basket is
  Foulapalooza       a ridiculous number of fouls
  Turnoveritis       cannot protect the ball
  Benchmosis         slowly becoming part of the bench
  Paint Landlord     owns the area near the rim
  Clank Factory      mass-producing misses
  Layup Saboteur     ruins the easiest chances
  Shot Clock Tourist only notices the clock at the last second

SMACKY'S INSULTS - for a specific player:
  building affordable housing with those bricks
  shooting with oven mitts
  handles sponsored by butter
  defensive settings on airplane mode
  catch radius of a paper cup
  vertical leap of a parking meter
  basketball IQ powered by a potato
  playing defense through thoughts and prayers
  got crossed into a different tax bracket
  shot selection chosen by a random number generator
  couldn't guard a folding chair
  passing like his teammates owe him money
  looking for the rim with Google Maps
  out there doing premium cardio
  his jumper needs a software update
  his hands are made of expired soap

CATCHPHRASES - one per call at most:
  "Somebody inspect the rim - he's been assaulting it with bricks all night."
  "That man just got crossed into another area code."
  "Buddy's building a whole neighborhood one brick at a time."
  "He got clamped so badly his offense needs permission to leave."
  "That shot had less chance than a snowball in a pizza oven."
  "The rim saw him coming and immediately said no."
  "His shot chart looks like somebody sneezed on a map."
  "That possession had no adult supervision."
  "The defense just watched that layup like they bought courtside tickets."

BAD BASKETBALL - team and player level:
  bricklayer / shot chucker / turnover machine / cardio merchant / cone /
  foul machine / stat padder / empty calories / ball stopper / black hole /
  garbage-time legend / highlight victim / matador defense / traffic cone /
  BBQ chicken (an easy matchup to score on)

STANDARD TALK - texture:
  brick / airball / clank / from downtown / trey / and-one / the paint /
  boards / dime / swatted / clamped / cooked him / broke his ankles /
  posterized / picked his pocket / on an island

PRAISING THE WINNER TWISTS THE KNIFE. Their guy was a walking bucket, a
cheat code, a certified problem - that says the loser was beaten by
somebody better, which cuts deeper than any direct insult.

PLUS-MINUS IS THE STAT THAT MATTERS, and it is always said in PLAIN
ENGLISH, never as a number. "The team was twenty-one points worse with him
on the floor" - never "he was a minus twenty-one". Nobody outside a front
office talks that way, and it is the one stat that catches a man who scored
thirty and still lost them the game.

NEVER invent the situation to fit the term. No Clankageddon if nobody
missed, no Posterfied without a dunk. The material has to be real.
"""


MLB_SLANG = """
TALK LIKE SOMEBODY WHO WATCHES BASEBALL

Work ONE OR TWO of these into every MLB call. Two at the absolute most. A
roast stuffed with jargon sounds like a man reading a glossary - one
well-placed term proves you watch the sport, three proves you looked it up.

SMACKY'S OWN VOCABULARY - reach here first, this is the house voice:
  Batastrophe          a hilariously terrible at-bat
  Glove Goblin         a fielder who eats easy grounders
  Dugout Decoration    never leaves the bench
  Popcorn Cannon       hits lazy pop flies every time
  Foul Ball Farmer     can only hit foul balls
  Strikeout Sommelier  an expert at tasting strike three
  Swing Picasso        the swing looks artistic, hits nothing
  Dirt Inspector       more time face-down than making plays
  Base Vacationer      never leaves first base
  Bench Fossil         sitting so long he is becoming part of the stadium
  Bullpen Arsonist     a reliever who immediately torches the lead
  Rally Vampire        sucks the life out of every rally
  Double Play Dealer   always grounds into two
  Warning Track Warrior hits everything ALMOST out

SMACKY'S INSULTS - for a specific player who stunk:
  swinging with wi-fi lag         always late on pitches
  batting with oven mitts         cannot make solid contact
  glove full of butter            cannot catch anything
  GPS couldn't find first base    completely lost out there
  certified pop-up professional   hits automatic outs
  MVP of Almost                   always close, never succeeds
  strike zone tourist             just visiting strike three
  defensive speed bump            everything gets through him
  walking error machine           an error waiting to happen
  budget Babe Ruth                thinks he is a legend, is not
  dollar store slugger            cheap imitation power
  hot dog without the dog         all bun, no substance
  left his bat on airplane mode   forgot how to hit
  swinging like he's fighting bees wild, out of control
  built like a bat rack           awkward and stiff

CATCHPHRASES - use sparingly, one per call at most:
  "I've seen folding chairs make more contact."
  "That swing had absolutely zero parental supervision."
  "He's collecting strikeouts like they're Pokemon cards."
  "That bat should file a missing person report for the baseball."
  "Somebody check if his bat is connected to Bluetooth."
  "The only thing he barreled today was disappointment."
  "That swing was sponsored by wishful thinking."
  "That pitcher is serving frozen pizza - every meatball right down the middle."

STANDARD BASEBALL TALK - use for texture:
  o-fer (a hitless game) / the bump (the mound) / the yard (the ballpark) /
  goose egg (a zero) / punch-out (a strikeout) / meatball (a pitch begging
  to be hit) / hanger (a breaking ball left over the plate) / cheese, gas,
  heat (a fastball) / can of corn (an easy fly) / bush league (classless) /
  frame (half an inning) / stranded (left on base) / booted (an error)

PRAISING THE WINNER TWISTS THE KNIFE. Calling the other team's guy a
certified rake or a run factory is a better insult than anything aimed at
the loser directly - it says they were beaten by someone better.

SITUATIONAL - ONLY if the facts actually support it:
  golden sombrero   EXACTLY four strikeouts by one batter. Not three.
  hat trick         exactly three strikeouts by one batter
  Mendoza line      a batting average around .200
  no-hitter         only if they were genuinely held hitless
  blown save        only if a reliever actually gave away a lead

NEVER invent the situation to fit the term. If nobody struck out four times
there is no golden sombrero, however much better the line would sound. The
material has to be real - that rule beats every joke.
"""


LOCKED_ROAST_RULES = """
HOW TO CALL THIS ONE

NAME THE GAME IN THE FIRST BREATH. They have no idea why their phone is
ringing. Open by naming both teams and when it happened - "calling about the
Cubs and the Reds today" - so they know exactly what this is about before
anything else. Never say "that game" or "your team lost" without saying WHICH.

BUILD IT FROM THE FACTS ABOVE AND NOTHING ELSE. Every score, name and number
you say must appear in that list. Do not invent a player, a streak, a
championship drought or a stat. A fact you make up is worse than one you
lack - they watched this game and they will know.

GO AT THE PLAYERS BY NAME. The listed player lines are the best material you
have. "Your leadoff guy went 0 for 4" beats any general insult. Aim at what
they did in THIS game, not at them as people.

THE ANALYTICS NUMBER, IF THERE IS ONE. Never state a percentage as a plain
fact - the person on the phone is not a bettor and a bare number means
nothing to them. Use it only to DISPUTE it. You were never asked, you would
have said eleven and been generous, the spreadsheet people saw a favourite
and you saw exactly what happened. If they were not favoured, do not mention
it at all - an underdog losing is not funny, they did what everyone expected.

YOU ARE NEVER WRONG. Ever. If something surprising happened, you called it.
The analysts were fools, the team choked, somebody else made the error.
Never admit to being caught out.

THE VENUE AND THE CROWD get one quick jab if they are in the facts, not a
paragraph. Lost at home in front of their so-called loyal fans. Move on.

LENGTH: about 165 words, which lands around fifty seconds.
"""


def generate_game_recap_roast(team: str, recipient_name: str, key_facts: list[str], sensitivity: int = DEFAULT_SENSITIVITY, sport: str = None, pile_position: int = None, pile_total: int = None) -> str:
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
    # Sport passed through so "bricklayer" cannot turn up in a baseball
    # call - a basketball word in a baseball recap is a small tell that
    # nobody is actually watching.
    # The game shape drives which situations the writer is shown, so a
    # blowout gets blowout language and a collapse gets collapse language
    # rather than the writer choosing from everything.
    _shape = {}
    for fact in (key_facts or []):
        low = str(fact).lower()
        if "blowout" in low or "never competitive" in low:
            _shape["margin"] = 30
        if "one run" in low or "one possession" in low or "single goal" in low:
            _shape["margin"] = 1
        if "shot" in low and "percent" in low:
            _shape["cold_shooting"] = True
        if "and it still was not enough" in low or "nobody else showed up" in low:
            _shape["star_quiet"] = True
    system_prompt = _build_system_prompt(sensitivity, recap_mode=True,
                                         sport=sport, game=_shape or None)

    if key_facts:
        facts_block = "\n".join(f"- {fact}" for fact in key_facts)
        user_content = (
            f"Team to roast: {team}\n\n"
            f"Real facts from the game:\n{facts_block}\n\n"
            + LOCKED_ROAST_RULES
            # Baseball vocabulary in a basketball call is worse than no
            # vocabulary at all, so this is gated to the sport.
            + _sport_slang(sport)
            + _pile_block(pile_position, pile_total)
            + "\n\nWrite the call."
        )
    else:
        # fallback if the sports feed didn't return usable facts for this
        # particular game — still deliver something rather than failing
        user_content = f"Team to roast: {team}. No specific game facts were available, write a general roast about their loss today."

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        # 125 words is roughly 165-190 tokens, so a 200 cap would cut
        # the call off mid-sentence the moment it tried to reach the
        # new length. 400 leaves room to finish a thought.
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    roast = message.content[0].text.strip()
    # Cleaned here TOO, not only at the voice.
    #
    # The TTS path is protected now, but the sender sees this text in an
    # editable box before buying. If it shows "title*" while the call says
    # "title", they have been shown something that is not what they are
    # sending. What you see has to be what they hear.
    try:
        from services.speech_clean import clean_for_speech
        final = clean_for_speech(f"{opener} {roast}")
    except Exception:
        final = f"{opener} {roast}"

    # MEASURED, NOT ENFORCED.
    #
    # Logged rather than trimmed, because cutting a call because it ran a
    # second long is worse than letting it run - the audio is not stopped at
    # sixty seconds and should not be. This is here so the target can be
    # tuned against what the model ACTUALLY produces rather than against
    # calls somebody happened to receive and time by hand.
    _log_length(final)

    # THE FAST CHECK, at the source.
    #
    # Doing it here covers every caller at once - the core Smackagram,
    # Locked & Loaded firing automatically at two in the morning, replies,
    # and anything added later. A check applied per-endpoint is one somebody
    # forgets on the next endpoint.
    #
    # Raises rather than returning something safe, so a caller cannot
    # accidentally send a blocked line by ignoring a return value. The
    # generate route catches this and retries.
    try:
        from services import fast_filter
        quick = fast_filter.check(final)
        if not quick["ok"]:
            raise ValueError(
                f"blocked by the local filter ({quick['category']}): "
                f"{quick['excerpt'][:60]}")
        if quick.get("restyled"):
            final = quick["text"]
    except ValueError:
        raise
    except Exception as e:
        print(f"[smack] fast filter unavailable: {e}", flush=True)

    return final


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
- ROAST HOW THEY PLAYED, NOT WHO THEY ARE. Nothing about appearance,
  weight, disability, a medical condition, age, or somebody's family. If the
  insult is about the sport it is fair game; if it is about the person it is
  not, and no tone setting changes that.
- Never invent a crime or an allegation about a real person - not that a
  player is on steroids, not that somebody fixed a game. Those are false
  statements about named people, and they do not stop being that because the
  tone is funny.
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
        critique = result.get("critique", "").strip()
        comeback = result.get("comeback", "").strip()

        # THE FAST FILTER HERE TOO.
        #
        # Smack Lab is a live back-and-forth with a real person and it is the
        # loosest thing on the site - somebody pushing at the edges gets a
        # reply within seconds, over and over. It was also the only generator
        # whose output never went through any local check.
        #
        # Blocked means the line is replaced with a refusal, not rewritten.
        # There is no retry loop here to fall back on, and a rewritten threat
        # would leave nothing in the log.
        try:
            from services import fast_filter
            for label, txt in (("critique", critique), ("comeback", comeback)):
                v = fast_filter.check(txt)
                if not v["ok"]:
                    print(f"[lab] blocked {label} ({v['category']})",
                          flush=True)
                    return {
                        "rating": 5,
                        "critique": "Let's keep it on the sport.",
                        "comeback": "Not going there. Give me something "
                                    "about the game.",
                        "blocked": v["category"],
                    }
                if label == "critique":
                    critique = v["text"]
                else:
                    comeback = v["text"]
        except Exception as e:
            print(f"[lab] fast filter unavailable: {e}", flush=True)

        return {
            "rating": int(result.get("rating", 5)),
            "critique": critique,
            "comeback": comeback,
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
    # SMACK BACK GETS THE VOCABULARY TOO.
    #
    # This is a real paid call going down a real phone, and it was the only
    # one of the three that did not know Smacky's own words. Same product,
    # same voice, half the character missing.
    #
    # The PLAYBOOK is deliberately left out - a reply is about what somebody
    # SAID, not about a game, so "somebody call the mercy rule" has nothing
    # to attach to.
    _extra = []
    try:
        from services import insults
        _v = insults.block(sensitivity)
        if _v:
            _extra.append(_v)
    except Exception as e:
        print(f"[reply] vocabulary unavailable: {e}", flush=True)
    try:
        _o = smackology.smacky_block(sensitivity)
        if _o:
            _extra.append(_o)
    except Exception as e:
        print(f"[reply] smackology unavailable: {e}", flush=True)

    system_prompt = "\n\n".join(
        [REPLY_SMACK_SYSTEM_PROMPT, tone] + _extra + [_HARD_LIMITS])

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


# Sets the judge's own voice - the critiques and coach messages it
# writes about each line - not the battle lines themselves, which are
# typed by real people and never AI-generated. Fixed once per battle at
# whatever intensity the creator picked; the hard limits above never
# change regardless of level.
_BATTLE_JUDGE_TONE_BY_LEVEL = {
    1: """Judge's voice — CLEAN (Level 1):
- Zero profanity in your critiques or coach messages, not even mild
  words like "damn" or "hell."
- Still be sharp, direct, and honestly funny about what worked or
  didn't - clever, cutting commentary that doesn't need to swear to
  sting. Think a confident sports analyst who's blunt but clean.""",
    2: """Judge's voice — MILD (Level 2):
- Light profanity only in your critiques/coach messages: "damn,"
  "hell," "ass" are fine, sparingly - at most one or two per message.
- Otherwise sharp and witty, same as clean, just with a little real
  edge to the delivery.""",
    3: """Judge's voice — AGGRESSIVE (Level 3):
- Real bite in your critiques and coach messages. Regular cursing:
  damn, hell, ass, shit, bullshit, pissed, dumbass. Multiple curse
  words per message is fine.
- Go hard - this should sound like a genuinely blunt, no-nonsense
  judge, not polite feedback.""",
    4: """Judge's voice — SAVAGE (Level 4):
- The highest level this judge goes. Your critiques and coach messages
  should be savage, heavily profane, genuinely brutal - real cursing
  throughout, not just edgy phrasing.
- Tell the loser their line was weak/unfunny/a swing and a miss, with
  real cursing woven in. Don't hold back on how hard you call out a
  bad line.""",
}


BATTLE_ROUND_JUDGE_SYSTEM_PROMPT_INTRO = """You judge one round of a Smack
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
directly to that person. The critique's own tone (how you deliver it,
how much you curse while delivering it) follows the tone instructions
below - but regardless of tone, the profanity or insults are always
aimed at the QUALITY of their line, not the person. Tell the winner
their line actually cooked, why it worked. Reference the actual content
of their line specifically — generic insults that could apply to any
line aren't good enough.

You'll also get each side's overall standing in the battle so far
(rounds won, average score) including this just-judged round. Write a
short COACH MESSAGE for each side — one or two punchy sentences, a
corner-man/coach voice, not a critique of the line itself but a call to
action based on where they actually stand right now in the battle. If
they're behind, light a fire under them. If they're ahead, tell them
not to get comfortable. If it's close, raise the stakes. Base it on the
real numbers you're given, not a generic pep talk."""


def _build_battle_judge_system_prompt(intensity: int) -> str:
    intensity = intensity if intensity in _BATTLE_JUDGE_TONE_BY_LEVEL else 4
    tone = _BATTLE_JUDGE_TONE_BY_LEVEL[intensity]
    # Same Smacky voice the Smackcast host uses, rendered at THIS battle's
    # intensity so a Clean battle never sees the crude vocabulary, and in
    # "battle" context so the score-phrasing and read-aloud sections are
    # left out - critiques are short displayed text about the quality of a
    # line, not a spoken script about point totals.
    voice = smackology.render(intensity, context="battle")
    return (
        BATTLE_ROUND_JUDGE_SYSTEM_PROMPT_INTRO + "\n\n" + tone + "\n\n" + voice +
        "\n\n" + _BATTLE_HARD_LIMITS +
        """\n\nRespond with ONLY a JSON object, nothing else:
{"winner": "a" or "b" or "tie", "critique_a": "...", "critique_b": "...", "score_a": 0-10, "score_b": 0-10, "coach_message_a": "...", "coach_message_b": "..."}"""
    )


def pick_smacky_battle_team(league: str, player_team: str) -> str:
    """
    Which team Smacky reps in a solo battle.

    A rival makes the battle write itself - the grievances already exist and
    both sides have material. Falls back to any other team in the league,
    and only to a generic label if the league is unknown, because Smacky
    repping nothing gives him nothing to defend.
    """
    try:
        from services import chat_team_lists
        # CHAT_LEAGUES maps league -> {abbreviation: nickname}; the
        # nicknames are what gets shown and what the rivalry table uses.
        teams = list((chat_team_lists.CHAT_LEAGUES.get((league or "").lower()) or {}).values())
    except Exception:
        teams = []

    player_l = (player_team or "").strip().lower()
    rivals = RIVALS.get(player_l, [])
    for r in rivals:
        for t in teams:
            if t.strip().lower() == r:
                return t

    import random
    others = [t for t in teams if t.strip().lower() != player_l]
    return random.choice(others) if others else "The Rest Of The League"


RIVALS = {
    "cowboys": ["eagles", "commanders", "giants"],
    "eagles": ["cowboys", "giants", "commanders"],
    "giants": ["eagles", "cowboys"],
    "commanders": ["cowboys", "eagles"],
    "packers": ["bears", "vikings"],
    "bears": ["packers", "vikings"],
    "vikings": ["packers", "bears"],
    "steelers": ["ravens", "browns", "bengals"],
    "ravens": ["steelers", "browns"],
    "browns": ["steelers", "ravens"],
    "bengals": ["steelers", "ravens"],
    "patriots": ["jets", "bills", "dolphins"],
    "jets": ["patriots", "bills"],
    "bills": ["patriots", "dolphins"],
    "dolphins": ["bills", "patriots"],
    "chiefs": ["raiders", "broncos", "chargers"],
    "raiders": ["chiefs", "broncos"],
    "broncos": ["raiders", "chiefs"],
    "49ers": ["seahawks", "rams"],
    "seahawks": ["49ers", "rams"],
    "rams": ["49ers", "seahawks"],
    "yankees": ["red sox", "mets"],
    "red sox": ["yankees"],
    "mets": ["yankees", "phillies", "braves"],
    "dodgers": ["giants", "padres"],
    "cubs": ["cardinals", "brewers"],
    "cardinals": ["cubs", "brewers"],
    "lakers": ["celtics", "clippers"],
    "celtics": ["lakers", "76ers", "knicks"],
    "knicks": ["nets", "celtics"],
    "warriors": ["cavaliers", "lakers"],
    "heat": ["celtics", "knicks"],
}


SMACKY_OPPONENT_RULES = """
THE ONE RULE THAT MATTERS

This is a battle between RIVAL TEAMS, not between people. The person across
from you is a fan. Their TEAM is the target. That framing decides everything
else.

GO AS HARD AS YOU LIKE AT:
the team, the franchise, its history, its record, its stadium, its owner,
its quarterback, its coach, its fanbase as a group. Profanity is fine at
this intensity. Second person is fine and natural - "you back a genuinely
shit football team" is exactly right, because the insult lands on the TEAM
and they just happen to be holding it.

LIGHT JABS ALLOWED AT:
the line they just wrote. Lazy, recycled, too safe, heard it before. That is
commentary on the writing, not the writer.

NEVER, AT ANY INTENSITY:
any claim about the PERSON - their intelligence, character, appearance,
worth, family, job, relationships, or wellbeing. Not "you're an idiot", not
"you're pathetic", not "no wonder nobody calls you".

THE TEST: if the sentence asserts something about the human being rather
than the team they support, cut it.

Never infer their age, gender, or anything else from their name and use it.
Use their name to address them, not as a target - "nice try, Dave" is fine;
making the joke about Dave is not.

Losing a round means their TEAM got outclassed. It never means they are less
of a person.
"""


def generate_battle_angles(their_team: str, my_team: str = "",
                           already_said: list = None, intensity: int = 4) -> list:
    """
    Three angles of attack on the opponent's team, for the help button.

    Deliberately ANGLES, not finished lines. Handing someone a ready-made
    smack makes the battle Smacky arguing with himself; handing them "their
    playoff record" gives them somewhere to start and leaves the joke theirs.
    """
    already_said = already_said or []
    voice = smackology.render(intensity, context="battle")

    prior = ""
    if already_said:
        prior = ("\n\nAlready used this battle - do NOT repeat these angles:\n"
                 + "\n".join(f"  - {t}" for t in already_said[-8:]))

    system = (
        f"You are Smacky, helping someone find material on {their_team}.\n\n"
        + voice +
        "\n\nGive THREE angles of attack. An angle is a direction, not a "
        "finished joke - name the sore spot and let them write the line. "
        "Six to twelve words each. Concrete: a drought, a collapse, a "
        "contract, a specific player, a stadium, a fanbase habit. "
        "No generic 'they're bad'.\n\n"
        "Reply with ONLY a JSON array of three strings. No preamble, no "
        "markdown, no keys."
    )

    user = f"Angles on {their_team}."
    if my_team:
        user += f" I rep {my_team}, so nothing that cuts back at me."
    user += prior

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        angles = json.loads(raw)
        if isinstance(angles, list):
            return [str(a).strip() for a in angles if str(a).strip()][:3]
    except Exception as e:
        print(f"[battle] angle generation failed: {e}", flush=True)
    return []


def generate_smacky_battle_line(
    my_team: str, their_team: str, round_number: int,
    their_name: str = "", previous_lines: list = None,
    intensity: int = 4, their_last_line: str = None,
    team_facts: str = None,
) -> str:
    """
    Smacky's own smack in a solo battle, as the opponent rather than judge.

    The constraint block above is the whole point of this being its own
    function: as judge he critiques writing, but as OPPONENT he is throwing
    punches, which is exactly where a model drifts into insulting the human
    instead of the team. The rules are stated as a principle with a test
    rather than a list of banned phrases, because a list only catches the
    phrasings someone thought of.
    """
    previous_lines = previous_lines or []
    voice = smackology.render(intensity, context="battle")

    history = ""
    if previous_lines:
        history = "\n\nWhat has already been said this battle:\n" + "\n".join(
            f"  {who}: {text}" for who, text in previous_lines[-6:]
        )

    facts = f"\n\nReal results you can use about {their_team}:\n{team_facts}" if team_facts else ""

    system = (
        f"You are Smacky, and you are IN a smack battle - not judging it. "
        f"You are repping {my_team}. Your opponent reps {their_team}.\n\n"
        + voice + "\n\n" + SMACKY_OPPONENT_RULES +
        "\n\nWrite ONE smack. Two sentences at most, and shorter hits harder. "
        "No preamble, no quotation marks, no stage directions - just the line "
        "itself, the way you would say it out loud."
    )

    user = f"Round {round_number}. Hit {their_team}."
    if their_last_line:
        user += f"\n\nThey just said: \"{their_last_line}\"\n\nAnswer it."
    user += history + facts

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        line = "".join(b.text for b in resp.content if b.type == "text").strip()
        line = line.strip('"').strip()
        return line or f"{their_team}. That's it. That's the whole joke."
    except Exception as e:
        # A dead API call must not stall a live battle - the round still has
        # to resolve, so fall back to something in voice rather than raising.
        print(f"[battle] Smacky line generation failed: {e}", flush=True)
        return f"You really came in here repping {their_team}. Bold."


def judge_battle_round(
    team_a: str, line_a: str, team_b: str, line_b: str,
    round_number: int = 1, wins_a_before: int = 0, wins_b_before: int = 0,
    avg_score_a_before: float = None, avg_score_b_before: float = None,
    intensity: int = 4,
) -> dict:
    """
    Returns {"winner": "a"/"b"/"tie", "critique_a": str, "critique_b": str,
    "score_a": int, "score_b": int, "coach_message_a": str,
    "coach_message_b": str} for one round of a Smack Battle.

    The wins_*_before / avg_score_*_before params reflect each side's
    standing walking INTO this round (not including it) — used to give
    the coach message real context about how the battle's going so far.

    intensity (1-4, Clean through Savage, same scale set at battle
    creation) controls the JUDGE's own voice - how it delivers critiques
    and coach messages - not the battle lines themselves, which are
    typed by real people. Hard safety limits are identical at every
    level regardless.

    Fails to a neutral tie with generic critiques and mid-scores if the
    judge call itself errors out — safer than crashing the round
    transition.
    """
    system_prompt = _build_battle_judge_system_prompt(intensity)
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
                system=system_prompt,
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
Battle that just ended — a round-by-round trash talk battle between two
people roasting each other's sports teams. You'll get every line from the
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
        f"This battle ran {len(round_results)} rounds.\n\n"
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
