from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Specialization(str, Enum):
    WANDERER = "wanderer"
    GUARDIAN = "guardian"
    HUNTER = "hunter"
    ALCHEMIST = "alchemist"
    NECROTECH = "necrotech"


class ItemType(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    CHARM = "charm"
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    RECIPE = "recipe"


class EquipmentSlot(str, Enum):
    MAIN_HAND = "main_hand"
    BODY = "body"
    CHARM = "charm"


class ActivityType(str, Enum):
    DUNGEON = "dungeon"
    REST = "rest"
    CAMP = "camp"
    HUNT = "hunt"
    RITUAL = "ritual"
    SALVAGE = "salvage"


@dataclass
class Stats:
    power: int = 5
    vitality: int = 5
    agility: int = 5
    insight: int = 5
    luck: int = 5


def zero_stats() -> Stats:
    return Stats(power=0, vitality=0, agility=0, insight=0, luck=0)


@dataclass
class Item:
    name: str
    item_type: str
    rarity: str
    power: int = 0
    level: int = 1
    quantity: int = 1
    slot: str | None = None
    equipped: bool = False
    affixes: list[str] = field(default_factory=list)
    stat_bonuses: Stats = field(default_factory=zero_stats)
    quality: int = 0
    crafted: bool = False
    tags: list[str] = field(default_factory=list)
    recipe_code: str = ""


@dataclass
class Character:
    name: str
    level: int = 1
    experience: int = 0
    specialization: str = Specialization.WANDERER.value
    stats: Stats = field(default_factory=Stats)
    gold: int = 0
    supplies: int = 3
    dungeon_depth: int = 1
    lifetime_ticks: int = 0
    wins: int = 0
    losses: int = 0
    mood: int = 50
    current_activity: str = ActivityType.DUNGEON.value
    title: str = "Hatchling Delver"
    unspent_stat_points: int = 0
    bosses_defeated: int = 0
    loss_streak: int = 0
    awaiting_player: bool = False
    awaiting_reason: str = ""
    known_recipes: list[str] = field(default_factory=list)


@dataclass
class WorldState:
    biome_tier: int = 1
    danger_rating: int = 1
    ambient_story: str = "A quiet beginning."
    last_event: str = "The creature wakes."
    current_region: str = "Moss Tunnels"
    current_threat: str = "Wandering vermin"
    boss_active: bool = False
    boss_name: str = ""
    boss_level: int = 0
    boss_countdown: int = 3
    boss_phase: int = 0


@dataclass
class DeviceState:
    battery_percent: int | None = None
    battery_voltage: float | None = None
    charging: bool | None = None
    low_power_mode: bool = False
    shutdown_requested: bool = False
    last_shutdown_reason: str = ""


@dataclass
class PartyState:
    peers_seen: list[str] = field(default_factory=list)
    allied_party: list[str] = field(default_factory=list)
    trade_log: list[str] = field(default_factory=list)


@dataclass
class SaveState:
    character: Character
    inventory: list[Item] = field(default_factory=list)
    world: WorldState = field(default_factory=WorldState)
    device: DeviceState = field(default_factory=DeviceState)
    party: PartyState = field(default_factory=PartyState)
    activity_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SaveState":
        character_data = data.get("character", {})
        character = Character(
            name=character_data.get("name", "Piko"),
            level=character_data.get("level", 1),
            experience=character_data.get("experience", 0),
            specialization=character_data.get(
                "specialization", Specialization.WANDERER.value
            ),
            stats=Stats(**character_data.get("stats", {})),
            gold=character_data.get("gold", 0),
            supplies=character_data.get("supplies", 3),
            dungeon_depth=character_data.get("dungeon_depth", 1),
            lifetime_ticks=character_data.get("lifetime_ticks", 0),
            wins=character_data.get("wins", 0),
            losses=character_data.get("losses", 0),
            mood=character_data.get("mood", 50),
            current_activity=character_data.get("current_activity", ActivityType.DUNGEON.value),
            title=character_data.get("title", "Hatchling Delver"),
            unspent_stat_points=character_data.get("unspent_stat_points", 0),
            bosses_defeated=character_data.get("bosses_defeated", 0),
            loss_streak=character_data.get("loss_streak", 0),
            awaiting_player=character_data.get("awaiting_player", False),
            awaiting_reason=character_data.get("awaiting_reason", ""),
            known_recipes=list(character_data.get("known_recipes", [])),
        )

        inventory = []
        for item in data.get("inventory", []):
            item_data = dict(item)
            stat_bonus_data = item_data.get("stat_bonuses")
            if stat_bonus_data:
                item_data["stat_bonuses"] = Stats(**stat_bonus_data)
            else:
                item_data["stat_bonuses"] = zero_stats()
            inventory.append(Item(**item_data))
        world = WorldState(**data.get("world", {}))
        device = DeviceState(**data.get("device", {}))
        party = PartyState(**data.get("party", {}))
        activity_log = list(data.get("activity_log", []))
        return cls(
            character=character,
            inventory=inventory,
            world=world,
            device=device,
            party=party,
            activity_log=activity_log,
        )


def default_save(name: str = "Piko") -> SaveState:
    return SaveState(character=Character(name=name))
