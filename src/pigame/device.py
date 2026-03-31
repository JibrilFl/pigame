from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol

from .core import GameEngine
from .models import SaveState


@dataclass
class RenderFrame:
    title: str
    lines: list[str]
    page: str = "status"
    header_right: str = ""
    battery_percent: int | None = None
    charging: bool | None = None
    low_power: bool = False


class Renderer(Protocol):
    def build_frame(self, state: SaveState, engine: GameEngine) -> RenderFrame:
        ...

    def render(self, frame: RenderFrame) -> str:
        ...


class TextRenderer:
    """Base text renderer used by both desktop and hardware adapters."""

    def build_frame(self, state: SaveState, engine: GameEngine) -> RenderFrame:
        pages = self.build_pages(state, engine)
        if not pages:
            return RenderFrame(title="PiGame", lines=["No renderable pages."], page="empty")
        index = state.character.lifetime_ticks % len(pages)
        return pages[index]

    def build_pages(self, state: SaveState, engine: GameEngine) -> list[RenderFrame]:
        c = state.character
        equipped = len([item for item in state.inventory if item.equipped])
        battery = state.device.battery_percent
        voltage = state.device.battery_voltage
        charge_flag = (
            "chg"
            if state.device.charging is True
            else "bat"
            if state.device.charging is False
            else "n/a"
        )
        battery_text = f"{battery}%" if battery is not None else "--%"
        battery_badge = (
            f"{battery_text}+"
            if state.device.charging is True
            else f"{battery_text}!"
            if state.device.low_power_mode
            else battery_text
        )
        battery_line = (
            f"Battery {battery_text} {charge_flag}  Volt {voltage:.2f}V"
            if voltage is not None
            else f"Battery {battery_text} {charge_flag}  Volt --.--V"
        )
        wait_text = "HOLD" if c.awaiting_player else "RUN"
        boss_text = (
            f"B {state.world.boss_level}"
            if state.world.boss_active
            else f"B {state.world.boss_countdown}"
        )
        region_text = self._short_region(state.world.current_region)
        spec_text = c.specialization[:4].upper()
        title_text = self._fit_text(c.title, 12)
        return [
            RenderFrame(
                title=f"{self._fit_text(c.name, 8)} L{c.level}",
                page="status",
                header_right=battery_badge,
                battery_percent=battery,
                charging=state.device.charging,
                low_power=state.device.low_power_mode,
                lines=[
                    f"{title_text} {spec_text}",
                    f"{self._abbr_activity(c.current_activity)} S{c.supplies} G{equipped}",
                    f"P{c.stats.power} V{c.stats.vitality}",
                    f"A{c.stats.agility} I{c.stats.insight} L{c.stats.luck}",
                    f"D{c.dungeon_depth} W{c.wins} L{c.losses}",
                    f"${c.gold} T{state.world.biome_tier} {boss_text}",
                    f"{region_text} / RISK {state.world.danger_rating}",
                    f"{wait_text} LS{c.loss_streak}",
                    f"ST{c.unspent_stat_points} PK{c.perk_points}",
                ],
            ),
            RenderFrame(
                title=f"{self._fit_text(c.name, 8)} GEAR",
                page="gear",
                header_right=battery_badge,
                battery_percent=battery,
                charging=state.device.charging,
                low_power=state.device.low_power_mode,
                lines=self._build_gear_lines(state, engine),
            ),
            RenderFrame(
                title=f"{self._fit_text(c.name, 8)} LOG",
                page="log",
                header_right=battery_badge,
                battery_percent=battery,
                charging=state.device.charging,
                low_power=state.device.low_power_mode,
                lines=self._build_log_lines(state),
            ),
        ]

    def render_to_text(self, frame: RenderFrame) -> str:
        border = "=" * max(40, len(frame.title))
        header = f"{frame.title} {frame.header_right}".strip()
        return "\n".join([border, header, border, *frame.lines])

    def render(self, frame: RenderFrame) -> str:
        return self.render_to_text(frame)

    def _build_gear_lines(self, state: SaveState, engine: GameEngine) -> list[str]:
        slots = {
            "main_hand": "MW",
            "body": "BD",
            "charm": "CH",
        }
        lines = [
            f"PWR {sum(item.power for item in state.inventory if item.equipped)}",
        ]
        for slot_key, label in slots.items():
            item = next(
                (entry for entry in state.inventory if entry.equipped and entry.slot == slot_key),
                None,
            )
            if item is None:
                lines.append(f"{label} -")
                continue
            crafted = " *" if item.crafted else ""
            lines.append(f"{label} {self._short_item_name(item.name)} +{item.power} q{item.quality}{crafted}")
        consumables = sum(item.quantity for item in state.inventory if item.item_type == "consumable")
        materials = sum(item.quantity for item in state.inventory if item.item_type == "material")
        blueprints = sum(item.quantity for item in state.inventory if item.item_type == "recipe")
        lines.append(f"INV {len(state.inventory)} U{consumables} M{materials} B{blueprints}")
        lines.append(f"RCP {len(state.character.known_recipes)}")
        passives = engine.passive_effects(state)
        if passives:
            lines.append(f"PERK {len(state.character.perks)}")
        return lines

    def _build_log_lines(self, state: SaveState) -> list[str]:
        recent = list(reversed(state.activity_log[-2:]))
        if not recent:
            recent = ["No notable events yet."]
        return [self._short_event(state.world.last_event), *[self._short_event(line) for line in recent]]


