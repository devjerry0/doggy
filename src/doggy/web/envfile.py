from __future__ import annotations

import json
from pathlib import Path

from doggy.core.config import TunableSettings


def write_env(tunable: TunableSettings, path: Path = Path(".env")) -> None:
    """Persist the tunable settings into .env in place: update existing keys,
    append missing ones, and preserve comments and non-tunable (structural) keys.
    """
    def _fmt(v: object) -> str:
        if isinstance(v, (str, int, float, bool)) or isinstance(v, Path):
            return str(v)
        return json.dumps(v)   # lists/tuples -> JSON so pydantic-settings can re-parse
    updates = {f"DOGGY_{k.upper()}": _fmt(v) for k, v in tunable.model_dump().items()}
    lines: list[str] = []
    seen: set[str] = set()
    if path.exists():
        for raw in path.read_text().splitlines():
            stripped = raw.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(raw)
    for key, val in updates.items():
        if key not in seen:
            lines.append(f"{key}={val}")
    path.write_text("\n".join(lines) + "\n")


# Backwards-compatible alias: the private name is what tests import.
_write_env = write_env
