"""Wikipedia — transferências, estatísticas de jogadores e placares recentes.

Conteúdo sob licença CC BY-SA 4.0: pode ser coletado e reutilizado, desde que
a fonte seja citada e os dados derivados sejam compartilhados pela mesma licença.

Páginas usadas (uma por temporada):
    /wiki/2026–27_Brighton_&_Hove_Albion_F.C._season   transferências, aparições, gols, assistências, cartões
    /wiki/2026–27_Premier_League                       matriz de resultados (completa o openfootball)

O robots.txt da Wikipedia bloqueia /w/ e /api/ para robôs genéricos e libera
/wiki/, então o script lê a página do artigo (que já vem do cache da Wikimedia).
A política de User-Agent da Wikimedia pede um identificador com contato:
configure `http.user_agent` no config.yaml.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from ..http import PoliteSession
from ..transform.teams import canonical_team
from ..transform.utils import classify_fee_gbp, parse_date
from .wikitable import ParsedTable, find_tables, flag_country, link_title, parse_wikitable, player_link

log = logging.getLogger(__name__)

BASE = "https://en.wikipedia.org/wiki/"


def season_title(template: str, season: int) -> str:
    """'{season}–{yy} Premier League' -> '2026–27 Premier League'"""
    return template.format(season=season, yy=str(season + 1)[-2:])


def raw_filename(title: str) -> str:
    """Nome do arquivo bruto salvo para uma página."""
    return re.sub(r"[^\w–.-]+", "_", title) + ".html"


class WikipediaScraper:
    def __init__(self, session: PoliteSession, raw_dir: Path) -> None:
        self.session = session
        self.raw_dir = Path(raw_dir) / "wikipedia"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def url(title: str) -> str:
        return BASE + quote(title.replace(" ", "_"), safe="_(),.'")

    def page(self, title: str, reuse_raw: bool = False, use_cache: bool = True) -> str:
        path = self.raw_dir / raw_filename(title)
        if reuse_raw and path.exists():
            return path.read_text(encoding="utf-8")
        html = self.session.get_text(self.url(title), use_cache=use_cache)
        path.write_text(html, encoding="utf-8")
        return html


# =============================================================================
# Placar: matriz "Results" da página da liga
# =============================================================================
_SCORE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")


def parse_results_matrix(html: str, season: int) -> pd.DataFrame:
    """Matriz mandante x visitante. Células com placar viram partidas; células
    vazias, 'a' (jogo futuro) e '—' (o próprio time) são ignoradas."""
    for _, table in find_tables(html, "Results"):
        first = table.find("tr")
        if not first or "home" not in first.get_text(" ", strip=True).lower():
            continue
        rows = table.find_all("tr")
        away = [canonical_team(link_title(th)) for th in rows[0].find_all("th")[1:]]
        out = []
        for tr in rows[1:]:
            th = tr.find("th")
            if th is None:
                continue
            home = canonical_team(link_title(th))
            for j, td in enumerate(tr.find_all("td")):
                m = _SCORE.match(td.get_text(" ", strip=True).replace("\xa0", " "))
                if m and j < len(away):
                    out.append(
                        {
                            "season": season,
                            "home": home,
                            "away": away[j],
                            "home_goals": int(m.group(1)),
                            "away_goals": int(m.group(2)),
                        }
                    )
        return pd.DataFrame(out)
    log.warning("Matriz de resultados não encontrada para %s", season)
    return pd.DataFrame(columns=["season", "home", "away", "home_goals", "away_goals"])


# =============================================================================
# Página da temporada do clube
# =============================================================================
TRANSFER_SECTIONS = {
    "in": ("Chegada", "Transferência"),
    "out": ("Saída", "Transferência"),
    "loaned in": ("Chegada", "Empréstimo"),
    "loans in": ("Chegada", "Empréstimo"),
    "loaned out": ("Saída", "Empréstimo"),
    "loans out": ("Saída", "Empréstimo"),
    "released / out of contract": ("Saída", "Fim de contrato"),
    "released": ("Saída", "Fim de contrato"),
}


def _window(d) -> str:
    if d is None or pd.isna(d):
        return "Sem data"
    if d.month in (5, 6, 7, 8, 9):
        return "Verão"
    if d.month in (1, 2):
        return "Inverno"
    return "Fora da janela"


def _player(pt: ParsedTable, row) -> tuple[str, str | None]:
    col = pt.find_col("player", "name")
    return player_link(row.cells.get(col)) if col else ("", None)


def player_key(name: str, wiki_id: str | None) -> str:
    """Chave estável: o artigo da Wikipedia; sem artigo, o nome normalizado."""
    from ..transform.utils import normalize_name

    return f"wiki:{wiki_id}" if wiki_id else "name:" + normalize_name(name).replace(" ", "-")


def parse_transfers(html: str, season: int) -> pd.DataFrame:
    rows = []
    for section, table in find_tables(html, *TRANSFER_SECTIONS):
        direction, movement = TRANSFER_SECTIONS[section.lower()]
        pt = parse_wikitable(table)
        c_date = pt.find_col("date")
        c_pos = pt.find_col("pos", "position")
        c_club = pt.find_col(
            "from", "to", "transferred from", "transferred to", "loaned from", "loaned to", "subsequent club"
        )
        c_fee = pt.find_col("fee")
        c_until = pt.find_col("loaned until", "on loan until", "date until")
        c_team = pt.find_col("team")
        c_player = pt.find_col("player", "name")
        for r in pt.rows:
            name, wid = _player(pt, r)
            if not name:
                continue
            fee_text = r.values.get(c_fee, "") if c_fee else ""
            if movement == "Empréstimo" and not fee_text:
                fee_text = "Loan"
            if movement == "Fim de contrato":
                fee_text = fee_text or "Released"
            fee_type, fee_gbp = classify_fee_gbp(fee_text)
            date = parse_date(r.values.get(c_date, "")) if c_date else None
            club = r.values.get(c_club, "") if c_club else ""
            rows.append(
                {
                    "season": season,
                    "date": date,
                    "window": _window(pd.Timestamp(date) if date else None),
                    "direction": direction,
                    "movement": movement,
                    "squad_group": (r.values.get(c_team) if c_team else None) or r.group or "",
                    "player_name": name,
                    "player_key": player_key(name, wid),
                    "position": r.values.get(c_pos, "") if c_pos else "",
                    "nationality": flag_country(r.cells.get(c_player)) if c_player else "",
                    "other_club": "" if club.lower() in {"retired", ""} else club,
                    "retired": club.lower() == "retired",
                    "loan_until": r.values.get(c_until, "") if c_until else "",
                    "fee_text": fee_text,
                    "fee_type": fee_type,
                    "fee_gbp": fee_gbp,
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        log.warning("Nenhuma transferência encontrada na temporada %s", season)
    return df


def _apps(text: str) -> tuple[int | None, int | None, int | None]:
    """(jogos, titular, reserva) a partir de '7+2', '20 (3)' ou '23'."""
    t = (text or "").strip()
    if m := re.fullmatch(r"(\d+)\s*\+\s*(\d+)", t):
        s, sub = int(m.group(1)), int(m.group(2))
        return s + sub, s, sub
    if m := re.fullmatch(r"(\d+)\s*\((\d+)\)", t):
        total, sub = int(m.group(1)), int(m.group(2))
        return total, total - sub, sub
    if re.fullmatch(r"\d+", t):
        return int(t), None, None
    return None, None, None


def _int(text: str | None) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def parse_appearances(html: str, season: int) -> pd.DataFrame:
    tables = find_tables(html, "Appearances and goals", "Appearances", "Squad statistics")
    if not tables:
        log.warning("Tabela de aparições não encontrada na temporada %s", season)
        return pd.DataFrame()
    pt = parse_wikitable(tables[0][1])
    c_no, c_pos, c_nat = pt.find_col("no"), pt.find_col("pos", "position"), pt.find_col("nat", "nation")
    c_pl_apps, c_pl_goals = pt.find_col("premier league|apps"), pt.find_col("premier league|goals")
    c_tot_apps, c_tot_goals = pt.find_col("total|apps"), pt.find_col("total|goals")
    rows = []
    for r in pt.rows:
        name, wid = _player(pt, r)
        if not name:
            continue
        pl_apps, pl_starts, pl_subs = _apps(r.values.get(c_pl_apps, "")) if c_pl_apps else (None, None, None)
        tot_apps, _, _ = _apps(r.values.get(c_tot_apps, "")) if c_tot_apps else (None, None, None)
        group = (r.group or "").lower()
        rows.append(
            {
                "season": season,
                "player_key": player_key(name, wid),
                "player_name": name,
                "shirt_number": _int(r.values.get(c_no)) if c_no else None,
                "position": r.values.get(c_pos, "") if c_pos else "",
                "nationality": flag_country(r.cells.get(c_nat)) if c_nat else "",
                "pl_apps": pl_apps,
                "pl_starts": pl_starts,
                "pl_subs": pl_subs,
                "pl_goals": _int(r.values.get(c_pl_goals)) if c_pl_goals else None,
                "total_apps": tot_apps,
                "total_goals": _int(r.values.get(c_tot_goals)) if c_tot_goals else None,
                "left_during_season": "left" in group or "loan" in group,
            }
        )
    return pd.DataFrame(rows)


def parse_ranking(html: str, season: int, section: str, value: str) -> pd.DataFrame:
    """Tabelas 'Goalscorers' e 'Assists': valor na Premier League e no total."""
    tables = find_tables(html, section)
    if not tables:
        return pd.DataFrame(columns=["season", "player_key", f"pl_{value}", f"total_{value}"])
    pt = parse_wikitable(tables[0][1])
    c_pl, c_tot = pt.find_col("premier league"), pt.find_col("total")
    rows = []
    for r in pt.rows:
        name, wid = _player(pt, r)
        if name:
            rows.append(
                {
                    "season": season,
                    "player_key": player_key(name, wid),
                    f"pl_{value}": _int(r.values.get(c_pl)) if c_pl else None,
                    f"total_{value}": _int(r.values.get(c_tot)) if c_tot else None,
                }
            )
    return pd.DataFrame(rows)


def parse_discipline(html: str, season: int) -> pd.DataFrame:
    tables = find_tables(html, "Disciplinary record")
    cols = ["season", "player_key", "pl_yellow", "pl_second_yellow", "pl_red"]
    if not tables:
        return pd.DataFrame(columns=cols)
    pt = parse_wikitable(tables[0][1])
    c_y = pt.find_col("premier league|yellow card")
    c_yr = pt.find_col("premier league|yellow card yellowred card")
    c_r = pt.find_col("premier league|red card")
    rows = []
    for r in pt.rows:
        name, wid = _player(pt, r)
        if name:
            rows.append(
                {
                    "season": season,
                    "player_key": player_key(name, wid),
                    "pl_yellow": _int(r.values.get(c_y)) if c_y else None,
                    "pl_second_yellow": _int(r.values.get(c_yr)) if c_yr else None,
                    "pl_red": _int(r.values.get(c_r)) if c_r else None,
                }
            )
    return pd.DataFrame(rows, columns=cols)


def parse_player_season(html: str, season: int) -> pd.DataFrame:
    """Junta aparições, gols, assistências e cartões em uma linha por jogador."""
    apps = parse_appearances(html, season)
    if apps.empty:
        return apps
    extras = {
        ("pl_assists", "total_assists"): ("Assists", lambda: parse_ranking(html, season, "Assists", "assists")),
        ("pl_yellow", "pl_second_yellow", "pl_red"): ("Disciplinary record", lambda: parse_discipline(html, season)),
    }
    for cols, (section, parse) in extras.items():
        if find_tables(html, section):
            extra = parse()
            apps = apps.merge(extra.drop(columns="season"), on="player_key", how="left")
            for c in cols:
                # a tabela só lista quem tem pelo menos 1: ausente = 0
                apps[c] = pd.to_numeric(apps[c]).fillna(0).astype("Int64")
        else:
            # temporada sem essa tabela na Wikipedia: fica vazio, não zero
            for c in cols:
                apps[c] = pd.array([pd.NA] * len(apps), dtype="Int64")
    return apps