class ConsoleRenderer(TextRenderer):
    def render(self, frame: RenderFrame) -> str:
        output = self.render_to_text(frame)
        print(output)
        return output


class WaveshareRenderer(TextRenderer):
    """
    Optional adapter for Pi hardware.

    It safely falls back to writing a text snapshot when Waveshare libraries are
    missing, so development remains possible on desktop systems.
    """

    def __init__(self, model: str = "epd2in13_V4", snapshot_path: Path | None = None) -> None:
        self.model = model
        self.snapshot_path = snapshot_path or Path("data/last-screen.txt")
        self._driver = None
        self._init_error: str | None = None
        self._setup_driver()

    @property
    def is_hardware_ready(self) -> bool:
        return self._driver is not None

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def _setup_driver(self) -> None:
        try:
            module = __import__(f"waveshare_epd.{self.model}", fromlist=["EPD"])
            self._driver = module.EPD()
        except Exception as exc:  # pragma: no cover - depends on Pi-only libs
            self._driver = None
            self._init_error = str(exc)

    def render(self, frame: RenderFrame) -> str:
        output = self.render_to_text(frame)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(output, encoding="utf-8")

        if self._driver is None:
            return output

        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception as exc:  # pragma: no cover - depends on Pi package state
            self._init_error = f"Pillow unavailable: {exc}"
            return output

        canvas_width, canvas_height = self._canvas_size()
        image = Image.new("1", (canvas_width, canvas_height), 255)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        self._draw_frame_ui(draw, font, frame, canvas_width, canvas_height)

        try:
            self._driver.init()
            buffer = self._buffer_for_driver(image)
            self._driver.display(buffer)
            self._driver.sleep()
        except Exception as exc:  # pragma: no cover - depends on Pi hardware libs
            self._init_error = f"render failed: {exc}"
        return output

    def _canvas_size(self) -> tuple[int, int]:
        if self._driver is None:
            return (250, 122)
        width = int(getattr(self._driver, "width", getattr(self._driver, "EPD_WIDTH", 250)))
        height = int(getattr(self._driver, "height", getattr(self._driver, "EPD_HEIGHT", 122)))
        return (max(width, height), min(width, height))

    def _buffer_for_driver(self, image):
        from PIL import Image

        candidates = [
            image,
            image.transpose(Image.Transpose.ROTATE_90),
            image.transpose(Image.Transpose.ROTATE_270),
        ]
        for candidate in candidates:
            try:
                return self._driver.getbuffer(candidate)
            except Exception:
                continue
        return self._driver.getbuffer(image)

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        words = text.split()
        if not words:
            return [text[:max_chars]]
        lines: list[str] = []
        current = ""
        for word in words:
            proposal = word if not current else f"{current} {word}"
            if len(proposal) <= max_chars:
                current = proposal
                continue
            if current:
                lines.append(current)
            current = word[:max_chars]
        if current:
            lines.append(current)
        return lines

    def _fit_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return text[: max_chars - 3] + "..."

    def _abbr_activity(self, activity: str) -> str:
        table = {
            "dungeon": "DNG",
            "camp": "CMP",
            "rest": "RST",
            "hunt": "HNT",
            "ritual": "RIT",
            "salvage": "SLV",
        }
        return table.get(activity, activity[:3].upper())

    def _short_region(self, region: str) -> str:
        table = {
            "Moss Tunnels": "MOSS",
            "Ash Vault": "ASH",
            "Static Hollows": "STAT",
            "Moon Well": "MOON",
            "Glass Catacomb": "GLAS",
        }
        return table.get(region, self._fit_text(region.upper(), 4))

    def _short_item_name(self, name: str) -> str:
        compact = (
            name.replace("Rust ", "")
            .replace("Saber", "Sab")
            .replace("Bone ", "")
            .replace("Sparks", "Spark")
            .replace("Charm of ", "")
            .replace("Lucky ", "Luck ")
        )
        return self._fit_text(compact, 10)

    def _short_event(self, text: str) -> str:
        compact = (
            text.replace("stays in camp awaiting guidance", "camp wait")
            .replace("cleared depth", "clr d")
            .replace("and broke through", "beat")
            .replace("Boss prep incomplete.", "prep")
            .replace("Repeated losses.", "loss")
        )
        return self._fit_text(compact, 28)

    def _draw_frame_ui(self, draw, font, frame: RenderFrame, width: int, height: int) -> None:
        self._draw_header(draw, font, frame, width)
        if frame.page == "status":
            self._draw_status_page(draw, font, frame, width, height)
            return
        if frame.page == "gear":
            self._draw_list_page(draw, font, frame, width, height, icon_set=["blade", "armor", "charm", "bag", "chip", "star"])
            return
        self._draw_list_page(draw, font, frame, width, height, icon_set=["log", "log", "log", "log", "log", "log"])

    def _draw_header(self, draw, font, frame: RenderFrame, width: int) -> None:
        draw.rectangle((0, 0, width - 1, 15), outline=0, fill=0)
        draw.text((6, 3), frame.title[:20], font=font, fill=255)
        badge_width = 45
        bx0 = width - badge_width - 5
        draw.rounded_rectangle((bx0, 2, width - 5, 14), radius=3, outline=255, fill=0)
        self._draw_battery_meter(draw, bx0 + 4, 4, frame)
        draw.text((bx0 + 20, 4), frame.header_right[:6], font=font, fill=255)
        pill_text = frame.page.upper()[:6]
        pill_width = 8 + len(pill_text) * 6
        draw.rounded_rectangle((5, 17, 5 + pill_width, 28), radius=3, outline=0, fill=0)
        draw.text((9, 19), pill_text, font=font, fill=255)
        self._draw_page_dots(draw, width - 30, 21, frame.page)
        draw.line((0, 31, width - 1, 31), fill=0, width=1)

    def _draw_battery_meter(self, draw, x: int, y: int, frame: RenderFrame) -> None:
        draw.rectangle((x, y, x + 11, y + 6), outline=255, fill=0)
        draw.rectangle((x + 12, y + 2, x + 13, y + 4), outline=255, fill=255)
        percent = frame.battery_percent if frame.battery_percent is not None else 0
        fill_w = max(0, min(9, round(percent / 100 * 9)))
        if fill_w > 0:
            fill_color = 255
            if frame.low_power:
                fill_color = 255
            draw.rectangle((x + 1, y + 1, x + fill_w, y + 5), outline=fill_color, fill=fill_color)
        if frame.charging:
            draw.line((x + 5, y + 1, x + 4, y + 3), fill=0, width=1)
            draw.line((x + 4, y + 3, x + 7, y + 3), fill=0, width=1)
            draw.line((x + 7, y + 3, x + 5, y + 5), fill=0, width=1)

    def _draw_page_dots(self, draw, x: int, y: int, page: str) -> None:
        order = ["status", "gear", "log"]
        for index, name in enumerate(order):
            x0 = x + index * 8
            fill = 0 if name == page else 255
            draw.ellipse((x0, y, x0 + 4, y + 4), outline=0, fill=fill)
            if name != page:
                draw.ellipse((x0 + 1, y + 1, x0 + 3, y + 3), outline=255, fill=255)

    def _draw_status_page(self, draw, font, frame: RenderFrame, width: int, height: int) -> None:
        cards = frame.lines[:6]
        body_top = 34
        card_w = (width - 18) // 2
        card_h = 16
        icons = ["star", "act", "stats", "skull", "coin", "map", "crown", "alert"]
        for index, line in enumerate(cards):
            col = index % 2
            row = index // 2
            x0 = 5 + col * (card_w + 8)
            y0 = body_top + row * (card_h + 4)
            if y0 + card_h > height - 24:
                break
            self._draw_card(draw, font, x0, y0, card_w, card_h, line, icons[index % len(icons)])
        footer = frame.lines[6:8]
        if footer:
            y0 = height - 23
            draw.rectangle((5, y0, width - 6, height - 5), outline=0, fill=255)
            for idx, line in enumerate(footer[:2]):
                draw.text((8, y0 + 2 + idx * 8), self._fit_text(line, 26), font=font, fill=0)

    def _draw_list_page(self, draw, font, frame: RenderFrame, width: int, height: int, icon_set: list[str]) -> None:
        y = 35
        for index, raw_line in enumerate(frame.lines):
            wrapped = self._wrap_text(self._fit_text(raw_line, 34), max_chars=26)
            if not wrapped:
                continue
            box_h = 11 + 10 * min(2, len(wrapped))
            if y + box_h > height - 4:
                break
            draw.rectangle((5, y, width - 6, y + box_h), outline=0, fill=255)
            self._draw_icon(draw, icon_set[index % len(icon_set)], 9, y + 3)
            text_y = y + 2
            for line in wrapped[:2]:
                draw.text((22, text_y), line, font=font, fill=0)
                text_y += 9
            y += box_h + 3

    def _draw_card(self, draw, font, x: int, y: int, w: int, h: int, text: str, icon_name: str) -> None:
        draw.rectangle((x, y, x + w, y + h), outline=0, fill=255)
        draw.rectangle((x + 1, y + 1, x + 14, y + h - 1), outline=0, fill=0)
        self._draw_icon(draw, icon_name, x + 3, y + 5, invert=True)
        wrapped = self._wrap_text(self._fit_text(text, 22), max_chars=13)
        if wrapped:
            draw.text((x + 18, y + 3), wrapped[0], font=font, fill=0)
        if len(wrapped) > 1:
            draw.text((x + 18, y + 10), wrapped[1], font=font, fill=0)

    def _draw_icon(self, draw, icon_name: str, x: int, y: int, invert: bool = False) -> None:
        ink = 255 if invert else 0
        paper = 0 if invert else 255
        if icon_name == "battery":
            draw.rectangle((x, y, x + 9, y + 6), outline=ink, fill=paper)
            draw.rectangle((x + 10, y + 2, x + 11, y + 4), outline=ink, fill=ink)
            return
        if icon_name == "star":
            draw.polygon([(x + 4, y), (x + 5, y + 3), (x + 8, y + 3), (x + 6, y + 5), (x + 7, y + 8), (x + 4, y + 6), (x + 1, y + 8), (x + 2, y + 5), (x, y + 3), (x + 3, y + 3)], outline=ink)
            return
        if icon_name == "stats":
            draw.rectangle((x, y + 4, x + 1, y + 8), outline=ink, fill=ink)
            draw.rectangle((x + 3, y + 2, x + 4, y + 8), outline=ink, fill=ink)
            draw.rectangle((x + 6, y, x + 7, y + 8), outline=ink, fill=ink)
            return
        if icon_name == "act":
            draw.polygon([(x, y + 4), (x + 4, y), (x + 8, y + 4), (x + 4, y + 8)], outline=ink)
            return
        if icon_name == "skull":
            draw.ellipse((x, y, x + 8, y + 6), outline=ink)
            draw.rectangle((x + 2, y + 6, x + 6, y + 8), outline=ink)
            return
        if icon_name == "coin":
            draw.ellipse((x, y, x + 8, y + 8), outline=ink)
            draw.line((x + 2, y + 4, x + 6, y + 4), fill=ink, width=1)
            return
        if icon_name == "map":
            draw.rectangle((x, y, x + 8, y + 8), outline=ink)
            draw.line((x + 3, y, x + 3, y + 8), fill=ink, width=1)
            draw.line((x + 6, y, x + 6, y + 8), fill=ink, width=1)
            return
        if icon_name == "crown":
            draw.polygon([(x, y + 8), (x + 1, y + 2), (x + 4, y + 5), (x + 7, y + 1), (x + 8, y + 8)], outline=ink)
            return
        if icon_name == "alert":
            draw.polygon([(x + 4, y), (x + 8, y + 8), (x, y + 8)], outline=ink)
            draw.line((x + 4, y + 3, x + 4, y + 5), fill=ink, width=1)
            return
        if icon_name == "blade":
            draw.line((x + 1, y + 7, x + 7, y + 1), fill=ink, width=1)
            draw.line((x, y + 8, x + 2, y + 6), fill=ink, width=1)
            return
        if icon_name == "armor":
            draw.polygon([(x + 1, y + 1), (x + 7, y + 1), (x + 8, y + 3), (x + 6, y + 8), (x + 2, y + 8), (x, y + 3)], outline=ink)
            return
        if icon_name == "charm":
            draw.ellipse((x + 1, y + 1, x + 7, y + 7), outline=ink)
            draw.line((x + 4, y, x + 4, y + 2), fill=ink, width=1)
            return
        if icon_name == "bag":
            draw.rectangle((x + 1, y + 3, x + 7, y + 8), outline=ink)
            draw.arc((x + 2, y, x + 6, y + 4), start=180, end=360, fill=ink)
            return
        if icon_name == "chip":
            draw.rectangle((x + 1, y + 1, x + 7, y + 7), outline=ink)
            return
        if icon_name == "log":
            draw.rectangle((x + 1, y + 1, x + 7, y + 7), outline=ink)
            draw.line((x + 2, y + 3, x + 6, y + 3), fill=ink, width=1)
            draw.line((x + 2, y + 5, x + 6, y + 5), fill=ink, width=1)
            return
        draw.rectangle((x + 1, y + 1, x + 7, y + 7), outline=ink)


