"""Gera os artefatos do Power BI a partir do código, para o modelo ficar
versionado e reprodutível:

    powerbi/power_query.pq                  consultas M (tipos de coluna já definidos)
    powerbi/medidas_dax_query_view.dax      todas as medidas em um bloco DEFINE
    powerbi/criar_modelo_tabular_editor.csx  script C#: medidas, formatos, pastas e relacionamentos
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import yaml

from .config import PROJECT_ROOT

POWERBI_DIR = PROJECT_ROOT / "powerbi"
# Libras inteiras. A escala com vírgulas ("#,0.0,,") não funciona com o Power BI em
# português: aparecia "£76.500.000,0,,M". Cartões e gráficos já abreviam sozinhos (Mi).
FORMAT_ALIASES = {"£M": '"£"#,0;-"£"#,0;"£"0'}


# ------------------------------------------------------------------ tipos M
def infer_pq_types(df: pd.DataFrame) -> dict[str, str]:
    """Mapeia cada coluna do DataFrame para um tipo do Power Query."""
    types: dict[str, str] = {}
    for col in df.columns:
        s = df[col]
        if col.endswith("_id") or col == "player_key":
            types[col] = "type text"
        elif pd.api.types.is_bool_dtype(s):
            types[col] = "type logical"
        elif pd.api.types.is_integer_dtype(s):
            types[col] = "Int64.Type"
        elif pd.api.types.is_float_dtype(s):
            types[col] = "type number"
        elif pd.api.types.is_datetime64_any_dtype(s):
            types[col] = "type datetime"
        else:
            sample = s.dropna()
            if sample.empty:
                types[col] = "type text"
            elif sample.map(lambda v: isinstance(v, bool)).all():
                types[col] = "type logical"
            elif sample.map(lambda v: isinstance(v, (int,)) and not isinstance(v, bool)).all():
                types[col] = "Int64.Type"
            elif sample.map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)).all():
                types[col] = "type number"
            elif sample.map(lambda v: isinstance(v, dt.date) and not isinstance(v, dt.datetime)).all():
                types[col] = "type date"
            else:
                types[col] = "type text"
    return types


def render_power_query(
    schema: dict[str, dict[str, str]],
    command: str = "python -m brighton powerbi",
    folder: str = "brighton-dashboard\\data\\processed",
) -> str:
    out = [
        "// ============================================================================",
        f"// Power Query (M) - Brighton Dashboard  |  gerado por `{command}`",
        "//",
        "// 1) Página Inicial > Transformar dados > Gerenciar Parâmetros > Novo parâmetro",
        f"//    Nome: PastaDados   Tipo: Texto   Valor: C:\\caminho\\{folder}",
        "// 2) Nova Fonte > Consulta Nula > Editor Avançado: cole o bloco 'fnCsv' e renomeie para fnCsv",
        "// 3) Para cada tabela: Consulta Nula > Editor Avançado > cole o bloco e renomeie",
        "//    com o nome indicado no comentário.",
        "// Os CSVs usam ponto decimal: por isso a conversão usa a cultura en-US.",
        "// ============================================================================",
        "",
        "// ----- Consulta: fnCsv",
        "(nome as text, tipos as list) as table =>",
        "let",
        '    Caminho = PastaDados & (if Text.EndsWith(PastaDados, "\\") then "" else "\\") & nome & ".csv",',
        '    Fonte = Csv.Document(File.Contents(Caminho), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),",
        '    SemVazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),',
        '    Tipado = Table.TransformColumnTypes(SemVazios, tipos, "en-US")',
        "in",
        "    Tipado",
        "",
    ]
    for table, cols in schema.items():
        pairs = ",\n        ".join(f'{{"{c}", {t}}}' for c, t in cols.items())
        out += [
            f"// ----- Consulta: {table}",
            "let",
            f'    Fonte = fnCsv("{table}", {{\n        {pairs}\n    }})',
            "in",
            "    Fonte",
            "",
        ]
    return "\n".join(out)


# ------------------------------------------------------------------ medidas
def load_measures(path: Path | None = None) -> dict:
    with open(path or POWERBI_DIR / "medidas.yaml", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    for m in spec["measures"]:
        m["expr"] = str(m["expr"]).strip()
        if m.get("format"):
            m["format"] = FORMAT_ALIASES.get(str(m["format"]), str(m["format"]))
    return spec


def check_measures(spec: dict) -> list[str]:
    """Validações simples: nomes únicos, parênteses/colchetes balanceados,
    medidas referenciadas existem."""
    import re

    errors = []
    names = [m["name"] for m in spec["measures"]]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        errors.append(f"medidas duplicadas: {dup}")
    known = set(names)
    for m in spec["measures"]:
        expr = re.sub(r'"[^"]*"', '""', m["expr"])  # ignora conteúdo de strings
        for o, c in ("()", "[]", "{}"):
            if expr.count(o) != expr.count(c):
                errors.append(f"{m['name']}: '{o}{c}' desbalanceado")
        # referências [Medida] sem tabela na frente
        for ref in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", expr):
            if not ref.startswith("@") and ref not in known:
                errors.append(f"{m['name']}: referência a medida inexistente [{ref}]")
    return errors


def render_dax_query_view(spec: dict) -> str:
    table = spec["measure_table"]
    lines = [
        "// Cole no Power BI Desktop > Exibição de consulta DAX e clique em",
        "// \"Atualizar modelo: adicionar N novas medidas\" acima do DEFINE.",
        f"// Antes: crie a tabela '{table}' (Página Inicial > Inserir dados > Carregar).",
        "// Formatos e pastas NÃO são aplicados por aqui; use o script do Tabular Editor para isso.",
        "DEFINE",
    ]
    for m in spec["measures"]:
        body = m["expr"].replace("\n", "\n        ")
        lines.append(f"    MEASURE '{table}'[{m['name']}] =\n        {body}")
    # consulta de conferência só com medidas que existem neste modelo
    names = {m["name"] for m in spec["measures"]}
    probe = [n for n in ("Pontos", "Posição Atual", "Saldo de Gols", "xG") if n in names] or [spec["measures"][0]["name"]]
    row = ", ".join(f'"{n}", [{n}]' for n in probe)
    lines += ["", "EVALUATE", f"    ROW ( {row} )", ""]
    return "\n".join(lines)


def _cs(s: str) -> str:
    """String C# verbatim."""
    return '@"' + s.replace('"', '""') + '"'


