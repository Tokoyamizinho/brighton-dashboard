// Script para o Tabular Editor 2 (gratuito) ou 3:
// Power BI Desktop > Ferramentas Externas > Tabular Editor > aba 'C# Script' > colar > Executar (F5)
// Depois: Ctrl+S no Tabular Editor para gravar no modelo.
var t = Model.Tables.Contains("_Medidas") ? Model.Tables["_Medidas"] : null;
if (t == null) { Error("Crie antes a tabela _Medidas (Página Inicial > Inserir dados)."); return; }

// ---------- relacionamentos
Action<string,string,string,string> rel = (dimT, dimC, factT, factC) => {
    var to = Model.Tables[dimT].Columns[dimC];
    var from = Model.Tables[factT].Columns[factC];
    foreach (var r in Model.Relationships.ToList())
        if (r.FromColumn == from && r.ToColumn == to) return;
    var nr = Model.AddRelationship();
    nr.FromColumn = from; nr.ToColumn = to;
    nr.CrossFilteringBehavior = CrossFilteringBehavior.OneDirection;
};
var desejadas = new HashSet<string> { "dim_season.season|fact_team_match.season", "dim_season.season|fact_standings.season", "dim_season.season|fact_player_season.season", "dim_season.season|fact_transfers.season", "dim_season.season|fact_fixtures.season", "dim_team.team_id|fact_team_match.team_id", "dim_team.team_id|fact_standings.team_id", "dim_team.team_id|fact_fixtures.opponent_id", "dim_player.player_key|fact_player_season.player_key", "dim_player.player_key|fact_transfers.player_key", "dim_date.date|fact_team_match.date", "dim_date.date|fact_fixtures.date" };
var removidas = 0;
Func<string, bool> nossa = n => n.StartsWith("dim_") || n.StartsWith("fact_") || n.StartsWith("meta_");
foreach (var r in Model.Relationships.ToList()) {
    // não mexe nas tabelas internas do Power BI (LocalDateTable_..., DateTableTemplate_...)
    if (!nossa(r.FromColumn.Table.Name) || !nossa(r.ToColumn.Table.Name)) continue;
    var chave = r.ToColumn.Table.Name + "." + r.ToColumn.Name + "|" + r.FromColumn.Table.Name + "." + r.FromColumn.Name;
    if (!desejadas.Contains(chave)) { r.Delete(); removidas++; }
}
rel("dim_season", "season", "fact_team_match", "season");
rel("dim_season", "season", "fact_standings", "season");
rel("dim_season", "season", "fact_player_season", "season");
rel("dim_season", "season", "fact_transfers", "season");
rel("dim_season", "season", "fact_fixtures", "season");
rel("dim_team", "team_id", "fact_team_match", "team_id");
rel("dim_team", "team_id", "fact_standings", "team_id");
rel("dim_team", "team_id", "fact_fixtures", "opponent_id");
rel("dim_player", "player_key", "fact_player_season", "player_key");
rel("dim_player", "player_key", "fact_transfers", "player_key");
rel("dim_date", "date", "fact_team_match", "date");
rel("dim_date", "date", "fact_fixtures", "date");

// ---------- ordenação de colunas
Model.Tables["dim_date"].Columns["month_name"].SortByColumn = Model.Tables["dim_date"].Columns["month"];
Model.Tables["dim_season"].Columns["season_label"].SortByColumn = Model.Tables["dim_season"].Columns["season"];

// ---------- tabela de datas
Model.Tables["dim_date"].DataCategory = "Time";
Model.Tables["dim_date"].Columns["date"].IsKey = true;

