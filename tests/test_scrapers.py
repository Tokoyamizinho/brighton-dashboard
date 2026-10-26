"""Parsers de cada fonte, testados contra dados reais (ver fixtures/NOTICE.md)."""
import json

import pandas as pd

from brighton.scrapers import footballdata, openfootball, wikipedia
from brighton.scrapers.wikitable import find_tables, parse_wikitable

from conftest import FIXTURES, read_fixture


# ---------------------------------------------------------------- openfootball
def test_openfootball_full_season():
    data = json.loads(read_fixture("openfootball_en1_2025-26.json"))
    m = openfootball.parse_matches(data, 2025)
    assert len(m) == 380
    assert m["home_goals"].notna().all()
    assert m["home"].nunique() == 20
    assert "Brighton & Hove Albion" in set(m["home"])  # sufixo "FC" removido
    assert "Bournemouth" in set(m["home"])  # "AFC Bournemouth" -> "Bournemouth"
    assert m["matchday"].between(1, 38).all()


def test_openfootball_score_as_list_and_unplayed():
    data = json.loads(read_fixture("openfootball_en1_2026-27.json"))
    m = openfootball.parse_matches(data, 2026)
    assert len(m) == 380
    # alguns placares vêm como lista [h, a] em vez de {"ft": [...]}
    raw_lists = [x for x in data["matches"] if isinstance(x.get("score"), list)]
    assert raw_lists, "o arquivo real tem placares em lista"
    first = raw_lists[0]
    row = m[(m["date"] == pd.Timestamp(first["date"])) & (m["home"].str.startswith(first["team1"].split()[0]))]
    assert row["home_goals"].iloc[0] == first["score"][0]
    # jogos futuros ficam sem placar
    assert m["home_goals"].isna().sum() > 300


# ------------------------------------------------------------------ Wikipedia
def test_results_matrix():
    df = wikipedia.parse_results_matrix(read_fixture("wiki_pl_2026-27_results.html"), 2026)
    assert len(df) > 50
    assert set(df["home"]) | set(df["away"]) <= {
        "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion", "Chelsea",
        "Coventry City", "Crystal Palace", "Everton", "Fulham", "Hull City", "Ipswich Town", "Leeds United",
        "Liverpool", "Manchester City", "Manchester United", "Newcastle United", "Nottingham Forest",
        "Sunderland", "Tottenham Hotspur",
    }
    sun = df[(df["home"] == "Sunderland") & (df["away"] == "Brighton & Hove Albion")].iloc[0]
    assert (sun["home_goals"], sun["away_goals"]) == (0, 2)
    # "a" (jogo marcado) e "—" (o próprio time) não viram partidas
    assert not ((df["home"] == "Crystal Palace") & (df["away"] == "Brighton & Hove Albion")).any()
    assert not (df["home"] == df["away"]).any()


def test_transfers_current_layout():
    tr = wikipedia.parse_transfers(read_fixture("wiki_bha_2026-27.html"), 2026)
    by = tr.set_index(["movement", "direction", "player_name"])
    vh = by.loc[("Transferência", "Saída", "Jan Paul van Hecke")]
    assert vh["other_club"] == "Tottenham Hotspur"
    assert (vh["fee_type"], vh["fee_gbp"]) == ("Pago", 52_000_000)
    assert vh["window"] == "Verão" and str(vh["date"]) == "2026-06-18"
    assert vh["nationality"] == "Netherlands" and vh["position"] == "CB"
    assert vh["player_key"] == "wiki:Jan_Paul_van_Hecke"
    assert by.loc[("Transferência", "Saída", "Jeremy Sarmiento"), "fee_type"] == "Não divulgado"
    assert by.loc[("Empréstimo", "Chegada", "Promise David"), "loan_until"] == "End of Season"
    # rowspan: "End of Season" vale para todas as linhas da tabela de empréstimos
    assert (tr[(tr["movement"] == "Empréstimo") & (tr["direction"] == "Saída")]["loan_until"] == "End of Season").all()
    milner = by.loc[("Fim de contrato", "Saída", "James Milner")]
    assert milner["retired"] and milner["other_club"] == ""
    # rowspan na data: as 3 liberações de 30/06 recebem a mesma data
    assert (tr[tr["player_name"].isin(["Joël Veltman", "Solly March", "Adam Webster"])]["date"].astype(str) == "2026-06-30").all()
    assert set(tr["squad_group"]) == {"First team"}
    assert len(tr) == 4 + 4 + 1 + 4 + 4


