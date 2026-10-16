from __future__ import annotations

from dataclasses import dataclass
import random

SUITS = ("♠", "♥", "♦", "♣")
RANKS = tuple(range(2, 15))


@dataclass(frozen=True)
class Card:
    rank: int
    suit: str

    @property
    def rank_text(self) -> str:
        return {11: "J", 12: "Q", 13: "K", 14: "A"}.get(self.rank, str(self.rank))

    @property
    def value(self) -> int:
        if self.rank == 14:
            return 11
        return min(self.rank, 10)

    @property
    def color(self) -> str:
        return "red" if self.suit in {"♥", "♦"} else "black"

    def public(self) -> dict:
        return {
            "rank": self.rank,
            "rank_text": self.rank_text,
            "suit": self.suit,
            "color": self.color,
        }


class Shoe:
    def __init__(self, decks: int = 6, *, seed: int | None = None) -> None:
        if decks < 1:
            raise ValueError("Shoe must contain at least one deck.")
        self.decks = decks
        self.rng = random.Random(seed)
        self.cards: list[Card] = []
        self.shuffle()

    def shuffle(self) -> None:
        self.cards = [Card(rank, suit) for _ in range(self.decks) for suit in SUITS for rank in RANKS]
        self.rng.shuffle(self.cards)

    def ensure_round_capacity(self) -> None:
        # Reshuffle before a round when the shoe is getting shallow.
        if len(self.cards) < 60:
            self.shuffle()

    def draw(self) -> Card:
        if not self.cards:
            self.shuffle()
        return self.cards.pop()
