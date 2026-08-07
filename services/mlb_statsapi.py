"""
MLB's own Stats API - the primary source for MLB scores AND box scores.
=======================================================================

statsapi.mlb.com: official, free, no key, and the API MLB's own apps run
on. It exists in this codebase because both third-party sources failed
in ways that put WRONG INFORMATION ON AIR:

  BALLDONTLIE files games under UTC days. A Padres home game starts
  9:40pm ET - 1:40am UTC the NEXT day - so their "Wednesday" contains
  Tuesday's late West Coast games and Wednesday's own late games sit
  under Thursday. A series is the same two teams on consecutive nights,
  so Tuesday's score replaced Wednesday's with the game count intact,
  and the episode read out the wrong result. Verified live: their
  Aug 5 card carried the Padres' Tuesday score.

  HIGHLIGHTLY lags a full day on MLB results. At 11am Thursday every
  Wednesday game was still "Scheduled" while two days back had 23
  finals. A 5:55am show loses that race every single morning, which is
  why the player-stat awards never fired.

statsapi has neither disease:
  - "officialDate" is the real LOCAL calendar day. No UTC trap.
  - finals appear within minutes of the last out.
  - /game/{gamePk}/boxscore carries every player's line plus season
    stats - exactly what Smack Ball, Certified Cooker and Clown Show
    were designed around.

SHAPES: finals() emits rows shaped like balldontlie.finals() so
espn_scores.fetch_finals can merge them without knowing which source
answered. game_detail() emits the ESPN-style detail dict the layout's
_hitters/_pitchers already parse - keys ["AB","H","R","RBI","HR","AVG"]
for hitters, ["IP","H","ER","SO","ERA"] for pitchers, batting order and
starter-first preserved. Nothing downstream changes.

Requests go through espn_gate with source="mlb_statsapi" - its own
budget, so a busy night here cannot starve another source.
"""

from services import espn_gate

BASE = "https://statsapi.mlb.com/api/v1"


def _get(path, params=None, ttl_ignored=None, wait=False):
    return espn_gate.get(f"{BASE}/{path}", params=params or {},
                         timeout=12, label=f"statsapi {path[:40]}",
                         source="mlb_statsapi", wait=wait)


def _nickname(team):
    """
    'Blue Jays' from a team object. The nickname, because that is what
    the rest of the pipeline compares on - and the detail dict's
    winner/loser MUST match the boxscore block names or _hitters finds
    nobody.
    """
    t = team or {}
    return (t.get("teamName") or t.get("clubName")
            or t.get("name") or "").strip()


def finals(date_str):
    """
    Finished MLB games on an EASTERN calendar day, balldontlie-shaped:
    {(home, away): {home, away, home_score, away_score, winner, loser,
                    id, venue, plays, source}}

    officialDate == the local day, so one query is one day - no
    two-UTC-day window, no neighbour-day spillover to filter.
    """
    d = _get("schedule", {"sportId": 1, "date": date_str})
    if d is None:
        # the gate refused or the request failed - say so, because a
        # silent None here becomes "NO gamePk" fifteen times downstream
        print(f"[statsapi] schedule {date_str}: no response "
              f"(gate refusal or network)", flush=True)
    out = {}
    for day in ((d or {}).get("dates") or []):
        for g in (day.get("games") or []):
            # THE OFFICIAL DATE IS THE CONTRACT. Belt and braces: keep
            # only rows whose officialDate is the day asked for, so even
            # a provider-side quirk cannot smuggle a neighbouring day in.
            if (g.get("officialDate") or date_str) != date_str:
                continue
            status = ((g.get("status") or {})
                      .get("abstractGameState") or "").lower()
            if status != "final":
                continue
            teams = g.get("teams") or {}
            home_t = (teams.get("home") or {})
            away_t = (teams.get("away") or {})
            home = _nickname(home_t.get("team"))
            away = _nickname(away_t.get("team"))
            hs, aws = home_t.get("score"), away_t.get("score")
            if not home or not away or hs is None or aws is None:
                continue
            if hs == aws:
                continue        # suspended/tied oddity - not a final
            row = {
                "home": home, "away": away,
                "home_score": hs, "away_score": aws,
                "winner": home if hs > aws else away,
                "loser": away if hs > aws else home,
                "id": g.get("gamePk"),
                "venue": ((g.get("venue") or {}).get("name")),
                "plays": [],
                "source": "mlb_statsapi",
                # Real season records, straight from the schedule - the
                # fix for the wrong-records complaint.
                "winner_record": _rec(home_t if hs > aws else away_t),
                "loser_record": _rec(away_t if hs > aws else home_t),
            }
            out[(home, away)] = row
    return out


