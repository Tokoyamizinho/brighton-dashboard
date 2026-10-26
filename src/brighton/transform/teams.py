"""Nome canônico dos clubes.

Cada fonte escreve de um jeito:
    openfootball   "Brighton & Hove Albion FC", "AFC Bournemouth", "Hull City AFC"
    Wikipedia      "Brighton & Hove Albion F.C.", "Hull City A.F.C."
    football-data  "Brighton", "Man City", "Nott'm Forest"
O nome canônico é o nome completo sem sufixos ("Brighton & Hove Albion").
"""
from __future__ import annotations

import re

from .utils import normalize_name

# apelidos usados pelo football-data.co.uk e outros
ALIASES = {
    "brighton": "Brighton & Hove Albion",
    "man city": "Manchester City",
    "man united": "Manchester United",
    "man utd": "Manchester United",
    "nott'm forest": "Nottingham Forest",
    "nottm forest": "Nottingham Forest",
    "wolves": "Wolverhampton Wanderers",
    "newcastle": "Newcastle United",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "west ham": "West Ham United",
    "leeds": "Leeds United",
    "leicester": "Leicester City",
    "ipswich": "Ipswich Town",
    "luton": "Luton Town",
    "coventry": "Coventry City",
    "hull": "Hull City",
    "sheffield united": "Sheffield United",
    "sheffield utd": "Sheffield United",
    "bournemouth": "Bournemouth",
    "west brom": "West Bromwich Albion",
    "norwich": "Norwich City",
    "cardiff": "Cardiff City",
    "swansea": "Swansea City",
    "stoke": "Stoke City",
    "huddersfield": "Huddersfield Town",
}

_SUFFIX = re.compile(r"\s+(F\.?C\.?|A\.?F\.?C\.?)$", re.IGNORECASE)
_PREFIX = re.compile(r"^(A\.?F\.?C\.?|F\.?C\.?)\s+", re.IGNORECASE)


def canonical_team(name: str | None) -> str:
    if not name:
        return ""
    n = re.sub(r"\s+", " ", name.replace("\xa0", " ")).strip()
    alias = ALIASES.get(n.lower())
    if alias:
        return alias
    n = _SUFFIX.sub("", n)
    n = _PREFIX.sub("", n)
    return ALIASES.get(n.lower(), n)


def team_id(name: str | None) -> str:
    """'Brighton & Hove Albion' -> 'brighton-hove-albion'"""
    return normalize_name(canonical_team(name)).replace(" ", "-")
