from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import GameEngine
from .device import TextRenderer
from .models import Item, SaveState, zero_stats
from .storage import DEFAULT_SAVE_PATH, load_save, save_state


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PiGame Manager</title>
  <style>
    :root {{
      --bg: #efe7d6;
      --panel: #fffaf0;
      --ink: #1f1a16;
      --line: #b7ac97;
      --accent: #8b5e3c;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Consolas, monospace; background: linear-gradient(180deg, #f5efdf, #e8dcc2); color: var(--ink); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    p {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 16px; align-items: start; }}
    .stack {{ display: grid; gap: 16px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); padding: 16px; box-shadow: 0 8px 24px rgba(34, 24, 15, 0.06); }}
    .stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .metric {{ padding: 10px; border: 1px solid var(--line); background: #fffef8; }}
    .metric strong {{ display: block; font-size: 18px; margin-bottom: 4px; }}
    .forms {{ display: grid; gap: 12px; }}
    form {{ display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); background: #fffef8; }}
    input, button, select {{ width: 100%; font: inherit; padding: 8px; border: 1px solid var(--line); background: white; }}
    button {{ background: var(--accent); color: white; border-color: var(--accent); cursor: pointer; }}
    button:hover {{ filter: brightness(0.94); }}
    pre {{ margin: 0; padding: 14px; white-space: pre-wrap; overflow: auto; background: #fffef8; border: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #ddd2bc; padding: 8px 6px; text-align: left; vertical-align: top; }}
    .pill {{ display: inline-block; padding: 2px 6px; border: 1px solid var(--line); background: #f7f0df; }}
  </style>
</head>
<body>
  <main>
    <h1>PiGame Manager</h1>
    <p>Desktop management for the idle e-ink pet. This page is meant for direct editing when the device is connected to a PC or local network.</p>

    <div class="grid">
      <section class="stack">
        <div class="panel">
          <h2>{name}</h2>
          <p><span class="pill">{title}</span> <span class="pill">{specialization}</span> <span class="pill">Activity {activity}</span></p>
          <div class="stats">
            <div class="metric"><strong>Level {level}</strong>XP {xp}</div>
            <div class="metric"><strong>Gold {gold}</strong>Supplies {supplies}</div>
            <div class="metric"><strong>Depth {depth}</strong>Mood {mood}</div>
            <div class="metric"><strong>Power {power}</strong>Vitality {vitality}</div>
            <div class="metric"><strong>Agility {agility}</strong>Insight {insight}</div>
            <div class="metric"><strong>Luck {luck}</strong>Wins {wins} / Losses {losses}</div>
          </div>
        </div>

        <div class="panel">
          <h2>Current Screen</h2>
          <pre>{screen}</pre>
        </div>

        <div class="panel">
          <h2>Equipped Gear</h2>
          {equipped_table}
        </div>

        <div class="panel">
          <h2>Inventory</h2>
          {inventory_table}
        </div>

        <div class="panel">
          <h2>Recent Activity</h2>
          {log_html}
        </div>
      </section>

      <aside class="stack">
        <div class="panel">
          <h2>World</h2>
          <p><strong>Region:</strong> {region}</p>
          <p><strong>Threat:</strong> {threat}</p>
          <p><strong>Danger:</strong> {danger}</p>
          <p><strong>Biome tier:</strong> {biome_tier}</p>
          <p><strong>Battery:</strong> {battery}</p>
          <p><strong>Last event:</strong> {last_event}</p>
        </div>

        <div class="panel">
          <h2>Quick Actions</h2>
          <div class="forms">
            <form method="post" action="/grant">
              <h3>Grant Item</h3>
              <input name="name" value="Field Ration" />
              <select name="item_type">
                <option value="consumable">consumable</option>
                <option value="weapon">weapon</option>
                <option value="armor">armor</option>
                <option value="charm">charm</option>
                <option value="material">material</option>
              </select>
              <input name="rarity" value="common" />
              <input name="power" value="0" />
              <input name="level" value="1" />
              <button type="submit">Grant Item</button>
            </form>

            <form method="post" action="/supplies">
              <h3>Add Supplies</h3>
              <input name="amount" value="5" />
              <button type="submit">Add Supplies</button>
            </form>

            <form method="post" action="/gold">
              <h3>Add Gold</h3>
              <input name="amount" value="100" />
              <button type="submit">Add Gold</button>
            </form>

            <form method="post" action="/xp">
              <h3>Add XP</h3>
              <input name="amount" value="50" />
              <button type="submit">Add XP</button>
            </form>
          </div>
        </div>

        <div class="panel">
          <h2>Raw Save</h2>
          <pre>{state}</pre>
        </div>
      </aside>
    </div>
  </main>
</body>
</html>
"""


class ManagerHandler(BaseHTTPRequestHandler):
    save_path = DEFAULT_SAVE_PATH
    engine = GameEngine()
    renderer = TextRenderer()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        state = load_save(self.save_path)
        if parsed.path == "/api/state":
            self._send_json(state.to_dict())
            return
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = self._build_home(state)
        self._send_html(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw, keep_blank_values=True)
        state = load_save(self.save_path)

        if parsed.path == "/grant":
            item = Item(
                name=form.get("name", ["Item"])[0],
                item_type=form.get("item_type", ["material"])[0],
                rarity=form.get("rarity", ["common"])[0],
                power=int(form.get("power", ["0"])[0]),
                level=int(form.get("level", ["1"])[0]),
                quantity=1,
                stat_bonuses=zero_stats(),
            )
            state.inventory.append(item)
            state.activity_log.append(f"Manager granted item: {item.name}.")
            save_state(state, self.save_path)
            self._redirect_home()
            return

        if parsed.path == "/supplies":
            amount = int(form.get("amount", ["0"])[0])
            state.character.supplies += amount
            state.activity_log.append(f"Manager added {amount} supplies.")
            save_state(state, self.save_path)
            self._redirect_home()
            return

        if parsed.path == "/gold":
            amount = int(form.get("amount", ["0"])[0])
            state.character.gold += amount
            state.activity_log.append(f"Manager added {amount} gold.")
            save_state(state, self.save_path)
            self._redirect_home()
            return

        if parsed.path == "/xp":
            amount = int(form.get("amount", ["0"])[0])
            state.character.experience += amount
            state.activity_log.append(f"Manager added {amount} XP.")
            save_state(state, self.save_path)
            self._redirect_home()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _build_home(self, state: SaveState) -> str:
        frame = self.renderer.build_frame(state, self.engine)
        c = state.character
        battery = (
            f"{state.device.battery_percent}% / {state.device.battery_voltage:.2f}V"
            if state.device.battery_percent is not None and state.device.battery_voltage is not None
            else "unknown"
        )
        return HTML.format(
            name=html.escape(c.name),
            title=html.escape(c.title),
            specialization=html.escape(c.specialization),
            activity=html.escape(c.current_activity),
            level=c.level,
            xp=c.experience,
            gold=c.gold,
            supplies=c.supplies,
            depth=c.dungeon_depth,
            mood=c.mood,
            power=c.stats.power,
            vitality=c.stats.vitality,
            agility=c.stats.agility,
            insight=c.stats.insight,
            luck=c.stats.luck,
            wins=c.wins,
            losses=c.losses,
            region=html.escape(state.world.current_region),
            threat=html.escape(state.world.current_threat),
            danger=state.world.danger_rating,
            biome_tier=state.world.biome_tier,
            battery=html.escape(battery),
            last_event=html.escape(state.world.last_event),
            screen=html.escape(self.renderer.render_to_text(frame)),
            equipped_table=self._render_items_table([item for item in state.inventory if item.equipped], empty_text="No equipment equipped."),
            inventory_table=self._render_items_table(state.inventory, empty_text="Inventory is empty."),
            log_html=self._render_log(state.activity_log),
            state=html.escape(json.dumps(state.to_dict(), ensure_ascii=False, indent=2)),
        )

    def _render_items_table(self, items: list[Item], empty_text: str) -> str:
        if not items:
            return f"<p>{html.escape(empty_text)}</p>"
        rows = []
        for item in items:
            affixes = ", ".join(item.affixes) if item.affixes else "-"
            rows.append(
                "<tr>"
                f"<td>{html.escape(item.name)}</td>"
                f"<td>{html.escape(item.item_type)}</td>"
                f"<td>{html.escape(item.rarity)}</td>"
                f"<td>{item.power}</td>"
                f"<td>{html.escape(item.slot or '-')}</td>"
                f"<td>{'yes' if item.equipped else 'no'}</td>"
                f"<td>{html.escape(affixes)}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr>"
            "<th>Name</th><th>Type</th><th>Rarity</th><th>Power</th><th>Slot</th><th>Eq</th><th>Affixes</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )

    def _render_log(self, activity_log: list[str]) -> str:
        recent = list(reversed(activity_log[-10:]))
        if not recent:
            return "<p>No recent activity.</p>"
        entries = "".join(f"<li>{html.escape(line)}</li>" for line in recent)
        return f"<ol>{entries}</ol>"

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect_home(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PiGame desktop manager")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE_PATH)
    args = parser.parse_args(argv)

    ManagerHandler.save_path = args.save
    server = ThreadingHTTPServer((args.host, args.port), ManagerHandler)
    print(f"PiGame manager listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
