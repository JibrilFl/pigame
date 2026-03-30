from __future__ import annotations

import random
from dataclasses import dataclass

from .models import (
    ActivityType,
    EquipmentSlot,
    Item,
    ItemType,
    SaveState,
    Specialization,
    Stats,
    zero_stats,
)


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
REGION_NAMES = ["Moss Tunnels", "Ash Vault", "Static Hollows", "Moon Well", "Glass Catacomb"]
THREAT_NAMES = ["Wandering vermin", "Apex brood", "Mirror cult", "Rift scavengers", "Bone machine"]

PREFIXES = [
    ("Savage", Stats(power=2, vitality=0, agility=0, insight=0, luck=0)),
    ("Ward", Stats(power=0, vitality=2, agility=0, insight=0, luck=0)),
    ("Swift", Stats(power=0, vitality=0, agility=2, insight=0, luck=0)),
    ("Sage", Stats(power=0, vitality=0, agility=0, insight=2, luck=0)),
    ("Lucky", Stats(power=0, vitality=0, agility=0, insight=0, luck=2)),
]

SUFFIXES = [
    ("of Hunger", Stats(power=1, vitality=0, agility=1, insight=0, luck=0)),
    ("of Shells", Stats(power=0, vitality=2, agility=0, insight=0, luck=0)),
    ("of Sparks", Stats(power=0, vitality=0, agility=1, insight=1, luck=0)),
    ("of Echoes", Stats(power=0, vitality=0, agility=0, insight=2, luck=0)),
    ("of Fortune", Stats(power=0, vitality=0, agility=0, insight=0, luck=2)),
]

