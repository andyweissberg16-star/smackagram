"""
Highlightly - the paid sports feed.
===================================
Replaces ESPN for baseball, football, hockey and the NBA. ESPN stays for the
WNBA only, because Highlightly's basketball API has no box scores.

WHY WE MOVED
------------
ESPN's endpoints are undocumented, unsupported, and have no published rate
limits. They blocked this server for hours on 4 August after a burst of
requests, which took down the team picker, the daily show and Locked &
Loaded at once - and Locked & Loaded decides whether customers get charged.

Highlightly publishes 99.993% uptime, runs a status page, and gives MORE
than ESPN did: per-player box scores with season averages alongside game
lines, inning-by-inning scoring, and play-by-play text.

THE ONE THING THAT WILL BITE YOU
--------------------------------
THEIR SCORE STRING IS "HOME - AWAY". ESPN's is away-home, and this entire
codebase was built on ESPN's order.

    "13 - 29"  with home=New England, away=Seattle
    means New England 13, Seattle 29. Seattle won.

Read it the other way and Locked & Loaded phones the WINNING fan to tell
them they lost, and charges them for it. Every score this module returns is
already normalised, so nothing downstream needs to know or care.

PER-SPORT QUIRKS, ALL REAL
--------------------------
  baseball  /matches?league=MLB      box scores at /box-scores/{id}  PLURAL
  football  /matches?league=NFL      box scores at /box-score/{id}   SINGULAR
  basketball /matches?leagueName=NBA no box scores at all
  hockey    /matches?league=NHL      box scores unverified

The parameter name and the endpoint name both differ by sport. That is not
a mistake in this file; it is how their API is.
"""

import os
import time
import threading

# Each sport is its own host and its own subscription.
HOSTS = {
    "mlb":   "https://baseball.highlightly.net",
    "nfl":   "https://american-football.highlightly.net",
    "ncaaf": "https://american-football.highlightly.net",
    "nhl":   "https://hockey.highlightly.net",
    "nba":   "https://basketball.highlightly.net",
}

# What they call each league, and which query parameter carries it.
LEAGUES = {
    "mlb":   ("MLB", "league"),
    "nfl":   ("NFL", "league"),
    "ncaaf": ("NCAA", "league"),
    # Hockey rejects "league" with a 400 - verified live. It takes
    # leagueName, the same as basketball. Each sport differs and there is
    # no pattern to it.
    "nhl":   ("NHL", "leagueName"),
    "nba":   ("NBA", "leagueName"),
}

# Baseball says "box-scores", football says "box-score". Verified against
# the live API - the plural form 404s on football and vice versa.
BOX_PATH = {
    "mlb": "box-scores", "nfl": "box-score", "ncaaf": "box-score",
    "nhl": "box-scores",
}

_lock = threading.Lock()
_cache = {}
_stats = {"sent": 0, "errors": 0, "cached": 0}


def enabled():
    """Off unless a key is set, so nothing changes until it is deliberate."""
    return bool(os.environ.get("HIGHLIGHTLY_KEY"))


def status():
    with _lock:
        return {"enabled": enabled(), "cached_keys": len(_cache), **_stats}


def _get(sport, path, params=None, ttl=45, timeout=10):
    """
    One request, cached briefly.

    Goes through the same gate as everything else - a separate budget from
    ESPN, so a busy night on one cannot starve the other, but the same
    ceiling and the same backoff when they push back.
    """
    key = os.environ.get("HIGHLIGHTLY_KEY")
    if not key:
        return None
    host = HOSTS.get(sport)
    if not host:
        return None

    url = f"{host}/{path}"
    ck = f"{url}?{sorted((params or {}).items())}"

    now = time.time()
    with _lock:
        hit = _cache.get(ck)
        if hit and (now - hit[0]) < ttl:
            _stats["cached"] += 1
            return hit[1]

    from services import espn_gate
    d = espn_gate.get(url, params=params, timeout=timeout,
                      label=f"hl {sport}/{path}",
                      headers={"x-rapidapi-key": key},
                      source="highlightly")
    with _lock:
        if d is None:
            _stats["errors"] += 1
        else:
            _stats["sent"] += 1
            _cache[ck] = (time.time(), d)
    return d