def _rec(side):
    r = (side or {}).get("leagueRecord") or {}
    w, l = r.get("wins"), r.get("losses")
    return f"{w}-{l}" if w is not None and l is not None else None


def _fmt_avg(v):
    """'.238' the way a broadcaster says it; statsapi sends '.238' already."""
    return v if v not in (None, "") else None


def game_detail(game_pk, winner_nick, loser_nick, wait=True):
    """
    The full box score as the ESPN-style detail dict the layout parses.

    wait=True stands in line at the gate rather than shipping an episode
    without stats - background render only, same rule as Highlightly's
    box scores.
    """
    d = _get(f"game/{game_pk}/boxscore", wait=wait)
    if not d:
        return None
    blocks = []
    for side in ("home", "away"):
        t = (d.get("teams") or {}).get(side) or {}
        nick = _nickname(t.get("team"))
        players = t.get("players") or {}

        # HITTERS, IN BATTING ORDER. The layout treats list position as
        # the batting order, so the order list is walked, not the dict.
        order_ids = [str(x) for x in (t.get("battingOrder") or [])]
        if not order_ids:
            # fall back: anyone with an at-bat, by their battingOrder key
            order_ids = sorted(
                (k for k, v in players.items()
                 if ((v.get("stats") or {}).get("batting") or {})
                 .get("atBats")),
                key=lambda k: int(players[k].get("battingOrder") or 999))
        hitters = []
        for pid in order_ids:
            p = players.get(pid) or players.get(f"ID{pid}") or {}
            bat = ((p.get("stats") or {}).get("batting") or {})
            if not bat or bat.get("atBats") in (None, 0):
                continue
            season = ((p.get("seasonStats") or {}).get("batting") or {})
            hitters.append({
                "athlete": {"displayName":
                            ((p.get("person") or {}).get("fullName") or "")},
                "stats": [str(bat.get("atBats", 0)),
                          str(bat.get("hits", 0)),
                          str(bat.get("runs", 0)),
                          str(bat.get("rbi", 0)),
                          str(bat.get("homeRuns", 0)),
                          _fmt_avg(season.get("avg")) or ""],
            })

        # PITCHERS, STARTER FIRST - the pitchers list is already in
        # appearance order, and pick_cooker treats index 0 as the starter.
        pitchers = []
        for pid in (t.get("pitchers") or []):
            p = players.get(str(pid)) or players.get(f"ID{pid}") or {}
            pit = ((p.get("stats") or {}).get("pitching") or {})
            if not pit:
                continue
            season = ((p.get("seasonStats") or {}).get("pitching") or {})
            pitchers.append({
                "athlete": {"displayName":
                            ((p.get("person") or {}).get("fullName") or "")},
                "stats": [str(pit.get("inningsPitched", "0")),
                          str(pit.get("hits", 0)),
                          str(pit.get("earnedRuns", 0)),
                          str(pit.get("strikeOuts", 0)),
                          str(season.get("era") or "")],
            })

        blocks.append({
            "team": {"name": nick, "shortDisplayName": nick},
            "statistics": [
                {"keys": ["AB", "H", "R", "RBI", "HR", "AVG"],
                 "athletes": hitters},
                {"keys": ["IP", "H", "ER", "SO", "ERA"],
                 "athletes": pitchers},
            ],
        })

    # THE DETAIL MUST SPEAK ITS OWN BLOCKS' LANGUAGE.
    #
    # The award pickers match winner/loser against the block team
    # names. The caller passes the GAME's names - full, "Washington
    # Nationals" - while the blocks carry statsapi nicknames -
    # "Nationals". Exact compare, no match, and every award said "no
    # hitter data" while fifteen perfect box scores sat attached.
    # Third appearance of the full-vs-nickname disease; this one is
    # killed by translating at the boundary: whatever names arrive,
    # the detail stores the BLOCK nicks.
    _nicks = [b["team"]["name"] for b in blocks]

    def _to_block(name):
        n = (name or "").lower().strip()
        for k in _nicks:
            if n == k.lower() or n.endswith(k.lower()):
                return k
        return name

    return {
        "league": "mlb",
        "event_id": str(game_pk),
        "winner": {"team": _to_block(winner_nick)},
        "loser": {"team": _to_block(loser_nick)},
        "boxscore": {"players": blocks},
    }


