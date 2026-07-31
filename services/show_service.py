"""
Last night's results, turned into things Smacky can roast.

Built on SportsDataIO's GamesByDate, which returns real, verified data:
final score, hits, errors, innings, winner and loser.

DELIBERATELY NOT using PlayerGameStatsByDate. That endpoint returns real
player NAMES attached to FAKE statistics on this subscription tier - 8.9
at-bats, 4.5 hits, and identical values across different players. Real names
on invented numbers is the worst possible combination: it looks legitimate
enough to build on, and a single listener who follows the sport would catch
it instantly. Team-level facts are less personal but they're true.

No safety screen is needed here, which is the other reason this beats the
news feed. A run differential cannot be a tragedy.
"""

from datetime import datetime, timedelta

from services import sports_service

# Only leagues whose GamesByDate shape is known good. Expandable, but each
# addition needs its score fields checked - they differ per sport.
LEAGUES = {
    "mlb":  {"label": "MLB",  "unit": "runs",   "period": "Inning"},
    "wnba": {"label": "WNBA", "unit": "points", "period": "Quarter"},
    "nfl":  {"label": "NFL",  "unit": "points", "period": "Quarter"},
    "nba":  {"label": "NBA",  "unit": "points", "period": "Quarter"},
    "nhl":  {"label": "NHL",  "unit": "goals",  "period": "Period"},
}

# SportsDataIO names the score field differently per sport - MLB uses
# HomeTeamRuns, NFL uses HomeScore, basketball uses HomeTeamScore. Guessing
# wrong returns zero games, which looks EXACTLY like "no games were played" -
# a failure that hides for weeks. This is the same fix already applied to
# get_game_result after the MLB scores silently came back None.
SCORE_FIELDS = {
    "home": ["HomeTeamRuns", "HomeScore", "HomeTeamScore", "HomePoints"],
    "away": ["AwayTeamRuns", "AwayScore", "AwayTeamScore", "AwayPoints"],
}


def _score(event, field):
    """Reads one named field. Values arrive as int, float or None."""
    v = event.get(field)
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _team_score(event, side):
    """
    Finds the score whatever the sport calls it. Returns None only when every
    known variant is absent, which is a genuine signal the game has no result
    rather than a mapping mistake on our side.
    """
    for field in SCORE_FIELDS[side]:
        v = _score(event, field)
        if v is not None:
            return v
    return None


def fetch_results(league: str, days_back: int = 1) -> list[dict]:
    """One league's finished games for a given day."""
    cfg = LEAGUES.get(league)
    if not cfg:
        return []

    day = datetime.utcnow() - timedelta(days=days_back)
    date_str = day.strftime("%Y-%b-%d").upper()

    try:
        events = sports_service._get(
            league, sports_service._games_by_date_endpoint(league, date_str)
        )
    except Exception as e:
        print(f"[show] {league} {date_str} failed: {e}")
        return []

    games = []
    for e in events or []:
        status = (e.get("Status") or "").lower()
        if not status.startswith("final") and status != "f/ot":
            continue

        away = _team_score(e, "away")
        home = _team_score(e, "home")
        if away is None or home is None or away == home:
            continue

        away_name = e.get("AwayTeam") or ""
        home_name = e.get("HomeTeam") or ""
        winner, loser = (home_name, away_name) if home > away else (away_name, home_name)

        games.append({
            "league": cfg["label"],
            "unit": cfg["unit"],
            "away": away_name, "home": home_name,
            "away_score": away, "home_score": home,
            "winner": winner, "loser": loser,
            "margin": abs(home - away),
            "loser_at_home": home < away,
            "away_hits": _score(e, "AwayTeamHits"),
            "home_hits": _score(e, "HomeTeamHits"),
            "away_errors": _score(e, "AwayTeamErrors"),
            "home_errors": _score(e, "HomeTeamErrors"),
            "periods": _score(e, cfg["period"]),
            "date": date_str,
        })

    print(f"[show] {league}: {len(games)} finished games on {date_str}")
    return games


