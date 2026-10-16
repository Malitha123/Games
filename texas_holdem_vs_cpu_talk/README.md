# Local Texas Hold'em vs CPU

A complete local, browser-based **No-Limit Texas Hold'em** game written in Python with a vanilla HTML/CSS/JavaScript interface.

You control **one human seat**. Every other player is controlled automatically by the computer.

## Main features

- Choose **2 to 8 total players**
  - 1 human player
  - 1 to 7 computer players
- Default starting stack: **$500**
- Configurable small blind and big blind, default **$5 / $10**
- **Home game dealer mode**
  - Dealer role rotates with the dealer button
- **Casino dealer mode**
  - Fixed house dealer
  - Dealer button still rotates correctly for blinds and action order
- First hand is dealt automatically
- Optional **Auto deal** for subsequent hands, enabled by default
- CPU players automatically:
  - post blinds
  - fold
  - check
  - call
  - bet
  - raise
  - go all-in
  - continue through flop, turn, river and showdown
- CPU actions are shown one at a time in the UI instead of resolving invisibly
- Your hole cards remain visible to you
- CPU hole cards remain hidden until showdown
- Full No-Limit Texas Hold'em betting rules
- Heads-up blind rules
- Minimum raise validation
- Short all-in handling
- Automatic flop, turn, river and showdown
- Full 7-card hand evaluation
- Side pots
- Split pots
- Bust-out detection
- Hand history
- Local browser UI
- No database
- No account
- No internet connection required after download
- No third-party Python packages required

## Computer-player logic

The computer players are not allowed to inspect the human player's hidden cards.

Each CPU decision is based on information it is entitled to know:

- its own two hole cards
- public community cards
- current pot
- amount required to call
- stack sizes
- number of remaining opponents
- legal actions available
- estimated winning equity generated with Monte Carlo card simulations
- pot odds
- its playing personality

CPU seats rotate through several built-in styles:

- **Balanced**
- **Aggressive**
- **Tight**
- **Loose**

These are poker heuristics, not a trained neural-network poker agent. They are intended to provide realistic local casual play while keeping the project lightweight and completely offline.

## Requirements

Python **3.10+** is recommended.

No `pip install` step is required.

## Run on Windows

Unzip the project, then double-click:

```text
start_windows.bat
```

Or open PowerShell / Command Prompt inside the project directory and run:

```bash
python run.py
```

The app opens automatically at:

```text
http://127.0.0.1:8765
```

## Run on macOS / Linux

```bash
chmod +x start_mac_linux.sh
./start_mac_linux.sh
```

Or:

```bash
python3 run.py
```

## How a game works

1. Select the total number of players.
2. Enter your name.
3. Select the starting stack and blinds.
4. Choose Home or Casino dealer mode.
5. Press **Start Game**.
6. The first hand is dealt immediately.
7. Computer seats act automatically whenever it is their turn.
8. When it becomes your turn, Fold, Check, Call, Bet, Raise and All-in controls appear.
9. After the hand ends, the result is displayed.
10. With **Auto deal** enabled, the next hand starts automatically after a short pause.

Turn off **Auto deal** if you want to pause between hands and inspect the result before continuing.

## Tests

Run all tests from the project directory:

```bash
python -m unittest discover -s tests -v
```

The automated tests cover:

- hand evaluation
- button rotation
- heads-up blinds
- dealer modes
- normal betting progression
- chip conservation
- human-card visibility
- CPU-card privacy
- automated CPU decision execution
- randomized human-vs-CPU game simulations

## Project structure

```text
texas_holdem_local/
├── run.py
├── start_windows.bat
├── start_mac_linux.sh
├── poker/
│   ├── __init__.py
│   ├── cards.py
│   ├── evaluator.py
│   ├── game.py
│   ├── bots.py
│   └── server.py
├── web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── tests/
    ├── test_evaluator.py
    ├── test_game.py
    └── test_bots.py
```

## Optional LAN access

By default, the web server is accessible only from the computer running the game.

To deliberately make it reachable from other devices on your trusted home network:

```bash
python run.py --host 0.0.0.0
```

Then open the host computer's LAN IP followed by port `8765`.

There is no login/authentication layer, so do not expose this server directly to the public internet.


## Table talk and pacing

Computer actions are intentionally paced with a randomized 2–4 second delay. The UI shows short table-talk lines such as `CPU 1: “I'll check.”`, `CPU 2: “Raise to $40.”`, or `CPU 3: “I'm out.”`. Your own actions are echoed in the same conversation strip so the hand feels less mechanical.