def _norm_score(match):
    """
    Turn their score into ours.

    THIS IS THE FUNCTION THAT MATTERS. Their "13 - 29" is home first. Every
    caller downstream expects winner and loser by NAME, so the ordering is
    resolved once, here, and never again.
    """
    state = match.get("state") or {}
    score = state.get("score") or {}
    cur = score.get("current")
    if not cur or "-" not in str(cur):
        return None

    try:
        left, right = [int(x.strip()) for x in str(cur).split("-")[:2]]
    except (TypeError, ValueError):
        return None

    home = (match.get("homeTeam") or {}).get("displayName") or ""
    away = (match.get("awayTeam") or {}).get("displayName") or ""
    if not home or not away:
        return None

    # left is HOME. Not away. This is the whole point of this function.
    home_pts, away_pts = left, right
    if home_pts == away_pts:
        return None

    if home_pts > away_pts:
        w, l, wp, lp = home, away, home_pts, away_pts
    else:
        w, l, wp, lp = away, home, away_pts, home_pts

    return {
        "final": True,
        "winner": w, "loser": l,
        "winner_score": wp, "loser_score": lp,
        "margin": abs(wp - lp),
        "home": home, "away": away,
        "match_id": match.get("id"),
    }


def finals(sport, date_str):
    """
    Every finished game in a league on a date, keyed by match id.

    One call covers the whole league, the same shape as the ESPN batching -
    so this does not scale with how many people are being smacked.
    """
    cfg = LEAGUES.get(sport)
    if not cfg:
        return {}
    league_name, param = cfg
    d = _get(sport, "matches", {param: league_name, "date": date_str,
                                "limit": 100})
    if not d:
        return {}

    rows = d.get("data") if isinstance(d, dict) else d
    out = {}
    for m in (rows or []):
        state = (m.get("state") or {})
        desc = (state.get("description") or "").lower()
        if "finish" not in desc and (state.get("report") or "").lower() != "final":
            continue
        got = _norm_score(m)
        if got:
            out[str(m.get("id"))] = got

    print(f"[highlightly] {sport} {date_str}: {len(out)} final(s)", flush=True)
    return out


def box_score(sport, match_id):
    """
    Per-player lines for one game.

    Returns a flat list of {name, team, stats:{...}} because every caller
    downstream wants "who did what", not their nested shape.
    """
    path = BOX_PATH.get(sport)
    if not path:
        return []
    d = _get(sport, f"{path}/{match_id}", ttl=300)
    if not d:
        return []

    out = []
    for team_block in (d if isinstance(d, list) else []):
        team = team_block.get("team") or {}
        tname = team.get("name") or ""
        # Football nests boxScores inside team; baseball puts it alongside.
        rows = team_block.get("boxScores") or team.get("boxScores") or []
        for row in rows:
            p = row.get("player") or {}
            name = p.get("name")
            if not name:
                continue
            stats = {}
            for s in (row.get("statistics") or []):
                n = s.get("name")
                if n:
                    stats[n] = s.get("value")
            out.append({"name": name, "team": tname,
                        "jersey": p.get("jersey"), "stats": stats})
    return out


# ---------------------------------------------------------------------------
# THE SHADOW RUN
# ---------------------------------------------------------------------------
#
# Before Highlightly decides anything, it runs ALONGSIDE ESPN and every
# disagreement is logged. ESPN still wins during this period.
#
# This exists because of one specific near-miss: their score string is
# home-first and ESPN's is away-first. Wired up on the obvious assumption,
# Locked & Loaded would have phoned every WINNING fan to say they lost and
# charged them for it - and nothing would have looked wrong until the
# refunds started.
#
# A field-order mistake is invisible in code review and obvious in a
# comparison. So: compare first, switch later.

_DISAGREEMENTS = []