def build_renderer(mode: str = "auto") -> Renderer:
    normalized = mode.lower()
    if normalized == "console":
        return ConsoleRenderer()
    if normalized == "text":
        return TextRenderer()
    if normalized in {"waveshare", "auto"}:
        renderer = WaveshareRenderer()
        if normalized == "waveshare" or renderer.is_hardware_ready:
            return renderer
    return TextRenderer()


class PeerSyncService:
    """Protocol placeholder for later BLE or Wi-Fi sync."""

    def announce_presence(self, state: SaveState) -> dict[str, object]:
        return {
            "name": state.character.name,
            "level": state.character.level,
            "specialization": state.character.specialization,
            "depth": state.character.dungeon_depth,
        }

    def merge_peer_snapshot(self, state: SaveState, peer_name: str) -> None:
        if peer_name not in state.party.peers_seen:
            state.party.peers_seen.append(peer_name)
        if peer_name not in state.party.allied_party:
            state.party.allied_party.append(peer_name)
            state.party.trade_log.append(f"Linked with nearby unit {peer_name}.")


class BatteryMonitor:
    """Placeholder for UPS Lite telemetry integration."""

    def __init__(self, low_battery_percent: int = 15, critical_battery_percent: int = 5) -> None:
        self.low_battery_percent = low_battery_percent
        self.critical_battery_percent = critical_battery_percent

    def read_status(self) -> dict[str, object]:
        return {
            "battery_percent": None,
            "battery_voltage": None,
            "charging": None,
            "low_power": False,
            "critical_power": False,
            "reason": "",
        }


