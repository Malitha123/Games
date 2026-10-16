from __future__ import annotations

from dataclasses import dataclass
import random

SUITS = ("♠", "♥", "♦", "♣")
RANKS = tuple(range(2, 15))
RANK_TO_TEXT = {11: "J", 12: "Q", 13: "K", 14: "A"}


@dataclass(frozen=True, order=True)
class Card:
    rank: int
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise ValueError(f"Invalid card rank: {self.rank}")
        if self.suit not in SUITS:
            raise ValueError(f"Invalid card suit: {self.suit}")

    @property
    def rank_text(self) -> str:
        return RANK_TO_TEXT.get(self.rank, str(self.rank))

    @property
    def code(self) -> str:
        return f"{self.rank_text}{self.suit}"

    @property
    def color(self) -> str:
        return "red" if self.suit in {"♥", "♦"} else "black"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "rank": self.rank,
            "rank_text": self.rank_text,
            "suit": self.suit,
            "code": self.code,
            "color": self.color,
        }


class Deck:
    def __init__(self, *, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self.cards = [Card(rank, suit) for suit in SUITS for rank in RANKS]
        self._rng.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            raise RuntimeError("The deck is empty")
        return self.cards.pop()

    def burn(self) -> Card:
        return self.draw()
