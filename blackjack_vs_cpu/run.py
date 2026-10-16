from __future__ import annotations

import threading
import time
import webbrowser

from blackjack.server import serve


if __name__ == "__main__":
    url = "http://127.0.0.1:8766"
    threading.Thread(target=lambda: (time.sleep(0.7), webbrowser.open(url)), daemon=True).start()
    serve()