def render_tabular_editor(spec: dict) -> str:
    table = spec["measure_table"]
    out = [
        "// Script para o Tabular Editor 2 (gratuito) ou 3:",
        "// Power BI Desktop > Ferramentas Externas > Tabular Editor > aba 'C# Script' > colar > Executar (F5)",
        "// Depois: Ctrl+S no Tabular Editor para gravar no modelo.",
        f'var t = Model.Tables.Contains("{table}") ? Model.Tables["{table}"] : null;',
        f'if (t == null) {{ Error("Crie antes a tabela {table} (Página Inicial > Inserir dados)."); return; }}',
        "",
        "// ---------- relacionamentos",
        "Action<string,string,string,string> rel = (dimT, dimC, factT, factC) => {",
        "    var to = Model.Tables[dimT].Columns[dimC];",
        "    var from = Model.Tables[factT].Columns[factC];",
        "    foreach (var r in Model.Relationships.ToList())",
        "        if (r.FromColumn == from && r.ToColumn == to) return;",
        "    var nr = Model.AddRelationship();",
        "    nr.FromColumn = from; nr.ToColumn = to;",
        "    nr.CrossFilteringBehavior = CrossFilteringBehavior.OneDirection;",
        "};",
    ]
    # remove relações que o Power BI cria sozinho ao carregar as tabelas ("detectar
    # automaticamente"): elas geram caminhos ambíguos (ex.: dim_date -> dim_season)
    wanted = ", ".join(f'"{dim}|{fact}"' for dim, fact in spec["relationships"])
    out += [
        f"var desejadas = new HashSet<string> {{ {wanted} }};",
        "var removidas = 0;",
        "Func<string, bool> nossa = n => n.StartsWith(\"dim_\") || n.StartsWith(\"fact_\") || n.StartsWith(\"meta_\");",
        "foreach (var r in Model.Relationships.ToList()) {",
        "    // não mexe nas tabelas internas do Power BI (LocalDateTable_..., DateTableTemplate_...)",
        "    if (!nossa(r.FromColumn.Table.Name) || !nossa(r.ToColumn.Table.Name)) continue;",
        '    var chave = r.ToColumn.Table.Name + "." + r.ToColumn.Name + "|" + r.FromColumn.Table.Name + "." + r.FromColumn.Name;',
        "    if (!desejadas.Contains(chave)) { r.Delete(); removidas++; }",
        "}",
    ]
    for dim, fact in spec["relationships"]:
        dt_, dc = dim.split(".")
        ft, fc = fact.split(".")
        out.append(f'rel("{dt_}", "{dc}", "{ft}", "{fc}");')

    out += ["", "// ---------- ordenação de colunas"]
    for col, by in spec.get("sort_by", []):
        t1, c1 = col.split(".")
        _, c2 = by.split(".")
        out.append(f'Model.Tables["{t1}"].Columns["{c1}"].SortByColumn = Model.Tables["{t1}"].Columns["{c2}"];')

    out += [
        "",
        "// ---------- tabela de datas",
        'Model.Tables["dim_date"].DataCategory = "Time";',
        'Model.Tables["dim_date"].Columns["date"].IsKey = true;',
        "",
        "// ---------- medidas",
        "Action<string,string,string,string,string> m = (nome, expr, pasta, formato, desc) => {",
        "    var x = t.Measures.Contains(nome) ? t.Measures[nome] : t.AddMeasure(nome);",
        "    x.Expression = expr; x.DisplayFolder = pasta;",
        "    if (!string.IsNullOrEmpty(formato)) x.FormatString = formato;",
        "    if (!string.IsNullOrEmpty(desc)) x.Description = desc;",
        "};",
    ]
    for ms in spec["measures"]:
        out.append(
            f"m({_cs(ms['name'])}, {_cs(ms['expr'])}, {_cs(ms['folder'])}, "
            f"{_cs(ms.get('format') or '')}, {_cs(ms.get('description') or '')});"
        )
        if ms.get("data_category"):
            out.append(f'Model.Tables["{table}"].Measures[{_cs(ms["name"])}].DataCategory = "{ms["data_category"]}";')
    if spec.get("image_columns"):
        out += ["", "// ---------- colunas com URL de imagem"]
        for ref in spec["image_columns"]:
            tb, c = ref.split(".")
            out.append(f'Model.Tables["{tb}"].Columns["{c}"].DataCategory = "ImageUrl";')
    out += [
        "",
        "// ---------- esconde colunas técnicas (chaves) nas tabelas fato",
        "foreach (var tb in Model.Tables.Where(x => x.Name.StartsWith(\"fact_\")))",
        "    foreach (var c in tb.Columns.Where(c => c.Name.EndsWith(\"_id\") || c.Name == \"player_key\"))",
        "        c.IsHidden = true;",
        'Info("Modelo configurado: " + t.Measures.Count + " medidas, " + Model.Relationships.Count + " relações (" + removidas + " automáticas removidas).");',
        "",
    ]
    return "\n".join(out)


