"""
Seeds Smack Chat's general chat rooms with realistic activity so new
visitors see real conversation happening instead of an empty room.

Run this yourself, pointed at the live site:
    python3 seed_chat.py

Hits the real public /api/chat/posts endpoint, same as any real user —
this isn't a database script, it's just automated posting through the
normal front door, with randomized delays so it doesn't look like a bulk
import.

Content is hand-written, not generated at run-time — more reliable, and
it means every line was actually checked to sound like a real person
typed it, not a model's voice. Deliberately mixes quality: some users
are one-word lazy replies, some put real effort in, matching how real
chat rooms actually feel.
"""

import random
import time
import sys
import requests

BASE_URL = "https://smackagram.com"

# The site is locked behind a password gate (SITE_PASSWORD env var on
# Render) using HTTP Basic Auth — any username works, only the password
# is actually checked. Without this, every request gets a plain-text 401
# instead of JSON. Passed as a command-line argument instead of an
# interactive prompt — simpler and more reliable than typing into a
# waiting prompt in the terminal, which is easy to get wrong.
if len(sys.argv) < 2 or not sys.argv[1].strip():
    print("Usage: python3 seed_chat.py YOUR_SITE_PASSWORD")
    print("(the exact SITE_PASSWORD value from your Render service's Environment tab)")
    raise SystemExit(1)

SITE_PASSWORD = sys.argv[1].strip()
AUTH = ("seed-script", SITE_PASSWORD)

# Mix of sports-themed and plain-sounding usernames — real chat rooms
# have both kinds, an all-sports-themed username list would read as
# artificial on its own.
USERNAMES = [
    "BleacherBum", "Mike_D23", "PuckDrunk88", "jennap_", "CourtsideCarl",
    "kevin.b", "GridironGirl", "amanda_r", "TrashTalkTravis", "tyler94",
    "DiamondDynasty", "nicole_m", "CoachKenny", "chris_t", "RowdyRafael",
    "sarahj99", "BenchWarmerBrad", "davidw", "MVPMaria", "jordan_p",
]

# Each username has a consistent "favorite team" personality per league,
# so their lines feel grounded in a real rivalry rather than generic.
# Also tagged with a quality tier so the SAME users are consistently
# lazy/short or consistently more effortful — real people don't randomly
# swap effort level message to message, they have a consistent "voice."
LAZY = "lazy"
EFFORT = "effort"
MID = "mid"

USER_PROFILES = {
    "BleacherBum": LAZY, "Mike_D23": MID, "PuckDrunk88": EFFORT,
    "jennap_": MID, "CourtsideCarl": EFFORT, "kevin.b": LAZY,
    "GridironGirl": EFFORT, "amanda_r": MID, "TrashTalkTravis": EFFORT,
    "tyler94": LAZY, "DiamondDynasty": EFFORT, "nicole_m": MID,
    "CoachKenny": EFFORT, "chris_t": LAZY, "RowdyRafael": MID,
    "sarahj99": LAZY, "BenchWarmerBrad": MID, "davidw": LAZY,
    "MVPMaria": EFFORT, "jordan_p": MID,
}

