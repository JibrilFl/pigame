from __future__ import annotations

import argparse
from pathlib import Path

from .core import GameEngine
from .device import PeerSyncService, build_renderer
from .runtime import GameRuntime, RuntimeConfig
from .storage import DEFAULT_SAVE_PATH, create_new_save, load_save, save_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PiGame CLI")
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a new save")
    init_parser.add_argument("--name", default="Piko")

    run_parser = subparsers.add_parser("run", help="advance the simulation")
    run_parser.add_argument("--ticks", type=int, default=1)

    subparsers.add_parser("render", help="render the current screen")

    peer_parser = subparsers.add_parser("peer", help="simulate nearby peer sync")
    peer_parser.add_argument("--name", required=True)

    daemon_parser = subparsers.add_parser("daemon", help="run autonomous device loop")
    daemon_parser.add_argument("--renderer", default="auto", choices=["auto", "waveshare", "console", "text"])
    daemon_parser.add_argument("--battery-backend", default="auto", choices=["auto", "cw2015", "max17040", "dummy"])
    daemon_parser.add_argument("--battery-bus", type=int, default=1)
    daemon_parser.add_argument("--battery-address", type=lambda value: int(value, 0), default=0x62)
    daemon_parser.add_argument("--tick-seconds", type=int, default=180)
    daemon_parser.add_argument("--render-every", type=int, default=1)
    daemon_parser.add_argument("--sync-every", type=int, default=5)
    daemon_parser.add_argument("--low-battery-percent", type=int, default=15)
    daemon_parser.add_argument("--critical-battery-percent", type=int, default=5)
    daemon_parser.add_argument("--shutdown-command")
    daemon_parser.add_argument("--max-ticks", type=int)
    daemon_parser.add_argument("--no-sleep", action="store_true")

    subparsers.add_parser("hardware-check", help="show Waveshare adapter status")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    engine = GameEngine()
    renderer = build_renderer("text")
    peer_sync = PeerSyncService()

    if args.command == "init":
        state = create_new_save(args.name, args.save)
        print(f"Created save for {state.character.name} at {args.save}")
        return 0

    state = load_save(args.save)

    if args.command == "run":
        for _ in range(args.ticks):
            result = engine.tick(state)
            print(result.summary)
            for item in result.loot:
                print(f"  loot: {item.rarity} {item.name} ({item.item_type})")
            if result.leveled_up:
                print(f"  level up -> {state.character.level}")
        save_state(state, args.save)
        return 0

    if args.command == "render":
        frame = renderer.build_frame(state, engine)
        print(renderer.render(frame))
        return 0

    if args.command == "peer":
        peer_sync.merge_peer_snapshot(state, args.name)
        save_state(state, args.save)
        print(f"Linked with peer {args.name}")
        return 0

    if args.command == "daemon":
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

    if args.command == "hardware-check":
        hw_renderer = build_renderer("waveshare")
        print(f"renderer={type(hw_renderer).__name__}")
        print(f"hardware_ready={getattr(hw_renderer, 'is_hardware_ready', False)}")
        init_error = getattr(hw_renderer, 'init_error', None)
        if init_error:
            print(f"init_error={init_error}")
        return 0

    parser.error("unknown command")
    return 2
