from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

from .bots import BotController
from .game import BlackjackGame, GameError

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
GAME: BlackjackGame | None = None
BOTS: BotController | None = None
LOCK = threading.RLock()


def _speech(action: dict) -> str:
    who = action.get("speaker", "Player")
    act = action.get("action", "")
    amount = action.get("amount")
    total = action.get("total")
    if who == "Dealer":
        if act == "hit":
            return f'Dealer: “{total}. I have to hit.”'
        if act == "stand":
            return f'Dealer: “{total}. I’ll stand.”'
        return 'Dealer: “All remaining hands are settled.”'
    if act == "hit":
        return f'{who}: “Hit me.”'
    if act == "stand":
        return f'{who}: “I’ll stand.”'
    if act == "double":
        return f'{who}: “Double down.”'
    if act == "split":
        return f'{who}: “I’ll split them.”'
    return f'{who}: “{act.title()}.”'


def _public_state(*, auto_action: dict | None = None) -> dict:
    if GAME is None:
        return {"configured": False}
    state = GAME.public_state()
    state["configured"] = True
    if BOTS is not None:
        for p in state["players"]:
            if p.get("is_bot"):
                p["bot_profile"] = BOTS.profile_for(int(p["index"])).name
    if auto_action is not None:
        auto_action = dict(auto_action)
        auto_action["speech"] = _speech(auto_action)
        state["auto_action"] = auto_action
    return state


class BlackjackHandler(BaseHTTPRequestHandler):
    server_version = "LocalBlackjack/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
        path = urlparse(self.path).path
        if path == "/":
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/styles.css":
            self._send_file("styles.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_file("app.js", "application/javascript; charset=utf-8")
        elif path == "/api/state":
            with LOCK:
                self._send_json(_public_state())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        global GAME, BOTS
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            with LOCK:
                if path == "/api/setup":
                    count = int(data.get("player_count", 4))
                    if not 1 <= count <= 7:
                        raise GameError("Choose between 1 and 7 total player seats.")
                    human_name = str(data.get("human_name", "You")).strip() or "You"
                    names = [human_name] + [f"CPU {i}" for i in range(1, count)]
                    GAME = BlackjackGame(
                        names,
                        starting_stack=float(data.get("starting_stack", 500)),
                        minimum_bet=float(data.get("minimum_bet", 10)),
                        bot_indices=set(range(1, count)),
                    )
                    BOTS = BotController(GAME)
                    GAME.new_round(float(data.get("default_bet", data.get("minimum_bet", 10))))
                    self._send_json(_public_state())
                    return

                if GAME is None:
                    raise GameError("Create a game first.")

                if path == "/api/new-round":
                    GAME.new_round(float(data.get("bet", GAME.last_human_bet)))
                    self._send_json(_public_state())
                    return

                if path == "/api/action":
                    idx = GAME.current_player_index
                    if idx is None:
                        raise GameError("No player is waiting to act.")
                    if GAME.players[idx].is_bot:
                        raise GameError("The CPU player is acting automatically.")
                    GAME.act(str(data.get("action", "")))
                    self._send_json(_public_state())
                    return

                if path == "/api/auto-step":
                    if GAME.phase == "player_turns":
                        if BOTS is None or not GAME.current_player_is_bot:
                            raise GameError("No CPU action is waiting.")
                        action = BOTS.step()
                    elif GAME.phase == "dealer_turn":
                        action = GAME.dealer_step()
                    else:
                        raise GameError("No automatic action is waiting.")
                    self._send_json(_public_state(auto_action=action))
                    return

                self.send_error(HTTPStatus.NOT_FOUND)
        except (GameError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"error": f"Unexpected server error: {exc}"}, status=500)


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    server = ThreadingHTTPServer((host, port), BlackjackHandler)
    print(f"Blackjack running at http://{host}:{port}")
    print("You are the human player. Other seats and the dealer play automatically.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Server stopped.")
