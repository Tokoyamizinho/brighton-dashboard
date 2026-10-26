"""Aplica o medidas.yaml direto nos arquivos TMDL de um projeto .pbip.

Alternativa ao script do Tabular Editor quando o relatório está salvo como
projeto (.pbip): com o Power BI Desktop FECHADO, este módulo

* atualiza a expressão, o formato, a pasta, a descrição e a categoria de dados
  das medidas que mudaram no YAML (mantendo o lineageTag e as anotações);
* cria as medidas novas;
* marca as colunas com URL de imagem (dataCategory: ImageUrl).

Medidas que existem só no Power BI (criadas à mão) não são tocadas.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_LEVEL1 = re.compile(r"^\t[^\t]")
_MEASURE = re.compile(r"^\tmeasure (?P<name>'(?:[^']|'')+'|[^ =]+) =(?P<rest>.*)$")


def _unquote(token: str) -> str:
    return token[1:-1].replace("''", "'") if token.startswith("'") else token


def _quote(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _norm(expr: str) -> str:
    return "\n".join(line.strip() for line in expr.strip().splitlines() if line.strip())


@dataclass
class _Block:
    start: int  # primeira linha (inclui a descrição ///)
    end: int  # depois da última linha útil
    header: str  # nome como está no arquivo (com aspas, se houver)
    name: str
    desc: list[str]
    expr: str
    props: list[str] = field(default_factory=list)  # linhas de nível 2 (sem a expressão)
    raw_expr: bool = False  # expressão com ``` (não mexemos)


def _parse_measures(lines: list[str]) -> list[_Block]:
    blocks = []
    i = 0
    while i < len(lines):
        m = _MEASURE.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        while start > 0 and lines[start - 1].startswith("\t///"):
            start -= 1
        desc = [ln[4:].lstrip(" ") if ln.startswith("\t/// ") else ln[4:] for ln in lines[start:i]]
        # o bloco vai até o próximo elemento de nível 1 (outra medida, ///, partition...)
        j = i + 1
        while j < len(lines) and not _LEVEL1.match(lines[j]) and (lines[j].startswith("\t") or not lines[j].strip()):
            j += 1
        end = j
        while end > i + 1 and lines[end - 1].strip() == "":
            end -= 1
        body = lines[i + 1 : end]
        rest = m.group("rest").strip()
        raw = rest.startswith("```")
        if rest and not raw:
            expr_lines, props = [rest], body
        else:
            k = 0
            while k < len(body):
                blank_inside = not body[k].strip() and k + 1 < len(body) and body[k + 1].startswith("\t\t\t")
                if not (body[k].startswith("\t\t\t") or blank_inside):
                    break
                if body[k].strip() == "```":
                    raw = True
                k += 1
            expr_lines, props = [ln[3:] for ln in body[:k]], body[k:]
        blocks.append(
            _Block(start, end, m.group("name"), _unquote(m.group("name")), desc, "\n".join(expr_lines), props, raw)
        )
        i = end
    return blocks


def _prop(props: list[str], key: str) -> str | None:
    for p in props:
        if p.startswith(f"\t\t{key}:"):
            return p.split(":", 1)[1].strip()
    return None


def _render(header: str, spec: dict, props: list[str]) -> list[str]:
    out = [f"\t/// {d}" for d in str(spec.get("description") or "").strip().splitlines() if d.strip()]
    expr = spec["expr"].strip()
    if "\n" in expr:
        out.append(f"\tmeasure {header} =")
        out += [f"\t\t\t{ln}" if ln.strip() else "" for ln in expr.splitlines()]
    else:
        out.append(f"\tmeasure {header} = {expr}")
    known = {"formatString", "displayFolder", "lineageTag", "dataCategory"}
    lineage = _prop(props, "lineageTag") or str(uuid.uuid4())
    if spec.get("format"):
        out.append(f"\t\tformatString: {spec['format']}")
    if spec.get("folder"):
        out.append(f"\t\tdisplayFolder: {spec['folder']}")
    out.append(f"\t\tlineageTag: {lineage}")
    if spec.get("data_category"):
        out.append(f"\t\tdataCategory: {spec['data_category']}")
    others = [p for p in props if p.strip() and p.strip().split(":", 1)[0].split(" ")[0] not in known]
    if others:
        out.append("")
        out += others
    return out


def _differs(b: _Block, spec: dict) -> bool:
    return (
        _norm(b.expr) != _norm(spec["expr"])
        or (_prop(b.props, "formatString") or "") != (spec.get("format") or "")
        or (_prop(b.props, "displayFolder") or "") != (spec.get("folder") or "")
        or (_prop(b.props, "dataCategory") or "") != (spec.get("data_category") or "")
        or " ".join(b.desc).strip() != " ".join(str(spec.get("description") or "").split()).strip()
    )


def sync_measures(path: Path, spec: dict) -> dict[str, list[str]]:
    """Atualiza o arquivo TMDL da tabela de medidas. Devolve o que mudou."""
    path = Path(path)
    text = path.read_bytes().decode("utf-8")  # sem converter \r\n
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    blocks = _parse_measures(lines)
    by_name = {b.name: b for b in blocks}
    report: dict[str, list[str]] = {"atualizadas": [], "criadas": [], "ignoradas": []}

    # de baixo para cima, para os índices continuarem válidos
    for b in sorted(blocks, key=lambda x: x.start, reverse=True):
        sp = next((m for m in spec["measures"] if m["name"] == b.name), None)
        if sp is None or not _differs(b, sp):
            continue
        if b.raw_expr:
            report["ignoradas"].append(b.name)
            continue
        lines[b.start : b.end] = _render(b.header, sp, b.props)
        report["atualizadas"].append(b.name)

    new = [m for m in spec["measures"] if m["name"] not in by_name]
    if new:
        blocks = _parse_measures(lines)
        at = blocks[-1].end if blocks else next(i for i, ln in enumerate(lines) if _LEVEL1.match(ln))
        chunk: list[str] = []
        for m in new:
            chunk += [""] + _render(_quote(m["name"]), m, [])
            report["criadas"].append(m["name"])
        lines[at:at] = chunk
    report["atualizadas"].reverse()
    if report["atualizadas"] or report["criadas"]:
        path.write_bytes(nl.join(lines).encode("utf-8"))
    return report


def set_image_columns(tables_dir: Path, refs: list[str]) -> list[str]:
    """Marca colunas como URL de imagem (ex.: 'dim_player.photo_url')."""
    changed = []
    for ref in refs:
        table, column = ref.split(".", 1)
        f = Path(tables_dir) / f"{table}.tmdl"
        if not f.exists():
            continue
        text = f.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        head = re.compile(rf"^\tcolumn (?:'{re.escape(column)}'|{re.escape(column)})\s*(=.*)?$")
        idx = next((i for i, ln in enumerate(lines) if head.match(ln)), None)
        if idx is None:
            continue
        j = idx + 1
        while j < len(lines) and not _LEVEL1.match(lines[j]):
            j += 1
        props = range(idx + 1, j)
        cat = next((i for i in props if lines[i].startswith("\t\tdataCategory:")), None)
        if cat is not None:
            if lines[cat].split(":", 1)[1].strip() == "ImageUrl":
                continue
            lines[cat] = "\t\tdataCategory: ImageUrl"
        else:
            after = next((i for i in props if lines[i].startswith("\t\tlineageTag:")), idx)
            lines.insert(after + 1, "\t\tdataCategory: ImageUrl")
        f.write_bytes(nl.join(lines).encode("utf-8"))
        changed.append(ref)
    return changed


# ------------------------------------------------------------ tabelas (CSV)
_TMDL_TYPES = {
    "Int64.Type": ("int64", ["\t\tformatString: 0"]),
    "type number": ("double", []),
    "type text": ("string", []),
    "type logical": ("boolean", ['\t\tformatString: """TRUE"";""TRUE"";""FALSE"""']),
    "type date": ("dateTime", ["\t\tformatString: Short Date"]),
    "type datetime": ("dateTime", ["\t\tformatString: General Date"]),
}


def _partition_m(table: str, cols: dict[str, str]) -> list[str]:
    pairs = ",\n".join(f'        {{"{c}", {t}}}' for c, t in cols.items())
    return ["let", f'    Fonte = fnCsv("{table}", {{', *pairs.split("\n"), "    })", "in", "    Fonte"]


def _column_block(name: str, pq_type: str) -> list[str]:
    dtype, extra = _TMDL_TYPES.get(pq_type, ("string", []))
    out = [f"\tcolumn {_quote(name) if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) else name}",
           f"\t\tdataType: {dtype}", *extra, f"\t\tlineageTag: {uuid.uuid4()}", "\t\tsummarizeBy: none",
           f"\t\tsourceColumn: {name}", "", "\t\tannotation SummarizationSetBy = Automatic"]
    if pq_type == "type date":
        out.append("")
        out.append("\t\tannotation UnderlyingDateTimeDataType = Date")
    return out + [""]


def sync_table_schema(tables_dir: Path, table: str, cols: dict[str, str]) -> dict[str, object]:
    """Deixa a tabela do modelo igual ao CSV: colunas novas e a lista de tipos do
    Power Query (partição). Colunas que sumiram do CSV não são apagadas."""
    f = Path(tables_dir) / f"{table}.tmdl"
    rep: dict[str, object] = {"colunas_novas": [], "consulta_atualizada": False}
    if not f.exists():
        return rep
    text = f.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    part = next((i for i, ln in enumerate(lines) if re.match(rf"^\tpartition .+ = m\s*$", ln)), None)
    if part is None:
        return rep

    # partição: as linhas da expressão vêm depois de "source =", com 4 tabs
    src = next((i for i in range(part + 1, len(lines)) if lines[i].strip() == "source ="), None)
    if src is not None:
        end = src + 1
        while end < len(lines) and (lines[end].startswith("\t\t\t") or (
                not lines[end].strip() and end + 1 < len(lines) and lines[end + 1].startswith("\t\t\t"))):
            end += 1
        old = [ln.strip() for ln in lines[src + 1 : end] if ln.strip()]
        new = _partition_m(table, cols)
        if old != [ln.strip() for ln in new]:
            lines[src + 1 : end] = ["\t\t\t\t" + ln for ln in new]
            rep["consulta_atualizada"] = True

    existing = {_unquote(m.group(1)) for ln in lines
                if (m := re.match(r"^\tcolumn ('(?:[^']|'')+'|[^ =]+)", ln))}
    missing = [c for c in cols if c not in existing]
    if missing:
        block: list[str] = []
        for c in missing:
            block += _column_block(c, cols[c])
        lines[part:part] = block
        rep["colunas_novas"] = missing
    if rep["colunas_novas"] or rep["consulta_atualizada"]:
        f.write_bytes(nl.join(lines).encode("utf-8"))
    return rep
