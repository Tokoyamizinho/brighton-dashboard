"""Aplicar o medidas.yaml direto nos arquivos TMDL do projeto .pbip."""
from brighton.tmdl import _parse_measures, set_image_columns, sync_measures

SAMPLE = """table _Medidas
\tlineageTag: 70dc6538

\tmeasure Jogos = CALCULATE ( COUNTROWS ( fact_team_match ), fact_team_match[is_brighton] = TRUE () )
\t\tformatString: 0
\t\tlineageTag: 59bfdd7c

\tmeasure 'Próximo Adversário' =
\t\t\tVAR _p = FILTER ( fact_fixtures, fact_fixtures[is_next] = TRUE () )
\t\t\tRETURN
\t\t\t    MAXX ( _p, fact_fixtures[opponent] )
\t\tdisplayFolder: 4. Tabela e Momento
\t\tlineageTag: c86aa411

\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}

\t/// Horário de Brasília.
\tmeasure 'Próximo Jogo (Brasília)' = MAXX ( FILTER ( fact_fixtures, fact_fixtures[is_next] ), fact_fixtures[kickoff_brasilia] )
\t\tformatString: dd/mm "às" hh:nn
\t\tdisplayFolder: 4. Tabela e Momento
\t\tlineageTag: 2089aa25

\tmeasure 'Feita à mão' = 1
\t\tlineageTag: 11111111

\tpartition _Medidas = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t  Origem = 1
\t\t\t\tin
\t\t\t\t  Origem

\tannotation PBI_ResultType = Table

"""

SPEC = {
    "measure_table": "_Medidas",
    "measures": [
        {"name": "Jogos", "folder": "", "format": "0",
         "expr": "CALCULATE ( COUNTROWS ( fact_team_match ), fact_team_match[is_brighton] = TRUE () )"},
        {"name": "Próximo Adversário", "folder": "4. Tabela e Momento",
         "expr": "VAR _k = [Próximo Jogo (Brasília)]\nRETURN\n    CALCULATE ( MAX ( fact_fixtures[opponent] ), fact_fixtures[kickoff_brasilia] = _k )"},
        {"name": "Próximo Jogo (Brasília)", "folder": "4. Tabela e Momento", "format": 'dd/mm "às" hh:nn',
         "description": "Horário de Brasília.",
         "expr": "CALCULATE ( MIN ( fact_fixtures[kickoff_brasilia] ), fact_fixtures[kickoff_brasilia] > NOW () )"},
        {"name": "Lesionados", "folder": "13. Departamento Médico", "format": "0",
         "expr": 'CALCULATE ( COUNTROWS ( fact_player_status ), fact_player_status[situation] = "Lesionado" )'},
        {"name": "Foto", "folder": "13. Departamento Médico", "data_category": "ImageUrl",
         "expr": "SELECTEDVALUE ( dim_player[photo_url] )"},
    ],
}


def test_parse_finds_all_measures_with_their_parts():
    blocks = {b.name: b for b in _parse_measures(SAMPLE.split("\n"))}
    assert list(blocks) == ["Jogos", "Próximo Adversário", "Próximo Jogo (Brasília)", "Feita à mão"]
    assert blocks["Próximo Adversário"].expr.startswith("VAR _p")
    assert blocks["Próximo Jogo (Brasília)"].desc == ["Horário de Brasília."]
    assert any("annotation" in p for p in blocks["Próximo Adversário"].props)