// ---------- medidas
Action<string,string,string,string,string> m = (nome, expr, pasta, formato, desc) => {
    var x = t.Measures.Contains(nome) ? t.Measures[nome] : t.AddMeasure(nome);
    x.Expression = expr; x.DisplayFolder = pasta;
    if (!string.IsNullOrEmpty(formato)) x.FormatString = formato;
    if (!string.IsNullOrEmpty(desc)) x.Description = desc;
};
m(@"Jogos", @"CALCULATE ( COUNTROWS ( fact_team_match ), fact_team_match[is_brighton] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Vitórias", @"CALCULATE ( [Jogos], fact_team_match[result] = ""W"" )", @"1. Resultados", @"0", @"");
m(@"Empates", @"CALCULATE ( [Jogos], fact_team_match[result] = ""D"" )", @"1. Resultados", @"0", @"");
m(@"Derrotas", @"CALCULATE ( [Jogos], fact_team_match[result] = ""L"" )", @"1. Resultados", @"0", @"");
m(@"Pontos", @"CALCULATE ( SUM ( fact_team_match[pts] ), fact_team_match[is_brighton] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Pontos por Jogo", @"DIVIDE ( [Pontos], [Jogos] )", @"1. Resultados", @"0.00", @"");
m(@"Aproveitamento %", @"DIVIDE ( [Pontos], [Jogos] * 3 )", @"1. Resultados", @"0.0%", @"");
m(@"Gols Pró", @"CALCULATE ( SUM ( fact_team_match[goals_for] ), fact_team_match[is_brighton] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Gols Contra", @"CALCULATE ( SUM ( fact_team_match[goals_against] ), fact_team_match[is_brighton] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Saldo de Gols", @"[Gols Pró] - [Gols Contra]", @"1. Resultados", @"+0;-0;0", @"");
m(@"Gols Pró por Jogo", @"DIVIDE ( [Gols Pró], [Jogos] )", @"1. Resultados", @"0.00", @"");
m(@"Gols Contra por Jogo", @"DIVIDE ( [Gols Contra], [Jogos] )", @"1. Resultados", @"0.00", @"");
m(@"Jogos sem Sofrer Gol", @"CALCULATE ( [Jogos], fact_team_match[clean_sheet] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Jogos sem Marcar", @"CALCULATE ( [Jogos], fact_team_match[failed_to_score] = TRUE () )", @"1. Resultados", @"0", @"");
m(@"Forma (Últimos 5)", @"VAR _ult5 =
    TOPN (
        5,
        CALCULATETABLE ( fact_team_match, fact_team_match[is_brighton] = TRUE () ),
        fact_team_match[datetime], DESC
    )
RETURN
    CONCATENATEX ( _ult5, fact_team_match[result_pt], ""  "", fact_team_match[datetime], ASC )", @"1. Resultados", @"", @"Resultados dos últimos 5 jogos em ordem cronológica (V/E/D).");
m(@"Pontos nos Últimos 5", @"VAR _ult5 =
    TOPN (
        5,
        CALCULATETABLE ( fact_team_match, fact_team_match[is_brighton] = TRUE () ),
        fact_team_match[datetime], DESC
    )
RETURN
    SUMX ( _ult5, fact_team_match[pts] )", @"1. Resultados", @"0", @"");
m(@"Jogos com Placar do Intervalo", @"CALCULATE ( [Jogos], NOT ISBLANK ( fact_team_match[ht_state] ) )", @"2. Primeiro e Segundo Tempo", @"0", @"O placar do intervalo vem do openfootball; jogos completados pela Wikipedia não têm.");
m(@"Gols no 1º Tempo", @"CALCULATE ( SUM ( fact_team_match[ht_goals_for] ), fact_team_match[is_brighton] = TRUE () )", @"2. Primeiro e Segundo Tempo", @"0", @"");
m(@"Gols no 2º Tempo", @"CALCULATE ( SUM ( fact_team_match[second_half_goals_for] ), fact_team_match[is_brighton] = TRUE () )", @"2. Primeiro e Segundo Tempo", @"0", @"");
m(@"Gols Sofridos no 1º Tempo", @"CALCULATE ( SUM ( fact_team_match[ht_goals_against] ), fact_team_match[is_brighton] = TRUE () )", @"2. Primeiro e Segundo Tempo", @"0", @"");
m(@"Gols Sofridos no 2º Tempo", @"CALCULATE ( SUM ( fact_team_match[second_half_goals_against] ), fact_team_match[is_brighton] = TRUE () )", @"2. Primeiro e Segundo Tempo", @"0", @"");
m(@"Pontos Ganhos após o Intervalo", @"CALCULATE (
    SUM ( fact_team_match[points_vs_halftime] ),
    fact_team_match[is_brighton] = TRUE (),
    fact_team_match[points_vs_halftime] > 0
)", @"2. Primeiro e Segundo Tempo", @"0", @"Pontos a mais do que o placar do intervalo daria (viradas e empates arrancados).");
m(@"Pontos Perdidos após o Intervalo", @"- CALCULATE (
    SUM ( fact_team_match[points_vs_halftime] ),
    fact_team_match[is_brighton] = TRUE (),
    fact_team_match[points_vs_halftime] < 0
)", @"2. Primeiro e Segundo Tempo", @"0", @"Pontos que o placar do intervalo daria e escaparam no 2º tempo.");
m(@"Saldo de Pontos no 2º Tempo", @"[Pontos Ganhos após o Intervalo] - [Pontos Perdidos após o Intervalo]", @"2. Primeiro e Segundo Tempo", @"+0;-0;0", @"");
m(@"Viradas", @"CALCULATE ( [Jogos], fact_team_match[ht_state] = ""Perdendo"", fact_team_match[result] = ""W"" )", @"2. Primeiro e Segundo Tempo", @"0", @"Jogos em que o Brighton perdia no intervalo e venceu.");
m(@"Aproveitamento Vencendo no Intervalo %", @"VAR _j = CALCULATE ( [Jogos], fact_team_match[ht_state] = ""Vencendo"" )
RETURN
    DIVIDE ( CALCULATE ( [Pontos], fact_team_match[ht_state] = ""Vencendo"" ), _j * 3 )", @"2. Primeiro e Segundo Tempo", @"0%", @"");
m(@"Chutes", @"CALCULATE ( SUM ( fact_team_match[shots_for] ), fact_team_match[is_brighton] = TRUE () )", @"3. Chutes (football-data)", @"0", @"Requer sources.football_data ligado no config.yaml. Sem a fonte, fica em branco.");
m(@"Chutes no Gol", @"CALCULATE ( SUM ( fact_team_match[shots_on_target_for] ), fact_team_match[is_brighton] = TRUE () )", @"3. Chutes (football-data)", @"0", @"");
m(@"Chutes Sofridos", @"CALCULATE ( SUM ( fact_team_match[shots_against] ), fact_team_match[is_brighton] = TRUE () )", @"3. Chutes (football-data)", @"0", @"");
m(@"Chutes no Gol Sofridos", @"CALCULATE ( SUM ( fact_team_match[shots_on_target_against] ), fact_team_match[is_brighton] = TRUE () )", @"3. Chutes (football-data)", @"0", @"");
m(@"Chutes por Jogo", @"DIVIDE (
    [Chutes],
    CALCULATE ( [Jogos], NOT ISBLANK ( fact_team_match[shots_for] ) )
)", @"3. Chutes (football-data)", @"0.0", @"");
m(@"Precisão dos Chutes %", @"DIVIDE ( [Chutes no Gol], [Chutes] )", @"3. Chutes (football-data)", @"0%", @"");
m(@"Conversão %", @"DIVIDE (
    CALCULATE ( [Gols Pró], NOT ISBLANK ( fact_team_match[shots_for] ) ),
    [Chutes]
)", @"3. Chutes (football-data)", @"0.0%", @"Gols por chute, apenas nos jogos que têm estatística de chutes.");
m(@"Escanteios", @"CALCULATE ( SUM ( fact_team_match[corners_for] ), fact_team_match[is_brighton] = TRUE () )", @"3. Chutes (football-data)", @"0", @"");
m(@"Domínio de Chutes %", @"DIVIDE ( [Chutes], [Chutes] + [Chutes Sofridos] )", @"3. Chutes (football-data)", @"0%", @"Participação do Brighton no total de chutes dos jogos (indicador simples de domínio).");
m(@"Rodada Atual", @"CALCULATE ( MAX ( fact_standings[round] ), dim_team[is_brighton] = TRUE () )", @"4. Tabela e Momento", @"0", @"");
m(@"Posição Atual", @"VAR _r = [Rodada Atual]
RETURN
    CALCULATE (
        MIN ( fact_standings[position] ),
        dim_team[is_brighton] = TRUE (),
        fact_standings[round] = _r
    )", @"4. Tabela e Momento", @"0""º""", @"");
m(@"Posição na Rodada", @"CALCULATE ( MIN ( fact_standings[position] ), dim_team[is_brighton] = TRUE () )", @"4. Tabela e Momento", @"0", @"Para o gráfico de evolução (fact_standings[round] no eixo X; inverta o eixo Y).");
m(@"Pontos Acumulados", @"CALCULATE ( MAX ( fact_standings[pts_cum] ), dim_team[is_brighton] = TRUE () )", @"4. Tabela e Momento", @"0", @"");
m(@"Pontos na Mesma Rodada (Temporada Anterior)", @"VAR _s = MAX ( dim_season[season] )
VAR _r =
    IF (
        ISFILTERED ( fact_standings[round] ),
        MAX ( fact_standings[round] ),
        [Rodada Atual]
    )
RETURN
    CALCULATE (
        MAX ( fact_standings[pts_cum] ),
        REMOVEFILTERS ( dim_season ),
        dim_team[is_brighton] = TRUE (),
        fact_standings[season] = _s - 1,
        fact_standings[round] = _r
    )", @"4. Tabela e Momento", @"0", @"");
m(@"Pontos vs Temporada Anterior", @"[Pontos] - [Pontos na Mesma Rodada (Temporada Anterior)]", @"4. Tabela e Momento", @"+0;-0;0", @"");
m(@"Distância para o 4º", @"VAR _r = [Rodada Atual]
VAR _tab =
    CALCULATETABLE ( fact_standings, fact_standings[round] = _r, REMOVEFILTERS ( dim_team ) )
VAR _quarto = MINX ( TOPN ( 4, _tab, fact_standings[pts_cum], DESC ), fact_standings[pts_cum] )
RETURN
    [Pontos Acumulados] - _quarto", @"4. Tabela e Momento", @"+0;-0;0", @"Negativo = pontos que faltam para alcançar o 4º colocado na mesma rodada.");
m(@"Distância para o Rebaixamento", @"VAR _r = [Rodada Atual]
VAR _tab =
    CALCULATETABLE ( fact_standings, fact_standings[round] = _r, REMOVEFILTERS ( dim_team ) )
VAR _z = MAXX ( TOPN ( 3, _tab, fact_standings[pts_cum], ASC ), fact_standings[pts_cum] )
RETURN
    [Pontos Acumulados] - _z", @"4. Tabela e Momento", @"+0;-0;0", @"Pontos de vantagem sobre o 18º colocado na mesma rodada.");
m(@"Próximo Jogo (Brasília)", @"VAR _agora = NOW () - 2 / 24
RETURN
    CALCULATE (
        MIN ( fact_fixtures[kickoff_brasilia] ),
        fact_fixtures[kickoff_brasilia] > _agora
    )", @"4. Tabela e Momento", @"dd/mm ""às"" hh:nn", @"Primeiro jogo que ainda não terminou (início + 2h), comparado com a hora do computador (NOW). Muda sozinho depois de cada jogo, sem precisar rodar o Python de novo.");
m(@"Próximo Adversário", @"VAR _k = [Próximo Jogo (Brasília)]
RETURN
    CALCULATE (
        MAXX ( fact_fixtures, fact_fixtures[opponent] & "" ("" & fact_fixtures[venue] & "")"" ),
        fact_fixtures[kickoff_brasilia] = _k
    )", @"4. Tabela e Momento", @"", @"");
m(@"Nº do Próximo Jogo", @"VAR _agora = NOW () - 2 / 24
VAR _k = MAX ( fact_fixtures[kickoff_brasilia] )
RETURN
    IF (
        HASONEVALUE ( fact_fixtures[kickoff_brasilia] ) && _k > _agora,
        CALCULATE (
            COUNTROWS ( fact_fixtures ),
            REMOVEFILTERS ( fact_fixtures ),
            fact_fixtures[kickoff_brasilia] > _agora,
            fact_fixtures[kickoff_brasilia] <= _k
        )
    )", @"4. Tabela e Momento", @"0", @"1 para o próximo jogo, 2 para o seguinte... (vazio para jogos já disputados). Use como filtro do visual (entre 1 e 5) na tabela de próximos jogos.");
m(@"Dificuldade Próximos 5", @"VAR _agora = NOW () - 2 / 24
VAR _prox =
    TOPN (
        5,
        FILTER ( fact_fixtures, fact_fixtures[kickoff_brasilia] > _agora ),
        fact_fixtures[kickoff_brasilia], ASC
    )
RETURN
    AVERAGEX ( _prox, fact_fixtures[difficulty] )", @"4. Tabela e Momento", @"0.0", @"Métrica própria de 1 (fácil) a 5 (difícil) pela posição atual de cada adversário na tabela.");
m(@"Jogos Restantes", @"CALCULATE ( COUNTROWS ( fact_fixtures ), fact_fixtures[finished] = FALSE () )", @"4. Tabela e Momento", @"0", @"");
m(@"Resultados Pendentes", @"CALCULATE ( COUNTROWS ( fact_fixtures ), fact_fixtures[result_pending] = TRUE () )", @"4. Tabela e Momento", @"0", @"Jogos já disputados cujo placar ainda não chegou às fontes. Mostre como aviso quando > 0.");
m(@"Dados Até", @"MAX ( dim_season[data_until] )", @"4. Tabela e Momento", @"dd/mm/yyyy", @"Data do último jogo do Brighton com resultado nos dados.");
m(@"Jogos (Jogador)", @"SUM ( fact_player_season[pl_apps] )", @"5. Jogadores", @"0", @"Partidas na Premier League (titular + reserva).");
m(@"Titularidades", @"SUM ( fact_player_season[pl_starts] )", @"5. Jogadores", @"0", @"");
m(@"Entradas do Banco", @"SUM ( fact_player_season[pl_subs] )", @"5. Jogadores", @"0", @"");
m(@"Titularidade %", @"DIVIDE ( [Titularidades], [Jogos (Jogador)] )", @"5. Jogadores", @"0%", @"");
m(@"Gols (Jogador)", @"SUM ( fact_player_season[pl_goals] )", @"5. Jogadores", @"0", @"");
m(@"Assistências", @"SUM ( fact_player_season[pl_assists] )", @"5. Jogadores", @"0", @"");
m(@"G+A", @"[Gols (Jogador)] + [Assistências]", @"5. Jogadores", @"0", @"");
m(@"G+A por Jogo", @"DIVIDE ( [G+A], [Jogos (Jogador)] )", @"5. Jogadores", @"0.00", @"");
m(@"Gols em Todas as Competições", @"SUM ( fact_player_season[total_goals] )", @"5. Jogadores", @"0", @"");
m(@"Cartões Amarelos", @"SUM ( fact_player_season[pl_yellow] )", @"5. Jogadores", @"0", @"");
m(@"Cartões Vermelhos", @"SUM ( fact_player_season[pl_red] ) + SUM ( fact_player_season[pl_second_yellow] )", @"5. Jogadores", @"0", @"");
m(@"Participação nos Gols %", @"DIVIDE ( [G+A], [Gols Pró] )", @"5. Jogadores", @"0%", @"Gols + assistências do jogador sobre os gols do time na Premier League.");
m(@"Jogadores Utilizados", @"CALCULATE ( DISTINCTCOUNT ( fact_player_season[player_key] ), fact_player_season[pl_apps] > 0 )", @"5. Jogadores", @"0", @"");
m(@"Artilheiro", @"VAR _t =
    TOPN (
        1,
        ADDCOLUMNS ( VALUES ( dim_player[player_name] ), ""@g"", [Gols (Jogador)] ),
        [@g], DESC
    )
RETURN
    MAXX ( _t, dim_player[player_name] & "" ("" & [@g] & "")"" )", @"5. Jogadores", @"", @"");
m(@"Líder em Assistências", @"VAR _t =
    TOPN (
        1,
        ADDCOLUMNS ( VALUES ( dim_player[player_name] ), ""@a"", [Assistências] ),
        [@a], DESC
    )
RETURN
    MAXX ( _t, dim_player[player_name] & "" ("" & [@a] & "")"" )", @"5. Jogadores", @"", @"");
m(@"Gasto", @"CALCULATE ( SUM ( fact_transfers[fee_gbp] ), fact_transfers[direction] = ""Chegada"" )", @"6. Transferências", @"""£""#,0;-""£""#,0;""£""0", @"Soma das taxas pagas em libras (valores não divulgados ficam de fora).");
m(@"Receita", @"CALCULATE ( SUM ( fact_transfers[fee_gbp] ), fact_transfers[direction] = ""Saída"" )", @"6. Transferências", @"""£""#,0;-""£""#,0;""£""0", @"");
m(@"Saldo de Transferências", @"[Receita] - [Gasto]", @"6. Transferências", @"""£""#,0;-""£""#,0;""£""0", @"Receita - Gasto. Positivo = o clube vendeu mais do que comprou.");
m(@"Chegadas", @"CALCULATE ( COUNTROWS ( fact_transfers ), fact_transfers[direction] = ""Chegada"" )", @"6. Transferências", @"0", @"");
m(@"Saídas", @"CALCULATE ( COUNTROWS ( fact_transfers ), fact_transfers[direction] = ""Saída"" )", @"6. Transferências", @"0", @"");
m(@"Contratações Pagas", @"CALCULATE (
    COUNTROWS ( fact_transfers ),
    fact_transfers[direction] = ""Chegada"",
    fact_transfers[fee_type] = ""Pago""
)", @"6. Transferências", @"0", @"");
m(@"Valores Não Divulgados", @"CALCULATE ( COUNTROWS ( fact_transfers ), fact_transfers[fee_type] = ""Não divulgado"" )", @"6. Transferências", @"0", @"Negócios sem valor público; não entram no Gasto nem na Receita.");
m(@"Empréstimos Cedidos", @"CALCULATE (
    COUNTROWS ( fact_transfers ),
    fact_transfers[direction] = ""Saída"",
    fact_transfers[movement] = ""Empréstimo""
)", @"6. Transferências", @"0", @"");
m(@"Gasto Médio por Contratação", @"DIVIDE ( [Gasto], [Contratações Pagas] )", @"6. Transferências", @"""£""#,0;-""£""#,0;""£""0", @"");
m(@"Maior Contratação", @"VAR _t =
    TOPN (
        1,
        FILTER ( fact_transfers, fact_transfers[direction] = ""Chegada"" && fact_transfers[fee_gbp] > 0 ),
        fact_transfers[fee_gbp], DESC
    )
RETURN
    MAXX ( _t, fact_transfers[player_name] & "" • £"" & FORMAT ( fact_transfers[fee_gbp] / 1000000, ""0.0"" ) & ""M"" )", @"6. Transferências", @"", @"");
m(@"Maior Venda", @"VAR _t =
    TOPN (
        1,
        FILTER ( fact_transfers, fact_transfers[direction] = ""Saída"" && fact_transfers[fee_gbp] > 0 ),
        fact_transfers[fee_gbp], DESC
    )
RETURN
    MAXX ( _t, fact_transfers[player_name] & "" • £"" & FORMAT ( fact_transfers[fee_gbp] / 1000000, ""0.0"" ) & ""M"" )", @"6. Transferências", @"", @"");
m(@"Título da Página", @"""Brighton & Hove Albion  •  "" & SELECTEDVALUE ( dim_season[season_label], ""Várias temporadas"" )", @"7. Textos e Cores", @"", @"");
m(@"Subtítulo da Rodada", @"""Premier League  •  após "" & [Rodada Atual] & "" rodadas  •  dados até "" & FORMAT ( [Dados Até], ""dd/mm/yyyy"" )", @"7. Textos e Cores", @"", @"");
m(@"Última Atualização", @"""Atualizado em "" & CALCULATE ( MAX ( meta_refresh[last_refresh_utc] ), meta_refresh[source] = ""pipeline"" ) & "" (UTC)""", @"7. Textos e Cores", @"", @"");
m(@"Fonte dos Dados", @"""Dados: Wikipedia (CC BY-SA 4.0) e openfootball (domínio público). Projeto sem afiliação com o clube ou a Premier League.""", @"7. Textos e Cores", @"", @"Texto de atribuição exigido pela licença CC BY-SA da Wikipedia. Deixe visível no rodapé.");
m(@"Cor do Resultado", @"SWITCH (
    SELECTEDVALUE ( fact_team_match[result_pt] ),
    ""V"", ""#2DA866"",
    ""E"", ""#D99A00"",
    ""D"", ""#D64545"",
    ""#8A9AB0""
)", @"7. Textos e Cores", @"", @"Formatação condicional (Valor do campo) para resultados V/E/D.");
m(@"Cor da Dificuldade", @"SWITCH (
    SELECTEDVALUE ( fact_fixtures[difficulty] ),
    1, ""#1E8E5A"",
    2, ""#2DA866"",
    3, ""#8A9AB0"",
    4, ""#E8743B"",
    5, ""#E53935"",
    ""#8A9AB0""
)", @"7. Textos e Cores", @"", @"");
m(@"Cor do Saldo de Gols", @"IF ( [Saldo de Gols] >= 0, ""#2DA866"", ""#D64545"" )", @"7. Textos e Cores", @"", @"");
m(@"Posição Final", @"VAR _s = MAX ( dim_season[season] )
RETURN
    IF (
        SELECTEDVALUE ( dim_season[is_current], FALSE () ),
        CALCULATE ( [Posição Atual], dim_season[season] = _s ),
        MAX ( dim_season[brighton_final_position] )
    )", @"8. Histórico", @"0""º""", @"Na temporada atual mostra a posição parcial.");

// ---------- esconde colunas técnicas (chaves) nas tabelas fato
foreach (var tb in Model.Tables.Where(x => x.Name.StartsWith("fact_")))
    foreach (var c in tb.Columns.Where(c => c.Name.EndsWith("_id") || c.Name == "player_key"))
        c.IsHidden = true;
Info("Modelo configurado: " + t.Measures.Count + " medidas, " + Model.Relationships.Count + " relações (" + removidas + " automáticas removidas).");
