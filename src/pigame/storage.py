from __future__ import annotations

import json
from pathlib import Path

from .models import (
    ActivityType,
    EquipmentSlot,
    ItemType,
    SaveState,
    default_save,
    zero_stats,
)


DEFAULT_SAVE_PATH = Path("data/save.json")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_save(path: Path = DEFAULT_SAVE_PATH) -> SaveState:
    if not path.exists():
        save = default_save()
        save_state(save, path)
        return save
    state = SaveState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    migrated = migrate_save(state)
    if migrated:
        save_state(state, path)
    return state


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


def migrate_save(state: SaveState) -> bool:
    changed = False

    if not state.character.current_activity:
        state.character.current_activity = ActivityType.DUNGEON.value
        changed = True
    if not state.character.title:
        state.character.title = infer_title(state.character.level)
        changed = True
    if state.character.unspent_stat_points < 0:
        state.character.unspent_stat_points = 0
        changed = True
    if state.character.bosses_defeated < 0:
        state.character.bosses_defeated = 0
        changed = True
    if state.character.loss_streak < 0:
        state.character.loss_streak = 0
        changed = True
    if state.character.known_recipes is None:
        state.character.known_recipes = []
        changed = True
    if not state.world.current_region:
        state.world.current_region = infer_region(state.character.dungeon_depth)
        changed = True
    if not state.world.current_threat:
        state.world.current_threat = "Wandering vermin"
        changed = True
    if state.world.boss_countdown <= 0:
        state.world.boss_countdown = 3
        changed = True
    if state.world.boss_level < 0:
        state.world.boss_level = 0
        changed = True
    if state.world.boss_phase < 0:
        state.world.boss_phase = 0
        changed = True

    for item in state.inventory:
        if item.slot is None:
            inferred_slot = infer_slot(item.item_type)
            if inferred_slot is not None:
                item.slot = inferred_slot
                changed = True
        if item.affixes is None:
            item.affixes = []
            changed = True
        if item.stat_bonuses is None:
            item.stat_bonuses = zero_stats()
            changed = True
        if item.quality < 0:
            item.quality = 0
            changed = True
        if item.tags is None:
            item.tags = []
            changed = True
        if item.recipe_code is None:
            item.recipe_code = ""
            changed = True

    if auto_equip_inventory(state):
        changed = True

    state.inventory = [item for item in state.inventory if item.quantity > 0]
    return changed


def infer_slot(item_type: str) -> str | None:
    if item_type == ItemType.WEAPON.value:
        return EquipmentSlot.MAIN_HAND.value
    if item_type == ItemType.ARMOR.value:
        return EquipmentSlot.BODY.value
    if item_type == ItemType.CHARM.value:
        return EquipmentSlot.CHARM.value
    return None


def infer_title(level: int) -> str:
    if level >= 40:
        return "Endless Ascendant"
    if level >= 25:
        return "Deep Archive Lord"
    if level >= 15:
        return "Blackwell Captain"
    if level >= 8:
        return "Seasoned Delver"
    return "Hatchling Delver"


def infer_region(depth: int) -> str:
    regions = ["Moss Tunnels", "Ash Vault", "Static Hollows", "Moon Well", "Glass Catacomb"]
    return regions[(max(1, depth) // 4) % len(regions)]


def auto_equip_inventory(state: SaveState) -> bool:
    changed = False
    best_by_slot: dict[str, tuple[int, object]] = {}

    for item in state.inventory:
        if item.slot is None:
            continue
        score = (
            item.power
            + item.stat_bonuses.power
            + item.stat_bonuses.vitality
            + item.stat_bonuses.agility
            + item.stat_bonuses.insight
            + item.stat_bonuses.luck
            + item.quality * 3
        )
        current = best_by_slot.get(item.slot)
        if current is None or score > current[0]:
            best_by_slot[item.slot] = (score, item)

    for item in state.inventory:
        should_equip = item.slot is not None and best_by_slot.get(item.slot, (None, None))[1] is item
        if item.equipped != should_equip:
            item.equipped = should_equip
            changed = True

    return changed
