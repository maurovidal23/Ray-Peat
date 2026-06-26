from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

KNOWLEDGE_RELATIVE_PATH = Path("data") / "knowledge" / "ray_peat_rules.yaml"


def default_knowledge_path() -> Path:
    env_path = os.getenv("PEAT_KNOWLEDGE_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path.cwd() / KNOWLEDGE_RELATIVE_PATH,
            Path(__file__).resolve().parents[2] / KNOWLEDGE_RELATIVE_PATH,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path(KNOWLEDGE_RELATIVE_PATH)


@lru_cache(maxsize=4)
def load_knowledge_base(path: str | Path | None = None) -> dict[str, Any]:
    resolved_path = Path(path) if path is not None else default_knowledge_path()
    with resolved_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"Invalid knowledge base file: {resolved_path}")
    return data