def build_facts(game: dict) -> list[str]:
    """
    Plain-English facts about one game, ordered most roastable first.

    Every line here is derived arithmetic on real numbers - nothing inferred,
    nothing embellished. Smacky supplies the cruelty; this supplies the truth.
    """
    facts = []
    u = game["unit"]
    facts.append(
        f"{game['winner']} beat {game['loser']} "
        f"{max(game['away_score'], game['home_score'])}-"
        f"{min(game['away_score'], game['home_score'])}"
    )

    if game["margin"] >= 8:
        facts.append(f"a {game['margin']}-{u[:-1]} beating")
    elif game["margin"] == 1:
        facts.append(f"lost by a single {u[:-1]}")

    if game["loser_at_home"]:
        facts.append(f"{game['loser']} lost at home")

    # Losing with more hits than the winner: they had the chances and wasted
    # them, which is a specific and funnier kind of failure than being outplayed.
    lh, ah = game["home_hits"], game["away_hits"]
    if lh is not None and ah is not None:
        loser_hits = lh if game["loser_at_home"] else ah
        winner_hits = ah if game["loser_at_home"] else lh
        if loser_hits > winner_hits:
            facts.append(
                f"{game['loser']} out-hit them {loser_hits} to {winner_hits} and still lost"
            )

    he, ae = game["home_errors"], game["away_errors"]
    if he is not None and ae is not None:
        loser_errs = he if game["loser_at_home"] else ae
        winner_errs = ae if game["loser_at_home"] else he
        if loser_errs >= 2:
            facts.append(f"{game['loser']} committed {loser_errs} errors")
        # Winning while kicking it around is its own indignity.
        if winner_errs >= 3:
            facts.append(f"{game['winner']} made {winner_errs} errors and won anyway")

    return facts


def _score_game(game: dict) -> int:
    """How roastable a result is. Margin dominates; sloppiness adds to it."""
    s = game["margin"] * 2
    if game["loser_at_home"]:
        s += 3
    errs = [e for e in (game["home_errors"], game["away_errors"]) if e]
    if errs:
        s += max(errs) * 2
    return s


# Words per minute measured from real Smackcast output - not the 150 usually
# assumed for read-aloud copy. Smacky talks slower than that.
SPOKEN_WORDS_PER_MINUTE = 115

# Runtime bands by how much actually happened. Four minutes is the ceiling,
# reached when a full slate of leagues is in season. Same approach as
# smackcast_service, and for the same reason: a fixed runtime forces padding
# on quiet nights, and padding is far more noticeable than a shorter show.
RUNTIME_BANDS = [
    (15, 4.0),   # 15+ games - in season, multiple leagues
    (8, 3.0),    # 8-14
    (4, 2.0),    # 4-7 - one league, quiet night
]
MIN_GAMES = 4    # below this, keep yesterday's show rather than publish thin


def plan_runtime(game_count: int) -> dict:
    """
    Decides how long this episode should be, and how many games to cover.

    Returns publish=False when there isn't enough to work with - the caller
    is expected to leave the previous show up rather than air something thin.
    """
    if game_count < MIN_GAMES:
        return {"publish": False, "minutes": 0, "word_budget": 0, "cover": 0,
                "reason": f"only {game_count} finished games - keeping the previous show"}

    minutes = 2.0
    for threshold, mins in RUNTIME_BANDS:
        if game_count >= threshold:
            minutes = mins
            break

    words = int(minutes * SPOKEN_WORDS_PER_MINUTE)
    # Roughly 55 words per game once the intro and outro are allowed for -
    # enough for a setup and a punchline without turning into a list.
    cover = max(3, min(game_count, int((words - 60) / 55)))
    return {"publish": True, "minutes": minutes, "word_budget": words,
            "cover": cover, "reason": f"{game_count} games -> {minutes:g} minutes"}


def get_show_material(leagues=None, days_back: int = 1, want: int = None) -> dict:
    """
    Everything the writer needs for one episode.

    Returns the games worth talking about plus any losing streaks found by
    looking back across the past week. Streaks are the most humiliating stat
    available because they compound - one loss is a night, six is a condition.
    """
    leagues = leagues or list(LEAGUES.keys())

    games = []
    for lg in leagues:
        games.extend(fetch_results(lg, days_back=days_back))

    games.sort(key=_score_game, reverse=True)
    plan = plan_runtime(len(games))
    top = games[:(want or plan["cover"])]

    return {
        "date": (datetime.utcnow() - timedelta(days=days_back)).strftime("%A, %B %-d"),
        "game_count": len(games),
        "leagues_played": sorted({g["league"] for g in games}),
        "plan": plan,
        "games": [{**g, "facts": build_facts(g)} for g in top],
        "streaks": find_streaks(leagues, days_back=days_back) if plan["publish"] else [],
    }