def compare(sport, date_str, espn_results):
    """
    Both sources, side by side. Returns nothing anybody acts on.

    espn_results is {event_id: {...}} from espn_scores.league_results.
    Ids differ between providers, so games are matched on TEAM NAMES.
    """
    if not enabled():
        return

    try:
        theirs = finals(sport, date_str)
    except Exception as e:
        print(f"[shadow] highlightly failed for {sport}: {e}", flush=True)
        return

    def key(row):
        # A game is identified by its two teams, whoever won.
        return tuple(sorted([
            (row.get("winner") or "").split()[-1].lower(),
            (row.get("loser") or "").split()[-1].lower(),
        ]))

    mine = {key(v): v for v in (espn_results or {}).values()}
    hers = {key(v): v for v in theirs.values()}

    both = set(mine) & set(hers)
    agree = disagree = 0
    for k in both:
        a, b = mine[k], hers[k]
        same_loser = ((a.get("loser") or "").split()[-1].lower()
                      == (b.get("loser") or "").split()[-1].lower())
        same_score = (a.get("winner_score") == b.get("winner_score")
                      and a.get("loser_score") == b.get("loser_score"))
        if same_loser and same_score:
            agree += 1
            continue
        disagree += 1
        note = {
            "sport": sport, "date": date_str, "teams": list(k),
            "espn": f"{a.get('winner')} {a.get('winner_score')}-"
                    f"{a.get('loser_score')} {a.get('loser')}",
            "highlightly": f"{b.get('winner')} {b.get('winner_score')}-"
                           f"{b.get('loser_score')} {b.get('loser')}",
            "wrong_loser": not same_loser,
        }
        _DISAGREEMENTS.append(note)
        # A different LOSER is the serious one - that is somebody being
        # charged for a call about a game they won. A different score with
        # the same loser is cosmetic by comparison.
        level = "WRONG LOSER" if not same_loser else "score differs"
        print(f"[shadow] {level}: {note['espn']}  vs  "
              f"{note['highlightly']}", flush=True)

    only_espn = len(set(mine) - set(hers))
    only_hers = len(set(hers) - set(mine))
    print(f"[shadow] {sport} {date_str}: {agree} agree, {disagree} differ, "
          f"{only_espn} only in ESPN, {only_hers} only in Highlightly",
          flush=True)


def disagreements(limit=50):
    """For the admin panel - what has differed so far."""
    return _DISAGREEMENTS[-limit:]


# ---------------------------------------------------------------------------
# ROAST FACTS
# ---------------------------------------------------------------------------
#
# The same job espn_scores.roast_facts does, from a better source. Their box
# scores carry SEASON AVERAGES alongside the game line, which ESPN does not -
# so "he is hitting .269 and looked nothing like it tonight" becomes possible
# in one call rather than two.

def _stat(p, *names):
    """First of these stats the player actually has."""
    for n in names:
        v = (p.get("stats") or {}).get(n)
        if v is not None:
            return v
    return None


