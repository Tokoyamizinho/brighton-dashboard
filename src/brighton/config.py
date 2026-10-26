"""Leitura do config.yaml e resolução de caminhos do projeto."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]

    # --- temporadas -------------------------------------------------------
    @property
    def current_season(self) -> int:
        return int(self.raw["seasons"]["current"])

    @property
    def all_seasons(self) -> list[int]:
        hist = [int(s) for s in self.raw["seasons"].get("history", [])]
        return sorted(set(hist + [self.current_season]))

    # --- time / liga / fontes / http -----------------------------------------
    @property
    def team(self) -> dict[str, Any]:
        return self.raw["team"]

    @property
    def league(self) -> dict[str, Any]:
        return self.raw["league"]

    def source_enabled(self, name: str) -> bool:
        return bool((self.raw.get("sources") or {}).get(name, False))

    @property
    def http(self) -> dict[str, Any]:
        return self.raw["http"]

    # --- caminhos -----------------------------------------------------------
    def path(self, key: str) -> Path:
        p = PROJECT_ROOT / self.raw["paths"][key]
        p.mkdir(parents=True, exist_ok=True)
        return p


def season_label(season: int) -> str:
    """2026 -> '2026/27'"""
    return f"{season}/{str(season + 1)[-2:]}"


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    with open(path, encoding="utf-8") as fh:
        return Settings(yaml.safe_load(fh))
