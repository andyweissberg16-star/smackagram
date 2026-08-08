"""
Reverse lookup: team name (or nickname) -> league key, for the Smack Feed's
league tabs. Built once from CHAT_LEAGUES.

The Smack Feed groups colleges (sec/bigten/big12/acc/ncaab/ncaawb) under a
single "ncaa" tab, and skips soccer/world_cup for the tab row (they still
appear in ALL). Everything maps to one of: mlb, nfl, nba, nhl, wnba, ncaa.
"""

from services.chat_team_lists import CHAT_LEAGUES

# CHAT_LEAGUES league -> the feed tab it belongs to.
_TAB_FOR = {
    "mlb": "mlb", "nfl": "nfl", "nba": "nba", "nhl": "nhl", "wnba": "wnba",
    "sec": "ncaa", "bigten": "ncaa", "big12": "ncaa", "acc": "ncaa",
    "ncaab": "ncaa", "ncaawb": "ncaa",
    # soccer + world cup have no dedicated tab; they still show in ALL.
    "mls": "soccer", "epl": "soccer", "laliga": "soccer",
    "bundesliga": "soccer", "seriea": "soccer", "world_cup": "soccer",
}

# Feed tab order for the league bar.
FEED_TABS = ["mlb", "nfl", "nba", "nhl", "wnba", "ncaa"]

# Build: lowercased team name AND nickname -> feed tab.
_NAME_TO_TAB = {}
for _lg, _teams in CHAT_LEAGUES.items():
    _tab = _TAB_FOR.get(_lg)
    if not _tab:
        continue
    for _code, _full in _teams.items():
        low = _full.lower()
        _NAME_TO_TAB.setdefault(low, _tab)
        # also index the last word (nickname), how posts usually store it
        nick = low.split()[-1] if low.split() else low
        _NAME_TO_TAB.setdefault(nick, _tab)


def league_for_team(name):
    """Best-effort league tab for a team name or nickname. None if unknown."""
    if not name:
        return None
    low = str(name).strip().lower()
    if low in _NAME_TO_TAB:
        return _NAME_TO_TAB[low]
    # try the last word (nickname) and a contains-match as a fallback
    parts = low.split()
    if parts and parts[-1] in _NAME_TO_TAB:
        return _NAME_TO_TAB[parts[-1]]
    for cand, tab in _NAME_TO_TAB.items():
        if cand in low or low in cand:
            return tab
    return None