class Max17040BatteryMonitor(BatteryMonitor):
    """
    Battery monitor for UPS-Lite boards built around the MAX17040G fuel gauge.

    Inference from vendor documentation:
    - UPS-Lite for Pi Zero exposes battery telemetry through MAX17040G over I2C.
    - Standard MAX17040 address is 0x36 on I2C bus 1.
    """

    VCELL_REGISTER = 0x02
    SOC_REGISTER = 0x04

    def __init__(
        self,
        bus: int = 1,
        address: int = 0x36,
        low_battery_percent: int = 15,
        critical_battery_percent: int = 5,
    ) -> None:
        super().__init__(
            low_battery_percent=low_battery_percent,
            critical_battery_percent=critical_battery_percent,
        )
        self.bus = bus
        self.address = address
        self._smbus = self._load_smbus()

    def _load_smbus(self):
        try:
            from smbus2 import SMBus  # type: ignore

            return SMBus
        except Exception:
            try:
                from smbus import SMBus  # type: ignore

                return SMBus
            except Exception:
                return None

    def read_status(self) -> dict[str, object]:
        if self._smbus is None:
            return {
                "battery_percent": None,
                "battery_voltage": None,
                "charging": None,
                "low_power": False,
                "critical_power": False,
                "reason": "smbus library not available",
            }

        try:
            with self._smbus(self.bus) as handle:
                vcell = handle.read_i2c_block_data(self.address, self.VCELL_REGISTER, 2)
                soc = handle.read_i2c_block_data(self.address, self.SOC_REGISTER, 2)
        except Exception as exc:
            return {
                "battery_percent": None,
                "battery_voltage": None,
                "charging": None,
                "low_power": False,
                "critical_power": False,
                "reason": f"battery read failed: {exc}",
            }

        raw_voltage = ((vcell[0] << 4) | (vcell[1] >> 4)) * 1.25 / 1000.0
        battery_percent = min(100, max(0, int(soc[0])))
        low_power = battery_percent <= self.low_battery_percent
        critical_power = battery_percent <= self.critical_battery_percent

        reason = ""
        if critical_power:
            reason = (
                f"Battery critical at {battery_percent}% ({raw_voltage:.2f}V). "
                "Saving and stopping."
            )
        elif low_power:
            reason = f"Battery low at {battery_percent}% ({raw_voltage:.2f}V)."

        return {
            "battery_percent": battery_percent,
            "battery_voltage": round(raw_voltage, 3),
            "charging": None,
            "low_power": low_power,
            "critical_power": critical_power,
            "reason": reason,
        }


