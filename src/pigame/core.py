from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Item, ItemType, SaveState, Specialization


RARITY_TABLE = [
    ("common", 0),
    ("uncommon", 2),
    ("rare", 4),
    ("epic", 7),
    ("mythic", 11),
]

WEAPON_NAMES = ["Bone Spear", "Rust Saber", "Echo Bow", "Static Claw", "Moon Pike"]
ARMOR_NAMES = ["Thread Mail", "Ash Coat", "Moss Plate", "Dust Mantle", "Gloom Vest"]
CHARM_NAMES = ["Charm of Sparks", "Lucky Fang", "Void Coin", "Root Sigil", "Mist Eye"]
MATERIAL_NAMES = ["Slime Core", "Iron Husk", "Old Rune", "Glow Dust", "Night Resin"]
CONSUMABLE_NAMES = ["Bitter Tonic", "Smoke Fruit", "Repair Gel", "Amber Tea"]


@dataclass
class TickResult:
    summary: str
    leveled_up: bool
    loot: list[Item]


class GameEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def tick(self, state: SaveState) -> TickResult:
        character = state.character
        character.lifetime_ticks += 1

        action_roll = self.rng.random()
        if action_roll < 0.15:
            summary = self._rest(state)
            loot: list[Item] = []
        elif action_roll < 0.85:
            summary, loot = self._dungeon_run(state)
        else:
            summary, loot = self._camp_action(state)

        leveled_up = self._apply_leveling(state)
        self._trim_logs(state)
        return TickResult(summary=summary, leveled_up=leveled_up, loot=loot)

    def _rest(self, state: SaveState) -> str:
        character = state.character
        character.mood = min(100, character.mood + 6)
        state.world.last_event = f"{character.name} rested and stabilized."
        state.activity_log.append(state.world.last_event)
        return state.world.last_event

    def _camp_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        character.supplies += 1
        character.gold += 2 + character.level
        character.mood = min(100, character.mood + 2)
        self._maybe_unlock_specialization(state)
        state.world.last_event = f"{character.name} prepared camp and gathered supplies."
        state.activity_log.append(state.world.last_event)
        return state.world.last_event, []

    def _dungeon_run(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        enemy_level = max(1, character.level + character.dungeon_depth // 3)
        enemy_power = enemy_level * 5 + state.world.danger_rating * 3
        hero_power = self._hero_power(state)
        variance = self.rng.randint(-6, 6)
        score = hero_power + variance - enemy_power

        if character.supplies > 0:
            character.supplies -= 1

        if score >= 0:
            character.wins += 1
            character.experience += 10 + enemy_level * 4
            character.gold += 4 + enemy_level * 2
            character.dungeon_depth += 1
            character.mood = min(100, character.mood + 3)
            state.world.danger_rating = min(9999, state.world.danger_rating + 1)
            state.world.biome_tier = 1 + character.dungeon_depth // 10
            loot = self._generate_loot(character.level, enemy_level)
            state.inventory.extend(loot)
            summary = (
                f"{character.name} cleared depth {character.dungeon_depth - 1} "
                f"and defeated a level {enemy_level} foe."
            )
        else:
            character.losses += 1
            character.experience += 3 + enemy_level
            character.mood = max(5, character.mood - 5)
            character.dungeon_depth = max(1, character.dungeon_depth - 1)
            loot = []
            summary = (
                f"{character.name} retreated from the dungeon after a hard fight "
                f"against a level {enemy_level} foe."
            )

        state.world.ambient_story = self._story_text(state, score)
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

    def _hero_power(self, state: SaveState) -> int:
        character = state.character
        stats = character.stats
        base = (
            stats.power * 2
            + stats.vitality * 2
            + stats.agility
            + stats.insight
            + stats.luck
            + character.level * 4
        )
        gear = sum(item.power * item.quantity for item in state.inventory if item.item_type != ItemType.MATERIAL.value)
        specialization_bonus = {
            Specialization.WANDERER.value: 2,
            Specialization.GUARDIAN.value: 6,
            Specialization.HUNTER.value: 5,
            Specialization.ALCHEMIST.value: 4,
            Specialization.NECROTECH.value: 7,
        }.get(character.specialization, 0)
        return base + gear + specialization_bonus

    def _generate_loot(self, hero_level: int, enemy_level: int) -> list[Item]:
        count = 1 if self.rng.random() < 0.75 else 2
        loot: list[Item] = []
        for _ in range(count):
            rarity, bonus = self._roll_rarity()
            item_type = self.rng.choice(
                [
                    ItemType.WEAPON.value,
                    ItemType.ARMOR.value,
                    ItemType.CHARM.value,
                    ItemType.CONSUMABLE.value,
                    ItemType.MATERIAL.value,
                ]
            )
            level = max(1, (hero_level + enemy_level) // 2)
            power = max(0, level + bonus + self.rng.randint(0, 3))
            if item_type == ItemType.WEAPON.value:
                name = self.rng.choice(WEAPON_NAMES)
            elif item_type == ItemType.ARMOR.value:
                name = self.rng.choice(ARMOR_NAMES)
            elif item_type == ItemType.CHARM.value:
                name = self.rng.choice(CHARM_NAMES)
            elif item_type == ItemType.CONSUMABLE.value:
                name = self.rng.choice(CONSUMABLE_NAMES)
                power = 0
            else:
                name = self.rng.choice(MATERIAL_NAMES)
                power = 0
            loot.append(
                Item(
                    name=name,
                    item_type=item_type,
                    rarity=rarity,
                    power=power,
                    level=level,
                    quantity=1,
                )
            )
        return loot

    def _roll_rarity(self) -> tuple[str, int]:
        roll = self.rng.random()
        if roll < 0.50:
            return RARITY_TABLE[0]
        if roll < 0.78:
            return RARITY_TABLE[1]
        if roll < 0.92:
            return RARITY_TABLE[2]
        if roll < 0.985:
            return RARITY_TABLE[3]
        return RARITY_TABLE[4]

    def _apply_leveling(self, state: SaveState) -> bool:
        character = state.character
        threshold = 20 + character.level * 15
        leveled_up = False
        while character.experience >= threshold:
            character.experience -= threshold
            character.level += 1
            character.stats.power += 1
            character.stats.vitality += 1
            if character.level % 2 == 0:
                character.stats.agility += 1
            if character.level % 3 == 0:
                character.stats.insight += 1
            if character.level % 5 == 0:
                character.stats.luck += 1
            character.supplies += 1
            leveled_up = True
            threshold = 20 + character.level * 15
        if leveled_up:
            self._maybe_unlock_specialization(state)
        return leveled_up

    def _maybe_unlock_specialization(self, state: SaveState) -> None:
        character = state.character
        if character.level < 5:
            return
        if character.specialization != Specialization.WANDERER.value:
            return
        if character.stats.vitality >= 9:
            character.specialization = Specialization.GUARDIAN.value
        elif character.stats.agility >= 9:
            character.specialization = Specialization.HUNTER.value
        elif character.stats.insight >= 9 and character.supplies >= 4:
            character.specialization = Specialization.ALCHEMIST.value
        elif character.stats.insight >= 9 and character.stats.luck >= 7:
            character.specialization = Specialization.NECROTECH.value

    def _story_text(self, state: SaveState, score: int) -> str:
        character = state.character
        if score >= 8:
            return f"{character.name} moved like a legend through the ruins."
        if score >= 0:
            return f"{character.name} pushed forward despite the rising danger."
        return f"{character.name} sensed the dungeon turning hostile."

    def ai_brief(self, state: SaveState) -> str:
        character = state.character
        pressure = state.world.danger_rating - character.level
        if pressure >= 8:
            return "Threat is outpacing growth. Focus on recovery and gear quality."
        if character.supplies <= 1:
            return "Supplies are low. The creature should favor camp actions soon."
        if character.specialization == Specialization.WANDERER.value and character.level >= 5:
            return "Core traits are mature enough to branch into a specialization."
        if len(state.party.allied_party) >= 2:
            return "Squad potential is rising. Cooperative dungeon bonuses should be added next."
        return "Progression is stable. Keep the idle loop running."

    def _trim_logs(self, state: SaveState) -> None:
        state.activity_log = state.activity_log[-20:]
        state.party.trade_log = state.party.trade_log[-20:]
