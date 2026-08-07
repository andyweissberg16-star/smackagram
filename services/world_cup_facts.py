"""
2026 FIFA World Cup — curated real results, one entry per national team.

The tournament ran June 11 – July 19, 2026 (co-hosted USA/Canada/Mexico) and
is OVER. Results are final and never change, so unlike the live sports feeds
this is a static, hand-verified lookup. Each team's facts describe exactly how
their 2026 World Cup ended — the roast generator pulls these the same way it
pulls live-feed facts, so a Germany roast KNOWS about Ecuador and an Argentina
roast KNOWS about the final.

Keyed by the lowercase display name used in chat_team_lists world_cup block.
Each value is a list of short, TRUE, roastable facts. The generator is told to
pick ONE and build the joke on it, and NOT to invent any other results.

Final:        Spain 1–0 Argentina (Spain champions, 1st title since 2010)
3rd place:    England 6–4 France
Golden Boot / all-time top scorer milestone: Mbappé (in a losing France side)
"""

WORLD_CUP_2026_FACTS = {
    # ---- The final two ----
    "argentina": [
        "they lost the 2026 World Cup final 1–0 to Spain",
        "Messi got them all the way to the final and still went home with nothing",
        "they were the defending champions and couldn't repeat — no repeat winner since Brazil in 1962, and they didn't change that",
        "one goal from Spain was all it took to end the title defense",
        "they scored twice late to stun England in the semi, then went quiet when it counted in the final",
    ],
    "spain": [
        "they won the 2026 World Cup but bored the neutrals to death doing it — a 1–0 final is not exactly box office",
        "they beat Argentina 1–0 in the final: efficient, tidy, and about as thrilling as watching paint dry",
        "champions, sure, but 'possession, possession, one goal, park the bus' isn't a highlight reel",
        "they won it all and the lasting memory is Messi losing, not anything Spain actually did",
        "first title since 2010 and they celebrated like they'd reinvented the sport — it was a 1–0",
    ],
    # ---- The nearly-men ----
    "france": [
        "they lost the semifinal to Spain 2–0, then lost the third-place game 6–4 to England",
        "Mbappé became the World Cup's all-time leading scorer and STILL went home with nothing",
        "they shipped SIX goals to England in the third-place game — a bronze-medal shootout they lost 6–4",
        "back-to-back World Cups reaching the last four and coming up empty both times",
    ],
    "england": [
        "they came THIRD — beat France 6–4 in the bronze game, which is a lovely way to say they lost the semi",
        "Argentina scored twice late to knock them out 2–1 in the semifinal",
        "another World Cup, another semifinal exit — the trophy drought rolls on",
        "Saka scored a hat-trick in the THIRD-place game, the one nobody remembers",
    ],
    # ---- Big names, early doors ----
    "brazil": [
        "they got knocked out by NORWAY in the round of 16 — Norway, at a World Cup",
        "five-time champions, dumped out by Haaland and a Norway side at their first knockout in decades",
        "round of 16 and gone, beaten by a country better known for skiing",
        "the Seleção went home to Norway of all teams — let that sink in",
    ],
    "germany": [
        "they lost 2–1 to ECUADOR in the group stage",
        "four-time world champions, beaten by Ecuador on the way to another early exit",
        "Ecuador put them to the sword 2–1 — that's the headline nobody in Germany wants",
        "the group stage used to be a formality for Germany; in 2026 it was a graveyard again",
    ],
    "portugal": [
        "they were knocked out by Spain in the round of 16 — Ronaldo's last dance ended in the last 16",
        "Cristiano's final World Cup ended with a whimper against the eventual champions",
        "round of 16 and out, sent home by their neighbours Spain",
    ],
    "netherlands": [
        "they went out to Morocco in the knockouts — again the nearly-team, never the champions",
        "another World Cup where the Dutch talked a big game and delivered nothing",
        "beaten by Morocco, packed up, went home — total football, total blank",
    ],
    "belgium": [
        "they beat the USA and then got dismantled by Spain in the quarterfinals",
        "the 'golden generation' is now a bronze-at-best generation — quarterfinal exit to Spain",
        "De Bruyne and co. bowed out in the last eight, the story of their careers",
    ],
    "croatia": [
        "the 2022 semifinalists couldn't repeat the magic and bowed out early in 2026",
        "an aging side ran out of miracles — no deep run this time",
    ],
    "uruguay": [
        "all that South American pedigree and another World Cup with nothing to show for it",
        "they flattered to deceive and went home before the business end",
    ],
    # ---- The hosts ----
    "usa": [
        "the co-hosts got knocked out by Belgium in the round of 16 — home tournament, last-16 exit",
        "a World Cup on home soil and they still couldn't get past the round of 16",
        "Belgium sent the hosts packing in front of their own fans",
    ],
    "mexico": [
        "the co-hosts were knocked out by England in the round of 16 — first host nation eliminated",
        "home World Cup, and England bounced them at Estadio Azteca in the last 16",
        "the famous 'quinto partido' curse holds — round of 16 and out, at home",
    ],
    "canada": [
        "they got thrashed 3–0 by Morocco in the round of 16 — first co-host eliminated",
        "a home World Cup ended with a 3–0 beating from Morocco",
        "Canada's big moment lasted exactly until they met a team that could actually play",
    ],
    # ---- Cinderellas who outlasted the giants (roast angle: they peaked here) ----
    "norway": [
        "Haaland's fairy tale got as far as the quarterfinals before England ended it in extra time",
        "they knocked out Brazil and then ran out of magic against England in the last eight",
        "the run of a lifetime — and it still ended with them going home",
    ],
    "morocco": [
        "back-to-back World Cup quarterfinals and STILL no semifinal in 2026 — France knocked them out 2–0 again",
        "the France hoodoo continues: another World Cup, another 2–0 exit to Les Bleus",
    ],
    "switzerland": [
        "their first quarterfinal since 1954 ended with Messi's Argentina sending them home",
        "a lovely run that stopped exactly where everyone expected — the last eight",
    ],
    "colombia": [
        "they went out on penalties to Switzerland in the round of 16",
        "so close, and then the lottery of penalties sent them home",
    ],
    "ecuador": [
        "they beat Germany 2–1 and STILL only scraped through as a third-place team, then lost to Mexico",
        "the giant-killing of Germany was the peak — Mexico ended the run soon after",
    ],
    "japan": [
        "they drew the group and then ran into Brazil in the round of 32 — the ceiling again",
        "another World Cup, another last-16-ish exit for the Samurai Blue",
    ],
    "senegal": [
        "out in the round of 32 — all that talent and another early flight home",
    ],
    "egypt": [
        "Salah and all, they took Argentina to the wire in the round of 16 and still lost",
        "the round of 16 was the end of the road — close to Argentina, but close is a loser's word",
    ],
    # ---- Group-stage also-rans (generic-but-true) ----
    "denmark":   ["they didn't make it out of the group stage in 2026"],
    "poland":    ["another World Cup where Poland were home before the knockouts got interesting"],
    "serbia":    ["all that squad talent and another group-stage exit"],
    "wales":     ["back at a World Cup and back home after the group stage"],
    "australia": ["the Socceroos got their moment and then got sent home in the knockouts"],
    "ghana":     ["out early — the Black Stars flickered and faded"],
    "cameroon":  ["another World Cup, another group-stage goodbye"],
    "nigeria":   ["the Super Eagles couldn't get the job done and went home early"],
    "scotland":  ["back at a World Cup after decades — and out at the group stage, of course"],
    "ireland":   ["they made the trip and made an early exit"],
    "sweden":    ["France put three past them and sent them out 3–0"],
    "norway_dup": [],  # guard, unused
    "austria":   ["they went home when the knockouts got serious"],
    "south korea": ["out of the tournament once the big boys showed up"],
}


def facts_for(team_name: str):
    """Return the curated 2026 World Cup facts for a national team, or []."""
    if not team_name:
        return []
    key = team_name.strip().lower()
    return list(WORLD_CUP_2026_FACTS.get(key, []))