def find_streaks(leagues, days_back: int = 1, lookback: int = 7, minimum: int = 3) -> list[dict]:
    """
    Teams on a current losing run.

    Walks back day by day from the target date. A team's streak ends the
    moment they win, so this stops counting at their first victory rather
    than tallying total losses over the window - "lost 5 of 7" is a
    statistic, "lost 5 straight" is a humiliation.
    """
    results = {}
    for offset in range(days_back, days_back + lookback):
        for lg in leagues:
            for g in fetch_results(lg, days_back=offset):
                for team, won in ((g["winner"], True), (g["loser"], False)):
                    results.setdefault(team, []).append((offset, won, g["league"]))

    streaks = []
    for team, entries in results.items():
        entries.sort(key=lambda x: x[0])          # most recent first
        run = 0
        for _, won, _lg in entries:
            if won:
                break
            run += 1
        if run >= minimum:
            streaks.append({"team": team, "losses": run, "league": entries[0][2]})

    streaks.sort(key=lambda s: s["losses"], reverse=True)
    return streaks[:3]


# ---------------------------------------------------------------------------
# The writer and the daily job
# ---------------------------------------------------------------------------

def write_script(material: dict) -> dict:
    """
    Turns a night's facts into Smacky's on-air script.

    Reuses smackology so the daily show sounds like the same character as
    every other surface. The one rule that matters: he may only reference
    facts supplied here. Inventing a reason a team lost is how a comedy bit
    becomes a defamation claim.
    """
    from services import smackology
    from services.smackcast_service import _get_client

    plan = material["plan"]
    if not plan["publish"]:
        return {"publish": False, "reason": plan["reason"]}

    lines = []
    for g in material["games"]:
        lines.append(f"- [{g['league']}] " + "; ".join(g["facts"]))
    for s in material.get("streaks", []):
        lines.append(f"- [{s['league']}] {s['team']} have lost {s['losses']} in a row")

    system = smackology.render(level=4, context="recap")

    user = (
        f"You are Smacky, hosting THE SMACKY REPORT — a daily sports radio "
        f"segment about what happened last night ({material['date']}).\n\n"
        f"FACTS. These are real and verified. You may ONLY reference what is "
        f"listed here. Do not invent injuries, reasons, quotes, player names "
        f"or anything about why a result happened — you were given scores, not "
        f"explanations. Making something up is worse than being short.\n\n"
        + "\n".join(lines) + "\n\n"
        f"LENGTH: about {plan['word_budget']} words total. That is a hard "
        f"target — this is a timed radio segment.\n\n"
        "SHAPE:\n"
        "1. Open with the branded greeting, then the date.\n"
        "2. Work through the results, worst beating first. Every one gets a "
        "setup and a punchline. Name both teams.\n"
        "3. Losing streaks are your best material — a single loss is a night, "
        "six straight is a condition.\n"
        "4. Close by telling them to come back tomorrow.\n\n"
        "Reply with JSON only:\n"
        '{"intro": "...", "segments": [{"text": "...", "reaction": "burn"}], '
        '"outro": "...", "best_line": "..."}\n'
        "No other text. reaction is one of: burn, laugh, shock, groan."
    )

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    text = text.replace("```json", "").replace("```", "").strip()

    import json as _json
    script = _json.loads(text)
    script["publish"] = True
    return script


def produce_daily_show(days_back: int = 1) -> dict:
    """
    The whole job, end to end: pull the night, decide the runtime, write it,
    render it, store it.

    Called by the cron endpoint. Returns a dict describing what happened, so
    a failure is visible in the logs rather than silent.
    """
    from services.smackcast_service import assemble_recap_audio, sanitize_for_speech

    material = get_show_material(days_back=days_back)
    plan = material["plan"]

    if not plan["publish"]:
        # Deliberately does NOT publish something thin. Yesterday's show stays
        # up, which is a better outcome than four minutes of padding.
        print(f"[show] holding: {plan['reason']}")
        return {"published": False, "reason": plan["reason"],
                "game_count": material["game_count"]}

    script = write_script(material)
    if not script.get("publish"):
        return {"published": False, "reason": script.get("reason", "no script")}

    # Same speech sanitiser the Smackcast uses - strips punctuation names,
    # em dashes and emoji that TTS would otherwise read aloud.
    intro = sanitize_for_speech(script["intro"])
    outro = sanitize_for_speech(script["outro"])
    segments = [
        {"text": sanitize_for_speech(s["text"]), "reaction": s.get("reaction", "burn")}
        for s in script["segments"]
    ]

    audio_url = assemble_recap_audio(intro, segments, outro)
    print(f"[show] published {plan['minutes']:g} min from {material['game_count']} games")

    return {
        "published": True,
        "audio_url": audio_url,
        "minutes": plan["minutes"],
        "game_count": material["game_count"],
        "leagues": material["leagues_played"],
        "best_line": script.get("best_line", ""),
        "date_label": material["date"],
    }