# (username, message) per league's general chat. Deliberately varied
# length/effort/casing/punctuation to avoid a uniform "generated" feel.
GENERAL_CHAT_SEEDS = {
    "nfl": [
        ("BleacherBum", "cowboys fans in shambles rn lol"),
        ("PuckDrunk88", "Every single year it's 'this is our year' and every single year it's the same disappointment by week 14. At some point you have to admit the pattern."),
        ("kevin.b", "eagles D been different tho"),
        ("GridironGirl", "Bold take: half the fanbases in this league would trade their whole roster for one competent offensive line coach and nobody would even blink."),
        ("tyler94", "ratio"),
        ("nicole_m", "the refs in that game were actually criminal, like actually should be investigated"),
        ("CoachKenny", "Not a single team in the AFC North has a real identity right now, it's just vibes and hoping the other three teams choke harder than you."),
        ("sarahj99", "lol ok"),
    ],
    "nba": [
        ("CourtsideCarl", "Every trade deadline this league turns into fantasy basketball and everyone acts surprised"),
        ("davidw", "lakers fans really said this is a championship roster huh"),
        ("MVPMaria", "The gap between 'this team has talent' and 'this team knows how to close a game' has never been wider than it is right now around the league."),
        ("jordan_p", "warriors window closed like 2 years ago and yall still talking like it's 2017"),
        ("chris_t", "trash"),
        ("amanda_r", "someone explain to me how a team with THAT much cap space still can't shoot free throws"),
        ("TrashTalkTravis", "Every fanbase thinks their guy deserves MVP the second he has one good week, meanwhile the actual best player in the league gets ignored because his team isn't on national TV enough."),
    ],
    "mlb": [
        ("DiamondDynasty", "It's July and half these 'contenders' are already mathematically cooked, just nobody's told their fanbase yet"),
        ("RowdyRafael", "yankees spent 300 million on a bullpen that blows every save after the 7th, incredible business model"),
        ("BenchWarmerBrad", "lol"),
        ("jennap_", "The amount of teams tanking right now disguised as 'player development' is honestly kind of impressive as a strategy"),
        ("kevin.b", "small market teams really out here building better rosters than half the big spenders, embarrassing honestly"),
        ("Mike_D23", "ok"),
        ("GridironGirl", "Every single broadcast this week has had at least one announcer say 'you can't teach that' about something that is, in fact, extremely teachable."),
    ],
    "nhl": [
        ("PuckDrunk88", "This league has like 4 real contenders and 28 teams just here for the ride, and everyone knows it"),
        ("tyler94", "canadian teams collectively cursed at this point, it's not even funny anymore"),
        ("CourtsideCarl", "The officiating inconsistency from period to period in some of these games genuinely makes we wonder if there's a rulebook at all or just vibes"),
        ("nicole_m", "power play units around this league are an actual crime scene"),
        ("davidw", "meh"),
        ("MVPMaria", "Every trade deadline someone's GM makes a move that makes zero sense on paper and somehow it works out, and I genuinely think it's just luck at this point."),
    ],
    "wnba": [
        ("amanda_r", "This league's depth has gotten so much better in the last two years and half the casual fans still haven't noticed"),
        ("chris_t", "fr"),
        ("jordan_p", "The physicality in these games right now is genuinely some of the best basketball being played anywhere, full stop"),
        ("sarahj99", "not this"),
        ("TrashTalkTravis", "Every team in this league has at least one player who could start on half the rosters in the men's game and people still act shocked by that."),
        ("BenchWarmerBrad", "refs missing calls left and right this week smh"),
    ],
    "sec": [
        ("DiamondDynasty", "SEC fans really think every other conference is playing high school ball, meanwhile half these SEC teams can't cover a slot receiver to save their lives"),
        ("kevin.b", "texas still adjusting to real competition lol"),
        ("RowdyRafael", "The gap between the top 4 SEC teams and everyone else in this conference is honestly bigger than most people want to admit."),
        ("Mike_D23", "smh"),
        ("GridironGirl", "Every SEC coach's hot seat talk starts the literal week after a loss, this fanbase has zero patience and I respect it honestly."),
    ],
    "bigten": [
        ("CourtsideCarl", "Big Ten defense this year has been legitimately elite, it's not even close to previous seasons"),
        ("nicole_m", "ohio state fans already measuring for championship rings again, some things never change"),
        ("davidw", "meh division looks weak this year ngl"),
        ("MVPMaria", "The West coast additions to this conference have genuinely changed the entire competitive balance and I don't think enough people are talking about it."),
        ("tyler94", "cope"),
    ],
    "big12": [
        ("amanda_r", "This conference gets disrespected every single year and then somehow ends up sending multiple teams to the playoff anyway"),
        ("chris_t", "trash conference ngl"),
        ("jordan_p", "Every year someone counts this conference out early and every year at least two teams make people regret it by November."),
        ("sarahj99", "lol no"),
    ],
    "acc": [
        ("TrashTalkTravis", "ACC football has been rebuilding its reputation for like a decade now and it's genuinely getting there, people just aren't paying attention"),
        ("BenchWarmerBrad", "clemson still living off 2019 apparently"),
        ("PuckDrunk88", "The parity in this conference this season has actually made for some of the better regular season football in the country, most people just don't tune in until bowl season."),
        ("kevin.b", "fr tho"),
    ],
    "ncaab": [
        ("DiamondDynasty", "March is going to be an absolute bloodbath with how tight the top 25 is this year"),
        ("Mike_D23", "gonzaga fans still think it's 2021"),
        ("GridironGirl", "The transfer portal has genuinely changed how you build a contender in this sport, teams that adapted fast are the ones actually competing now."),
        ("nicole_m", "meh"),
    ],
    "ncaawb": [
        ("CourtsideCarl", "Women's college basketball has never had this much national attention and honestly it's overdue"),
        ("davidw", "same 4 teams every year lol"),
        ("MVPMaria", "The talent depth across the whole sport right now is legitimately the best it's ever been, not just at the top of the bracket."),
        ("tyler94", "fr"),
    ],
    "mls": [
        ("amanda_r", "MLS keeps getting disrespected internationally and then keeps landing genuinely good young talent nobody saw coming"),
        ("chris_t", "still watching real leagues personally"),
        ("jordan_p", "The level of play in this league has jumped so much in the last few years, people comparing it to leagues from a decade ago are just wrong at this point."),
        ("sarahj99", "meh"),
    ],
    "epl": [
        ("TrashTalkTravis", "This title race is going to come down to the final matchday and everyone knows it, nobody's pulling away"),
        ("BenchWarmerBrad", "var ruining football one call at a time"),
        ("PuckDrunk88", "The gap between the top six and everyone else in this league has genuinely narrowed this season, mid-table teams are causing way more upsets than usual."),
        ("kevin.b", "cope"),
    ],
    "laliga": [
        ("DiamondDynasty", "La Liga's depth outside the top two clubs has actually gotten really competitive this season"),
        ("Mike_D23", "same two teams every year tho lol"),
        ("GridironGirl", "The tactical quality in this league week to week is genuinely some of the best football being played in Europe right now, casual fans just don't tune in enough."),
        ("nicole_m", "fr"),
    ],
    "bundesliga": [
        ("CourtsideCarl", "This league's youth development pipeline is legitimately the best model in world football and other leagues should be taking notes"),
        ("davidw", "same team wins every year tho"),
        ("MVPMaria", "The pressing intensity in this league is unmatched anywhere else in Europe, it's just a completely different style of football."),
        ("tyler94", "meh"),
    ],
    "seriea": [
        ("amanda_r", "Serie A tactics this season have been genuinely fascinating to watch, way more variety than people give it credit for"),
        ("chris_t", "boring league ngl"),
        ("jordan_p", "The defensive quality in this league is still unmatched anywhere in the world, people sleep on how technical it actually is."),
        ("sarahj99", "cope"),
    ],
}


