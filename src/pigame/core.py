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
BOSS_TITLES = ["Brood Tyrant", "Vault Warden", "Static Monarch", "Moon Executor", "Glass Leviathan"]

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

SPECIALIZATION_PASSIVES = {
    Specialization.WANDERER.value: [
        "Adaptive growth: small all-stat baseline and flexible loot.",
        "Field instincts: boss timers arrive slightly later.",
    ],
    Specialization.GUARDIAN.value: [
        "Bulwark: extra combat value from vitality, armor quality, and boss fights.",
        "Steady hands: dungeon losses cost less depth and mood.",
    ],
    Specialization.HUNTER.value: [
        "Ambush: agility and luck spike combat variance upward.",
        "Trophy eye: stronger chance for extra loot on clean clears and bosses.",
    ],
    Specialization.ALCHEMIST.value: [
        "Reagents: consumables and salvage upgrades are more potent.",
        "Field brewing: hunts and camping recover more supplies and gold.",
    ],
    Specialization.NECROTECH.value: [
        "Soul graft: charm quality and insight amplify ritual and boss power.",
        "Last echo: near-losses can convert into partial retreats instead of full failures.",
    ],
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

        self._add_items(state, loot)
        self._auto_equip(state, loot)
        self._consume_when_needed(state)
        leveled_up = self._apply_leveling(state)
        self._update_world(state)
        self._stack_inventory(state)
        self._trim_logs(state)
        return TickResult(summary=summary, leveled_up=leveled_up, loot=loot)

    def forge(self, state: SaveState) -> tuple[str, list[Item]]:
        summary, loot = self._salvage_action(state)
        self._add_items(state, loot)
        self._auto_equip(state, loot)
        self._stack_inventory(state)
        self._trim_logs(state)
        return summary, loot

    def total_stats(self, state: SaveState) -> Stats:
        return self._total_stats(state)

    def hero_power(self, state: SaveState) -> int:
        return self._hero_power(state)

    def passive_effects(self, state: SaveState) -> list[str]:
        return SPECIALIZATION_PASSIVES.get(state.character.specialization, [])

    def _choose_activity(self, state: SaveState) -> str:
        character = state.character
        roll = self.rng.random()
        materials = self._material_count(state)

        if state.world.boss_active:
            return ActivityType.DUNGEON.value
        if character.mood < 25 or character.supplies <= 0:
            return ActivityType.REST.value if roll < 0.55 else ActivityType.CAMP.value
        if character.specialization == Specialization.ALCHEMIST.value and character.supplies < 4 and roll < 0.32:
            return ActivityType.HUNT.value
        if character.specialization == Specialization.NECROTECH.value and roll < 0.22:
            return ActivityType.RITUAL.value
        if (materials >= 4 or self._forgeable_spares(state)) and roll < 0.18:
            return ActivityType.SALVAGE.value
        if roll < 0.10:
            return ActivityType.REST.value
        if roll < 0.22:
            return ActivityType.CAMP.value
        if roll < 0.34:
            return ActivityType.HUNT.value
        return ActivityType.DUNGEON.value

    def _rest(self, state: SaveState) -> str:
        character = state.character
        bonus_supplies = 2 if character.specialization == Specialization.ALCHEMIST.value else 1
        character.mood = min(100, character.mood + 8)
        character.supplies += bonus_supplies
        state.world.last_event = f"{character.name} rested, patched gear, and regained focus."
        state.activity_log.append(state.world.last_event)
        return state.world.last_event

    def _camp_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        gold_gain = 2 + character.level + (2 if character.specialization == Specialization.ALCHEMIST.value else 0)
        if character.specialization == Specialization.WANDERER.value:
            gold_gain += 1
        character.supplies += 1 + (1 if character.specialization == Specialization.ALCHEMIST.value else 0)
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
        if character.specialization == Specialization.ALCHEMIST.value:
            gains += 1
        character.supplies += gains
        character.experience += 4 + character.level
        character.mood = min(100, character.mood + 1)
        loot = [self._make_item("Field Ration", ItemType.CONSUMABLE.value, "common", 0, character.level, quantity=1)]
        if self.rng.random() < 0.35:
            loot.append(self._make_item("Glow Dust", ItemType.MATERIAL.value, "common", 0, character.level, quantity=1))
        summary = f"{character.name} hunted through {state.world.current_region} and secured {gains} supplies."
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

    def _ritual_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        bonus = 5 + character.level + (3 if character.specialization == Specialization.NECROTECH.value else 0)
        character.experience += bonus
        character.mood = max(5, character.mood - 1)
        if self.rng.random() < 0.25:
            character.stats.insight += 1
        summary = f"{character.name} performed a field ritual and extracted {bonus} arcane experience."
        state.world.last_event = summary
        state.activity_log.append(summary)
        loot: list[Item] = []
        chance = 0.45 + (0.12 if character.specialization == Specialization.NECROTECH.value else 0.0)
        if self.rng.random() < chance:
            loot.extend(self._generate_loot(character.level, character.level + 1, forced_type=ItemType.CHARM.value))
        return summary, loot

    def _salvage_action(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        spare = self._weakest_spare_item(state)
        materials = self._material_count(state)
        loot: list[Item] = []

        if spare is not None:
            yield_count = 1 + self._rarity_bonus(spare.rarity) // 2 + spare.quality
            spare.quantity -= 1
            scrap = self._make_item("Forge Scrap", ItemType.MATERIAL.value, "uncommon", 0, max(1, spare.level), quantity=max(1, yield_count))
            loot.append(scrap)
            summary = f"{character.name} dismantled {spare.name} into {scrap.quantity} Forge Scrap."
        elif materials >= 4 and character.gold >= self._upgrade_cost(state):
            spent_gold = self._upgrade_cost(state)
            target = self._upgrade_target(state)
            if target is None:
                summary = f"{character.name} surveyed the pack but found nothing worth refining."
            else:
                self._spend_materials(state, 4)
                character.gold -= spent_gold
                self._upgrade_item(target, state)
                summary = f"{character.name} reforged {target.name} to quality +{target.quality}."
        elif materials >= 3:
            self._spend_materials(state, 3)
            crafted_type = self._preferred_craft_type(state)
            loot = self._generate_loot(character.level, character.level + 2, forced_type=crafted_type)
            for item in loot:
                item.quality += 1
                item.crafted = True
                if "crafted" not in item.tags:
                    item.tags.append("crafted")
            summary = f"{character.name} assembled fresh {crafted_type} gear from salvaged parts."
        else:
            summary = f"{character.name} found nothing worth reforging."

        state.inventory = [item for item in state.inventory if item.quantity > 0]
        state.character.experience += 4 + (2 if loot else 0)
        if character.specialization == Specialization.ALCHEMIST.value and loot:
            character.mood = min(100, character.mood + 2)
        state.world.last_event = summary
        state.activity_log.append(summary)
        return summary, loot

    def _dungeon_run(self, state: SaveState) -> tuple[str, list[Item]]:
        character = state.character
        boss_fight = state.world.boss_active
        enemy_level = max(1, character.level + character.dungeon_depth // 3)
        if boss_fight:
            enemy_level = max(enemy_level + 2, state.world.boss_level)
        enemy_power = enemy_level * 5 + state.world.danger_rating * 3
        if boss_fight:
            enemy_power += 10 + state.world.boss_phase * 4

        hero_power = self._hero_power(state)
        passive_bonus, passive_notes = self._specialization_combat_bonus(state, boss_fight)
        variance = self.rng.randint(-6, 6)
        if character.specialization == Specialization.HUNTER.value:
            variance += self.rng.randint(0, max(2, self._total_stats(state).agility // 4))
        score = hero_power + passive_bonus + variance - enemy_power

        supply_cost = 1
        if character.specialization == Specialization.ALCHEMIST.value and self.rng.random() < 0.35:
            supply_cost = 0
        if character.supplies >= supply_cost:
            character.supplies -= supply_cost

        if boss_fight:
            summary, loot = self._resolve_boss_fight(state, enemy_level, score, passive_notes)
        elif score >= 0:
            character.wins += 1
            character.experience += 10 + enemy_level * 4
            character.gold += 4 + enemy_level * 2
            character.dungeon_depth += 1
            character.mood = min(100, character.mood + 3)
            state.world.danger_rating = min(9999, state.world.danger_rating + 1)
            state.world.biome_tier = 1 + character.dungeon_depth // 10
            loot = self._generate_loot(character.level, enemy_level)
            if character.specialization == Specialization.HUNTER.value and score >= 8 and self.rng.random() < 0.4:
                loot.extend(self._generate_loot(character.level, enemy_level, forced_type=ItemType.MATERIAL.value))
                passive_notes.append("trophy eye")
            self._advance_boss_counter(state)
            summary = (
                f"{character.name} cleared depth {character.dungeon_depth - 1} "
                f"and broke through a level {enemy_level} threat."
            )
        else:
            character.losses += 1
            character.experience += 3 + enemy_level
            retreat_depth = 1
            mood_loss = 5
            if character.specialization == Specialization.GUARDIAN.value:
                retreat_depth = 0 if score >= -3 else 1
                mood_loss = 2
                passive_notes.append("bulwark hold")
            elif character.specialization == Specialization.NECROTECH.value and score >= -4:
                retreat_depth = 0
                mood_loss = 3
                passive_notes.append("last echo")
            character.mood = max(5, character.mood - mood_loss)
            character.dungeon_depth = max(1, character.dungeon_depth - retreat_depth)
            loot = []
            summary = (
                f"{character.name} retreated from {state.world.current_region} after a hard fight "
                f"with a level {enemy_level} threat."
            )

        note_suffix = f" Passive: {', '.join(passive_notes)}." if passive_notes else ""
        state.world.ambient_story = self._story_text(state, score, boss_fight)
        state.world.last_event = summary + note_suffix
        state.activity_log.append(state.world.last_event)
        return state.world.last_event, loot

    def _resolve_boss_fight(
        self,
        state: SaveState,
        enemy_level: int,
        score: int,
        passive_notes: list[str],
    ) -> tuple[str, list[Item]]:
        character = state.character
        loot: list[Item] = []
        boss_name = state.world.boss_name or self._boss_name(state)
        if score >= 0:
            character.wins += 1
            character.bosses_defeated += 1
            character.experience += 20 + enemy_level * 6
            character.gold += 12 + enemy_level * 3
            character.dungeon_depth += 2
            character.mood = min(100, character.mood + 6)
            state.world.danger_rating = min(9999, state.world.danger_rating + 2)
            state.world.biome_tier = 1 + character.dungeon_depth // 10
            loot.extend(self._generate_loot(character.level + 1, enemy_level + 2))
            loot.extend(
                self._generate_loot(
                    character.level + 1,
                    enemy_level + 2,
                    forced_type=self._preferred_craft_type(state),
                )
            )
            for item in loot:
                if item.slot is not None:
                    item.quality += 1
            if character.specialization == Specialization.HUNTER.value:
                loot.extend(self._generate_loot(character.level, enemy_level, forced_type=ItemType.MATERIAL.value))
                passive_notes.append("trophy eye")
            summary = f"{character.name} defeated boss {boss_name} at depth {character.dungeon_depth - 2}."
            self._clear_boss(state, won=True)
        else:
            character.losses += 1
            character.experience += 6 + enemy_level
            character.mood = max(5, character.mood - 6)
            if character.specialization == Specialization.GUARDIAN.value and score >= -5:
                character.dungeon_depth = max(1, character.dungeon_depth - 1)
                passive_notes.append("bulwark hold")
                summary = f"{character.name} withstood boss {boss_name} and escaped with the route mapped."
            elif character.specialization == Specialization.NECROTECH.value and score >= -5:
                character.dungeon_depth = max(1, character.dungeon_depth - 1)
                passive_notes.append("last echo")
                summary = f"{character.name} tore free from boss {boss_name} through a soul graft retreat."
            else:
                character.dungeon_depth = max(1, character.dungeon_depth - 2)
                summary = f"{character.name} was driven back by boss {boss_name}."
            state.world.boss_level = max(1, state.world.boss_level - 1)
            state.world.current_threat = boss_name
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
        gear = sum(item.power + item.quality * 2 for item in state.inventory if item.equipped)
        return base + gear

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
            if item.quality > 0:
                total.power += item.quality if item.slot == EquipmentSlot.MAIN_HAND.value else 0
                total.vitality += item.quality if item.slot == EquipmentSlot.BODY.value else 0
                total.insight += item.quality if item.slot == EquipmentSlot.CHARM.value else 0
        return total

    def _specialization_combat_bonus(self, state: SaveState, boss_fight: bool) -> tuple[int, list[str]]:
        total = self._total_stats(state)
        character = state.character
        notes: list[str] = []
        bonus = 0

        if character.specialization == Specialization.WANDERER.value:
            bonus += 2 + state.character.level // 5
            if not boss_fight:
                bonus += 1
        elif character.specialization == Specialization.GUARDIAN.value:
            armor = self._equipped_in_slot(state, EquipmentSlot.BODY.value)
            bonus += total.vitality // 2
            bonus += (armor.quality * 3) if armor is not None else 0
            if boss_fight:
                bonus += 6
            notes.append("bulwark")
        elif character.specialization == Specialization.HUNTER.value:
            bonus += total.agility // 2 + total.luck // 3
            if boss_fight:
                bonus += 3
            notes.append("ambush")
        elif character.specialization == Specialization.ALCHEMIST.value:
            bonus += total.insight // 2
            if any(item.item_type == ItemType.CONSUMABLE.value and item.quantity > 0 for item in state.inventory):
                bonus += 4
                notes.append("reagents")
            if character.supplies <= 2:
                bonus += 2
        elif character.specialization == Specialization.NECROTECH.value:
            charm = self._equipped_in_slot(state, EquipmentSlot.CHARM.value)
            bonus += total.insight // 2
            bonus += (charm.quality * 3) if charm is not None else 0
            if boss_fight:
                bonus += 5
            notes.append("soul graft")

        return bonus, notes

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
            quality = self._roll_quality(rarity, enemy_level)
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
                quality = 0
            else:
                name = self.rng.choice(MATERIAL_NAMES)
                power = 0
                quality = 0
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
                    quality=quality,
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
        quality: int = 0,
        quantity: int = 1,
        crafted: bool = False,
        tags: list[str] | None = None,
    ) -> Item:
        return Item(
            name=name,
            item_type=item_type,
            rarity=rarity,
            power=power,
            level=level,
            quantity=quantity,
            slot=slot,
            equipped=False,
            affixes=affixes or [],
            stat_bonuses=stat_bonuses or zero_stats(),
            quality=quality,
            crafted=crafted,
            tags=tags or [],
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

    def _roll_quality(self, rarity: str, enemy_level: int) -> int:
        base = {
            "common": 0,
            "uncommon": 0,
            "rare": 1,
            "epic": 2,
            "mythic": 3,
        }[rarity]
        if enemy_level >= 10 and self.rng.random() < 0.35:
            base += 1
        return min(5, base)

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
        return (
            item.power
            + bonuses.power
            + bonuses.vitality
            + bonuses.agility
            + bonuses.insight
            + bonuses.luck
            + item.quality * 3
        )

    def _consume_when_needed(self, state: SaveState) -> None:
        character = state.character
        if character.mood > 35 and character.supplies > 0:
            return
        consumable = next(
            (item for item in state.inventory if item.item_type == ItemType.CONSUMABLE.value and item.quantity > 0),
            None,
        )
        if consumable is None:
            return
        consumable.quantity -= 1
        recover = 12 if character.specialization == Specialization.ALCHEMIST.value else 10
        character.mood = min(100, character.mood + recover)
        character.supplies += 1 + (1 if character.specialization == Specialization.ALCHEMIST.value else 0)
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
            character.unspent_stat_points += 1
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

    def _story_text(self, state: SaveState, score: int, boss_fight: bool) -> str:
        character = state.character
        if boss_fight and score >= 0:
            return f"{character.name} toppled the tyrant ruling {state.world.current_region}."
        if boss_fight:
            return f"{character.name} felt the whole dungeon tighten around the boss chamber."
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
        if state.world.boss_active:
            return f"Boss active: {state.world.boss_name}. Forge gear or prepare for a forced dungeon push."
        if pressure >= 8:
            return "Threat is outpacing growth. Focus on recovery, forging, and gear quality."
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
        if state.world.boss_active:
            state.world.current_threat = state.world.boss_name
        else:
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

    def _advance_boss_counter(self, state: SaveState) -> None:
        countdown_step = 2 if state.character.specialization == Specialization.WANDERER.value else 1
        state.world.boss_countdown -= countdown_step
        if state.world.boss_countdown <= 0:
            self._spawn_boss(state)

    def _spawn_boss(self, state: SaveState) -> None:
        state.world.boss_active = True
        state.world.boss_phase += 1
        state.world.boss_level = max(
            state.character.level + 2,
            state.character.dungeon_depth // 2 + state.world.biome_tier,
        )
        state.world.boss_name = self._boss_name(state)
        state.world.current_threat = state.world.boss_name
        state.activity_log.append(f"Boss sighted: {state.world.boss_name}.")

    def _clear_boss(self, state: SaveState, won: bool) -> None:
        state.world.boss_active = False
        state.world.boss_name = ""
        state.world.boss_level = 0
        state.world.boss_countdown = 4 + max(0, state.character.bosses_defeated // 2) + (0 if won else 1)

    def _boss_name(self, state: SaveState) -> str:
        region_index = (state.character.dungeon_depth // 4) % len(REGION_NAMES)
        return f"{BOSS_TITLES[region_index]} of {state.world.current_region}"

    def _stack_inventory(self, state: SaveState) -> None:
        merged: list[Item] = []
        stacks: dict[tuple[str, str, str, int], Item] = {}
        for item in state.inventory:
            if item.quantity <= 0:
                continue
            stackable = item.item_type in {ItemType.CONSUMABLE.value, ItemType.MATERIAL.value}
            if not stackable:
                merged.append(item)
                continue
            key = (item.name, item.item_type, item.rarity, item.level)
            current = stacks.get(key)
            if current is None:
                stacks[key] = item
                merged.append(item)
                continue
            current.quantity += item.quantity
        state.inventory = merged

    def _add_items(self, state: SaveState, items: list[Item]) -> None:
        for item in items:
            if item.item_type in {ItemType.CONSUMABLE.value, ItemType.MATERIAL.value}:
                existing = next(
                    (
                        entry
                        for entry in state.inventory
                        if entry.name == item.name
                        and entry.item_type == item.item_type
                        and entry.rarity == item.rarity
                        and entry.level == item.level
                    ),
                    None,
                )
                if existing is not None:
                    existing.quantity += item.quantity
                    continue
            state.inventory.append(item)

    def _material_count(self, state: SaveState) -> int:
        return sum(item.quantity for item in state.inventory if item.item_type == ItemType.MATERIAL.value)

    def _spend_materials(self, state: SaveState, amount: int) -> None:
        remaining = amount
        for item in state.inventory:
            if item.item_type != ItemType.MATERIAL.value or remaining <= 0:
                continue
            spent = min(item.quantity, remaining)
            item.quantity -= spent
            remaining -= spent
        state.inventory = [item for item in state.inventory if item.quantity > 0]

    def _forgeable_spares(self, state: SaveState) -> int:
        return len([item for item in state.inventory if item.slot is not None and not item.equipped])

    def _weakest_spare_item(self, state: SaveState) -> Item | None:
        spares = [item for item in state.inventory if item.slot is not None and not item.equipped and item.quantity > 0]
        if not spares:
            return None
        return min(spares, key=self._gear_score)

    def _upgrade_target(self, state: SaveState) -> Item | None:
        equipped = [item for item in state.inventory if item.slot is not None and item.equipped]
        if not equipped:
            return None
        return min(equipped, key=lambda item: (item.quality, self._gear_score(item)))

    def _upgrade_cost(self, state: SaveState) -> int:
        target = self._upgrade_target(state)
        if target is None:
            return 0
        return 6 + target.level + target.quality * 3

    def _upgrade_item(self, item: Item, state: SaveState) -> None:
        item.quality = min(5, item.quality + 1)
        item.power += 1 + max(1, state.character.level // 5)
        item.crafted = True
        if "crafted" not in item.tags:
            item.tags.append("crafted")
        if item.slot == EquipmentSlot.MAIN_HAND.value:
            item.stat_bonuses.power += 1
        elif item.slot == EquipmentSlot.BODY.value:
            item.stat_bonuses.vitality += 1
        elif item.slot == EquipmentSlot.CHARM.value:
            item.stat_bonuses.insight += 1
        if state.character.specialization == Specialization.ALCHEMIST.value:
            item.stat_bonuses.luck += 1
        elif state.character.specialization == Specialization.HUNTER.value:
            item.stat_bonuses.agility += 1

    def _preferred_craft_type(self, state: SaveState) -> str:
        equipped_slots = {item.slot for item in state.inventory if item.equipped and item.slot is not None}
        for desired in [EquipmentSlot.MAIN_HAND.value, EquipmentSlot.BODY.value, EquipmentSlot.CHARM.value]:
            if desired not in equipped_slots:
                return {
                    EquipmentSlot.MAIN_HAND.value: ItemType.WEAPON.value,
                    EquipmentSlot.BODY.value: ItemType.ARMOR.value,
                    EquipmentSlot.CHARM.value: ItemType.CHARM.value,
                }[desired]
        spec = state.character.specialization
        if spec == Specialization.GUARDIAN.value:
            return ItemType.ARMOR.value
        if spec == Specialization.HUNTER.value:
            return ItemType.WEAPON.value
        return ItemType.CHARM.value

    def _rarity_bonus(self, rarity: str) -> int:
        return next((bonus for name, bonus in RARITY_TABLE if name == rarity), 0)
