from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

from .bots import BotController
from .game import GameError, HoldemGame

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
GAME: HoldemGame | None = None
BOTS: BotController | None = None
LOCK = threading.RLock()


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _public_state(*, bot_action: dict | None = None) -> dict:
    if GAME is None:
        return {"configured": False}
    state = GAME.public_state()
    state["configured"] = True
    if BOTS is not None:
        for p in state["players"]:
            if p.get("is_bot"):
                p["bot_profile"] = BOTS.profile_for(int(p["index"])).name
    if bot_action is not None:
        # Equity is useful internally, but the normal UI only needs the visible action.
        state["bot_action"] = bot_action
    return state


class PokerHandler(BaseHTTPRequestHandler):
    server_version = "LocalHoldem/2.0"

    def log_message(self, fmt: str, *args) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filename: str, content_type: str) -> None:
        path = WEB_DIR / filename
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            raise GameError("Invalid JSON request.") from None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_file("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/state":
            with LOCK:
                self._send_json(_public_state())
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        global GAME, BOTS
        parsed = urlparse(self.path)
        try:
            data = self._read_json()
            with LOCK:
                if parsed.path == "/api/setup":
                    count = int(data.get("player_count", 4))
                    if not 2 <= count <= 8:
                        raise GameError("Choose between 2 and 8 total players.")
                    human_name = str(data.get("human_name", "You")).strip() or "You"
                    names = [human_name] + [f"CPU {i}" for i in range(1, count)]
                    GAME = HoldemGame(
                        names,
                        starting_stack=int(data.get("starting_stack", 500)),
                        small_blind=int(data.get("small_blind", 5)),
                        big_blind=int(data.get("big_blind", 10)),
                        dealer_mode=str(data.get("dealer_mode", "home")),
                        bot_indices=set(range(1, count)),
                    )
                    BOTS = BotController(GAME)
                    # The first hand is dealt immediately. CPU turns are advanced by
                    # /api/bot-step so the browser can visibly animate each action.
                    GAME.new_hand()
                    self._send_json(_public_state())
                    return

                if GAME is None:
                    raise GameError("Create a game first.")

                if parsed.path == "/api/new-hand":
                    GAME.new_hand()
                    self._send_json(_public_state())
                    return

                if parsed.path == "/api/action":
                    idx = GAME.current_player_index
                    if idx is None:
                        raise GameError("No player is waiting to act.")
                    if GAME.players[idx].is_bot:
                        raise GameError("The computer player is acting automatically.")
                    GAME.act(str(data.get("action", "")), data.get("amount"))
                    self._send_json(_public_state())
                    return

                if parsed.path == "/api/bot-step":
                    if BOTS is None:
                        raise GameError("Computer players are not configured.")
                    action = BOTS.step()
                    self._send_json(_public_state(bot_action=action))
                    return

                self.send_error(HTTPStatus.NOT_FOUND)
        except (GameError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"error": f"Unexpected server error: {exc}"}, status=500)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), PokerHandler)
    print(f"Texas Hold'em running at http://{host}:{port}")
    print("You are the human player. All other seats are computer controlled.")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("Server stopped.")
