"""Orquestração: coleta -> tratamento -> CSVs para o Power BI.

Uso:
    python -m brighton all                    # coleta tudo e gera os CSVs
    python -m brighton scrape --only wikipedia
    python -m brighton transform              # reprocessa a partir de data/raw (offline)
    python -m brighton all --refresh          # ignora o cache local
    python -m brighton powerbi                # regenera os scripts do Power BI (M, DAX, C#)
    python -m brighton pbip                   # gera/atualiza o projeto powerbi/Brighton.pbip (Power BI FECHADO)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import load_settings
from .http import PoliteSession, ScrapeError
from .powerbi import generate_all
from .scrapers.footballdata import FootballDataScraper
from .scrapers.openfootball import OpenFootballScraper
from .scrapers.wikipedia import WikipediaScraper, season_title
from .transform.model import ModelBuilder

log = logging.getLogger("brighton")
SOURCES = ("openfootball", "wikipedia", "football_data")


def scrape_openfootball(settings, session, refresh: bool) -> None:
    of = OpenFootballScraper(session, settings.path("raw"), settings.league["openfootball_file"])
    for season in settings.all_seasons:
        past = season != settings.current_season and not refresh
        of.season(season, reuse_raw=past, use_cache=not refresh)


def scrape_wikipedia(settings, session, refresh: bool) -> None:
    wk = WikipediaScraper(session, settings.path("raw"))
    for season in settings.all_seasons:
        past = season != settings.current_season and not refresh
        wk.page(season_title(settings.team["wikipedia_season_page"], season), reuse_raw=past, use_cache=not refresh)
    # a matriz de resultados só é necessária onde o openfootball pode estar atrasado
    wk.page(season_title(settings.league["wikipedia_season_page"], settings.current_season), use_cache=not refresh)


def scrape_football_data(settings, session, refresh: bool) -> None:
    fd = FootballDataScraper(session, settings.path("raw"), settings.league.get("football_data_division", "E0"))
    for season in settings.all_seasons:
        past = season != settings.current_season and not refresh
        fd.season_csv(season, reuse_raw=past, use_cache=not refresh)


SCRAPERS = {
    "openfootball": scrape_openfootball,
    "wikipedia": scrape_wikipedia,
    "football_data": scrape_football_data,
}


def run_scrape(settings, only: list[str], refresh: bool) -> list[str]:
    if "SEU_EMAIL_AQUI" in settings.http["user_agent"]:
        log.warning(
            "Configure um contato em http.user_agent (config.yaml): a política de "
            "User-Agent da Wikimedia pede um identificador com e-mail ou URL do projeto."
        )
    session = PoliteSession.from_settings(settings)
    failures = []
    for name in only:
        if name == "football_data" and not settings.source_enabled("football_data"):
            log.info("football_data desligado no config.yaml (sources.football_data); pulando")
            continue
        t0 = time.monotonic()
        log.info("==== coletando %s ====", name)
        try:
            SCRAPERS[name](settings, session, refresh)
            log.info("%s concluído em %.0fs", name, time.monotonic() - t0)
        except ScrapeError as exc:
            # uma fonte fora do ar não derruba as outras
            log.error("%s falhou: %s", name, exc)
            failures.append(name)
    return failures


def run_transform(settings) -> None:
    builder = ModelBuilder(settings)
    builder.build()
    paths = builder.write()
    log.info("%s tabelas gravadas em %s", len(paths), settings.path("processed"))
    run_powerbi(settings)


def run_powerbi(settings) -> None:
    for p in generate_all(settings.path("processed")):
        log.info("artefato do Power BI: %s", p.name)


def run_pbip(settings, data_folder: str | None = None) -> None:
    from .pbip import generate_project

    log.info("Lembrete: o Power BI Desktop precisa estar FECHADO.")
    r = generate_project(settings.path("processed"), data_folder=data_folder)
    m = r["modelo"]
    if m["modo"] == "criado":
        log.info("modelo criado: %s tabelas, %s medidas", len(m["tabelas"]), m["medidas"])
    else:
        med = m["medidas"]
        log.info("modelo sincronizado: %s medidas atualizadas, %s criadas", len(med["atualizadas"]),
                 len(med["criadas"]))
    log.info("%s páginas, %s visuais: %s", len(r["paginas"]), r["visuais"], ", ".join(r["paginas"]))
    log.info("Abra %s no Power BI Desktop e clique em Atualizar.", r["arquivo"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brighton", description="Pipeline de dados do Brighton Dashboard")
    parser.add_argument("command", choices=["scrape", "transform", "all", "powerbi", "pbip"])
    parser.add_argument("--only", default=",".join(SOURCES), help="fontes separadas por vírgula")
    parser.add_argument("--refresh", action="store_true", help="ignora o cache local")
    parser.add_argument("--config", default=None, help="caminho alternativo para o config.yaml")
    parser.add_argument("--pasta", default=None,
                        help="pbip: pasta dos CSVs gravada no parâmetro PastaDados (padrão: data/processed)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = load_settings(args.config)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = set(only) - set(SOURCES)
    if unknown:
        parser.error(f"fontes desconhecidas: {', '.join(sorted(unknown))}")

    failures: list[str] = []
    if args.command in ("scrape", "all"):
        failures = run_scrape(settings, only, args.refresh)
    if args.command in ("transform", "all"):
        run_transform(settings)
    if args.command == "powerbi":
        run_powerbi(settings)
    if args.command == "pbip":
        run_pbip(settings, args.pasta)

    if failures:
        log.warning("Fontes com falha: %s (os CSVs usam o último dado bruto disponível)", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
