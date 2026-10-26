import json

from brighton.config import load_settings
from brighton.powerbi import POWERBI_DIR, check_measures, generate_all, load_measures
from brighton.transform.model import ModelBuilder


def test_measures_yaml_is_valid():
    spec = load_measures()
    assert check_measures(spec) == []
    assert len(spec["measures"]) >= 70


def test_relationships_point_to_real_columns(raw_project):
    _, cfg = raw_project
    b = ModelBuilder(load_settings(cfg))
    tables = b.build()
    spec = load_measures()
    for dim, fact in spec["relationships"]:
        for ref in (dim, fact):
            t, c = ref.split(".")
            assert c in tables[t].columns, f"{ref} não existe"
        dt, dc = dim.split(".")
        assert tables[dt][dc].is_unique, f"{dim} não é chave única"


def test_generated_artifacts(raw_project, tmp_path):
    _, cfg = raw_project
    s = load_settings(cfg)
    b = ModelBuilder(s)
    b.build()
    b.write()
    schema = json.loads((s.path("processed") / "_schema.json").read_text(encoding="utf-8"))
    assert schema["fact_team_match"]["goals_for"] == "Int64.Type"
    assert schema["fact_team_match"]["shots_for"] == "Int64.Type"  # coluna opcional existe mesmo vazia
    assert schema["fact_team_match"]["is_brighton"] == "type logical"
    assert schema["fact_team_match"]["round"] == "Int64.Type"
    assert schema["dim_date"]["date"] == "type date"
    assert schema["fact_team_match"]["team_id"] == "type text"

    out = tmp_path / "pbi"
    out.mkdir()
    (out / "medidas.yaml").write_text((POWERBI_DIR / "medidas.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    paths = {p.name: p.read_text(encoding="utf-8") for p in generate_all(s.path("processed"), out)}
    assert 'fnCsv("fact_transfers"' in paths["power_query.pq"]
    assert "MEASURE '_Medidas'[Posição Atual]" in paths["medidas_dax_query_view.dax"]
    csx = paths["criar_modelo_tabular_editor.csx"]
    assert 'rel("dim_player", "player_key", "fact_transfers", "player_key");' in csx
    assert '""£""#,0;-""£""#,0;""£""0' in csx  # sem a escala ",," (quebra em pt-BR)
    assert '""Chegada""' in csx  # aspas escapadas na string verbatim do C#


def test_dax_probe_query_only_uses_existing_measures():
    from brighton.powerbi import render_dax_query_view

    spec = load_measures()
    dax = render_dax_query_view(spec)
    probe = dax.split("EVALUATE")[1]
    names = {m["name"] for m in spec["measures"]}
    import re

    for ref in re.findall(r"\[([^\]]+)\]", probe):
        assert ref in names, ref


def test_script_removes_auto_detected_relationships():
    """O Power BI cria relações sozinho ao carregar (ex.: dim_date.season -> dim_season),
    o que causa caminhos ambíguos. O script remove tudo que não está no medidas.yaml."""
    from brighton.powerbi import render_tabular_editor

    spec = load_measures()
    csx = render_tabular_editor(spec)
    assert '"dim_season.season|fact_fixtures.season"' in csx
    assert "r.Delete()" in csx
    assert csx.index("r.Delete()") < csx.index('rel("dim_season"')  # limpa antes de criar
    # nunca apaga as relações das tabelas de data automáticas do Power BI (LocalDateTable_...)
    assert csx.index("if (!nossa(r.FromColumn.Table.Name)") < csx.index("r.Delete()")
