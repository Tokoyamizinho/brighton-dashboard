"""Páginas do dashboard público (só dados abertos: openfootball e Wikipedia).

Cada função monta uma página 1920x1080 com os blocos de `brighton.report`.
Para mudar o layout, edite aqui e rode `python -m brighton pbip` com o Power BI fechado.
"""
from __future__ import annotations

from .report import (
    GAP, LEFT, W, F, Page, agg, col, filter_item, mea, measure_between, uid,
)

HALF = (W - 2 * LEFT - GAP) // 2
SEASON = col("dim_season", "season_label")


def page_overview(name: str | None = None) -> Page:
    p = Page("pub-geral", "Visão Geral", name)
    p.header()
    p.season_slicer()
    p.card_row(["Pontos", "Posição Final", "Aproveitamento %", "Vitórias", "Empates", "Derrotas"], y=96)
    p.line(LEFT, 224, HALF, 400, "Posição na tabela, rodada a rodada", col("fact_standings", "round"),
           [F(mea("Posição na Rodada"), "Posição")], labels=True,
           value_axis={"start": 1, "end": 20, "invertAxis": True})
    p.line(LEFT + HALF + GAP, 224, HALF, 400, "Pontos acumulados x mesma rodada da temporada anterior",
           col("fact_standings", "round"),
           [F(mea("Pontos Acumulados"), "Esta temporada"),
            F(mea("Pontos na Mesma Rodada (Temporada Anterior)"), "Temporada anterior")])
    p.table(LEFT, 640, 1150, 398, "Jogo a jogo", [
        F(col("fact_team_match", "round"), "Rod.", w=0.5),
        F(col("fact_team_match", "match_label"), "Jogo", w=2.6),
        F(col("fact_team_match", "result_label"), "Resultado", w=1.2),
        F(agg("fact_team_match", "goals_for"), "Gols pró", w=0.8, fmt="0"),
        F(agg("fact_team_match", "goals_against"), "Gols contra", w=0.8, fmt="0"),
    ], filters=[filter_item(uid("f", "pub-bha"), "fact_team_match", "is_brighton", [True], hidden=True)],
        sort=[(col("fact_team_match", "round"), "Ascending")], text_size=13, row_padding=6,
        col_colors={"fact_team_match.result_label": "Cor do Resultado"})
    x0 = LEFT + 1150 + GAP
    cw = (W - LEFT - x0 - GAP) // 2
    cards = ["Gols Pró", "Gols Contra", "Saldo de Gols", "Jogos sem Sofrer Gol", "Viradas",
             "Pontos Ganhos após o Intervalo"]
    for i, m in enumerate(cards):
        p.card(m, x0 + (i % 2) * (cw + GAP), 640 + (i // 2) * 138, cw, 122)
    return p


def page_league() -> Page:
    p = Page("pub-tabela", "Tabela da Liga")
    p.header()
    p.season_slicer()
    team = col("dim_team", "team_name")
    p.table(LEFT, 96, 1000, 942, "Classificação", [
        F(mea("Pos. (Tabela)"), "Pos.", w=0.6),
        F(team, "Time", w=2.4),
        F(mea("Jogos (Tabela)"), "J", w=0.6),
        F(mea("Pts (Tabela)"), "Pts", w=0.7),
        F(mea("Pontos por Jogo (Tabela)"), "Pts/J", w=0.8),
        F(mea("GP (Tabela)"), "GP", w=0.7),
        F(mea("GC (Tabela)"), "GC", w=0.7),
        F(mea("SG (Tabela)"), "SG", w=0.7),
    ], sort=[(mea("Pos. (Tabela)"), "Ascending")], text_size=14, row_padding=10, row_back="Fundo do Time")
    p.columns(LEFT + 1000 + GAP, 96, W - 2 * LEFT - 1000 - GAP, 942, "Pontos por time", team,
              [F(mea("Pts (Tabela)"), "Pontos")], kind="clusteredBarChart",
              sort=[(mea("Pts (Tabela)"), "Descending")], color_measure="Cor do Time")
    return p


def page_moment() -> Page:
    p = Page("pub-momento", "Momento da Temporada")
    p.header()
    p.filters.append(filter_item(uid("f", "pub-cur"), "dim_season", "is_current", [True]))
    p.card_row(["Posição Atual", "Pontos", "Forma (Últimos 5)", "Pontos vs Temporada Anterior",
                "Distância para o 4º", "Distância para o Rebaixamento"], y=96)
    p.card("Próximo Adversário", LEFT, 224, 736, 100, size=20)
    p.card("Próximo Jogo (Brasília)", LEFT, 336, 736, 88, size=18)
    cw = (736 - GAP) // 2
    p.card("Dificuldade Próximos 5", LEFT, 440, cw, 104, size=20)
    p.card("Jogos Restantes", LEFT + cw + GAP, 440, cw, 104, size=20)
    p.table(LEFT + 752, 224, W - 2 * LEFT - 752, 320, "Próximos 5 jogos", [
        F(col("fact_fixtures", "opponent"), "Adversário", w=2),
        F(col("fact_fixtures", "venue"), "Local", w=0.8),
        F(col("fact_fixtures", "kickoff_brasilia"), "Data (Brasília)", w=1.5, fmt='dd/mm "às" hh:nn'),
        F(col("fact_fixtures", "opponent_position_now"), "Posição dele", w=1, fmt='0"º"'),
        F(col("fact_fixtures", "difficulty"), "Dificuldade (1 a 5)", w=1.2),
    ], filters=[measure_between(uid("f", "pub-next"), "Nº do Próximo Jogo", 1, 5)],
        sort=[(col("fact_fixtures", "kickoff_brasilia"), "Ascending")], text_size=14, row_padding=10,
        col_colors={"fact_fixtures.difficulty": "Cor da Dificuldade"})
    w_line = W - 2 * LEFT - 356 - GAP
    p.line(LEFT, 560, w_line, 478, "Pontos acumulados: esta temporada x anterior", col("fact_standings", "round"),
           [F(mea("Pontos Acumulados"), "Esta temporada"),
            F(mea("Pontos na Mesma Rodada (Temporada Anterior)"), "Temporada anterior")], labels=True)
    x0 = LEFT + w_line + GAP
    for i, m in enumerate(["Rodada Atual", "Resultados Pendentes", "Dados Até"]):
        p.card(m, x0, 560 + i * 165, 356, 148)
    return p


def page_players() -> Page:
    p = Page("pub-jogadores", "Jogadores")
    p.header()
    p.season_slicer()
    p.slicer("dim_player", "position_group", W - LEFT - 300 - GAP - 260, 12, 260, 60, "Setor")
    p.card_row(["Artilheiro", "Líder em Assistências", "Jogadores Utilizados"], y=96, size=18)
    p.table(LEFT, 224, 1150, 814, "Elenco na Premier League (Wikipedia)", [
        F(col("dim_player", "player_name"), "Jogador", w=2.2),
        F(col("dim_player", "position_group"), "Setor", w=1.2),
        F(mea("Jogos (Jogador)"), "Jogos"),
        F(mea("Titularidades"), "Titular"),
        F(mea("Gols (Jogador)"), "Gols"),
        F(mea("Assistências"), "Assist."),
        F(mea("G+A"), "G+A"),
        F(mea("Cartões Amarelos"), "Amarelos"),
        F(mea("Participação nos Gols %"), "Part. gols", w=1.1),
    ], sort=[(mea("G+A"), "Descending")], text_size=13, row_padding=5)
    x0 = LEFT + 1150 + GAP
    p.columns(x0, 224, W - LEFT - x0, 814, "Gols e assistências", col("dim_player", "player_name"),
              [F(mea("Gols (Jogador)"), "Gols"), F(mea("Assistências"), "Assistências")],
              kind="barChart", sort=[(mea("Gols (Jogador)"), "Descending")])
    return p


def page_transfers() -> Page:
    p = Page("pub-transferencias", "Transferências")
    p.header()
    slicer = p.season_slicer()
    p.card_row(["Gasto", "Receita", "Saldo de Transferências", "Chegadas", "Saídas", "Valores Não Divulgados"],
               y=96)
    p.card("Maior Contratação", LEFT, 224, HALF, 92, size=16)
    p.card("Maior Venda", LEFT + HALF + GAP, 224, HALF, 92, size=16)
    chart = p.columns(LEFT, 332, 640, 706, "Gasto x receita por temporada (todas)", SEASON,
                      [F(mea("Gasto"), "Gasto"), F(mea("Receita"), "Receita")], sort=[(SEASON, "Ascending")])
    p.no_filter(slicer, chart)
    x0 = LEFT + 640 + GAP
    w = W - LEFT - x0
    fields = [
        F(col("fact_transfers", "date"), "Data", w=0.9, fmt="dd/mm/yyyy"),
        F(col("fact_transfers", "player_name"), "Jogador", w=1.8),
        F(col("fact_transfers", "position_group"), "Setor", w=1),
        F(col("fact_transfers", "other_club"), "Clube", w=1.8),
        F(col("fact_transfers", "fee_type"), "Tipo", w=1.1),
        F(agg("fact_transfers", "fee_gbp"), "Valor", w=1, fmt='"£"#,0'),
    ]
    date_desc = [(col("fact_transfers", "date"), "Descending")]
    p.table(x0, 332, w, 345, "Chegadas", fields, sort=date_desc, text_size=12,
            filters=[filter_item(uid("f", "pub-in"), "fact_transfers", "direction", ["Chegada"], hidden=True)])
    p.table(x0, 693, w, 345, "Saídas", fields, sort=date_desc, text_size=12,
            filters=[filter_item(uid("f", "pub-out"), "fact_transfers", "direction", ["Saída"], hidden=True)])
    return p


def page_history() -> Page:
    p = Page("pub-historico", "Histórico")
    p.header(subtitle_measure=None)
    order = [(SEASON, "Ascending")]
    p.columns(LEFT, 96, HALF, 452, "Pontos por temporada", SEASON, [F(mea("Pontos"), "Pontos")], sort=order)
    p.columns(LEFT + HALF + GAP, 96, HALF, 452, "Posição final (temporada atual: parcial)", SEASON,
              [F(mea("Posição Final"), "Posição")], sort=order,
              value_axis={"start": 1, "end": 20, "invertAxis": True})
    p.line(LEFT, 564, HALF, 474, "Gols pró e contra por jogo", SEASON,
           [F(mea("Gols Pró por Jogo"), "Gols pró por jogo"), F(mea("Gols Contra por Jogo"), "Gols contra por jogo")],
           labels=True, sort=order)
    summary = [
        F(SEASON, "Temporada", w=1.5), F(mea("Pontos"), "Pts"), F(mea("Pontos por Jogo"), "Pts/J"),
        F(mea("Posição Final"), "Pos."), F(mea("Gols Pró"), "GP"), F(mea("Gols Contra"), "GC"),
        F(mea("Gasto"), "Gasto", w=1.8), F(mea("Saldo de Transferências"), "Saldo transf.", w=1.9),
    ]
    p.table(LEFT + HALF + GAP, 564, HALF, 474, "Resumo por temporada", summary, sort=order, text_size=16,
            row_padding=22)
    return p


def build(existing_first_page: str | None = None) -> list[Page]:
    return [page_overview(existing_first_page), page_league(), page_moment(), page_players(),
            page_transfers(), page_history()]
