"""Gera o projeto do Power BI (.pbip) inteiro a partir do código.

    python -m brighton pbip

Cria em powerbi/:
    Brighton.pbip                       abre no Power BI Desktop
    Brighton.SemanticModel/definition/  modelo em TMDL: tabelas (Power Query), tipos,
                                        relacionamentos, tabela de datas e medidas
    Brighton.Report/definition/         páginas e visuais em PBIR (brighton.dashboard)

O modelo vem de data/processed/_schema.json e de powerbi/medidas.yaml; as páginas, de
brighton/dashboard.py. Se o projeto já existir, o modelo é SINCRONIZADO (colunas e
medidas novas entram, o que foi criado à mão no Power BI fica) e as páginas geradas
são regravadas. Feche o Power BI Desktop antes de rodar.

Os identificadores (lineageTag) são derivados dos nomes, então rodar de novo não
gera diferenças no git à toa.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from .powerbi import POWERBI_DIR, load_measures
from .report import Page, write_json, write_pages
from .tmdl import _column_block, _partition_m, _render, set_image_columns, sync_measures, sync_table_schema

NS = uuid.UUID("6f1c8a52-2c55-4c1e-9f0e-5b7f3a1d2b10")
MEASURE_TABLE_SOURCE = [
    "let",
    '  Origem = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", '
    'BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) '
    'in type table [#"Coluna 1" = _t]),',
    '    #"Colunas Removidas" = Table.RemoveColumns(Origem,{"Coluna 1"})',
    "in",
    '  #"Colunas Removidas"',
]
BASE_THEME = "Fluent2-CY26SU10"
VERSION_AT_IMPORT = {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def _write(path: Path, lines: list[str] | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = lines if isinstance(lines, str) else "\n".join(lines) + "\n"
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def default_data_folder(processed: Path) -> str:
    """Caminho da pasta de CSVs que vai no parâmetro PastaDados (Windows)."""
    if os.name == "nt":
        return str(Path(processed).resolve())
    return "C:\\caminho\\para\\brighton-dashboard\\data\\processed"


# ------------------------------------------------------------- modelo (TMDL)
def _table_tmdl(table: str, cols: dict[str, str], spec: dict) -> list[str]:
    sort_by = {a.split(".")[1]: b.split(".")[1] for a, b in spec.get("sort_by", []) if a.startswith(table + ".")}
    images = {r.split(".")[1] for r in spec.get("image_columns", []) if r.startswith(table + ".")}
    out = [f"table {table}", f"\tlineageTag: {_id('table', table)}"]
    if table == "dim_date":
        out.append("\tdataCategory: Time")
    out.append("")
    for c, t in cols.items():
        hidden = table.startswith("fact_") and (c.endswith("_id") or c == "player_key")
        out += _column_block(c, t, hidden=hidden, key=(table == "dim_date" and c == "date"),
                             sort_by=sort_by.get(c), data_category="ImageUrl" if c in images else None,
                             lineage=_id("column", table, c))
    out += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource ="]
    out += ["\t\t\t\t" + ln for ln in _partition_m(table, cols)]
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return out


def _measures_tmdl(spec: dict) -> list[str]:
    name = spec["measure_table"]
    out = [f"table {name}", f"\tlineageTag: {_id('table', name)}", ""]
    for m in spec["measures"]:
        out += _render("'" + m["name"].replace("'", "''") + "'", m, [f"\t\tlineageTag: {_id('measure', m['name'])}"])
        out.append("")
    out += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    out += ["\t\t\t\t" + ln for ln in MEASURE_TABLE_SOURCE]
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return out


def write_semantic_model(dest: Path, name: str, schema: dict, spec: dict, data_folder: str) -> dict:
    """Cria o modelo do zero ou sincroniza um existente. Devolve um resumo."""
    definition = dest / "definition"
    tables_dir = definition / "tables"
    if (definition / "model.tmdl").exists():
        changes = {t: sync_table_schema(tables_dir, t, cols) for t, cols in schema.items()}
        set_image_columns(tables_dir, spec.get("image_columns", []))
        measures = sync_measures(tables_dir / f"{spec['measure_table']}.tmdl", spec)
        return {"modo": "sincronizado", "tabelas": {t: c for t, c in changes.items() if any(c.values())},
                "medidas": measures}

    tables = list(schema) + [spec["measure_table"]]
    _write(dest / "definition.pbism", json.dumps({"version": "4.2", "settings": {}}, indent=2))
    _write(dest / ".platform", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": name},
        "config": {"version": "2.0", "logicalId": _id("semanticmodel", name)},
    }, indent=2))
    _write(definition / "database.tmdl", ["database", "\tcompatibilityLevel: 1606", ""])
    query_order = json.dumps(["PastaDados", "fnCsv", *tables], ensure_ascii=False)
    _write(definition / "model.tmdl", [
        "model Model",
        "\tculture: pt-BR",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: pt-BR",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",  # sem as tabelas de data automáticas
        "",
        f"annotation PBI_QueryOrder = {query_order}",
        "",
        *[f"ref table {t}" for t in tables],
        "",
    ])
    folder = data_folder.replace('"', '""')
    _write(definition / "expressions.tmdl", [
        "expression PastaDados =",
        "\t\tlet",
        f'\t\t    Fonte = "{folder}" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = type text]',
        "\t\tin",
        "\t\t    Fonte",
        f"\tlineageTag: {_id('expression', 'PastaDados')}",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
        "expression fnCsv =",
        "\t\t(nome as text, tipos as list) as table =>",
        "\t\tlet",
        '\t\t    Caminho = PastaDados & (if Text.EndsWith(PastaDados, "\\") then "" else "\\") & nome & ".csv",',
        '\t\t    Fonte = Csv.Document(File.Contents(Caminho), [Delimiter = ",", Encoding = 65001, '
        "QuoteStyle = QuoteStyle.Csv]),",
        "\t\t    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),",
        '\t\t    SemVazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, '
        "Table.ColumnNames(Cabecalho)),",
        '\t\t    Tipado = Table.TransformColumnTypes(SemVazios, tipos, "en-US")',
        "\t\tin",
        "\t\t    Tipado",
        f"\tlineageTag: {_id('expression', 'fnCsv')}",
        "",
        "\tannotation PBI_ResultType = Function",
        "",
    ])
    rels = []
    for dim, fact in spec["relationships"]:
        rels += [f"relationship {_id('rel', dim, fact)}", f"\tfromColumn: {fact}", f"\ttoColumn: {dim}", ""]
    _write(definition / "relationships.tmdl", rels)
    for t, cols in schema.items():
        _write(tables_dir / f"{t}.tmdl", _table_tmdl(t, cols, spec))
    _write(tables_dir / f"{spec['measure_table']}.tmdl", _measures_tmdl(spec))
    return {"modo": "criado", "tabelas": list(schema), "medidas": len(spec["measures"])}


# ------------------------------------------------------------ relatório (PBIR)
def write_report_skeleton(dest: Path, name: str, model_name: str, base_theme: Path) -> None:
    if (dest / "definition" / "report.json").exists():
        return
    _write(dest / ".platform", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": name},
        "config": {"version": "2.0", "logicalId": _id("report", name)},
    }, indent=2))
    _write(dest / "definition.pbir", json.dumps(
        {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{model_name}.SemanticModel"}}}, indent=2))
    write_json(dest / "definition" / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    shared = dest / "StaticResources" / "SharedResources" / "BaseThemes"
    shared.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_theme, shared / f"{BASE_THEME}.json")
    write_json(dest / "definition" / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": BASE_THEME, "reportVersionAtImport": VERSION_AT_IMPORT,
                                          "type": "SharedResources"}},
        "objects": {"section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}]},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json",
                                         "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    })


def generate_project(
    processed: Path,
    out_dir: Path = POWERBI_DIR,
    name: str = "Brighton",
    spec: dict | None = None,
    build_pages: Callable[[str | None], list[Page]] | None = None,
    theme: Path | None = None,
    data_folder: str | None = None,
) -> dict:
    from . import dashboard

    schema = json.loads((Path(processed) / "_schema.json").read_text(encoding="utf-8"))
    spec = spec or load_measures(out_dir / "medidas.yaml")
    model = write_semantic_model(out_dir / f"{name}.SemanticModel", name, schema, spec,
                                 data_folder or default_data_folder(processed))
    report_dir = out_dir / f"{name}.Report"
    write_report_skeleton(report_dir, name, name, out_dir / "base" / f"{BASE_THEME}.json")
    theme = theme or out_dir / "tema_brighton_claro.json"
    pages = write_pages(report_dir, build_pages or dashboard.build,
                        {"Brighton_Seagulls_claro.json": (theme, "CustomTheme")})
    pbip = out_dir / f"{name}.pbip"
    if not pbip.exists():
        _write(pbip, json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{name}.Report"}}],
                                 "settings": {"enableAutoRecovery": True}}, indent=2))
    return {"modelo": model, "paginas": [p.title for p in pages], "visuais": sum(len(p.visuals) for p in pages),
            "arquivo": pbip}
