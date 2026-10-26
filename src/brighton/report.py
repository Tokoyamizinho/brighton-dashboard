"""Relatório do Power BI como código (formato PBIR).

Cada página é um objeto `Page`; os métodos (`card`, `line`, `table`, `slicer`...)
gravam os visuais com posição, campos, filtros e formatação. `write_pages` grava
tudo na pasta `<nome>.Report/definition` de um projeto .pbip e registra o tema e
as imagens. As saídas seguem os esquemas oficiais em
https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition

Usado por `brighton.pbip` (versão pública) e por private/powerbi/gerar_relatorio.py.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VC_SCHEMA = f"{SCHEMA}/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = f"{SCHEMA}/page/2.1.0/schema.json"
PAGES_SCHEMA = f"{SCHEMA}/pagesMetadata/1.1.0/schema.json"

M = "_Medidas"
W, H = 1920, 1080
GAP = 16
LEFT = 24
SEASON_NOW = "2026/27"  # temporada pré-selecionada nos filtros (troque a cada agosto)
# cores do escudo: azul Brighton, branco e o amarelo do bico da gaivota
BLUE, NAVY, GREY, WHITE, GOLD = "#0057B8", "#0B2545", "#5B6B82", "#FFFFFF", "#E5A800"
BAND_H = 84  # faixa azul do título

AGG = {"sum": 0, "avg": 1, "count_distinct": 2, "min": 3, "max": 4}
AGG_LABEL = {0: "Sum", 1: "Avg", 2: "CountNonNull", 3: "Min", 4: "Max"}


def uid(*parts: str) -> str:
    """Nome estável de 20 caracteres (o mesmo a cada execução)."""
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:20]


# ------------------------------------------------------------ expressões
def col(table: str, column: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def mea(name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}


def agg(table: str, column: str, fn: str = "sum") -> dict:
    return {"Aggregation": {"Expression": col(table, column), "Function": AGG[fn]}}


def lit(value) -> dict:
    """Literal de formatação: texto entre aspas simples, número com D, bool."""
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)):
        v = f"{value}D"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


def color(hex_: str) -> dict:
    return {"solid": {"color": lit(hex_)}}


def resource(name: str) -> dict:
    return {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1,
                                             "ItemName": name}}}


NO_FRAME = {"background": [{"properties": {"show": lit(False)}}],
            "border": [{"properties": {"show": lit(False)}}],
            "title": [{"properties": {"show": lit(False)}}]}


def projection(field: dict, display: str | None = None, fmt: str | None = None) -> dict:
    if "Measure" in field:
        p = field["Measure"]
        ref, native = f"{M}.{p['Property']}", p["Property"]
    elif "Column" in field:
        c = field["Column"]
        t = c["Expression"]["SourceRef"]["Entity"]
        ref, native = f"{t}.{c['Property']}", c["Property"]
    else:
        a = field["Aggregation"]
        c = a["Expression"]["Column"]
        t = c["Expression"]["SourceRef"]["Entity"]
        fn = AGG_LABEL[a["Function"]]
        ref, native = f"{fn}({t}.{c['Property']})", f"{fn} of {c['Property']}"
    out = {"field": field, "queryRef": ref, "nativeQueryRef": native}
    if display:
        out["displayName"] = display
    if fmt:
        out["format"] = fmt
    return out


class F(tuple):
    """Campo de um visual: F(campo, "Título", w=peso_da_largura, px=largura_fixa, fmt="formato")."""

    def __new__(cls, field: dict, display: str | None = None, w: float = 1.0, px: int | None = None,
                fmt: str | None = None):
        obj = super().__new__(cls, (field, display))
        obj.w, obj.px, obj.fmt = w, px, fmt
        return obj


def query(roles: dict, sort: list | None = None) -> dict:
    state = {}
    for role, fields in roles.items():
        projs = []
        for f in fields:
            field, display = f if isinstance(f, tuple) else (f, None)
            projs.append(projection(field, display, getattr(f, "fmt", None)))
        state[role] = {"projections": projs}
    q = {"queryState": state}
    if sort:
        q["sortDefinition"] = {
            "sort": [{"field": f, "direction": d} for f, d in sort],
            "isDefaultSort": True,
        }
    return q


# ---------------------------------------------------------------- filtros
def _where(table: str, column: str, cond_builder) -> dict:
    alias = table[0] + table.split("_")[-1][:3]
    ref = {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": column}}
    return {
        "Version": 2,
        "From": [{"Name": alias, "Entity": table, "Type": 0}],
        "Where": [{"Condition": cond_builder(ref)}],
    }


def _values(values) -> list:
    out = []
    for v in values:
        if isinstance(v, bool):
            s = "true" if v else "false"
        elif isinstance(v, int):
            s = f"{v}L"
        else:
            s = "'" + str(v).replace("'", "''") + "'"
        out.append([{"Literal": {"Value": s}}])
    return out


def in_filter(table: str, column: str, values, exclude: bool = False) -> dict:
    def cond(ref):
        c = {"In": {"Expressions": [ref], "Values": _values(values)}}
        return {"Not": {"Expression": c}} if exclude else c

    return _where(table, column, cond)


def filter_item(name: str, table: str, column: str, values, exclude: bool = False, hidden=False) -> dict:
    item = {
        "name": name,
        "field": col(table, column),
        "type": "Categorical",
        "filter": in_filter(table, column, values, exclude),
        "howCreated": "User",
    }
    if hidden:
        item["isHiddenInViewMode"] = True
    return item


def measure_between(name: str, measure: str, low: int, high: int) -> dict:
    """Filtro de visual por medida: low <= [medida] <= high (vazios ficam de fora)."""
    ref = {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}}

    def cmp(kind, value):
        return {"Comparison": {"ComparisonKind": kind, "Left": ref, "Right": {"Literal": {"Value": f"{value}L"}}}}

    return {
        "name": name,
        "field": mea(measure),
        "type": "Advanced",
        "filter": {"Version": 2, "From": [{"Name": "m", "Entity": M, "Type": 0}],
                   "Where": [{"Condition": {"And": {"Left": cmp(2, low), "Right": cmp(4, high)}}}]},
        "howCreated": "User",
        "isHiddenInViewMode": True,
    }


# ----------------------------------------------------------------- visuais
class Page:
    """Uma página 1920x1080. Os métodos desenham os blocos prontos do relatório."""

    crest: str | None = None  # imagem registrada ao lado do título (só na versão privada)
    footer: str = "Fonte dos Dados"  # medida de texto no rodapé

    def __init__(self, key: str, title: str, page_name: str | None = None):
        self.key = key
        self.title = title
        self.name = page_name or uid("page", key)
        self.visuals: list[dict] = []
        self.filters: list[dict] = []
        self.interactions: list[dict] = []

    # -- infraestrutura
    def add(self, kind: str, x, y, w, h, visual: dict, title: str | None = None,
            filters: list | None = None, vco: dict | None = None) -> str:
        name = uid(self.key, kind, str(len(self.visuals)))
        visual = {"visualType": kind, **visual}
        container_objs = dict(vco or {})
        if title is not None:
            container_objs.setdefault("title", [{"properties": {"show": lit(True), "text": lit(title)}}])
        if container_objs:
            visual["visualContainerObjects"] = container_objs
        visual.setdefault("drillFilterOtherVisuals", True)
        z = len(self.visuals) * 1000
        vc = {
            "$schema": VC_SCHEMA,
            "name": name,
            "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
            "visual": visual,
        }
        if filters:
            vc["filterConfig"] = {"filters": filters}
        self.visuals.append(vc)
        return name

    def no_filter(self, source: str, target: str):
        self.interactions.append({"source": source, "target": target, "type": "NoFilter"})

    # -- blocos prontos
    def header(self, subtitle_measure: str | None = "Título da Página"):
        # faixa azul no topo (caixa de texto vazia com fundo azul)
        self.add("textbox", 0, 0, W, BAND_H, {
            "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": ""}]}]}}]},
        }, vco={"background": [{"properties": {"show": lit(True), "color": color(BLUE),
                                               "transparency": lit(0)}}],
                "border": [{"properties": {"show": lit(False)}}]})
        x_title = LEFT
        if self.crest:  # escudo ao lado do título
            self.add("image", LEFT, 8, 68, 68, {
                "objects": {"general": [{"properties": {"imageUrl": resource(self.crest)}}],
                            "imageScaling": [{"properties": {"imageScalingType": lit("Fit")}}]},
            }, vco=NO_FRAME)
            x_title = LEFT + 80
        self.add("textbox", x_title, 12, 644 - x_title, 60, {
            "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [{
                "value": self.title,
                "textStyle": {"fontFamily": "Segoe UI Bold", "fontSize": "24pt", "color": WHITE},
            }]}]}}]},
        }, vco=NO_FRAME)
        if subtitle_measure:
            self.card(subtitle_measure, 660, 16, 620, 52, size=14, label=False, align_left=True,
                      transparent=True, font=WHITE)
        self.card(self.footer, LEFT, H - 34, W - 2 * LEFT, 28, size=9, label=False,
                  transparent=True, align_left=True, font=GREY)

    def card(self, measure: str, x, y, w, h, size: int = 22, label: bool = True,
             align_left: bool = False, transparent: bool = False, font: str | None = None) -> str:
        labels = {"fontSize": lit(size)}
        if font:
            labels["color"] = color(font)
        objs = {
            "labels": [{"properties": labels}],
            "categoryLabels": [{"properties": {"show": lit(label), "fontSize": lit(10)}}],
        }
        if align_left:
            objs["wordWrap"] = [{"properties": {"show": lit(True)}}]
        vco = {"title": [{"properties": {"show": lit(False)}}]}
        if transparent:
            vco["background"] = [{"properties": {"show": lit(False)}}]
            vco["border"] = [{"properties": {"show": lit(False)}}]
        return self.add("card", x, y, w, h, {"query": query({"Values": [mea(measure)]}), "objects": objs},
                        vco=vco)

    def card_row(self, measures: list[str], y: int, h: int = 112, x0: int = LEFT, width: int | None = None,
                 size: int = 22):
        width = width or (W - 2 * LEFT)
        n = len(measures)
        w = (width - GAP * (n - 1)) // n
        for i, m in enumerate(measures):
            self.card(m, x0 + i * (w + GAP), y, w, h, size=size)

    def slicer(self, table: str, column: str, x, y, w, h, title: str, dropdown: bool = True,
               single: bool = False, default=None, sync: str | None = None) -> str:
        objs = {
            "data": [{"properties": {"mode": lit("Dropdown" if dropdown else "Basic")}}],
            "selection": [{"properties": {"singleSelect": lit(single), "strictSingleSelect": lit(single)}}],
            "header": [{"properties": {"show": lit(True), "text": lit(title)}}],
        }
        if default is not None:
            objs["general"] = [{"properties": {"filter": {"filter": in_filter(table, column, [default])}}}]
        visual = {"query": query({"Values": [col(table, column)]}), "objects": objs}
        if sync:
            visual["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        return self.add("slicer", x, y, w, h, visual,
                        vco={"title": [{"properties": {"show": lit(False)}}]})

    def season_slicer(self, x=W - LEFT - 300, y=12, w=300, h=60):
        return self.slicer("dim_season", "season_label", x, y, w, h, "Temporada", single=True,
                           default=SEASON_NOW, sync="temporada")

    def line(self, x, y, w, h, title, category, values, labels=False, value_axis: dict | None = None,
             sort=None) -> str:
        objs = {
            "lineStyles": [{"properties": {"showMarker": lit(True)}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}],
            "labels": [{"properties": {"show": lit(labels)}}],
            "categoryAxis": [{"properties": {"axisType": lit("Categorical"), "showAxisTitle": lit(False)}}],
        }
        if value_axis:
            objs["valueAxis"] = [{"properties": {k: lit(v) for k, v in value_axis.items()}}]
        return self.add("lineChart", x, y, w, h, {
            "query": query({"Category": [category], "Y": values}, sort=sort),
            "objects": objs,
        }, title=title)

    def columns(self, x, y, w, h, title, category, values, kind="clusteredColumnChart", labels=True,
                value_axis: dict | None = None, filters=None, sort=None, series=None,
                color_measure: str | None = None) -> str:
        objs = {
            "legend": [{"properties": {"show": lit(len(values) > 1 or series is not None), "position": lit("Top")}}],
            "labels": [{"properties": {"show": lit(labels)}}],
            "categoryAxis": [{"properties": {"showAxisTitle": lit(False)}}],
            "valueAxis": [{"properties": {"showAxisTitle": lit(False),
                                          **{k: lit(v) for k, v in (value_axis or {}).items()}}}],
        }
        if color_measure:
            objs["dataPoint"] = [{"properties": {"fill": {"solid": {"color": {"expr": mea(color_measure)}}}},
                                  "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]
        roles = {"Category": [category], "Y": values}
        if series is not None:
            roles["Series"] = [series]
        return self.add(kind, x, y, w, h, {"query": query(roles, sort=sort), "objects": objs},
                        title=title, filters=filters)

    def table(self, x, y, w, h, title, fields, filters=None, sort=None, image_height=None,
              col_colors: dict | None = None, text_size: int = 12, row_padding: int | None = None,
              header_hidden: bool = False, row_back: str | None = None) -> str:
        """Tabela que ocupa o quadro inteiro: as larguras das colunas são calculadas a
        partir da largura do visual (peso `w` de cada campo, ou `px` fixo para fotos)."""
        fields = [f if isinstance(f, F) else F(*f) if isinstance(f, tuple) else F(f) for f in fields]
        header = {"fontSize": lit(text_size), "autoSizeColumnWidth": lit(False)}
        if header_hidden:  # cabeçalho da cor do fundo (para uma coluna só de imagem)
            header.update(backColor=color(WHITE), fontColor=color(WHITE), fontSize=lit(1))
        objs: dict = {"grid": [{"properties": {"textSize": lit(text_size)}}],
                      "columnHeaders": [{"properties": header}],
                      "total": [{"properties": {"totals": lit(False)}}]}
        if row_padding is not None:
            objs["grid"][0]["properties"]["rowPadding"] = lit(row_padding)
        if image_height:
            objs["grid"][0]["properties"]["imageHeight"] = lit(image_height)
        values = [
            {"properties": {"fontColor": {"solid": {"color": {"expr": mea(m)}}}},
             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": ref}}
            for ref, m in (col_colors or {}).items()
        ]
        if row_back:  # cor de fundo da linha inteira vinda de uma medida (ex.: destacar um time)
            values += [
                {"properties": {"backColor": {"solid": {"color": {"expr": mea(row_back)}}}},
                 "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                              "metadata": projection(f[0])["queryRef"]}}
                for f in fields
            ]
        if values:
            objs["values"] = values
        # largura útil: tira margens internas e a barra de rolagem
        free = w - 44 - sum(f.px or 0 for f in fields)
        weights = sum(f.w for f in fields if not f.px) or 1
        objs["columnWidth"] = [
            {"properties": {"value": lit(round(f.px or free * f.w / weights))},
             "selector": {"metadata": projection(f[0])["queryRef"]}}
            for f in fields
        ]
        return self.add("tableEx", x, y, w, h, {"query": query({"Values": fields}, sort=sort), "objects": objs},
                        title=title, filters=filters)

    # -- saída
    def page_json(self) -> dict:
        p = {
            "$schema": PAGE_SCHEMA,
            "name": self.name,
            "displayName": self.title,
            "displayOption": "FitToPage",
            "height": H,
            "width": W,
        }
        if self.filters:
            p["filterConfig"] = {"filters": self.filters}
        if self.interactions:
            p["visualInteractions"] = self.interactions
        return p


# ================================================================== gravação
def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_pages(
    report: Path,
    build: Callable[[str | None], list[Page]],
    resources: dict[str, tuple[Path, str]],
    obsolete: frozenset[str] = frozenset(),
) -> list[Page]:
    """Grava as páginas em `report/definition/pages` e registra os recursos.

    build(nome_da_primeira_página_existente) devolve as páginas; resources é
    {nome_no_relatório: (arquivo, "Image" | "CustomTheme")}. Páginas criadas à mão
    no Power BI (com outros nomes) são mantidas, depois das geradas."""
    pages_dir = report / "definition" / "pages"
    meta_path = pages_dir / "pages.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old_order = meta.get("pageOrder", [])
    pages = build(old_order[0] if old_order else None)
    ours = {p.name for p in pages}

    for page in pages:
        folder = pages_dir / page.name
        if (folder / "visuals").exists():
            shutil.rmtree(folder / "visuals")
        write_json(folder / "page.json", page.page_json())
        for v in page.visuals:
            write_json(folder / "visuals" / v["name"] / "visual.json", v)

    keep = [n for n in old_order if n not in ours and (pages_dir / n).exists()]
    write_json(meta_path, {"$schema": PAGES_SCHEMA, "pageOrder": [p.name for p in pages] + keep,
                           "activePageName": pages[0].name})

    res = report / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True, exist_ok=True)
    for name, (src, _) in resources.items():
        if Path(src).exists():
            shutil.copyfile(src, res / name)
        else:
            print(f"aviso: {Path(src).name} não encontrado")
    rj_path = report / "definition" / "report.json"
    if rj_path.exists():
        rj = json.loads(rj_path.read_text(encoding="utf-8"))
        pkgs = rj.setdefault("resourcePackages", [])
        reg = next((p for p in pkgs if p.get("name") == "RegisteredResources"), None)
        if reg is None:
            reg = {"name": "RegisteredResources", "type": "RegisteredResources", "items": []}
            pkgs.append(reg)
        wanted = {n: t for n, (_, t) in resources.items()}
        theme = next((n for n, t in wanted.items() if t == "CustomTheme"), None)
        drop = set(wanted) | set(obsolete)
        # um relatório só tem um tema personalizado: troca o anterior
        reg["items"] = [i for i in reg["items"]
                        if not (theme and i.get("type") == "CustomTheme") and i.get("name") not in drop]
        reg["items"] += [{"name": n, "path": n, "type": t} for n, t in wanted.items()]
        if theme:
            themes = rj.setdefault("themeCollection", {})
            custom = themes.get("customTheme") or {}
            custom.update({"name": theme, "type": "RegisteredResources"})
            custom.setdefault("reportVersionAtImport",
                              (themes.get("baseTheme") or {}).get("reportVersionAtImport", {}))
            if not custom["reportVersionAtImport"]:
                custom.pop("reportVersionAtImport")
            themes["customTheme"] = custom
        write_json(rj_path, rj)
    return pages
