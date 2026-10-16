# Local Blackjack vs CPU

A self-contained browser-based Blackjack game powered by Python. You play one manual seat while the other player seats and the house dealer act automatically.

## Features

- 1 to 7 total player seats, one human plus up to six CPU players
- Starting bankroll configurable, default $500
- Table minimum and your default wager configurable
- CPU players place wagers automatically
- Hit, stand, double down, and split
- Up to four hands after splitting
- Split aces receive one card each
- 6-deck shoe with automatic reshuffle when it gets low
- Dealer stands on soft 17
- Natural blackjack pays 3:2
- CPU players use a conventional multi-deck basic strategy
- Dealer hole card stays hidden until the dealer phase
- CPU players and dealer act automatically
- Randomized 2 to 4 second pacing between automated actions
- Table-talk lines such as `CPU 1: “Hit me.”`, `CPU 2: “I’ll stand.”`, and `Dealer: “16. I have to hit.”`
- Automatic next rounds can be enabled or disabled
- No third-party Python packages required

This version intentionally omits insurance and surrender because those rules vary by casino.

## Run on Windows

Unzip the folder and double-click:

```text
start_windows.bat
```

Or run:

```bash
python run.py
```

The browser opens at:

```text
http://127.0.0.1:8766
```

## Run on macOS/Linux

```bash
./start_mac_linux.sh
```

or:

```bash
python3 run.py
```

## Tests

From the project folder:

```bash
python -m unittest discover -s tests -v
```
