"""Projeto do Power BI (.pbip) gerado por código: modelo TMDL + relatório PBIR."""
import json
import re
import shutil

from brighton.config import load_settings
from brighton.pbip import generate_project
from brighton.powerbi import POWERBI_DIR, load_measures
from brighton.tmdl import _parse_measures
from brighton.transform.model import ModelBuilder


def _project(raw_project, tmp_path):
    _, cfg = raw_project
    s = load_settings(cfg)
    b = ModelBuilder(s)
    b.build()
    b.write()
    out = tmp_path / "powerbi"
    out.mkdir()
    for f in ("medidas.yaml", "tema_brighton_claro.json"):
        shutil.copy(POWERBI_DIR / f, out / f)
    shutil.copytree(POWERBI_DIR / "base", out / "base")
    return s.path("processed"), out


def _fields(obj):
    """(tabela, campo) de todas as referências a colunas/medidas de um visual."""
    if isinstance(obj, dict):
        for k in ("Column", "Measure"):
            if k in obj and "Entity" in obj[k]["Expression"].get("SourceRef", {}):
                yield obj[k]["Expression"]["SourceRef"]["Entity"], obj[k]["Property"]
        for v in obj.values():
            yield from _fields(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _fields(v)


def test_generates_a_complete_project(raw_project, tmp_path):
    processed, out = _project(raw_project, tmp_path)
    r = generate_project(processed, out, data_folder="C:\\dados\\processed")
    assert r["modelo"]["modo"] == "criado" and len(r["paginas"]) == 6
    assert json.loads((out / "Brighton.pbip").read_text())["artifacts"][0]["report"]["path"] == "Brighton.Report"
    d = out / "Brighton.SemanticModel" / "definition"
    assert 'Fonte = "C:\\dados\\processed"' in (d / "expressions.tmdl").read_text(encoding="utf-8")
    assert "annotation __PBI_TimeIntelligenceEnabled = 0" in (d / "model.tmdl").read_text(encoding="utf-8")

    # todos os campos usados nos visuais existem no modelo gerado
    model = {}
    for f in (d / "tables").glob("*.tmdl"):
        lines = f.read_bytes().decode("utf-8").splitlines()
        model[f.stem] = {m.group(1) for ln in lines if (m := re.match(r"^\tcolumn (\w+)", ln))}
        model[f.stem] |= {b.name for b in _parse_measures(lines)}
    assert len(model["_Medidas"]) == len(load_measures()["measures"])
    used = set()
    for v in (out / "Brighton.Report" / "definition" / "pages").rglob("visual.json"):
        used |= set(_fields(json.loads(v.read_text(encoding="utf-8"))))
    missing = {(t, c) for t, c in used if c not in model.get(t, set())}
    assert not missing, missing

    # nada da versão privada no relatório público
    text = " ".join(p.read_text(encoding="utf-8") for p in (out / "Brighton.Report").rglob("*.json"))
    for private in ("xG", "fact_shots", "photo_url", "Uso Pessoal", "escudo"):
        assert private not in text, private

    # tabela de datas marcada, chaves escondidas e ordenação do mês
    dates = (d / "tables" / "dim_date.tmdl").read_text(encoding="utf-8")
    assert "\tdataCategory: Time" in dates and "\t\tisKey" in dates and "\t\tsortByColumn: month" in dates
    assert "\t\tisHidden" in (d / "tables" / "fact_team_match.tmdl").read_text(encoding="utf-8")
    assert (d / "relationships.tmdl").read_text(encoding="utf-8").count("relationship ") == 12


def test_second_run_only_syncs(raw_project, tmp_path):
    processed, out = _project(raw_project, tmp_path)
    generate_project(processed, out, data_folder="C:\\x")
    before = (out / "Brighton.SemanticModel" / "definition" / "tables" / "_Medidas.tmdl").read_bytes()
    r = generate_project(processed, out, data_folder="C:\\x")
    assert r["modelo"]["modo"] == "sincronizado"
    assert r["modelo"]["medidas"] == {"atualizadas": [], "criadas": [], "ignoradas": []}
    assert r["modelo"]["tabelas"] == {}
    assert (out / "Brighton.SemanticModel" / "definition" / "tables" / "_Medidas.tmdl").read_bytes() == before