def roast_facts(sport, match_id, loser_nick):
    """
    Named performances from the losing side, ready to hand to the writer.

    Returns a list of plain sentences. Empty on any failure, which leaves
    the call working with the scoreline alone - the same behaviour every
    other fact path already has.
    """
    try:
        rows = box_score(sport, match_id)
    except Exception as e:
        print(f"[highlightly] box score failed for {match_id}: {e}",
              flush=True)
        return []
    if not rows:
        return []

    want = (loser_nick or "").split()[-1].lower()
    theirs = [p for p in rows
              if want and want in (p.get("team") or "").lower()]
    if not theirs:
        return []

    out = []

    if sport == "mlb":
        # The pitcher who wore it.
        for p in theirs:
            er = _stat(p, "Total Earned Runs")
            ip = _stat(p, "Innings Pitched")
            if er is not None and ip is not None and float(er or 0) >= 3:
                out.append(f"{p['name']} gave up {er} earned in {ip} innings")
                break
        # A hitter who did nothing, with his season average for contrast.
        for p in theirs:
            ab = _stat(p, "Total At-Bats")
            h = _stat(p, "Total Hits")
            avg = _stat(p, "Batting Average")
            if ab and int(ab) >= 3 and h is not None and int(h) == 0:
                line = f"{p['name']} went 0 for {ab}"
                if avg:
                    line += f" and he is hitting {avg} on the season"
                out.append(line)
                break
        # Anyone who did well on a losing side is its own joke.
        for p in theirs:
            hr = _stat(p, "Total Home Runs")
            rbi = _stat(p, "Total Runs Batted In (RBI)")
            if hr and int(hr) >= 1:
                out.append(f"{p['name']} homered and they still lost")
                break

    elif sport in ("nfl", "ncaaf"):
        for p in theirs:
            att = _stat(p, "Total Passes")
            cmp_ = _stat(p, "Total Successful Passes")
            yds = _stat(p, "Total Passing Yards")
            ints = _stat(p, "Total Passing Interceptions")
            sacks = _stat(p, "Total Sacks")
            if att:
                line = f"{p['name']} went {cmp_} of {att} for {yds}"
                if ints and int(ints) > 0:
                    line += f" and threw {ints} away"
                out.append(line)
                if sacks and int(sacks) >= 3:
                    out.append(f"{p['name']} was sacked {sacks} times")
                break
        # The running game, or the absence of one.
        best = None
        for p in theirs:
            ry = _stat(p, "Total Rushing Yards")
            ra = _stat(p, "Total Rushing Attempts")
            if ry is not None and ra and int(ra) >= 3:
                if best is None or int(ry) > int(best[1]):
                    best = (p["name"], ry, ra)
        if best and int(best[1]) < 40:
            out.append(f"their leading rusher was {best[0]} with "
                       f"{best[1]} yards on {best[2]} carries")

    # WHO WAS MISSING, appended to the same fact list.
    #
    # This reaches every generator that uses roast_facts - the daily show,
    # Locked & Loaded and the roast detail inside calls - rather than only
    # the send page picker.
    #
    # Phrased as ABSENCE, never injury. A writer handed "Sam Howell did not
    # play for them" has no reason to reach for why, and the rules in the
    # character doc and every prompt say plainly that the injury is never
    # the joke.
    try:
        out.extend(missing_men(sport, match_id, loser_nick, limit=1))
    except Exception:
        pass

    return out[:5]


def board(sport, date_str=None):
    """
    Every game today - live, finished and upcoming - for the Smack Board.

    finals() only returns FINISHED games, which is right for deciding who
    lost and useless for a scoreboard: most of what a board shows is in
    progress or yet to start.

    RETURNS THE EXACT SHAPE ESPN'S BOARD ALREADY RETURNS. The page renders
    nested home/away objects with nick, abbr, score, logo and record, plus
    final/live/upcoming flags. Returning anything else would render an
    empty board rather than an error, which is the worst kind of break -
    it looks like there are no games.
    """
    cfg = LEAGUES.get(sport)
    if not cfg:
        return []
    league_name, param = cfg

    from datetime import datetime as _dt
    date_str = date_str or _dt.utcnow().strftime("%Y-%m-%d")

    d = _get(sport, "matches", {param: league_name, "date": date_str,
                                "limit": 100}, ttl=30)
    if not d:
        return []

    rows = d.get("data") if isinstance(d, dict) else d
    out = []
    for m in (rows or []):
        state = m.get("state") or {}
        desc = (state.get("description") or "").lower()
        if "finish" in desc:
            st = "post"
        elif any(k in desc for k in ("progress", "half", "period", "delay")):
            st = "in"
        else:
            st = "pre"

        score = state.get("score") or {}
        cur = str(score.get("current") or "")
        hp = ap = None
        if "-" in cur:
            try:
                # HOME FIRST. Their ordering, resolved here as everywhere.
                hp, ap = [int(x.strip()) for x in cur.split("-")[:2]]
            except (TypeError, ValueError):
                pass

        def side(team, pts):
            t = team or {}
            full = t.get("displayName") or t.get("name") or ""
            nick = t.get("name") or (full.split()[-1] if full else "")
            city = full[:-len(nick)].strip() if nick and full.endswith(nick) else ""
            return {
                "nick": nick,
                "abbr": t.get("abbreviation") or "",
                "city": city,
                "score": pts,
                "record": "",
                "colour": None,
                "logo": t.get("logo") or "",
            }

        h = side(m.get("homeTeam"), hp)
        a = side(m.get("awayTeam"), ap)

        losing = None
        if st == "post" and hp is not None and ap is not None and hp != ap:
            losing = a["nick"] if hp > ap else h["nick"]

        out.append({
            "espn_id": None,
            "highlightly_id": str(m.get("id")),
            "state": st,
            "final": st == "post",
            "live": st == "in",
            "upcoming": st == "pre",
            "status": state.get("report") or state.get("description") or "",
            "clock": state.get("clock"),
            "period": None,
            "start": m.get("date"),
            "venue": (m.get("venue") or {}).get("name"),
            "home": h, "away": a,
            "losing": losing,
        })

    # Live first, then upcoming, then finished - the order somebody opening
    # the board actually wants.
    order = {"in": 0, "pre": 1, "post": 2}
    out.sort(key=lambda g: (order.get(g["state"], 3), g.get("start") or ""))
    return out


