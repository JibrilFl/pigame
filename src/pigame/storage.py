from __future__ import annotations

import json
from pathlib import Path

from .models import SaveState, default_save


DEFAULT_SAVE_PATH = Path("data/save.json")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_save(path: Path = DEFAULT_SAVE_PATH) -> SaveState:
    if not path.exists():
        save = default_save()
        save_state(save, path)
        return save
    return SaveState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(state: SaveState, path: Path = DEFAULT_SAVE_PATH) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_new_save(name: str, path: Path = DEFAULT_SAVE_PATH) -> SaveState:
    save = default_save(name)
    save_state(save, path)
    return save