def check_auth():
    """Quick single request to confirm the password works before running
    the full seed — fails fast instead of watching 80 skips scroll by."""
    try:
        resp = requests.get(f"{BASE_URL}/", auth=AUTH, timeout=15)
        if resp.status_code == 401:
            print("Password rejected (401) — double check the SITE_PASSWORD value in Render's Environment tab and try again.")
            return False
        return True
    except Exception as e:
        print(f"Couldn't reach the site to check auth: {e}")
        return False


def seed():
    if not check_auth():
        return

    total_posted = 0
    total_failed = 0

    for league, seeds in GENERAL_CHAT_SEEDS.items():
        print(f"\n--- Seeding {league} general chat ---")
        for username, message in seeds:
            try:
                resp = requests.post(
                    f"{BASE_URL}/api/chat/posts",
                    json={
                        "league": league,
                        "team": "_general",
                        "display_name": username,
                        "message": message,
                    },
                    auth=AUTH,
                    timeout=15,
                )
                if resp.status_code == 200:
                    print(f"  [ok] {username}: {message[:50]}")
                    total_posted += 1
                else:
                    try:
                        error_detail = resp.json().get("error")
                    except ValueError:
                        error_detail = resp.text[:200]
                    print(f"  [skip] {username} — {resp.status_code}: {error_detail}")
                    total_failed += 1
            except Exception as e:
                print(f"  [error] {username} — {e}")
                total_failed += 1

            # Randomized delay so this reads as organic activity over
            # time, not a bulk drop all at once.
            time.sleep(random.uniform(1.5, 5.0))

    print(f"\nDone. Posted {total_posted}, skipped/failed {total_failed}.")


if __name__ == "__main__":
    seed()
