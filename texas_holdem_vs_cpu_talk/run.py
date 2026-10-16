from __future__ import annotations

import argparse
import threading
import webbrowser

from poker.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Texas Hold'em game.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address, default 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port, default 8765")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()

    if not args.no_browser and args.host in {"127.0.0.1", "localhost"}:
        url = f"http://{args.host}:{args.port}"
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    serve(args.host, args.port)


if __name__ == "__main__":
    main()
