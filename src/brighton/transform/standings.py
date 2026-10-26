"""Reconstrução da tabela da liga rodada a rodada a partir dos jogos."""
from __future__ import annotations

import pandas as pd


def standings_by_round(team_matches: pd.DataFrame) -> pd.DataFrame:
    """Classificação de cada time após o seu n-ésimo jogo.

    Critérios da Premier League: pontos, saldo de gols, gols marcados.
    """
    cols = ["season", "team_id", "round", "pts", "goals_for", "goals_against"]
    df = team_matches[cols].sort_values(["season", "team_id", "round"]).copy()

    g = df.groupby(["season", "team_id"], sort=False)
    df["pts_cum"] = g["pts"].cumsum()
    df["gf_cum"] = g["goals_for"].cumsum()
    df["ga_cum"] = g["goals_against"].cumsum()
    df["gd_cum"] = df["gf_cum"] - df["ga_cum"]
    df["ppg_cum"] = df["pts_cum"] / df["round"]

    # ranking dentro de (temporada, rodada) com desempate pts > saldo > gols
    key = df["pts_cum"] * 1_000_000 + (df["gd_cum"] + 500) * 1_000 + df["gf_cum"]
    df["position"] = key.groupby([df["season"], df["round"]]).rank(method="min", ascending=False).astype(int)
    out_cols = ["season", "team_id", "round", "pts_cum", "ppg_cum", "gf_cum", "ga_cum", "gd_cum", "position"]
    return df[out_cols].reset_index(drop=True)


def final_table(standings: pd.DataFrame) -> pd.DataFrame:
    """Última rodada disponível de cada time em cada temporada, reclassificada
    (útil quando há jogos adiados e os times têm números de jogos diferentes)."""
    idx = standings.groupby(["season", "team_id"])["round"].idxmax()
    last = standings.loc[idx].copy()
    key = last["pts_cum"] * 1_000_000 + (last["gd_cum"] + 500) * 1_000 + last["gf_cum"]
    last["final_position"] = key.groupby(last["season"]).rank(method="min", ascending=False).astype(int)
    return last.reset_index(drop=True)