class Cw2015BatteryMonitor(BatteryMonitor):
    """
    Battery monitor for UPS-Lite v1.3 boards exposing a CW2015 at I2C address 0x62.

    Based on vendor/user-guide code paths and common UPS-Lite v1.3 integrations.
    Charging detection is inferred from GPIO4 when available.
    """

    VCELL_REGISTER = 0x02
    SOC_REGISTER = 0x04
    MODE_REGISTER = 0x0A
    CHARGING_GPIO = 4

    def __init__(
        self,
        bus: int = 1,
        address: int = 0x62,
        low_battery_percent: int = 15,
        critical_battery_percent: int = 5,
    ) -> None:
        super().__init__(
            low_battery_percent=low_battery_percent,
            critical_battery_percent=critical_battery_percent,
        )
        self.bus = bus
        self.address = address
        self._smbus = self._load_smbus()
        self._gpio = self._load_gpio()
        self._gpio_ready = False
        self._prepare_gpio()
        self._quickstart_done = False

    def _load_smbus(self):
        try:
            from smbus2 import SMBus  # type: ignore

            return SMBus
        except Exception:
            try:
                from smbus import SMBus  # type: ignore

                return SMBus
            except Exception:
                return None

    def _load_gpio(self):
        try:
            import RPi.GPIO as GPIO  # type: ignore

            return GPIO
        except Exception:
            return None

    def _prepare_gpio(self) -> None:
        if self._gpio is None:
            return
        try:
            self._gpio.setwarnings(False)
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setup(self.CHARGING_GPIO, self._gpio.IN)
            self._gpio_ready = True
        except Exception:
            self._gpio_ready = False

    def _quickstart(self) -> None:
        if self._quickstart_done:
            return
        if self._smbus is not None:
            try:
                with self._smbus(self.bus) as handle:
                    handle.write_word_data(self.address, self.MODE_REGISTER, 0x30)
                self._quickstart_done = True
                return
            except Exception:
                self._quickstart_done = False
        try:
            subprocess.run(
                [
                    "i2cset",
                    "-y",
                    str(self.bus),
                    hex(self.address),
                    hex(self.MODE_REGISTER),
                    "0x30",
                    "w",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self._quickstart_done = True
        except Exception:
            self._quickstart_done = False

    def _charging_state(self) -> bool | None:
        if not self._gpio_ready or self._gpio is None:
            return None
        try:
            return self._gpio.input(self.CHARGING_GPIO) == self._gpio.HIGH
        except Exception:
            return None

    def read_status(self) -> dict[str, object]:
        self._quickstart()

        raw_voltage: int | None = None
        raw_soc: int | None = None
        reason = ""

        if self._smbus is not None:
            try:
                with self._smbus(self.bus) as handle:
                    raw_voltage = handle.read_word_data(self.address, self.VCELL_REGISTER)
                    raw_soc = handle.read_word_data(self.address, self.SOC_REGISTER)
            except Exception as exc:
                reason = f"battery read failed via smbus: {exc}"

        if raw_voltage is None or raw_soc is None:
            try:
                raw_voltage = self._read_word_via_i2cget(self.VCELL_REGISTER)
                raw_soc = self._read_word_via_i2cget(self.SOC_REGISTER)
                reason = ""
            except Exception as exc:
                reason = f"battery read failed via i2cget: {exc}"

        if raw_voltage is None or raw_soc is None:
            return {
                "battery_percent": None,
                "battery_voltage": None,
                "charging": self._charging_state(),
                "low_power": False,
                "critical_power": False,
                "reason": reason or "battery reader unavailable",
            }

        swapped_voltage = ((raw_voltage & 0xFF) << 8) | ((raw_voltage >> 8) & 0xFF)
        swapped_soc = ((raw_soc & 0xFF) << 8) | ((raw_soc >> 8) & 0xFF)
        voltage = swapped_voltage * 0.305 / 1000.0
        battery_percent = min(100, max(0, int(swapped_soc / 256)))
        low_power = battery_percent <= self.low_battery_percent
        critical_power = battery_percent <= self.critical_battery_percent

        reason = ""
        if critical_power:
            reason = (
                f"Battery critical at {battery_percent}% ({voltage:.2f}V). "
                "Saving and stopping."
            )
        elif low_power:
            reason = f"Battery low at {battery_percent}% ({voltage:.2f}V)."

        return {
            "battery_percent": battery_percent,
            "battery_voltage": round(voltage, 3),
            "charging": self._charging_state(),
            "low_power": low_power,
            "critical_power": critical_power,
            "reason": reason,
        }

    def _read_word_via_i2cget(self, register: int) -> int:
        result = subprocess.run(
            [
                "i2cget",
                "-y",
                str(self.bus),
                hex(self.address),
                hex(register),
                "w",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        value = result.stdout.strip()
        if not value.startswith("0x"):
            raise RuntimeError(f"unexpected i2cget output: {value}")
        return int(value, 16)
