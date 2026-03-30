from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import GameEngine
from .device import TextRenderer
from .models import Item
from .storage import DEFAULT_SAVE_PATH, load_save, save_state


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PiGame Manager</title>
  <style>
    body { font-family: Consolas, monospace; margin: 24px; background: #f4f0e8; color: #1e1e1e; }
    h1 { margin-bottom: 8px; }
    pre { padding: 16px; background: #fffdf7; border: 1px solid #b6ae9f; overflow: auto; }
    form { margin: 16px 0; padding: 12px; background: #fffdf7; border: 1px solid #b6ae9f; }
    input, button { font: inherit; padding: 6px 8px; margin-right: 8px; }
  </style>
</head>
<body>
  <h1>PiGame Manager</h1>
  <p>Use this page when the device is connected to a PC. The form grants a simple item directly into the save file.</p>
  <form method="post" action="/grant">
    <input name="name" value="Field Ration" />
    <input name="item_type" value="consumable" />
    <input name="rarity" value="common" />
    <input name="power" value="0" />
    <input name="level" value="1" />
    <button type="submit">Grant Item</button>
  </form>
  <form method="post" action="/supplies">
    <input name="amount" value="5" />
    <button type="submit">Add Supplies</button>
  </form>
  <h2>Current screen</h2>
  <pre>{screen}</pre>
  <h2>Save state</h2>
  <pre>{state}</pre>
</body>
</html>
"""


class ManagerHandler(BaseHTTPRequestHandler):
    save_path = DEFAULT_SAVE_PATH
    engine = GameEngine()
    renderer = TextRenderer()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(load_save(self.save_path).to_dict())
            return
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        state = load_save(self.save_path)
        frame = self.renderer.build_frame(state, self.engine)
        body = HTML.format(
            screen=self.renderer.render_to_text(frame),
            state=json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        )
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

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

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
