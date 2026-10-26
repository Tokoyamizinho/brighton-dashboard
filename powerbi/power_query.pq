// ============================================================================
// Power Query (M) - Brighton Dashboard  |  gerado por `python -m brighton powerbi`
//
// 1) Página Inicial > Transformar dados > Gerenciar Parâmetros > Novo parâmetro
//    Nome: PastaDados   Tipo: Texto   Valor: C:\caminho\brighton-dashboard\data\processed
// 2) Nova Fonte > Consulta Nula > Editor Avançado: cole o bloco 'fnCsv' e renomeie para fnCsv
// 3) Para cada tabela: Consulta Nula > Editor Avançado > cole o bloco e renomeie
//    com o nome indicado no comentário.
// Os CSVs usam ponto decimal: por isso a conversão usa a cultura en-US.
// ============================================================================

// ----- Consulta: fnCsv
(nome as text, tipos as list) as table =>
let
    Caminho = PastaDados & (if Text.EndsWith(PastaDados, "\") then "" else "\") & nome & ".csv",
    Fonte = Csv.Document(File.Contents(Caminho), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    SemVazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipado = Table.TransformColumnTypes(SemVazios, tipos, "en-US")
in
    Tipado

// ----- Consulta: dim_date
let
    Fonte = fnCsv("dim_date", {
        {"date", type date},
        {"year", Int64.Type},
        {"month", Int64.Type},
        {"month_name", type text},
        {"month_year", type text},
        {"weekday", type text},
        {"season", Int64.Type},
        {"season_label", type text}
    })
in
    Fonte

// ----- Consulta: dim_player
let
    Fonte = fnCsv("dim_player", {
        {"player_key", type text},
        {"player_name", type text},
        {"position", type text},
        {"nationality", type text},
        {"first_season", Int64.Type},
        {"last_season", Int64.Type},
        {"position_group", type text},
        {"wikipedia_url", type text},
        {"played_for_club", type logical}
    })
in
    Fonte

// ----- Consulta: dim_season
let
    Fonte = fnCsv("dim_season", {
        {"season", Int64.Type},
        {"season_label", type text},
        {"is_current", type logical},
        {"brighton_matches_played", Int64.Type},
        {"brighton_final_position", Int64.Type},
        {"brighton_points", Int64.Type},
        {"data_until", type date}
    })
in
    Fonte

// ----- Consulta: dim_team
let
    Fonte = fnCsv("dim_team", {
        {"team_id", type text},
        {"team_name", type text},
        {"is_brighton", type logical}
    })
in
    Fonte

// ----- Consulta: fact_fixtures
let
    Fonte = fnCsv("fact_fixtures", {
        {"season", Int64.Type},
        {"matchday", Int64.Type},
        {"kickoff_uk", type datetime},
        {"home_away", type text},
        {"opponent", type text},
        {"goals_for", Int64.Type},
        {"goals_against", Int64.Type},
        {"opponent_id", type text},
        {"venue", type text},
        {"finished", type logical},
        {"date", type date},
        {"kickoff_brasilia", type datetime},
        {"opponent_position_now", Int64.Type},
        {"opponent_ppg_now", type number},
        {"difficulty", Int64.Type},
        {"fixture_number", Int64.Type},
        {"result_pending", type logical},
        {"is_next", type logical},
        {"next_n", Int64.Type},
        {"result_pt", type text}
    })
in
    Fonte

// ----- Consulta: fact_player_season
let
    Fonte = fnCsv("fact_player_season", {
        {"season", Int64.Type},
        {"player_key", type text},
        {"player_name", type text},
        {"shirt_number", type number},
        {"position", type text},
        {"nationality", type text},
        {"pl_apps", type number},
        {"pl_starts", type number},
        {"pl_subs", type number},
        {"pl_goals", type number},
        {"total_apps", type number},
        {"total_goals", type number},
        {"left_during_season", type logical},
        {"pl_assists", Int64.Type},
        {"total_assists", Int64.Type},
        {"pl_yellow", Int64.Type},
        {"pl_second_yellow", Int64.Type},
        {"pl_red", Int64.Type},
        {"season_label", type text},
        {"position_group", type text},
        {"pl_goal_contributions", Int64.Type}
    })
in
    Fonte

// ----- Consulta: fact_standings
let
    Fonte = fnCsv("fact_standings", {
        {"season", Int64.Type},
        {"team_id", type text},
        {"round", Int64.Type},
        {"pts_cum", Int64.Type},
        {"ppg_cum", type number},
        {"gf_cum", Int64.Type},
        {"ga_cum", Int64.Type},
        {"gd_cum", Int64.Type},
        {"position", Int64.Type}
    })
in
    Fonte

// ----- Consulta: fact_team_match
let
    Fonte = fnCsv("fact_team_match", {
        {"season", Int64.Type},
        {"match_id", type text},
        {"matchday", Int64.Type},
        {"datetime", type datetime},
        {"team", type text},
        {"opponent", type text},
        {"home_away", type text},
        {"goals_for", Int64.Type},
        {"goals_against", Int64.Type},
        {"ht_goals_for", Int64.Type},
        {"ht_goals_against", Int64.Type},
        {"score_source", type text},
        {"shots_for", Int64.Type},
        {"shots_against", Int64.Type},
        {"shots_on_target_for", Int64.Type},
        {"shots_on_target_against", Int64.Type},
        {"corners_for", Int64.Type},
        {"corners_against", Int64.Type},
        {"fouls_for", Int64.Type},
        {"fouls_against", Int64.Type},
        {"yellow_for", Int64.Type},
        {"yellow_against", Int64.Type},
        {"red_for", Int64.Type},
        {"red_against", Int64.Type},
        {"referee", type text},
        {"team_id", type text},
        {"opponent_id", type text},
        {"date", type date},
        {"result", type text},
        {"result_pt", type text},
        {"result_label", type text},
        {"pts", Int64.Type},
        {"goal_diff", Int64.Type},
        {"is_home", type logical},
        {"venue", type text},
        {"clean_sheet", type logical},
        {"failed_to_score", type logical},
        {"ht_state", type text},
        {"points_vs_halftime", type number},
        {"second_half_goals_for", type number},
        {"second_half_goals_against", type number},
        {"round", Int64.Type},
        {"is_brighton", type logical},
        {"season_label", type text},
        {"match_label", type text}
    })
in
    Fonte

// ----- Consulta: fact_transfers
let
    Fonte = fnCsv("fact_transfers", {
        {"season", Int64.Type},
        {"date", type date},
        {"window", type text},
        {"direction", type text},
        {"movement", type text},
        {"squad_group", type text},
        {"player_name", type text},
        {"player_key", type text},
        {"position", type text},
        {"nationality", type text},
        {"other_club", type text},
        {"retired", type logical},
        {"loan_until", type text},
        {"fee_text", type text},
        {"fee_type", type text},
        {"fee_gbp", type number},
        {"season_label", type text},
        {"position_group", type text},
        {"fee_gbp_signed", type number},
        {"is_first_team", type logical}
    })
in
    Fonte

// ----- Consulta: meta_refresh
let
    Fonte = fnCsv("meta_refresh", {
        {"source", type text},
        {"files", type number},
        {"last_refresh_utc", type text},
        {"last_result_date", type date}
    })
in
    Fonte
