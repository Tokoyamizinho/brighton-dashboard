"""Teste de ponta a ponta: data/raw (arquivos reais) -> modelo estrela -> CSVs."""
import datetime as dt

import pandas as pd

from brighton.config import load_settings
from brighton.transform.model import ModelBuilder

EXPECTED = {
    "dim_season", "dim_team", "dim_player", "dim_date", "fact_team_match", "fact_standings",
    "fact_fixtures", "fact_player_season", "fact_transfers", "meta_refresh",
}
BHA = "brighton-hove-albion"


def _build(cfg, today=dt.date(2026, 10, 23)):
    builder = ModelBuilder(load_settings(cfg))
    builder.today = today
    tables = builder.build()
    paths = builder.write()
    return tables, paths


def test_all_tables_written(raw_project):
    tmp, cfg = raw_project
    tables, paths = _build(cfg)
    assert {p.stem for p in paths} == EXPECTED
    for p in paths:
        assert pd.read_csv(p).shape[0] > 0, f"{p.name} vazio"
    assert (tmp / "processed" / "LICENSE-DATA.md").exists()


def test_final_table_matches_reality(raw_project):
    """2025/26 reconstruída a partir dos 380 jogos: Brighton terminou em 8º."""
    _, cfg = raw_project
    t, _ = _build(cfg)
    ds = t["dim_season"].set_index("season")
    assert ds.loc[2025, "brighton_matches_played"] == 38
    assert ds.loc[2025, "brighton_final_position"] == 8
    st = t["fact_standings"]
    last = st[(st["season"] == 2025) & (st["round"] == 38)]
    assert sorted(last["position"]) == list(range(1, 21))  # sem empates na tabela final