def test_transfers_old_layout():
    tr = wikipedia.parse_transfers(read_fixture("wiki_bha_2022-23.html"), 2022)
    by = tr.set_index("player_name")
    assert by.loc["Yves Bissouma", "fee_gbp"] == 25_000_000
    assert by.loc["Yves Bissouma", "other_club"] == "Tottenham Hotspur"  # coluna "Transferred to"
    assert by.loc["Imari Samuels", "fee_type"] == "Grátis"
    assert by.loc["Tudor Băluță", "fee_type"] == "Fim de contrato"  # "Released" na coluna Fee
    assert by.loc["Julio Enciso", "squad_group"] == "First Team"  # coluna "Team" do layout antigo
    assert by.loc["Levi Colwill", "movement"] == "Empréstimo"  # seção "Loans in"
    # jogador sem artigo na Wikipedia: chave pelo nome
    assert by.loc["Fynn Talley", "player_key"] == "name:fynn-talley"


def test_player_season_current_layout():
    ps = wikipedia.parse_player_season(read_fixture("wiki_bha_2026-27.html"), 2026).set_index("player_name")
    dunk = ps.loc["Lewis Dunk"]
    assert (dunk["pl_starts"], dunk["pl_subs"], dunk["pl_apps"], dunk["pl_goals"]) == (5, 1, 6, 1)
    assert dunk["total_apps"] == 8 and dunk["shirt_number"] == 5 and dunk["nationality"] == "England"
    # assistências e cartões vêm de outras tabelas; quem não aparece nelas tem 0
    assert dunk["pl_assists"] == 0 and dunk["pl_yellow"] == 0


def test_player_season_old_layout_without_assists_table():
    ps = wikipedia.parse_player_season(read_fixture("wiki_bha_2022-23.html"), 2022).set_index("player_name")
    assert len(ps) == 4  # linhas de agrupamento ("Goalkeepers"...) não viram jogadores
    lamptey = ps.loc["Tariq Lamptey"]
    assert (lamptey["pl_starts"], lamptey["pl_subs"], lamptey["pl_apps"]) == (3, 17, 20)
    assert ps.loc["Robert Sánchez", "pl_apps"] == 23 and pd.isna(ps.loc["Robert Sánchez", "pl_starts"])
    # 2022-23 não tem tabela de assistências: vazio, não zero
    assert ps["pl_assists"].isna().all()


def test_wikitable_two_row_header_and_groups():
    (_, table), = find_tables(read_fixture("wiki_bha_2026-27.html"), "Disciplinary record")
    pt = parse_wikitable(table)
    assert "Premier League|Yellow card" in pt.columns
    assert "Premier League|Red card" in pt.columns
    assert all(r.values["Player"] != "Total" for r in pt.rows)  # linha de total ignorada


def test_wikipedia_url_encoding():
    url = wikipedia.WikipediaScraper.url("2026–27 Brighton & Hove Albion F.C. season")
    assert url == "https://en.wikipedia.org/wiki/2026%E2%80%9327_Brighton_%26_Hove_Albion_F.C._season"


# --------------------------------------------------------------- football-data
def test_football_data_csv():
    df = footballdata.parse_csv((FIXTURES / "football_data_sample.csv").read_text(encoding="utf-8"), 2026)
    assert len(df) == 5
    assert "Brighton & Hove Albion" in set(df["home"])
    assert "Nottingham Forest" in set(df["home"]) and "Manchester City" in set(df["away"])
    first = df.iloc[0]
    assert (first["home_shots"], first["home_shots_on_target"], first["referee"]) == (18, 9, "Referee A")
    assert footballdata.season_code(2026) == "2627"


def test_player_link_absolute_href_from_article_page():
    """A página do artigo (o que o scraper baixa) usa links absolutos; a API usa relativos."""
    from bs4 import BeautifulSoup

    from brighton.scrapers.wikitable import player_link

    live = BeautifulSoup(
        '<td><span><span><a href="https://en.wikipedia.org/wiki/Poland" title="Poland"><img alt="Poland"></a>'
        '</span></span> <a href="https://en.wikipedia.org/wiki/Kacper_Kozłowski_(footballer)" '
        'title="Kacper Kozłowski (footballer)">Kacper Kozłowski</a></td>', "lxml").td
    assert player_link(live) == ("Kacper Kozłowski", "Kacper_Kozłowski_(footballer)")
    api = BeautifulSoup('<td><a href="/wiki/Pascal_Gro%C3%9F" title="Pascal Groß">Pascal Groß</a></td>', "lxml").td
    assert player_link(api) == ("Pascal Groß", "Pascal_Groß")
    file_link = BeautifulSoup('<td><a href="https://en.wikipedia.org/wiki/File:X.svg">x</a> Fulano</td>', "lxml").td
    assert player_link(file_link)[1] is None
