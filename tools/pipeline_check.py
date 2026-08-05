"""
Does the show pipeline survive the data it will actually get?
=============================================================

WHY THIS EXISTS
---------------
The daily show broke four separate times in one day, each with a
different error, and every one was found by a person running it rather
than by anything checking first:

    'margin'                  a field the shape did not provide
    every game a shutout      home_score/away_score missing, silently
    fifteen-minute hang       a fetch made twice as expensive
    zero games                one date asked for instead of two

They share a cause. The pipeline was written against ESPN's data, ESPN
stopped answering, and every layer that assumed ESPN's shape failed one
at a time as it was reached.

WHAT THIS DOES
--------------
Runs the ENTIRE pipeline - layout, facts, running order, script
assembly - against games shaped like each source really returns, with
NO network calls at all.

    RICH      everything Highlightly gives with a box score
    PLAIN     scoreline only, which is what a bad night looks like
    PLAYS     balldontlie: scoring plays, no box score
    MINIMAL   the least any source could return and still be a game
    EMPTY     no games, which must hold rather than crash

If a stage reads a field a source cannot supply, this says so HERE
rather than at 5:55 in the morning.

RUN IT
------
    python3 tools/pipeline_check.py

Or from the admin panel at /api/admin/pipeline-check.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base(source, league="mlb"):
    """The fields EVERY source can supply, because they come from the
    scoreline. Anything beyond this is a bonus, and the pipeline must
    survive without it."""
    return {
        "league": league, "label": "MLB", "unit": "runs",
        "winner": "Yankees", "loser": "Red Sox",
        "winner_score": 7, "loser_score": 2,
        "home_score": 2, "away_score": 7,
        "home": "Red Sox", "away": "Yankees",
        "id": "1", "highlightly_id": "1",
        "venue": None, "plays": [], "source": source,
        "margin": 5, "one_run": False, "shutout": False,
        "at_home": True, "loser_at_home": True,
        "extras": False, "starter_short": False, "big_hitter": False,
        "quality_start": False, "stranded": 0, "strikeouts": 0,
        "errors": 0, "home_hits": 0, "away_hits": 0,
        "home_errors": 0, "away_errors": 0,
        "periods": None, "facts": [], "deep_facts": [],
    }


def samples():
    """One game per realistic shape."""
    rich = _base("highlightly")
    rich.update({
        "venue": "Yankee Stadium", "home_hits": 4, "away_hits": 11,
        "home_errors": 3, "away_errors": 0, "stranded": 11,
        "strikeouts": 13, "errors": 3, "quality_start": True,
        "big_hitter": True, "deep_facts": ["Judge went 4 for 5"],
    })

    plays = _base("balldontlie")
    plays["plays"] = ["Judge homered to right center (410 feet).",
                      "Duran homered to left (406 feet)."]

    plain = _base("highlightly")

    minimal = {
        "league": "wnba", "label": "WNBA", "unit": "points",
        "winner": "Mercury", "loser": "Sky",
        "winner_score": 106, "loser_score": 101,
        "home_score": 101, "away_score": 106,
        "home": "Sky", "away": "Mercury",
        "id": "9", "highlightly_id": None, "source": "balldontlie",
        "margin": 5, "one_run": False, "shutout": False,
        "at_home": True, "loser_at_home": True,
        "venue": None, "plays": [],
        "extras": False, "starter_short": False, "big_hitter": False,
        "quality_start": False, "stranded": 0, "strikeouts": 0,
        "errors": 0, "home_hits": 0, "away_hits": 0,
        "home_errors": 0, "away_errors": 0,
        "periods": None, "facts": [], "deep_facts": [],
    }

    # NO SCORELINE AT ALL.
    #
    # A postponed game, or a thin feed. This shape crashed a whole
    # episode with "'>' not supported between instances of NoneType and
    # NoneType", because max(None, None) raises - and .get(key, 0) does
    # not help when the key EXISTS and holds None.
    #
    # It is here so that never surprises anybody again.
    noscore = _base("highlightly")
    noscore.update({
        "winner_score": None, "loser_score": None,
        "home_score": None, "away_score": None,
        "margin": 0, "shutout": False, "one_run": False,
    })

    # A BLANK TEAM NAME.
    #
    # "".split() is an EMPTY LIST, so [-1] on it raises IndexError. Rare
    # but entirely possible from a thin feed, and it would have taken the
    # whole episode down.
    blank = _base("highlightly")
    blank.update({"winner": "", "loser": "Red Sox"})

    return {
        "RICH  (Highlightly + box score)": [rich],
        "BLANK TEAM NAME": [blank],
        "NO SCORELINE (postponed / thin feed)": [noscore],
        "PLAYS (balldontlie, no box)": [plays],
        "PLAIN (scoreline only)": [plain],
        "MINIMAL (least possible)": [minimal],
        "MIXED (all sources at once)": [rich, plays, plain, minimal],
        "EMPTY (no games at all)": [],
    }


def check_stage(name, fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
        return True, out, ""
    except Exception as e:
        tb = traceback.format_exc().strip().split("\n")
        where = [l.strip() for l in tb if "line" in l and "/" in l]
        return False, None, f"{type(e).__name__}: {e}" + (
            f"  at {where[-1][:70]}" if where else "")


def run():
    from services import show_layout

    failures = []
    print("PIPELINE CHECK - no network, no cost\n")

    for label, games in samples().items():
        print(f"  {label}")

        # read_game - the layout's view of a game
        if games:
            for g in games:
                ok, out, err = check_stage("read_game",
                                           show_layout.read_game, g)
                if not ok:
                    failures.append((label, "read_game", err))
                    print(f"      read_game        FAILED  {err[:60]}")
                    break
            else:
                print(f"      read_game        ok")

        # the id that unlocks box scores - the Smack Ball needs it
        if games:
            need = [g for g in games
                    if g.get("source") == "highlightly"
                    and g.get("highlightly_id")]
            if need:
                from services import show_service
                try:
                    show_service._attach_highlightly_ids(
                        need, log=lambda *a, **k: None)
                    got = sum(1 for g in need if g.get("_hl_id"))
                    mark = "ok" if got == len(need) else "FAILED"
                    if got != len(need):
                        failures.append((label, "_hl_id",
                                         f"{got}/{len(need)} got an id"))
                    print(f"      _hl_id attached  {mark}"
                          f"      {got}/{len(need)}")
                except Exception as e:
                    failures.append((label, "_hl_id", str(e)))
                    print(f"      _hl_id attached  FAILED  {e}")

        # build_facts - where a None scoreline crashed a whole episode
        if games:
            from services import show_service
            bad = None
            for g in games:
                ok, out, err = check_stage("build_facts",
                                           show_service.build_facts, g)
                if not ok:
                    bad = err
                    break
            if bad:
                failures.append((label, "build_facts", bad))
                print(f"      build_facts      FAILED  {bad[:58]}")
            else:
                print(f"      build_facts      ok")

        # build - assigning games to slots
        ok, out, err = check_stage("build", show_layout.build, games)
        if ok:
            slots = len((out or {}).get("slots", []))
            print(f"      build            ok      {slots} slot(s)")
        else:
            failures.append((label, "build", err))
            print(f"      build            FAILED  {err[:60]}")
        print()

    # ---- THE STAGES AFTER THE LAYOUT ----
    #
    # The show has never got far enough to exercise these, because it
    # kept crashing earlier. So they were completely untested - and one
    # of them lost a whole episode on a one-segment night.
    print("  SEGMENT STAGES (never reached in a real run until now)\n")
    from services import show_service

    seg_cases = {
        "no segments":     [],
        "ONE segment":     [{"league": "MLB", "text": "One game tonight."}],
        "two segments":    [{"league": "MLB", "text": "A."},
                            {"league": "WNBA", "text": "B."}],
        "eight segments":  [{"league": "MLB", "text": f"Seg {i}."}
                            for i in range(8)],
    }
    # The whole segment chain, not just one stage - each one hands its
    # output to the next, so a count that survives one can still break
    # the one after.
    _quiet = lambda *a, **k: None
    _plan = {"publish": True, "minutes": 5, "word_budget": 750}
    chain = [
        ("maybe_interruption",
         lambda sg: show_service.maybe_interruption(sg)),
        ("_flag_repeats",
         lambda sg: show_service._flag_repeats(sg, _quiet) or sg),
        ("_cap_construction",
         lambda sg: show_service._cap_construction(sg)),
        ("enforce_length",
         lambda sg: show_service.enforce_length(sg, _plan, log=_quiet)),
    ]
    for label, segs in seg_cases.items():
        current = [dict(x) for x in segs]
        line = f"    {label:18}"
        broke = False
        for stage_name, fn in chain:
            ok, out, err = check_stage(stage_name, fn, current)
            if not ok:
                failures.append((label, stage_name, err))
                line += f"  {stage_name}: FAILED"
                broke = True
                break
            if isinstance(out, list):
                current = out
        if not broke:
            line += f"  all {len(chain)} stages ok, {len(current)} segment(s)"
        print(line)
    print()

    print("=" * 60)
    if failures:
        print(f"{len(failures)} FAILURE(S) - the show would break on this data:\n")
        for label, stage, err in failures:
            print(f"  {label}")
            print(f"    {stage}: {err}\n")
        return 1
    print("All shapes survive the layout. No stage reads a field its")
    print("source cannot supply.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
