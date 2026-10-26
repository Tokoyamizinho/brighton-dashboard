"""Testes da camada HTTP e da orquestração da coleta, com a rede simulada."""
import json

import pytest

from brighton import pipeline
from brighton.config import load_settings
from brighton.http import PoliteSession, ScrapeError

from conftest import FIXTURES, read_fixture


class FakeResp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text
        self.content = text.encode()


def _session(tmp_path, responses, robots="User-agent: *\nAllow: /"):
    s = PoliteSession("test-agent", tmp_path, min_delay_seconds=0, max_retries=3, cache_hours=1)
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResp(200, robots)
        return responses.pop(0)

    s.session.get = fake_get
    return s, calls


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("brighton.http.time.sleep", lambda *_: None)


def test_retry_then_success_and_cache(tmp_path):
    s, calls = _session(tmp_path, [FakeResp(503), FakeResp(200, '{"ok": 1}')])
    assert s.get_json("https://x.com/a") == {"ok": 1}
    assert calls.count("https://x.com/a") == 2  # 1 falha + 1 sucesso
    assert s.get_json("https://x.com/a") == {"ok": 1}  # do cache, sem rede
    assert calls.count("https://x.com/a") == 2


def test_non_retryable_error_raises(tmp_path):
    s, _ = _session(tmp_path, [FakeResp(404)])
    with pytest.raises(ScrapeError, match="404"):
        s.get_text("https://x.com/missing")


def test_gives_up_after_max_retries(tmp_path):
    s, _ = _session(tmp_path, [FakeResp(429), FakeResp(429), FakeResp(429)])
    with pytest.raises(ScrapeError, match="3 tentativas"):
        s.get_text("https://x.com/busy")


def test_robots_disallow(tmp_path):
    s, calls = _session(tmp_path, [], robots="User-agent: *\nDisallow: /w/")
    with pytest.raises(ScrapeError, match="robots.txt"):
        s.get_text("https://x.com/w/api.php?action=parse")
    assert not any("/w/" in c for c in calls)


def test_wikipedia_robots_rules_allow_article_pages(tmp_path):
    """Com as regras reais da Wikipedia (/w/ e /api/ bloqueados), a página do
    artigo é permitida e a API não."""
    robots = "User-agent: *\nAllow: /w/load.php?\nDisallow: /w/\nDisallow: /api/\nDisallow: /wiki/Special:\n"
    s, _ = _session(tmp_path, [FakeResp(200, "<html></html>")], robots=robots)
    assert s.get_text("https://en.wikipedia.org/wiki/2026%E2%80%9327_Premier_League") == "<html></html>"
    with pytest.raises(ScrapeError, match="robots.txt"):
        s.get_text("https://en.wikipedia.org/w/api.php?action=parse&page=X")


class RecordingSession:
    """Substitui o PoliteSession: responde com os arquivos de teste."""

    def __init__(self):
        self.urls = []

    def get_json(self, url, headers=None, use_cache=True):
        self.urls.append(url)
        season = "2026-27" if "2026-27" in url else "2025-26"
        return json.loads(read_fixture(f"openfootball_en1_{season}.json"))

    def get_text(self, url, headers=None, use_cache=True):
        self.urls.append(url)
        if "football-data" in url:
            return read_fixture("football_data_sample.csv")
        if "Premier_League" in url:
            return read_fixture("wiki_pl_2026-27_results.html")
        return read_fixture("wiki_bha_2026-27.html")


def _settings(raw_project, tmp_path):
    _, cfg = raw_project
    settings = load_settings(cfg)
    settings.raw["paths"]["raw"] = str(tmp_path / "out_raw")  # não sobrescreve as fixtures
    return settings


def test_scrape_orchestration(raw_project, tmp_path, monkeypatch):
    settings = _settings(raw_project, tmp_path)
    fake = RecordingSession()
    monkeypatch.setattr(pipeline.PoliteSession, "from_settings", classmethod(lambda cls, s: fake))

    failures = pipeline.run_scrape(settings, list(pipeline.SOURCES), refresh=False)
    assert failures == []
    assert any(u.endswith("/2025-26/en.1.json") for u in fake.urls)
    assert any(u.endswith("/2026-27/en.1.json") for u in fake.urls)
    assert any("/wiki/2025%E2%80%9326_Brighton_%26_Hove_Albion_F.C._season" in u for u in fake.urls)
    # a matriz da liga só é baixada para a temporada atual
    assert [u for u in fake.urls if "Premier_League" in u] == [
        "https://en.wikipedia.org/wiki/2026%E2%80%9327_Premier_League"
    ]
    # nunca usa a API bloqueada pelo robots.txt
    assert not any("/w/api.php" in u for u in fake.urls)
    # football-data está desligado por padrão
    assert not any("football-data" in u for u in fake.urls)
    assert (tmp_path / "out_raw" / "openfootball" / "2026-27_en.1.json").exists()

    # segunda execução: temporada passada não é baixada de novo
    fake.urls.clear()
    pipeline.run_scrape(settings, list(pipeline.SOURCES), refresh=False)
    assert not any("2025-26" in u or "2025%E2%80%9326" in u for u in fake.urls)
    assert any("2026-27" in u for u in fake.urls)


def test_football_data_only_when_enabled(raw_project_with_fd, tmp_path, monkeypatch):
    settings = _settings(raw_project_with_fd, tmp_path)
    fake = RecordingSession()
    monkeypatch.setattr(pipeline.PoliteSession, "from_settings", classmethod(lambda cls, s: fake))
    pipeline.run_scrape(settings, ["football_data"], refresh=False)
    assert "https://www.football-data.co.uk/mmz4281/2627/E0.csv" in fake.urls
    assert (tmp_path / "out_raw" / "football_data" / "E0_2627.csv").exists()