SPECIALIZATION_BONUSES = {
    Specialization.WANDERER.value: Stats(power=1, vitality=1, agility=1, insight=1, luck=1),
    Specialization.GUARDIAN.value: Stats(power=2, vitality=4, agility=0, insight=0, luck=0),
    Specialization.HUNTER.value: Stats(power=3, vitality=0, agility=3, insight=0, luck=1),
    Specialization.ALCHEMIST.value: Stats(power=0, vitality=1, agility=0, insight=4, luck=1),
    Specialization.NECROTECH.value: Stats(power=2, vitality=1, agility=0, insight=3, luck=1),
}


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

        activity = self._choose_activity(state)
        character.current_activity = activity

        if activity == ActivityType.REST.value:
            summary, loot = self._rest(state), []
        elif activity == ActivityType.CAMP.value:
            summary, loot = self._camp_action(state)
        elif activity == ActivityType.HUNT.value:
            summary, loot = self._hunt_action(state)
        elif activity == ActivityType.RITUAL.value:
            summary, loot = self._ritual_action(state)
        elif activity == ActivityType.SALVAGE.value:
            summary, loot = self._salvage_action(state)
        else:
            summary, loot = self._dungeon_run(state)

        self._auto_equip(state, loot)
        self._consume_when_needed(state)
        leveled_up = self._apply_leveling(state)
        self._update_world(state)
        self._trim_logs(state)
        return TickResult(summary=summary, leveled_up=leveled_up, loot=loot)

    def _choose_activity(self, state: SaveState) -> str:
        character = state.character
        roll = self.rng.random()
        if character.mood < 25 or character.supplies <= 0:
            return ActivityType.REST.value if roll < 0.55 else ActivityType.CAMP.value
        if character.specialization == Specialization.ALCHEMIST.value and character.supplies < 3 and roll < 0.30:
            return ActivityType.HUNT.value
        if character.specialization == Specialization.NECROTECH.value and roll < 0.20:
            return ActivityType.RITUAL.value
        if len([item for item in state.inventory if item.item_type == ItemType.MATERIAL.value]) >= 4 and roll < 0.15:
            return ActivityType.SALVAGE.value
        if roll < 0.10:
            return ActivityType.REST.value
        if roll < 0.22:
            return ActivityType.CAMP.value
        if roll < 0.33:
            return ActivityType.HUNT.value
        return ActivityType.DUNGEON.value

    def _rest(self, state: SaveState) -> str:
        character = state.character
        character.mood = min(100, character.mood + 8)
        character.supplies += 1
        state.world.last_event = f"{character.name} rested, ate lightly, and regained focus."
        state.activity_log.append(state.world.last_event)
        return state.world.last_event

    def _camp_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        gold_gain = 2 + character.level + (1 if character.specialization == Specialization.ALCHEMIST.value else 0)
        character.supplies += 1
        character.gold += gold_gain
        character.mood = min(100, character.mood + 3)
        self._maybe_unlock_specialization(state)
        summary = f"{character.name} maintained camp, sorted gear, and recovered {gold_gain} value in supplies."
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, []

    def _hunt_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        gains = 2 + self.rng.randint(0, 2) + character.level // 4
        character.supplies += gains
        character.experience += 4 + character.level
        character.mood = min(100, character.mood + 1)
        loot = [self._make_item("Field Ration", ItemType.CONSUMABLE.value, "common", 0, character.level)]
        summary = f"{character.name} hunted through {state.world.current_region} and secured {gains} supplies."
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

    def _ritual_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        bonus = 5 + character.level
        character.experience += bonus
        character.mood = max(5, character.mood - 1)
        character.stats.insight += 1 if self.rng.random() < 0.25 else 0
        summary = f"{character.name} performed a field ritual and extracted {bonus} arcane experience."
        state.world.last_event = summary
        state.activity_log.append(summary)
        loot: list[Item] = []
        if self.rng.random() < 0.45:
            loot.append(self._generate_loot(character.level, character.level + 1, forced_type=ItemType.CHARM.value)[0])
        return summary, loot

    def _salvage_action(self, state: SaveState) -> tuple[str, list[Item]]:
        materials = [item for item in state.inventory if item.item_type == ItemType.MATERIAL.value and item.quantity > 0]
        summary = f"{state.character.name} found nothing worth reforging."
        loot: list[Item] = []
        if materials:
            spent = materials[0]
            spent.quantity -= 1
            state.character.gold += 3 + state.character.level
            state.character.experience += 6
            loot = self._generate_loot(state.character.level, state.character.level + 2, forced_type=self.rng.choice([
                ItemType.WEAPON.value,
                ItemType.ARMOR.value,
                ItemType.CHARM.value,
            ]))
            summary = f"{state.character.name} reforged {spent.name} into fresh equipment."
        state.inventory = [item for item in state.inventory if item.quantity > 0]
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

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
                f"and broke through a level {enemy_level} threat."
            )
        else:
            character.losses += 1
            character.experience += 3 + enemy_level
            character.mood = max(5, character.mood - 5)
            character.dungeon_depth = max(1, character.dungeon_depth - 1)
            loot = []
            summary = (
                f"{character.name} retreated from {state.world.current_region} after a hard fight "
                f"with a level {enemy_level} threat."
            )

        state.world.ambient_story = self._story_text(state, score)
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

    def _hero_power(self, state: SaveState) -> int:
        character = state.character
        stats = self._total_stats(state)
        base = (
            stats.power * 2
            + stats.vitality * 2
            + stats.agility
            + stats.insight
            + stats.luck
            + character.level * 4
        )
        gear = sum(item.power for item in state.inventory if item.equipped)
        specialization = SPECIALIZATION_BONUSES.get(character.specialization, zero_stats())
        specialization_score = (
            specialization.power
            + specialization.vitality
            + specialization.agility
            + specialization.insight
            + specialization.luck
        )
        return base + gear + specialization_score

    def _total_stats(self, state: SaveState) -> Stats:
        total = Stats(
            power=state.character.stats.power,
            vitality=state.character.stats.vitality,
            agility=state.character.stats.agility,
            insight=state.character.stats.insight,
            luck=state.character.stats.luck,
        )
        specialization = SPECIALIZATION_BONUSES.get(state.character.specialization, zero_stats())
        total.power += specialization.power
        total.vitality += specialization.vitality
        total.agility += specialization.agility
        total.insight += specialization.insight
        total.luck += specialization.luck
        for item in state.inventory:
            if not item.equipped:
                continue
            total.power += item.stat_bonuses.power
            total.vitality += item.stat_bonuses.vitality
            total.agility += item.stat_bonuses.agility
            total.insight += item.stat_bonuses.insight
            total.luck += item.stat_bonuses.luck
        return total

    def _generate_loot(self, hero_level: int, enemy_level: int, forced_type: str | None = None) -> list[Item]:
        count = 1 if self.rng.random() < 0.75 else 2
        loot: list[Item] = []
        for _ in range(count):
            rarity, bonus = self._roll_rarity()
            item_type = forced_type or self.rng.choice(
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
            affixes, stat_bonuses, named = self._roll_affixes(item_type, rarity)
            slot = self._slot_for_item_type(item_type)
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
            final_name = f"{named} {name}".strip() if named else name
            loot.append(
                self._make_item(
                    final_name,
                    item_type,
                    rarity,
                    power,
                    level,
                    slot=slot,
                    affixes=affixes,
                    stat_bonuses=stat_bonuses,
                )
            )
        return loot

    def _make_item(
        self,
        name: str,
        item_type: str,
        rarity: str,
        power: int,
        level: int,
        slot: str | None = None,
        affixes: list[str] | None = None,
        stat_bonuses: Stats | None = None,
    ) -> Item:
        return Item(
            name=name,
            item_type=item_type,
            rarity=rarity,
            power=power,
            level=level,
            quantity=1,
            slot=slot,
            equipped=False,
            affixes=affixes or [],
            stat_bonuses=stat_bonuses or zero_stats(),
        )

    def _roll_affixes(self, item_type: str, rarity: str) -> tuple[list[str], Stats, str]:
        if item_type in {ItemType.CONSUMABLE.value, ItemType.MATERIAL.value}:
            return [], zero_stats(), ""
        affixes: list[str] = []
        bonuses = zero_stats()
        prefix_text = ""
        if rarity in {"rare", "epic", "mythic"}:
            prefix, prefix_bonus = self.rng.choice(PREFIXES)
            affixes.append(prefix)
            bonuses.power += prefix_bonus.power
            bonuses.vitality += prefix_bonus.vitality
            bonuses.agility += prefix_bonus.agility
            bonuses.insight += prefix_bonus.insight
            bonuses.luck += prefix_bonus.luck
            prefix_text = prefix
        if rarity in {"epic", "mythic"}:
            suffix, suffix_bonus = self.rng.choice(SUFFIXES)
            affixes.append(suffix)
            bonuses.power += suffix_bonus.power
            bonuses.vitality += suffix_bonus.vitality
            bonuses.agility += suffix_bonus.agility
            bonuses.insight += suffix_bonus.insight
            bonuses.luck += suffix_bonus.luck
            prefix_text = f"{prefix_text} {suffix}".strip()
        return affixes, bonuses, prefix_text

    def _slot_for_item_type(self, item_type: str) -> str | None:
        if item_type == ItemType.WEAPON.value:
            return EquipmentSlot.MAIN_HAND.value
        if item_type == ItemType.ARMOR.value:
            return EquipmentSlot.BODY.value
        if item_type == ItemType.CHARM.value:
            return EquipmentSlot.CHARM.value
        return None

    def _auto_equip(self, state: SaveState, loot: list[Item]) -> None:
        if not loot:
            return
        for item in loot:
            if item.slot is None:
                continue
            current = self._equipped_in_slot(state, item.slot)
            current_score = self._gear_score(current) if current else -1
            candidate_score = self._gear_score(item)
            if candidate_score > current_score:
                if current is not None:
                    current.equipped = False
                item.equipped = True
                state.activity_log.append(f"{state.character.name} equipped {item.name}.")

    def _equipped_in_slot(self, state: SaveState, slot: str) -> Item | None:
        for item in state.inventory:
            if item.slot == slot and item.equipped:
                return item
        return None

    def _gear_score(self, item: Item | None) -> int:
        if item is None:
            return -1
        bonuses = item.stat_bonuses
        return item.power + bonuses.power + bonuses.vitality + bonuses.agility + bonuses.insight + bonuses.luck

    def _consume_when_needed(self, state: SaveState) -> None:
        character = state.character
        if character.mood > 35 and character.supplies > 0:
            return
        consumable = next((item for item in state.inventory if item.item_type == ItemType.CONSUMABLE.value and item.quantity > 0), None)
        if consumable is None:
            return
        consumable.quantity -= 1
        character.mood = min(100, character.mood + 10)
        character.supplies += 1
        state.activity_log.append(f"{character.name} used {consumable.name}.")
        state.inventory = [item for item in state.inventory if item.quantity > 0]

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
            character.title = self._title_for_level(character.level)
            leveled_up = True
            threshold = 20 + character.level * 15
        if leveled_up:
            self._maybe_unlock_specialization(state)
        return leveled_up

    def _maybe_unlock_specialization(self, state: SaveState) -> None:
        character = state.character
        if character.level < 5 or character.specialization != Specialization.WANDERER.value:
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
        if state.device.low_power_mode:
            return "Battery is low. Favor rest, camp actions, and minimal risk."
        if pressure >= 8:
            return "Threat is outpacing growth. Focus on recovery and gear quality."
        if character.supplies <= 1:
            return "Supplies are low. The creature should favor camp actions soon."
        if character.specialization == Specialization.WANDERER.value and character.level >= 5:
            return "Core traits are mature enough to branch into a specialization."
        if len(state.party.allied_party) >= 2:
            return "Squad potential is rising. Cooperative dungeon bonuses should be added next."
        equipped = len([item for item in state.inventory if item.equipped])
        if equipped < 2:
            return "Equipment depth is still shallow. The next dungeon clear may matter a lot."
        return "Progression is stable. Keep the idle loop running."

    def _update_world(self, state: SaveState) -> None:
        state.world.current_region = REGION_NAMES[(state.character.dungeon_depth // 4) % len(REGION_NAMES)]
        state.world.current_threat = THREAT_NAMES[state.world.danger_rating % len(THREAT_NAMES)]

    def _title_for_level(self, level: int) -> str:
        if level >= 40:
            return "Endless Ascendant"
        if level >= 25:
            return "Deep Archive Lord"
        if level >= 15:
            return "Blackwell Captain"
        if level >= 8:
            return "Seasoned Delver"
        return "Hatchling Delver"

    def _trim_logs(self, state: SaveState) -> None:
        state.activity_log = state.activity_log[-20:]
        state.party.trade_log = state.party.trade_log[-20:]
