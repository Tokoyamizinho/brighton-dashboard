"""Leitura genérica de tabelas `wikitable` da Wikipedia.

As tabelas das páginas de temporada mudam de um ano para outro: nomes de
coluna diferentes ("Pos" / "Pos." / "Position", "From" / "Transferred from"),
cabeçalhos em duas linhas, células mescladas (rowspan/colspan), linhas de
agrupamento ("First team", "Academy", "Goalkeepers") e linhas de total.
Este módulo resolve isso uma vez só:

1. expande rowspan/colspan em uma grade retangular;
2. monta o nome de cada coluna juntando as linhas de cabeçalho
   ("Premier League|Apps");
3. devolve cada linha de dados com o grupo atual e as células originais
   (para extrair links e bandeiras).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

_NOISE = "sup.reference, sup, style, .mw-editsection, .sortkey, .reference"


def clean_text(cell: Tag | None) -> str:
    """Texto visível da célula; se não houver texto, usa o `alt` das imagens."""
    if cell is None:
        return ""
    c = copy.copy(cell)
    for el in c.select(_NOISE):
        el.decompose()
    text = c.get_text(" ", strip=True).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = " ".join(img.get("alt", "") for img in c.find_all("img")).strip()
    return text


def norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9|+ ]", "", text.lower()).strip()


@dataclass
class Row:
    values: dict[str, str]
    cells: dict[str, Tag]
    group: str | None = None
    raw: list[str] = field(default_factory=list)


@dataclass
class ParsedTable:
    columns: list[str]
    rows: list[Row]

    def find_col(self, *candidates: str) -> str | None:
        """Primeira coluna cujo nome normalizado bate com algum candidato
        (igualdade, ou prefixo quando o candidato termina em '*')."""
        normed = {c: norm_header(c) for c in self.columns}
        for cand in candidates:
            prefix = cand.endswith("*")
            key = norm_header(cand.rstrip("*"))
            for col, n in normed.items():
                if (prefix and n.startswith(key)) or n == key:
                    return col
        return None


def _expand(table: Tag) -> list[list[tuple[Tag, bool]]]:
    """Grade com (célula, é_cabeçalho), repetindo células mescladas."""
    body = table.find("tbody") or table
    trs = [tr for tr in body.find_all("tr", recursive=False)]
    grid: list[list[tuple[Tag, bool] | None]] = []
    pending: dict[tuple[int, int], tuple[Tag, bool]] = {}
    for r, tr in enumerate(trs):
        row: list[tuple[Tag, bool] | None] = []
        col = 0
        cells = tr.find_all(["td", "th"], recursive=False)
        ci = 0
        while ci < len(cells) or (r, col) in pending:
            if (r, col) in pending:
                row.append(pending.pop((r, col)))
                col += 1
                continue
            cell = cells[ci]
            ci += 1
            try:
                rs = max(1, int(cell.get("rowspan", 1)))
                cs = max(1, int(cell.get("colspan", 1)))
            except ValueError:
                rs, cs = 1, 1
            item = (cell, cell.name == "th")
            for k in range(cs):
                row.append(item)
                for dr in range(1, rs):
                    pending[(r + dr, col + k)] = item
            col += cs
        grid.append(row)
    return grid


def parse_wikitable(table: Tag) -> ParsedTable:
    grid = _expand(table)
    if not grid:
        return ParsedTable([], [])

    # linhas de cabeçalho: as primeiras compostas só de <th>
    header_rows = []
    for row in grid:
        if row and all(is_th for _, is_th in row) and len({id(c) for c, _ in row}) > 1:
            header_rows.append(row)
        else:
            break
    ncols = max(len(r) for r in grid)

    columns = []
    for j in range(ncols):
        parts = []
        for hr in header_rows:
            if j < len(hr):
                t = clean_text(hr[j][0])
                if t and (not parts or parts[-1] != t):
                    parts.append(t)
        name = "|".join(parts) or f"col{j}"
        while name in columns:  # nomes repetidos ganham sufixo
            name += "_"
        columns.append(name)

    rows: list[Row] = []
    group = None
    for row in grid[len(header_rows):]:
        if not row:
            continue
        has_td = any(not is_th for _, is_th in row)
        distinct = {id(c) for c, _ in row}
        if not has_td:
            if len(distinct) == 1:  # uma única célula ocupando a linha toda
                group = clean_text(row[0][0]) or group
            # demais linhas só de <th> são totais ou cabeçalho repetido
            continue
        values, cells = {}, {}
        for j, (cell, _) in enumerate(row[:ncols]):
            values[columns[j]] = clean_text(cell)
            cells[columns[j]] = cell
        rows.append(Row(values=values, cells=cells, group=group, raw=list(values.values())))
    return ParsedTable(columns, rows)


# ------------------------------------------------------------------ seções
def iter_sections(html: str):
    """Percorre a página em ordem e devolve (título_da_seção, tabela) para cada
    wikitable, usando o último título h2/h3/h4 visto antes dela."""
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one(".mw-parser-output") or soup
    current = ""

    def wanted(el: Tag) -> bool:
        if not isinstance(el, Tag):
            return False
        if el.name in ("h2", "h3", "h4"):
            return True
        return el.name == "table" and "wikitable" in (el.get("class") or [])

    for el in root.find_all(wanted):
        if el.name in ("h2", "h3", "h4"):
            current = clean_text(el)
            continue
        if el.find_parent("table") is not None:
            continue  # tabela aninhada
        yield current, el


def find_tables(html: str, *titles: str) -> list[tuple[str, Tag]]:
    keys = {t.lower() for t in titles}
    return [(s, t) for s, t in iter_sections(html) if s.lower() in keys]


# ------------------------------------------------------------------ células
_WIKI_HREF = re.compile(r"^(?:https?://[a-z-]+\.wikipedia\.org)?/wiki/([^?#]+)")


def player_link(cell: Tag | None) -> tuple[str, str | None]:
    """(nome, id_wiki) do jogador. Ignora os links de bandeira/federação."""
    if cell is None:
        return "", None
    for a in cell.find_all("a", href=True):
        if a.find_parent(class_="flagicon") or a.find("img") or not a.get_text(strip=True):
            continue
        # a API devolve "/wiki/Nome"; a página do artigo, "https://en.wikipedia.org/wiki/Nome"
        m = _WIKI_HREF.match(a["href"])
        if m and ":" not in unquote(m.group(1)):
            return a.get_text(" ", strip=True), unquote(m.group(1))
    # jogador sem artigo na Wikipedia: só texto
    c = copy.copy(cell)
    for f in c.select(".flagicon, sup"):
        f.decompose()
    return c.get_text(" ", strip=True).replace("\xa0", " ").strip(), None


def flag_country(cell: Tag | None) -> str:
    if cell is None:
        return ""
    img = cell.select_one(".flagicon img")
    return img.get("alt", "") if img else ""


def link_title(cell: Tag | None) -> str:
    """Título do artigo linkado (ex.: 'Brighton & Hove Albion F.C.')."""
    if cell is None:
        return ""
    for a in cell.find_all("a", href=True):
        if a.find_parent(class_="flagicon"):
            continue
        return a.get("title") or a.get_text(strip=True)
    return clean_text(cell)
