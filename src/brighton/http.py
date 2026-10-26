"""Cliente HTTP "educado" usado por todos os scrapers.

Responsabilidades:
- respeitar o robots.txt de cada domínio (configurável)
- limitar a taxa de requisições por domínio (min_delay_seconds)
- repetir requisições com backoff exponencial em erros temporários (429/5xx)
- guardar respostas em cache no disco para não bater no site à toa
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class ScrapeError(RuntimeError):
    """Erro de coleta com mensagem amigável."""


class PoliteSession:
    def __init__(
        self,
        user_agent: str,
        cache_dir: Path,
        min_delay_seconds: float = 3.0,
        max_retries: int = 4,
        timeout_seconds: float = 30,
        cache_hours: float = 12,
        respect_robots_txt: bool = True,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_delay = min_delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout_seconds
        self.cache_seconds = cache_hours * 3600
        self.respect_robots = respect_robots_txt
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    @classmethod
    def from_settings(cls, settings) -> "PoliteSession":
        h = settings.http
        return cls(
            user_agent=h["user_agent"],
            cache_dir=settings.path("cache"),
            min_delay_seconds=float(h.get("min_delay_seconds", 3)),
            max_retries=int(h.get("max_retries", 4)),
            timeout_seconds=float(h.get("timeout_seconds", 30)),
            cache_hours=float(h.get("cache_hours", 12)),
            respect_robots_txt=bool(h.get("respect_robots_txt", True)),
        )

    # ------------------------------------------------------------------ robots
    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                resp = self.session.get(f"{base}/robots.txt", timeout=self.timeout)
                if resp.status_code >= 400:
                    rp = None  # sem robots.txt acessível -> sem restrições declaradas
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[base] = rp
        rp = self._robots[base]
        if rp is None:
            return True
        return rp.can_fetch(self.session.headers["User-Agent"], url)

    # ------------------------------------------------------------- rate limit
    def _wait_turn(self, url: str) -> None:
        domain = urlparse(url).netloc
        last = self._last_hit.get(domain)
        if last is not None:
            # pequena variação aleatória para não bater em intervalos exatos
            wait = self.min_delay + random.uniform(0, 1.0) - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[domain] = time.monotonic()

    # ------------------------------------------------------------------ cache
    def _cache_path(self, url: str, headers: dict | None) -> Path:
        key = url + json.dumps(headers or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(key.encode()).hexdigest() + ".cache")

    def _read_cache(self, path: Path) -> str | None:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_seconds:
            return None
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------- core
    def get_text(self, url: str, headers: dict | None = None, use_cache: bool = True) -> str:
        cache_file = self._cache_path(url, headers)
        if use_cache:
            cached = self._read_cache(cache_file)
            if cached is not None:
                log.debug("cache hit %s", url)
                return cached

        if not self._allowed(url):
            raise ScrapeError(
                f"robots.txt não permite coletar {url}. "
                "Ajuste a fonte ou revise 'respect_robots_txt' no config.yaml com consciência."
            )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_turn(url)
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                log.warning("tentativa %s/%s falhou (%s): %s", attempt, self.max_retries, url, exc)
            else:
                if resp.status_code == 200:
                    cache_file.write_text(resp.text, encoding="utf-8")
                    log.info("GET %s -> 200 (%s KB)", url, len(resp.content) // 1024)
                    return resp.text
                if resp.status_code not in RETRY_STATUS:
                    raise ScrapeError(f"GET {url} retornou HTTP {resp.status_code}")
                last_error = ScrapeError(f"HTTP {resp.status_code}")
                log.warning("tentativa %s/%s: HTTP %s em %s", attempt, self.max_retries, resp.status_code, url)
            time.sleep(min(60, 2 ** attempt + random.uniform(0, 1)))

        raise ScrapeError(f"Falha ao coletar {url} após {self.max_retries} tentativas: {last_error}")

    def get_json(self, url: str, headers: dict | None = None, use_cache: bool = True) -> Any:
        text = self.get_text(url, headers=headers, use_cache=use_cache)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ScrapeError(f"Resposta de {url} não é JSON válido: {text[:200]!r}") from exc
