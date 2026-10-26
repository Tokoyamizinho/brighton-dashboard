"""Fixtures de teste: monta um data/raw usando arquivos REAIS das fontes
(openfootball e trechos da Wikipedia, ver tests/fixtures/NOTICE.md) para
testar o pipeline inteiro sem internet."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from brighton.scrapers.wikipedia import raw_filename

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parents[1]


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def raw_project(tmp_path: Path):
    """Projeto temporário com config.yaml e data/raw preenchidos.

    Temporadas: 2026 (atual) e 2025. A página do Brighton de 2025–26 usa o
    trecho real de 2022–23, que tem o layout antigo das tabelas (bom para
    testar a robustez do parser).
    """
    raw = tmp_path / "raw"
    of = raw / "openfootball"
    wk = raw / "wikipedia"
    fdd = raw / "football_data"
    for d in (of, wk, fdd):
        d.mkdir(parents=True)

    shutil.copy(FIXTURES / "openfootball_en1_2026-27.json", of / "2026-27_en.1.json")
    shutil.copy(FIXTURES / "openfootball_en1_2025-26.json", of / "2025-26_en.1.json")
    (wk / raw_filename("2026–27 Brighton & Hove Albion F.C. season")).write_text(read_fixture("wiki_bha_2026-27.html"), encoding="utf-8")
    (wk / raw_filename("2025–26 Brighton & Hove Albion F.C. season")).write_text(read_fixture("wiki_bha_2022-23.html"), encoding="utf-8")
    (wk / raw_filename("2026–27 Premier League")).write_text(read_fixture("wiki_pl_2026-27_results.html"), encoding="utf-8")
    shutil.copy(FIXTURES / "football_data_sample.csv", fdd / "E0_2627.csv")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["seasons"] = {"current": 2026, "history": [2025]}
    cfg["paths"] = {"raw": str(raw), "processed": str(tmp_path / "processed"), "cache": str(tmp_path / "cache")}
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return tmp_path, cfg_path


@pytest.fixture()
def raw_project_with_fd(raw_project):
    """Mesmo projeto com a fonte opcional football-data ligada."""
    tmp, cfg_path = raw_project
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["sources"] = {"football_data": True}
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return tmp, cfg_path
