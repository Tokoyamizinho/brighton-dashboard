"""openfootball / football.json — resultados e calendário da Premier League.

Dados em domínio público, publicados no GitHub:
    https://raw.githubusercontent.com/openfootball/football.json/master/{2026-27}/en.1.json

Mantido por voluntários: as temporadas passadas estão completas, mas a
temporada em andamento pode ficar algumas rodadas atrasada. Por isso os
placares que faltarem são completados com a Wikipedia (ver wikipedia.py).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..http import PoliteSession
from ..transform.teams import canonical_team

BASE = "https://raw.githubusercontent.com/openfootball/football.json/master/"


def season_folder(season: int) -> str:
    """2026 -> '2026-27'"""
    return f"{season}-{str(season + 1)[-2:]}"


class OpenFootballScraper:
    def __init__(self, session: PoliteSession, raw_dir: Path, league_file: str = "en.1.json") -> None:
        self.session = session
        self.league_file = league_file
        self.raw_dir = Path(raw_dir) / "openfootball"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def season(self, season: int, reuse_raw: bool = False, use_cache: bool = True) -> dict[str, Any]:
        path = self.raw_dir / f"{season_folder(season)}_{self.league_file}"
        if reuse_raw and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = self.session.get_json(f"{BASE}{season_folder(season)}/{self.league_file}", use_cache=use_cache)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def _score(score: Any) -> tuple[int | None, int | None, int | None, int | None]:
    """(gols_casa, gols_fora, intervalo_casa, intervalo_fora).
    O placar vem como {"ft": [h, a], "ht": [h, a]} ou, às vezes, só [h, a]."""
    if isinstance(score, dict):
        ft, ht = score.get("ft"), score.get("ht")
    elif isinstance(score, list):
        ft, ht = score, None
    else:
        return None, None, None, None
    ft = ft if isinstance(ft, list) and len(ft) == 2 else [None, None]
    ht = ht if isinstance(ht, list) and len(ht) == 2 else [None, None]
    return ft[0], ft[1], ht[0], ht[1]


def parse_matches(data: dict[str, Any], season: int) -> pd.DataFrame:
    """Uma linha por partida (disputada ou não)."""
    rows = []
    for m in data.get("matches", []):
        hg, ag, hth, hta = _score(m.get("score"))
        rnd = re.search(r"\d+", str(m.get("round", "")))
        rows.append(
            {
                "season": season,
                "matchday": int(rnd.group()) if rnd else None,
                "date": m.get("date"),
                "time": m.get("time"),
                "home": canonical_team(m.get("team1")),
                "away": canonical_team(m.get("team2")),
                "home_goals": hg,
                "away_goals": ag,
                "ht_home_goals": hth,
                "ht_away_goals": hta,
                "score_source": "openfootball" if hg is not None else None,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        for c in ("home_goals", "away_goals", "ht_home_goals", "ht_away_goals"):
            df[c] = pd.to_numeric(df[c]).astype("Int64")
    return df
