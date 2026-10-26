"""Constrói o modelo estrela (fatos + dimensões) que o Power BI vai consumir.

Lê SOMENTE os arquivos brutos salvos em data/raw/ (nada de rede aqui), o que
permite reprocessar quantas vezes quiser e testar sem internet.

Saída em data/processed/*.csv:

    dim_season, dim_team, dim_player, dim_date
    fact_team_match      1 linha por time por jogo (todos os 20 times)
    fact_standings       classificação de cada time após cada rodada
    fact_fixtures        calendário do Brighton na temporada atual, com dificuldade
    fact_player_season   jogos, gols, assistências e cartões por jogador/temporada
    fact_transfers       chegadas e saídas por janela
    meta_refresh         quando cada fonte foi atualizada e até que data vão os dados

Licença dos dados derivados: CC BY-SA 4.0 (por usar conteúdo da Wikipedia).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ..config import Settings, season_label
from ..powerbi import infer_pq_types
from ..scrapers import footballdata as fd_p
from ..scrapers import openfootball as of_p
from ..scrapers import wikipedia as wk_p
from .standings import final_table, standings_by_round
from .teams import canonical_team, team_id

log = logging.getLogger(__name__)

RESULT_PT = {"W": "V", "D": "E", "L": "D"}
RESULT_LABEL = {"W": "Vitória", "D": "Empate", "L": "Derrota"}
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

POSITION_GROUP = {
    "GK": "Goleiro",
    **dict.fromkeys(["DF", "CB", "RB", "LB", "RWB", "LWB", "SW", "FB", "WB"], "Defensor"),
    **dict.fromkeys(["MF", "DM", "CM", "CAM", "AM", "LM", "RM", "CDM"], "Meio-campo"),
    **dict.fromkeys(["FW", "CF", "ST", "LW", "RW", "SS", "W"], "Atacante"),
}

STAT_COLUMNS = ("shots", "shots_on_target", "corners", "fouls", "yellow", "red")

UK = ZoneInfo("Europe/London")
BRT = ZoneInfo("America/Sao_Paulo")
MATCH_LENGTH = timedelta(hours=2)  # do apito inicial ao final, com intervalo e acréscimos


def position_group(code: str | None) -> str | None:
    return POSITION_GROUP.get(str(code or "").strip().upper())


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _read_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


class ModelBuilder:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.raw = settings.path("raw")
        self.team_name = canonical_team(settings.team["name"])
        self.brighton_id = team_id(self.team_name)
        self.tables: dict[str, pd.DataFrame] = {}
        # data de referência para "próximo jogo" (pode ser fixada nos testes)
        self.today = datetime.now(BRT).date()
        self._now: datetime | None = None

    @property
    def now(self) -> datetime:
        """Agora, no horário de Brasília (sem fuso). Se só `today` foi fixado (testes),
        vale o início desse dia."""
        if self._now is not None:
            return self._now
        real = datetime.now(BRT).replace(tzinfo=None)
        return real if real.date() == self.today else datetime.combine(self.today, time())

    @now.setter
    def now(self, value: datetime) -> None:
        self._now = value
        self.today = value.date()

    # ---------------------------------------------------------- arquivos brutos
    def _openfootball(self, season: int):
        f = f"{of_p.season_folder(season)}_{self.s.league['openfootball_file']}"
        return _read_json(self.raw / "openfootball" / f)

    def _wiki(self, template: str, season: int) -> str | None:
        title = wk_p.season_title(template, season)
        return _read_text(self.raw / "wikipedia" / wk_p.raw_filename(title))

    def _football_data(self, season: int) -> str | None:
        div = self.s.league.get("football_data_division", "E0")
        return _read_text(self.raw / "football_data" / f"{div}_{fd_p.season_code(season)}.csv")

    # =============================================================== partidas
    def _season_matches(self, season: int) -> pd.DataFrame:
        data = self._openfootball(season)
        if data is None:
            log.warning("Sem arquivo do openfootball para %s (rode o scraping)", season)
            return pd.DataFrame()
        m = of_p.parse_matches(data, season)

        # 1) Wikipedia completa placares que o openfootball ainda não tem
        html = self._wiki(self.s.league["wikipedia_season_page"], season)
        if html:
            wk = wk_p.parse_results_matrix(html, season)
            if not wk.empty:
                m = m.merge(wk.drop(columns="season"), on=["home", "away"], how="left", suffixes=("", "_wk"))
                both = m["home_goals"].notna() & m["home_goals_wk"].notna()
                diff = both & ((m["home_goals"] != m["home_goals_wk"]) | (m["away_goals"] != m["away_goals_wk"]))
                if diff.any():
                    log.warning("%s placares divergem entre openfootball e Wikipedia em %s", int(diff.sum()), season)
                fill = m["home_goals"].isna() & m["home_goals_wk"].notna()
                m.loc[fill, "home_goals"] = m.loc[fill, "home_goals_wk"]
                m.loc[fill, "away_goals"] = m.loc[fill, "away_goals_wk"]
                m.loc[fill, "score_source"] = "wikipedia"
                m = m.drop(columns=["home_goals_wk", "away_goals_wk"])
                missing = set(zip(wk["home"], wk["away"])) - set(zip(m["home"], m["away"]))
                if missing:
                    log.warning("%s jogos da Wikipedia sem correspondente no calendário: %s", len(missing), sorted(missing)[:3])

        # 2) football-data (opcional): estatísticas e, se faltar, o placar
        if self.s.source_enabled("football_data"):
            text = self._football_data(season)
            if text:
                fd = fd_p.parse_csv(text, season).drop(columns=["season", "date"])
                m = m.merge(fd, on=["home", "away"], how="left", suffixes=("", "_fd"))
                for c in ("home_goals", "away_goals", "ht_home_goals", "ht_away_goals"):
                    if f"{c}_fd" in m.columns:
                        fill = m[c].isna() & m[f"{c}_fd"].notna()
                        m.loc[fill, c] = m.loc[fill, f"{c}_fd"]
                        if c == "home_goals":
                            m.loc[fill, "score_source"] = "football-data"
                        m = m.drop(columns=f"{c}_fd")
        return m

    def build_matches(self) -> None:
        seasons = [self._season_matches(s) for s in self.s.all_seasons]
        seasons = [s for s in seasons if not s.empty]
        if not seasons:
            raise FileNotFoundError("Nenhum dado de partidas em data/raw. Rode: python -m brighton scrape")
        matches = pd.concat(seasons, ignore_index=True)
        matches["kickoff_uk"] = pd.to_datetime(
            matches["date"].dt.strftime("%Y-%m-%d") + " " + matches["time"].fillna("15:00"), errors="coerce"
        )
        self._matches = matches

        played = matches[matches["home_goals"].notna()].copy()
        sides = []
        for side, opp in (("home", "away"), ("away", "home")):
            t = pd.DataFrame(
                {
                    "season": played["season"],
                    "match_id": played["season"].astype(str) + "-" + played["home"].map(team_id) + "-" + played["away"].map(team_id),
                    "matchday": played["matchday"],
                    "datetime": played["kickoff_uk"],
                    "team": played[side],
                    "opponent": played[opp],
                    "home_away": "h" if side == "home" else "a",
                    "goals_for": played[f"{side}_goals"].astype(int),
                    "goals_against": played[f"{opp}_goals"].astype(int),
                    "ht_goals_for": played[f"ht_{side}_goals"],
                    "ht_goals_against": played[f"ht_{opp}_goals"],
                    "score_source": played["score_source"],
                }
            )
            # estatísticas do football-data (opcional): as colunas existem sempre,
            # vazias quando a fonte está desligada, para as medidas DAX não quebrarem
            for stat in STAT_COLUMNS:
                if f"{side}_{stat}" in played.columns:
                    t[f"{stat}_for"] = played[f"{side}_{stat}"].astype("Int64")
                    t[f"{stat}_against"] = played[f"{opp}_{stat}"].astype("Int64")
                else:
                    t[f"{stat}_for"] = pd.array([pd.NA] * len(played), dtype="Int64")
                    t[f"{stat}_against"] = pd.array([pd.NA] * len(played), dtype="Int64")
            t["referee"] = played["referee"] if "referee" in played.columns else None
            sides.append(t)
        tm = pd.concat(sides, ignore_index=True)

        tm["team_id"] = tm["team"].map(team_id)
        tm["opponent_id"] = tm["opponent"].map(team_id)
        tm["date"] = tm["datetime"].dt.date
        diff = tm["goals_for"] - tm["goals_against"]
        tm["result"] = diff.map(lambda d: "W" if d > 0 else ("D" if d == 0 else "L"))
        tm["result_pt"] = tm["result"].map(RESULT_PT)
        tm["result_label"] = tm["result"].map(RESULT_LABEL)
        tm["pts"] = tm["result"].map({"W": 3, "D": 1, "L": 0})
        tm["goal_diff"] = diff
        tm["is_home"] = tm["home_away"].eq("h")
        tm["venue"] = tm["is_home"].map({True: "Casa", False: "Fora"})
        tm["clean_sheet"] = tm["goals_against"].eq(0)
        tm["failed_to_score"] = tm["goals_for"].eq(0)

        # situação no intervalo e pontos conquistados no 2º tempo
        ht = tm["ht_goals_for"].astype("Float64") - tm["ht_goals_against"].astype("Float64")
        tm["ht_state"] = ht.map(
            lambda d: None if pd.isna(d) else ("Vencendo" if d > 0 else ("Empatando" if d == 0 else "Perdendo"))
        )
        ht_pts = ht.map(lambda d: None if pd.isna(d) else (3 if d > 0 else (1 if d == 0 else 0)))
        tm["points_vs_halftime"] = tm["pts"] - pd.to_numeric(ht_pts)
        tm["second_half_goals_for"] = tm["goals_for"] - tm["ht_goals_for"].astype("Float64")
        tm["second_half_goals_against"] = tm["goals_against"] - tm["ht_goals_against"].astype("Float64")

        tm = tm.sort_values(["season", "team_id", "datetime"]).reset_index(drop=True)
        tm["round"] = tm.groupby(["season", "team_id"]).cumcount() + 1
        tm["is_brighton"] = tm["team_id"].eq(self.brighton_id)
        tm["season_label"] = tm["season"].map(season_label)
        tm["match_label"] = tm["datetime"].dt.strftime("%d/%m") + " " + tm["venue"].str[0] + " x " + tm["opponent"]
        self.tables["fact_team_match"] = tm

        teams = sorted(set(tm["team"]) | set(matches["home"]) | set(matches["away"]))
        self.tables["dim_team"] = pd.DataFrame(
            {"team_id": [team_id(t) for t in teams], "team_name": teams, "is_brighton": [team_id(t) == self.brighton_id for t in teams]}
        )

        st = standings_by_round(tm)
        self._final = final_table(st)
        # classificação atual: a última linha de cada time, reclassificada (com jogos
        # adiados os times não têm o mesmo número de partidas)
        latest = self._final.set_index(["season", "team_id", "round"])["final_position"]
        key = pd.MultiIndex.from_frame(st[["season", "team_id", "round"]])
        st["table_position"] = pd.array(latest.reindex(key).to_numpy(), dtype="Int64")
        st["is_latest"] = st["table_position"].notna()
        self.tables["fact_standings"] = st

    # ============================================================= calendário
    def build_fixtures(self) -> None:
        season = self.s.current_season
        m = self._matches[self._matches["season"] == season]
        b = m[(m["home"] == self.team_name) | (m["away"] == self.team_name)].copy()
        if b.empty:
            self.tables["fact_fixtures"] = pd.DataFrame()
            return
        home = b["home"] == self.team_name
        fx = pd.DataFrame(
            {
                "season": season,
                "matchday": b["matchday"],
                "kickoff_uk": b["kickoff_uk"],
                "home_away": home.map({True: "h", False: "a"}),
                "opponent": b["away"].where(home, b["home"]),
                "goals_for": b["home_goals"].where(home, b["away_goals"]),
                "goals_against": b["away_goals"].where(home, b["home_goals"]),
            }
        ).sort_values("kickoff_uk").reset_index(drop=True)
        fx["opponent_id"] = fx["opponent"].map(team_id)
        fx["venue"] = fx["home_away"].map({"h": "Casa", "a": "Fora"})
        fx["finished"] = fx["goals_for"].notna()
        fx["date"] = fx["kickoff_uk"].dt.date
        fx["kickoff_brasilia"] = fx["kickoff_uk"].map(
            lambda d: d.replace(tzinfo=UK).astimezone(BRT).replace(tzinfo=None) if pd.notna(d) else None
        )

        # força do adversário hoje (posição e pontos por jogo na temporada atual)
        st = self.tables["fact_standings"]
        cur = st[st["season"] == season]
        now = cur.loc[cur.groupby("team_id")["round"].idxmax(), ["team_id", "position", "ppg_cum"]]
        fx = fx.merge(
            now.rename(columns={"team_id": "opponent_id", "position": "opponent_position_now", "ppg_cum": "opponent_ppg_now"}),
            on="opponent_id",
            how="left",
        )
        # dificuldade própria (1 fácil a 5 difícil) pela posição atual do adversário
        fx["difficulty"] = pd.cut(
            fx["opponent_position_now"], bins=[0, 4, 8, 12, 16, 20], labels=[5, 4, 3, 2, 1]
        ).astype("Int64")

        fx["fixture_number"] = range(1, len(fx) + 1)
        # jogo sem placar que já terminou (início + 2h) = resultado ainda não publicado
        # nas fontes; "próximo jogo" é o primeiro que ainda não terminou
        over = pd.to_datetime(fx["kickoff_brasilia"]) + pd.Timedelta(MATCH_LENGTH) <= pd.Timestamp(self.now)
        fx["result_pending"] = ~fx["finished"] & over
        upcoming = fx.index[~fx["finished"] & ~fx["result_pending"]]
        fx["is_next"] = False
        if len(upcoming):
            fx.loc[upcoming[0], "is_next"] = True
        fx["next_n"] = pd.array([pd.NA] * len(fx), dtype="Int64")
        fx.loc[upcoming, "next_n"] = list(range(1, len(upcoming) + 1))
        res = (fx["goals_for"] - fx["goals_against"]).astype("Float64")
        fx["result_pt"] = res.map(lambda d: None if pd.isna(d) else ("V" if d > 0 else ("E" if d == 0 else "D")))
        self.tables["fact_fixtures"] = fx

    # ======================================================== jogadores / mercado
    def build_wikipedia_club(self) -> None:
        players, transfers = [], []
        tmpl = self.s.team["wikipedia_season_page"]
        for season in self.s.all_seasons:
            html = self._wiki(tmpl, season)
            if html is None:
                log.warning("Sem página da Wikipedia do clube para %s", season)
                continue
            players.append(wk_p.parse_player_season(html, season))
            transfers.append(wk_p.parse_transfers(html, season))

        ps = pd.concat([p for p in players if not p.empty], ignore_index=True) if any(not p.empty for p in players) else pd.DataFrame()
        if not ps.empty:
            ps["season_label"] = ps["season"].map(season_label)
            ps["position_group"] = ps["position"].map(position_group)
            ps["pl_goal_contributions"] = ps["pl_goals"].astype("Int64") + ps["pl_assists"]
        self.tables["fact_player_season"] = ps

        tr = pd.concat([t for t in transfers if not t.empty], ignore_index=True) if any(not t.empty for t in transfers) else pd.DataFrame()
        if not tr.empty:
            tr["season_label"] = tr["season"].map(season_label)
            tr["position_group"] = tr["position"].map(position_group)
            tr["fee_gbp_signed"] = tr["fee_gbp"].astype("Float64") * tr["direction"].map({"Chegada": -1, "Saída": 1})
            tr["is_first_team"] = ~tr["squad_group"].str.lower().str.contains("academy|u21|under|u23|youth", regex=True)
        self.tables["fact_transfers"] = tr

    def build_dim_player(self) -> None:
        frames = []
        for name, cols in (
            ("fact_player_season", ["player_key", "player_name", "position", "nationality", "season"]),
            ("fact_transfers", ["player_key", "player_name", "position", "nationality", "season"]),
        ):
            t = self.tables.get(name, pd.DataFrame())
            if not t.empty:
                frames.append(t[cols])
        if not frames:
            self.tables["dim_player"] = pd.DataFrame(columns=["player_key", "player_name"])
            return
        allp = pd.concat(frames, ignore_index=True).sort_values("season")
        allp = allp.replace({"position": {"": None}, "nationality": {"": None}})
        # o registro mais recente com valor preenchido ganha
        dim = allp.groupby("player_key").agg(
            player_name=("player_name", "last"),
            position=("position", lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
            nationality=("nationality", lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
            first_season=("season", "min"),
            last_season=("season", "max"),
        ).reset_index()
        dim["position_group"] = dim["position"].map(position_group)
        dim["wikipedia_url"] = dim["player_key"].map(
            lambda k: "https://en.wikipedia.org/wiki/" + k[5:] if k.startswith("wiki:") else None
        )
        ps = self.tables.get("fact_player_season", pd.DataFrame())
        played_keys = set(ps["player_key"]) if not ps.empty else set()
        dim["played_for_club"] = dim["player_key"].isin(played_keys)
        self.tables["dim_player"] = dim

    # ========================================================== dimensões
    def build_dims(self) -> None:
        fin = self._final[self._final["team_id"] == self.brighton_id].set_index("season")
        tm = self.tables["fact_team_match"]
        rows = []
        for s in self.s.all_seasons:
            bt = tm[(tm["season"] == s) & (tm["team_id"] == self.brighton_id)]
            rows.append(
                {
                    "season": s,
                    "season_label": season_label(s),
                    "is_current": s == self.s.current_season,
                    "brighton_matches_played": int(len(bt)),
                    "brighton_final_position": int(fin.loc[s, "final_position"]) if s in fin.index else None,
                    "brighton_points": int(fin.loc[s, "pts_cum"]) if s in fin.index else None,
                    "data_until": bt["date"].max() if not bt.empty else None,
                }
            )
        self.tables["dim_season"] = pd.DataFrame(rows)

        start = pd.Timestamp(f"{min(self.s.all_seasons)}-07-01")
        end = pd.Timestamp(f"{self.s.current_season + 1}-06-30")
        d = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
        d["year"] = d["date"].dt.year
        d["month"] = d["date"].dt.month
        d["month_name"] = d["month"].map(lambda m: MONTHS_PT[m - 1])
        d["month_year"] = d["month_name"] + "/" + d["date"].dt.strftime("%y")
        d["weekday"] = d["date"].dt.weekday.map(lambda w: WEEKDAYS_PT[w])
        d["season"] = d["date"].apply(lambda x: x.year if x.month >= 7 else x.year - 1)
        d["season_label"] = d["season"].map(season_label)
        d["date"] = d["date"].dt.date
        self.tables["dim_date"] = d

    def build_meta(self) -> None:
        rows = []
        tm = self.tables["fact_team_match"]
        for src in ("openfootball", "wikipedia", "football_data"):
            files = list((self.raw / src).rglob("*.*"))
            if not files:
                continue
            newest = max(f.stat().st_mtime for f in files)
            label = {"openfootball": "openfootball", "wikipedia": "wikipedia", "football_data": "football-data"}[src]
            last_score = tm.loc[tm["score_source"] == label, "date"]
            rows.append(
                {
                    "source": src,
                    "files": len(files),
                    "last_refresh_utc": datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "last_result_date": last_score.max() if not last_score.empty else None,
                }
            )
        rows.append(
            {
                "source": "pipeline",
                "files": None,
                "last_refresh_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "last_result_date": tm["date"].max(),
            }
        )
        self.tables["meta_refresh"] = pd.DataFrame(rows)

    # ================================================================ run
    def build(self) -> dict[str, pd.DataFrame]:
        self.build_matches()
        self.build_fixtures()
        self.build_wikipedia_club()
        self.build_dim_player()
        self.build_dims()
        self.build_meta()
        return self.tables

    def write(self, out_dir: Path | None = None) -> list[Path]:
        out = Path(out_dir) if out_dir else self.s.path("processed")
        out.mkdir(parents=True, exist_ok=True)
        written = []
        schema = {}
        for name, df in sorted(self.tables.items()):
            if df is None:
                continue
            schema[name] = infer_pq_types(df)
            df = df.copy()
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
            path = out / f"{name}.csv"
            # separador vírgula + ponto decimal; no Power BI importe com cultura en-US
            df.to_csv(path, index=False, encoding="utf-8")
            written.append(path)
            log.info("%-22s %6d linhas", name, len(df))
        (out / "_schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "LICENSE-DATA.md").write_text(DATA_LICENSE, encoding="utf-8")
        return written


DATA_LICENSE = """# Licença dos dados processados

Estes CSVs combinam:

- **openfootball / football.json** (domínio público): resultados e calendário da Premier League.
- **Wikipedia** (CC BY-SA 4.0): placares recentes, transferências e estatísticas de jogadores,
  extraídos das páginas "<temporada> Brighton & Hove Albion F.C. season" e "<temporada> Premier League".
- **football-data.co.uk** (opcional, apenas se ativado no config.yaml): estatísticas por jogo.

Por incluírem conteúdo da Wikipedia, os dados derivados são distribuídos sob a mesma licença,
**Creative Commons Attribution-ShareAlike 4.0** (https://creativecommons.org/licenses/by-sa/4.0/).
Atribuição: "Dados: Wikipedia (CC BY-SA 4.0) e openfootball (domínio público)".

O código do projeto tem licença própria (ver LICENSE na raiz).
"""