def test_wikipedia_fills_recent_results(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    tm = t["fact_team_match"]
    b = tm[(tm["season"] == 2026) & tm["is_brighton"]].sort_values("datetime")
    # openfootball tinha só 5 jogos do Brighton; a Wikipedia completa Sunderland e Palace
    assert len(b) == 7
    assert b["score_source"].value_counts().to_dict() == {"openfootball": 5, "wikipedia": 2}
    sun = b[b["opponent"] == "Sunderland"].iloc[0]
    assert (sun["goals_for"], sun["goals_against"], sun["result_pt"], sun["venue"]) == (2, 0, "V", "Fora")
    assert list(b["round"]) == list(range(1, 8))
    # placar do intervalo vem do openfootball; nos jogos da Wikipedia fica vazio
    assert b.loc[b["score_source"] == "openfootball", "ht_state"].notna().all()
    assert b.loc[b["score_source"] == "wikipedia", "ht_state"].isna().all()


def test_fixtures_next_match_and_timezone(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    fx = t["fact_fixtures"]
    assert len(fx) == 38 and fx["is_next"].sum() == 1
    nxt = fx[fx["is_next"]].iloc[0]
    assert nxt["opponent"] == "Liverpool" and nxt["venue"] == "Fora"
    # 25/10/2026 o Reino Unido já saiu do horário de verão: 14h em Londres = 11h em Brasília
    assert nxt["kickoff_brasilia"] == pd.Timestamp("2026-10-25 11:00")
    assert 1 <= nxt["difficulty"] <= 5 and 1 <= nxt["opponent_position_now"] <= 20
    assert fx.loc[fx["finished"], "result_pt"].notna().all()
    assert fx["next_n"].dropna().tolist() == list(range(1, 32))
    assert not fx["result_pending"].any()


def test_past_match_without_score_is_pending_not_next(raw_project):
    """Sem a Wikipedia, os jogos de 10/10 e 18/10 não têm placar: não podem
    aparecer como "próximo jogo"."""
    tmp, cfg = raw_project
    for f in (tmp / "raw" / "wikipedia").glob("*Premier_League*"):
        f.unlink()
    t, _ = _build(cfg)
    fx = t["fact_fixtures"]
    assert fx.loc[fx["result_pending"], "opponent"].tolist() == ["Sunderland", "Crystal Palace"]
    assert fx[fx["is_next"]].iloc[0]["opponent"] == "Liverpool"


def test_next_match_rolls_over_after_kickoff(raw_project):
    """Liverpool x Brighton foi em 25/10 às 11h (Brasília). Depois do jogo, mesmo sem
    o placar nas fontes, o próximo jogo passa a ser o seguinte; antes do apito final
    ele ainda é o próximo."""
    import datetime as dt

    _, cfg = raw_project
    b = ModelBuilder(load_settings(cfg))
    b.now = dt.datetime(2026, 10, 25, 12, 30)  # bola rolando
    fx = b.build()["fact_fixtures"]
    assert fx[fx["is_next"]].iloc[0]["opponent"] == "Liverpool"

    b = ModelBuilder(load_settings(cfg))
    b.now = dt.datetime(2026, 10, 26, 12, 0)
    fx = b.build()["fact_fixtures"]
    liv = fx[fx["opponent"] == "Liverpool"].iloc[0]
    assert liv["result_pending"] and not liv["is_next"]
    nxt = fx[fx["is_next"]].iloc[0]
    assert nxt["kickoff_brasilia"] > pd.Timestamp("2026-10-26 12:00") and nxt["next_n"] == 1


def test_players_and_transfers(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    dim = t["dim_player"].set_index("player_key")
    assert dim.index.is_unique
    # Adingra aparece duas vezes na mesma temporada (chegada e empréstimo): uma linha
    assert (t["fact_transfers"]["player_key"] == "wiki:Simon_Adingra").sum() == 2
    adingra = dim.loc["wiki:Simon_Adingra"]
    assert adingra["wikipedia_url"] == "https://en.wikipedia.org/wiki/Simon_Adingra"
    # Struijk: contratado e com jogos na mesma temporada -> uma linha, jogou pelo clube
    struijk_dim = dim.loc["wiki:Pascal_Struijk"]
    assert struijk_dim["played_for_club"] and struijk_dim["position_group"] == "Defensor"
    assert not dim.loc["wiki:Jan_Paul_van_Hecke", "played_for_club"]  # só aparece como venda
    tr = t["fact_transfers"]
    vh = tr[tr["player_name"] == "Jan Paul van Hecke"].iloc[0]
    assert vh["fee_gbp_signed"] == 52_000_000  # receita = positivo
    struijk = tr[tr["player_name"] == "Pascal Struijk"].iloc[0]
    assert struijk["fee_gbp_signed"] == -15_000_000  # gasto = negativo
    assert set(tr.loc[tr["season"] == 2025, "is_first_team"]) == {True, False}


def test_referential_integrity(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    players = set(t["dim_player"]["player_key"])
    for fact in ("fact_player_season", "fact_transfers"):
        assert set(t[fact]["player_key"]) <= players, fact
    teams = set(t["dim_team"]["team_id"])
    assert BHA in teams and len(teams) >= 20
    for fact, col in (("fact_team_match", "team_id"), ("fact_team_match", "opponent_id"),
                      ("fact_standings", "team_id"), ("fact_fixtures", "opponent_id")):
        assert set(t[fact][col]) <= teams, (fact, col)
    seasons = set(t["dim_season"]["season"])
    for fact in ("fact_team_match", "fact_standings", "fact_player_season", "fact_transfers", "fact_fixtures"):
        assert set(t[fact]["season"]) <= seasons, fact
    dates = set(t["dim_date"]["date"])
    assert set(t["fact_team_match"]["date"]) <= dates


def test_optional_football_data(raw_project_with_fd):
    _, cfg = raw_project_with_fd
    t, _ = _build(cfg)
    tm = t["fact_team_match"]
    b = tm[(tm["season"] == 2026) & tm["is_brighton"]].set_index("opponent")
    assert (b.loc["Aston Villa", "shots_for"], b.loc["Aston Villa", "shots_on_target_for"]) == (18, 9)
    assert b.loc["Aston Villa", "shots_against"] == 5 and b.loc["Aston Villa", "referee"] == "Referee A"
    # jogo sem linha no CSV do football-data: estatística vazia
    assert pd.isna(b.loc["Leeds United", "shots_for"])


def test_without_football_data_stats_columns_exist_but_empty(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    tm = t["fact_team_match"]
    assert {"shots_for", "shots_on_target_against", "referee"} <= set(tm.columns)
    assert tm["shots_for"].isna().all()


def test_meta_refresh(raw_project):
    _, cfg = raw_project
    t, _ = _build(cfg)
    meta = t["meta_refresh"].set_index("source")
    assert meta.loc["pipeline", "last_result_date"] >= dt.date(2026, 10, 18)
    assert t["dim_season"].set_index("season").loc[2026, "data_until"] == dt.date(2026, 10, 18)
    assert meta.loc["openfootball", "last_result_date"] < meta.loc["wikipedia", "last_result_date"]


def test_current_table_uses_each_teams_latest_game(raw_project):
    """Com jogos adiados os times têm números de jogos diferentes. A classificação
    atual usa o último jogo de CADA time (antes, só os times com mais jogos apareciam)."""
    _, cfg = raw_project
    t, _ = _build(cfg)
    st = t["fact_standings"]
    for season, g in st.groupby("season"):
        latest = g[g["is_latest"]]
        assert latest["team_id"].is_unique and len(latest) == g["team_id"].nunique() == 20, season
        assert sorted(latest["table_position"]) == list(range(1, 21)), season
        assert g.loc[~g["is_latest"], "table_position"].isna().all()
    # simula um jogo adiado: sem a última partida de um time, ele continua na tabela atual
    from brighton.transform.standings import final_table, standings_by_round

    tm = t["fact_team_match"]
    tm = tm[~((tm["season"] == 2026) & (tm["team_id"] == "arsenal") & (tm["round"] == tm["round"].max()))]
    fin = final_table(standings_by_round(tm))
    assert len(fin[fin["season"] == 2026]) == 20
    # a final de 2025/26 continua batendo com a realidade: Brighton em 8º
    bha = st[(st["season"] == 2025) & st["is_latest"] & (st["team_id"] == BHA)]
    assert bha["table_position"].iloc[0] == 8
