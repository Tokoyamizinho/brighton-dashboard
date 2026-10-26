"""football-data.co.uk (OPCIONAL) — estatísticas por jogo: chutes, chutes no
gol, escanteios, faltas, cartões e árbitro.

Fica DESLIGADO por padrão (`sources.football_data: false` no config.yaml).
O robots.txt do site permite robôs comuns, mas antes de ligar leia os termos
de uso em https://www.football-data.co.uk e confirme que o seu uso está de
acordo com eles.

Arquivo por temporada (Premier League = E0):
    https://www.football-data.co.uk/mmz4281/2627/E0.csv
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from ..http import PoliteSession
from ..transform.teams import canonical_team

BASE = "https://www.football-data.co.uk/mmz4281/"

COLUMNS = {
    "FTHG": "home_goals", "FTAG": "away_goals", "HTHG": "ht_home_goals", "HTAG": "ht_away_goals",
    "HS": "home_shots", "AS": "away_shots", "HST": "home_shots_on_target", "AST": "away_shots_on_target",
    "HC": "home_corners", "AC": "away_corners", "HF": "home_fouls", "AF": "away_fouls",
    "HY": "home_yellow", "AY": "away_yellow", "HR": "home_red", "AR": "away_red",
    "Referee": "referee",
}


def season_code(season: int) -> str:
    """2026 -> '2627'"""
    return f"{str(season)[-2:]}{str(season + 1)[-2:]}"


class FootballDataScraper:
    def __init__(self, session: PoliteSession, raw_dir: Path, division: str = "E0") -> None:
        self.session = session
        self.division = division
        self.raw_dir = Path(raw_dir) / "football_data"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def season_csv(self, season: int, reuse_raw: bool = False, use_cache: bool = True) -> str:
        path = self.raw_dir / f"{self.division}_{season_code(season)}.csv"
        if reuse_raw and path.exists():
            return path.read_text(encoding="utf-8")
        text = self.session.get_text(f"{BASE}{season_code(season)}/{self.division}.csv", use_cache=use_cache)
        path.write_text(text, encoding="utf-8")
        return text


def parse_csv(text: str, season: int) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text.lstrip("﻿")))
    df = df.dropna(subset=["HomeTeam", "AwayTeam"])
    out = pd.DataFrame(
        {
            "season": season,
            "date": pd.to_datetime(df["Date"], dayfirst=True, errors="coerce"),
            "home": df["HomeTeam"].map(canonical_team),
            "away": df["AwayTeam"].map(canonical_team),
        }
    )
    for src, dst in COLUMNS.items():
        if src in df.columns:
            out[dst] = df[src] if src == "Referee" else pd.to_numeric(df[src], errors="coerce").astype("Int64")
    return out.reset_index(drop=True)
