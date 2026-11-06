"""Configuration loading and hashing."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def canonical_hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


@dataclass
class Config:
    profile: dict
    assumptions: dict
    seed: int
    out_dir: Path

    @property
    def name(self) -> str:
        return self.profile["profile"]

    @property
    def config_hash(self) -> str:
        return canonical_hash({"profile": self.profile, "assumptions": self.assumptions, "seed": self.seed})


def load_config(profile: str, seed: int = 20261023, out_dir: str | Path | None = None,
                overrides: dict | None = None) -> Config:
    prof_path = Path(profile)
    if not prof_path.exists():
        prof_path = CONFIG_DIR / "profiles" / f"{profile}.yaml"
    prof = _load_yaml(prof_path)
    if overrides:
        prof.update(overrides)
    assumptions = _load_yaml(CONFIG_DIR / "assumptions.yaml")
    out = Path(out_dir) if out_dir else ROOT / "data" / prof["profile"]
    return Config(profile=prof, assumptions=assumptions, seed=int(seed), out_dir=out)
