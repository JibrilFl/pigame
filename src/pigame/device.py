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
        battery_line = (
            f"Battery {battery_text} {charge_flag}  Volt {voltage:.2f}V"
            if voltage is not None
            else f"Battery {battery_text} {charge_flag}  Volt --.--V"
        )
        return [
            RenderFrame(
                title=f"{c.name} | Status | lvl {c.level}",
                page="status",
                lines=[
                    f"{c.title}  Spec {c.specialization}",
                    f"Stats P{c.stats.power} V{c.stats.vitality} A{c.stats.agility} I{c.stats.insight} L{c.stats.luck}",
                    f"Act {c.current_activity}  Supplies {c.supplies}  Gear {equipped}",
                    f"Depth {c.dungeon_depth}  Wins {c.wins}  Losses {c.losses}  Mood {c.mood}",
                    f"{state.world.current_region}  danger {state.world.danger_rating}  tier {state.world.biome_tier}",
                    f"XP {c.experience}  Gold {c.gold}",
                    battery_line,
                    f"LowPower {state.device.low_power_mode}  Shutdown {state.device.shutdown_requested}",
                    f"AI: {engine.ai_brief(state)}",
                ],
            ),
            RenderFrame(
                title=f"{c.name} | Gear | lvl {c.level}",
                page="gear",
                lines=self._build_gear_lines(state),
            ),
            RenderFrame(
                title=f"{c.name} | Log | lvl {c.level}",
                page="log",
                lines=self._build_log_lines(state),
            ),
        ]

    def render_to_text(self, frame: RenderFrame) -> str:
        border = "=" * max(40, len(frame.title))
        return "\n".join([border, frame.title, border, *frame.lines])

    def render(self, frame: RenderFrame) -> str:
        return self.render_to_text(frame)

    def _build_gear_lines(self, state: SaveState) -> list[str]:
        slots = {
            "main_hand": "Main",
            "body": "Body",
            "charm": "Charm",
        }
        lines = [
            f"Power from gear {sum(item.power for item in state.inventory if item.equipped)}",
            f"Inventory {len(state.inventory)} items",
        ]
        for slot_key, label in slots.items():
            item = next(
                (entry for entry in state.inventory if entry.equipped and entry.slot == slot_key),
                None,
            )
            if item is None:
                lines.append(f"{label}: empty")
                continue
            affix = f" [{' / '.join(item.affixes)}]" if item.affixes else ""
            lines.append(f"{label}: {item.name} +{item.power}{affix}")
        consumables = sum(item.quantity for item in state.inventory if item.item_type == "consumable")
        materials = sum(item.quantity for item in state.inventory if item.item_type == "material")
        lines.append(f"Consumables {consumables}  Materials {materials}")
        return lines

    def _build_log_lines(self, state: SaveState) -> list[str]:
        recent = list(reversed(state.activity_log[-6:]))
        if not recent:
            recent = ["No notable events yet."]
        return [f"Last event: {state.world.last_event}", *recent]


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

        y = 4
        draw.text((4, y), frame.title[:28], font=font, fill=0)
        y += 14
        draw.line((2, y, canvas_width - 2, y), fill=0, width=1)
        y += 4

        for raw_line in frame.lines:
            for line in self._wrap_text(raw_line, max_chars=max(12, canvas_width // 7)):
                if y > canvas_height - 12:
                    break
                draw.text((4, y), line, font=font, fill=0)
                y += 12
            if y > canvas_height - 12:
                break

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
