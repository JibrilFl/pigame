from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .core import GameEngine
from .device import (
    BatteryMonitor,
    Cw2015BatteryMonitor,
    Max17040BatteryMonitor,
    PeerSyncService,
    Renderer,
    build_renderer,
)
from .storage import DEFAULT_SAVE_PATH, load_save, save_state


@dataclass
class RuntimeConfig:
    save_path: Path = DEFAULT_SAVE_PATH
    renderer_mode: str = "auto"
    battery_backend: str = "auto"
    battery_bus: int = 1
    battery_address: int = 0x36
    tick_seconds: int = 180
    render_every_ticks: int = 1
    sync_every_ticks: int = 5
    low_battery_percent: int = 15
    critical_battery_percent: int = 5
    shutdown_command: str | None = None
    max_ticks: int | None = None
    sleep_when_idle: bool = True


class GameRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
        engine: GameEngine | None = None,
        renderer: Renderer | None = None,
        peer_sync: PeerSyncService | None = None,
        battery: BatteryMonitor | None = None,
    ) -> None:
        self.config = config
        self.engine = engine or GameEngine()
        self.renderer = renderer or build_renderer(config.renderer_mode)
        self.peer_sync = peer_sync or PeerSyncService()
        self.battery = battery or self._build_battery_monitor(config)

    def run(self) -> int:
        tick_count = 0
        while True:
            state = load_save(self.config.save_path)
            self._reset_stale_shutdown_request(state)
            tick_count += 1
            result = self.engine.tick(state)
            battery_status = self.battery.read_status()
            self._apply_battery_status(state, battery_status)

            if tick_count % self.config.sync_every_ticks == 0:
                snapshot = self.peer_sync.announce_presence(state)
                state.activity_log.append(
                    f"Presence beacon emitted for {snapshot['name']} lvl {snapshot['level']}."
                )

            if tick_count % self.config.render_every_ticks == 0:
                frame = self.renderer.build_frame(state, self.engine)
                self.renderer.render(frame)

            save_state(state, self.config.save_path)

            if state.device.shutdown_requested:
                self._shutdown_if_configured()
                break

            if self.config.max_ticks is not None and tick_count >= self.config.max_ticks:
                break
            if self.config.sleep_when_idle:
                time.sleep(self.config.tick_seconds)
        return 0

    def _reset_stale_shutdown_request(self, state) -> None:
        if not state.device.shutdown_requested:
            return
        state.device.shutdown_requested = False
        state.device.low_power_mode = False
        if state.device.last_shutdown_reason:
            state.activity_log.append("Cleared stale shutdown request from previous power event.")
        state.device.last_shutdown_reason = ""
        state.activity_log = state.activity_log[-20:]

    def _build_battery_monitor(self, config: RuntimeConfig) -> BatteryMonitor:
        if config.battery_backend == "cw2015":
            return Cw2015BatteryMonitor(
                bus=config.battery_bus,
                address=config.battery_address,
                low_battery_percent=config.low_battery_percent,
                critical_battery_percent=config.critical_battery_percent,
            )
        if config.battery_backend == "max17040":
            return Max17040BatteryMonitor(
                bus=config.battery_bus,
                address=config.battery_address,
                low_battery_percent=config.low_battery_percent,
                critical_battery_percent=config.critical_battery_percent,
            )
        if config.battery_backend == "auto":
            if config.battery_address == 0x62:
                return Cw2015BatteryMonitor(
                    bus=config.battery_bus,
                    address=config.battery_address,
                    low_battery_percent=config.low_battery_percent,
                    critical_battery_percent=config.critical_battery_percent,
                )
            if config.battery_address == 0x36:
                return Max17040BatteryMonitor(
                    bus=config.battery_bus,
                    address=config.battery_address,
                    low_battery_percent=config.low_battery_percent,
                    critical_battery_percent=config.critical_battery_percent,
                )
            return Cw2015BatteryMonitor(
                bus=config.battery_bus,
                address=0x62,
                low_battery_percent=config.low_battery_percent,
                critical_battery_percent=config.critical_battery_percent,
            )
        return BatteryMonitor(
            low_battery_percent=config.low_battery_percent,
            critical_battery_percent=config.critical_battery_percent,
        )

    def _apply_battery_status(self, state, battery_status: dict[str, object]) -> None:
        percent = battery_status.get("battery_percent")
        voltage = battery_status.get("battery_voltage")
        charging = battery_status.get("charging")
        low_power = bool(battery_status.get("low_power"))
        critical_power = bool(battery_status.get("critical_power"))
        reason = str(battery_status.get("reason") or "")

        state.device.battery_percent = percent if isinstance(percent, int) else None
        state.device.battery_voltage = (
            float(voltage) if isinstance(voltage, (int, float)) else None
        )
        state.device.charging = charging if isinstance(charging, bool) else None
        state.device.low_power_mode = low_power

        if low_power and not critical_power:
            state.activity_log.append(
                f"Battery low: {state.device.battery_percent if state.device.battery_percent is not None else '?'}%."
            )

        if critical_power:
            state.device.shutdown_requested = True
            state.device.last_shutdown_reason = reason or "Critical battery level reached."
            state.world.last_event = state.device.last_shutdown_reason
            state.activity_log.append(state.device.last_shutdown_reason)
        else:
            state.device.shutdown_requested = False
            if not low_power:
                state.device.last_shutdown_reason = ""

        state.activity_log = state.activity_log[-20:]

    def _shutdown_if_configured(self) -> None:
        if not self.config.shutdown_command:
            return
        subprocess.run(self.config.shutdown_command, shell=True, check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PiGame runtime daemon")
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE_PATH)
    parser.add_argument("--renderer", default="auto", choices=["auto", "waveshare", "console", "text"])
    parser.add_argument("--battery-backend", default="auto", choices=["auto", "cw2015", "max17040", "dummy"])
    parser.add_argument("--battery-bus", type=int, default=1)
    parser.add_argument("--battery-address", type=lambda value: int(value, 0), default=0x62)
    parser.add_argument("--tick-seconds", type=int, default=180)
    parser.add_argument("--render-every", type=int, default=1)
    parser.add_argument("--sync-every", type=int, default=5)
    parser.add_argument("--low-battery-percent", type=int, default=15)
    parser.add_argument("--critical-battery-percent", type=int, default=5)
    parser.add_argument("--shutdown-command")
    parser.add_argument("--max-ticks", type=int)
    parser.add_argument("--no-sleep", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RuntimeConfig(
        save_path=args.save,
        renderer_mode=args.renderer,
        battery_backend=args.battery_backend,
        battery_bus=args.battery_bus,
        battery_address=args.battery_address,
        tick_seconds=args.tick_seconds,
        render_every_ticks=args.render_every,
        sync_every_ticks=args.sync_every,
        low_battery_percent=args.low_battery_percent,
        critical_battery_percent=args.critical_battery_percent,
        shutdown_command=args.shutdown_command,
        max_ticks=args.max_ticks,
        sleep_when_idle=not args.no_sleep,
    )
    return GameRuntime(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