def merge_specs(*specs: dict) -> dict:
    """Junta vários arquivos de medidas (ex.: público + privado)."""
    merged = {"measure_table": specs[0]["measure_table"], "relationships": [], "sort_by": [], "measures": [],
              "image_columns": []}
    for sp in specs:
        merged["relationships"] += sp.get("relationships", [])
        merged["sort_by"] += sp.get("sort_by", [])
        merged["measures"] += sp.get("measures", [])
        merged["image_columns"] += sp.get("image_columns", [])
    return merged


def generate_all(
    processed_dir: Path,
    out_dir: Path = POWERBI_DIR,
    spec: dict | None = None,
    command: str = "python -m brighton powerbi",
    folder: str = "brighton-dashboard\\data\\processed",
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    schema_file = Path(processed_dir) / "_schema.json"
    if schema_file.exists():
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        p = out_dir / "power_query.pq"
        p.write_text(render_power_query(schema, command, folder), encoding="utf-8")
        written.append(p)

    spec = spec or load_measures(out_dir / "medidas.yaml")
    errors = check_measures(spec)
    if errors:
        raise ValueError("Problemas no medidas.yaml:\n  " + "\n  ".join(errors))
    for name, fn in (
        ("medidas_dax_query_view.dax", render_dax_query_view),
        ("criar_modelo_tabular_editor.csx", render_tabular_editor),
    ):
        p = out_dir / name
        p.write_text(fn(spec), encoding="utf-8")
        written.append(p)
    return written