def test_sync_updates_changed_creates_new_and_keeps_the_rest(tmp_path):
    f = tmp_path / "_Medidas.tmdl"
    f.write_text(SAMPLE, encoding="utf-8")
    rep = sync_measures(f, SPEC)
    assert rep["atualizadas"] == ["Próximo Adversário", "Próximo Jogo (Brasília)"]
    assert rep["criadas"] == ["Lesionados", "Foto"]
    out = f.read_text(encoding="utf-8")
    # identidade preservada, expressão nova, anotação mantida
    assert "lineageTag: c86aa411" in out and "lineageTag: 2089aa25" in out
    assert "is_next" not in out and "fact_fixtures[kickoff_brasilia] > NOW ()" in out
    assert 'annotation PBI_FormatHint = {"isGeneralNumber":true}' in out
    # medida criada à mão e partição continuam lá, partição depois das medidas
    assert "measure 'Feita à mão' = 1" in out
    assert out.index("measure 'Foto'") < out.index("partition _Medidas")
    assert "\t\tdataCategory: ImageUrl" in out
    blocks = {b.name: b for b in _parse_measures(out.split("\n"))}
    assert len(blocks) == 6 and blocks["Lesionados"].props[0] == "\t\tformatString: 0"
    # segunda execução não muda nada
    assert sync_measures(f, SPEC) == {"atualizadas": [], "criadas": [], "ignoradas": []}


def test_sync_keeps_windows_line_endings(tmp_path):
    f = tmp_path / "_Medidas.tmdl"
    f.write_bytes(SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    sync_measures(f, SPEC)
    data = f.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n")


def test_image_columns(tmp_path):
    (tmp_path / "fact_player_status.tmdl").write_text(
        "table fact_player_status\n\tlineageTag: x\n\n\tcolumn photo_url\n\t\tdataType: string\n"
        "\t\tlineageTag: 2c83\n\t\tsummarizeBy: none\n\t\tsourceColumn: photo_url\n\n"
        "\t\tannotation SummarizationSetBy = Automatic\n\n\tcolumn player_key\n\t\tdataType: string\n",
        encoding="utf-8",
    )
    assert set_image_columns(tmp_path, ["fact_player_status.photo_url", "dim_x.y"]) == ["fact_player_status.photo_url"]
    text = (tmp_path / "fact_player_status.tmdl").read_text(encoding="utf-8")
    assert "\t\tlineageTag: 2c83\n\t\tdataCategory: ImageUrl\n" in text
    assert set_image_columns(tmp_path, ["fact_player_status.photo_url"]) == []  # já marcado


TABLE = (
    "table fact_player_status\r\n\tlineageTag: x\r\n\r\n\tcolumn web_name\r\n\t\tdataType: string\r\n"
    "\t\tlineageTag: a1\r\n\t\tsummarizeBy: none\r\n\t\tsourceColumn: web_name\r\n\r\n"
    "\t\tannotation SummarizationSetBy = Automatic\r\n\r\n"
    "\tpartition fact_player_status = m\r\n\t\tmode: import\r\n\t\tsource =\r\n"
    "\t\t\t\tlet\r\n\t\t\t\t    Fonte = fnCsv(\"fact_player_status\", {\r\n"
    "\t\t\t\t        {\"web_name\", type text}\r\n\t\t\t\t    })\r\n\t\t\t\tin\r\n\t\t\t\t    Fonte\r\n\r\n"
    "\tannotation PBI_ResultType = Table\r\n\r\n"
)


def test_table_schema_gets_new_columns_and_types(tmp_path):
    from brighton.tmdl import sync_table_schema

    f = tmp_path / "fact_player_status.tmdl"
    f.write_bytes(TABLE.encode("utf-8"))
    cols = {"web_name": "type text", "situation": "type text", "expected_back": "type date",
            "is_medical": "type logical", "days_out": "Int64.Type"}
    rep = sync_table_schema(tmp_path, "fact_player_status", cols)
    assert rep == {"colunas_novas": ["situation", "expected_back", "is_medical", "days_out"],
                   "consulta_atualizada": True}
    out = f.read_bytes().decode("utf-8")
    assert out.count("\n") == out.count("\r\n")
    assert '{"expected_back", type date}' in out and "\tcolumn expected_back\r\n\t\tdataType: dateTime" in out
    assert out.index("\tcolumn days_out") < out.index("\tpartition")
    assert "\tannotation PBI_ResultType = Table" in out
    assert sync_table_schema(tmp_path, "fact_player_status", cols) == {"colunas_novas": [],
                                                                        "consulta_atualizada": False}