def injuries(sport, match_id):
    """
    Who was unavailable, from the match detail.

    ESPN only publishes injuries LEAGUE-WIDE - a 3MB document per league,
    which is what got this server throttled. Highlightly puts them inside
    the match itself, so they arrive with data already being fetched and
    cost nothing extra.

    THE RULE TRAVELS WITH THE NAME. Every generator is told the same thing:
    the ABSENCE is fair game, the INJURY is not. A team that cannot cope
    without one man is a joke; the man's body is not.
    """
    d = _get(sport, f"matches/{match_id}", ttl=600)
    if not d:
        return []
    rows = d[0] if isinstance(d, list) and d else d
    if not isinstance(rows, dict):
        return []

    out = []
    for block in (rows.get("injuries") or []):
        team = ((block.get("team") or {}).get("displayName")
                or (block.get("team") or {}).get("name") or "")
        for item in (block.get("data") or block.get("injuries") or []):
            p = (item or {}).get("player") or item or {}
            nm = p.get("name") or p.get("displayName")
            if not nm:
                continue
            out.append({"name": nm, "team": team,
                        "position": p.get("position"),
                        "jersey": p.get("jersey")})
    return out


def missing_men(sport, match_id, loser_nick, limit=2):
    """
    Sentences about who the LOSING side was without, for any generator.

    Deliberately phrased as absence rather than injury, so a writer given
    these has no reason to reach for the injury itself.
    """
    try:
        rows = injuries(sport, match_id)
    except Exception:
        return []
    want = (loser_nick or "").split()[-1].lower()
    theirs = [r for r in rows if want and want in (r.get("team") or "").lower()]
    if not theirs:
        return []

    out = []
    for r in theirs[:limit]:
        pos = f" ({r['position']})" if r.get("position") else ""
        out.append(f"{r['name']}{pos} did not play for them")
    if len(theirs) > limit:
        out.append(f"they were missing {len(theirs)} players in total")
    return out


def team_injuries(sport, team_name, limit=20):
    """
    Who is currently unavailable for one team, for the name picker.

    Found through today's or yesterday's fixtures rather than a separate
    endpoint, because the match detail already carries them - so this
    reuses a request that is usually cached rather than making a new kind.

    Returns [] when the team is not playing, which is the honest answer:
    an injury list is only knowable here from a game they appear in.
    """
    from datetime import datetime as _dt, timedelta as _td
    want = (team_name or "").split()[-1].lower()
    if not want:
        return []

    for off in (0, 1):
        day = (_dt.utcnow() - _td(days=off)).strftime("%Y-%m-%d")
        cfg = LEAGUES.get(sport)
        if not cfg:
            return []
        league_name, param = cfg
        d = _get(sport, "matches", {param: league_name, "date": day,
                                    "limit": 100}, ttl=600)
        if not d:
            continue
        rows = d.get("data") if isinstance(d, dict) else d
        for m in (rows or []):
            names = {
                ((m.get("homeTeam") or {}).get("displayName") or "").split()[-1].lower(),
                ((m.get("awayTeam") or {}).get("displayName") or "").split()[-1].lower(),
            }
            if want not in names:
                continue
            hits = [r for r in injuries(sport, m.get("id"))
                    if want in (r.get("team") or "").lower()]
            if hits:
                return hits[:limit]
    return []