# per-day schedule cache: (date) -> {(home, away): gamePk}, so a game
# that arrived from another source can still find its box score.
_pk_cache = {}


def game_pk_for(date_str, home_nick, away_nick):
    """gamePk for a matchup on a day, resolving via the day's schedule."""
    m = _pk_cache.get(date_str)
    if m is None:
        m = {}
        for (h, a), row in (finals(date_str) or {}).items():
            m[(h.lower(), a.lower())] = row["id"]
        _pk_cache[date_str] = m
        if len(_pk_cache) > 8:
            _pk_cache.pop(next(iter(_pk_cache)))
    def _match(h, a):
        """
        Exact first, then SUFFIX matching - because the caller's names
        come from whichever source supplied the game. Highlightly says
        "Toronto Blue Jays", statsapi's key is "Blue Jays", and an
        exact compare matched NOTHING - which is why box scores flowed
        (22 rosters parsed) while every award said "no hitter data".
        Same disease as the MLB/mlb case bug, one abstraction over.
        """
        h, a = (h or "").lower().strip(), (a or "").lower().strip()
        hit = m.get((h, a)) or m.get((a, h))
        if hit:
            return hit
        for (kh, ka), pk in m.items():
            if ((h.endswith(kh) and a.endswith(ka))
                    or (h.endswith(ka) and a.endswith(kh))):
                return pk
        return None
    return _match(home_nick, away_nick)


def named_facts(detail):
    """
    The box score as ammunition: 2-3 short NAMED lines per game.
    READS THE ESPN SHAPE this module itself emits - keys zipped
    against stats lists, athlete.displayName - because the first
    version read dict-shaped stats, hit a silent AttributeError on
    the first athlete, and the broad except returned nothing. The
    prompt got zero NAMED lines and the writer confabulated names
    from training - "Kyle Harrison of the Milwaukee Brewers" was a
    real Giant blended into a Brewers award. The proof had passed
    against the same wrong shape the code assumed. Test against the
    shape the system actually produces, not the one imagined.
    """
    out = []
    try:
        blocks = detail["boxscore"]["players"]
        loser = ((detail.get("loser") or {}).get("team") or "")
        for b in blocks:
            team = (b.get("team") or {}).get("name", "")
            best = None
            for grp in (b.get("statistics") or []):
                keys = [k.upper() for k in (grp.get("keys") or [])]
                is_bat = "AB" in keys
                is_pit = "IP" in keys
                for idx, a in enumerate(grp.get("athletes") or []):
                    row = dict(zip(keys, a.get("stats") or []))
                    name = ((a.get("athlete") or {}).get("displayName")
                            or a.get("name") or "")
                    if not name:
                        continue

                    def _n(k):
                        try:
                            return int(float(row.get(k) or 0))
                        except (TypeError, ValueError):
                            return 0
                    if is_bat:
                        score = _n("H") + 2 * _n("HR") + _n("RBI")
                        if score >= 2 and (best is None
                                           or score > best[1]):
                            bits = [f"{_n('H')}-for-{_n('AB')}"]
                            if _n("HR"):
                                bits.append(f"{_n('HR')} HR")
                            if _n("RBI"):
                                bits.append(f"{_n('RBI')} RBI")
                            best = (f"{name} ({team}): "
                                    + ", ".join(bits), score)
                    elif is_pit and idx == 0:      # the starter
                        tag = (" - took the loss"
                               if team == loser else "")
                        out.append(
                            f"{name} started for {team}: "
                            f"{row.get('IP', '?')} IP, "
                            f"{_n('ER')} ER, "
                            f"{_n('SO') or _n('K')} K{tag}")
            if best:
                out.insert(0, best[0])
    except Exception as e:
        print(f"[named_facts] failed: {type(e).__name__}: {e}",
              flush=True)
    return out[:4]
