from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable

from .cards import Card

CATEGORY_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "One Pair",
    0: "High Card",
}


def _straight_high(ranks: Iterable[int]) -> int | None:
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    for i in range(len(unique) - 4):
        window = unique[i : i + 5]
        if window[0] - window[4] == 4 and len(set(window)) == 5:
            return window[0]
    return None


def evaluate_five(cards: Iterable[Card]) -> tuple[int, ...]:
    cards = list(cards)
    if len(cards) != 5:
        raise ValueError("evaluate_five requires exactly five cards")

    ranks = [c.rank for c in cards]
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    is_flush = len({c.suit for c in cards}) == 1
    straight_high = _straight_high(ranks)

    if is_flush and straight_high is not None:
        return (8, straight_high)

    if groups[0][0] == 4:
        quad_rank = groups[0][1]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        return (7, quad_rank, kicker)

    if sorted(counts.values()) == [2, 3]:
        trip_rank = max(rank for rank, count in counts.items() if count == 3)
        pair_rank = max(rank for rank, count in counts.items() if count == 2)
        return (6, trip_rank, pair_rank)

    if is_flush:
        return (5, *sorted(ranks, reverse=True))

    if straight_high is not None:
        return (4, straight_high)

    if groups[0][0] == 3:
        trip_rank = groups[0][1]
        kickers = sorted((rank for rank in ranks if rank != trip_rank), reverse=True)
        return (3, trip_rank, *kickers)

    pairs = sorted((rank for rank, count in counts.items() if count == 2), reverse=True)
    if len(pairs) == 2:
        kicker = max(rank for rank in ranks if rank not in pairs)
        return (2, pairs[0], pairs[1], kicker)

    if len(pairs) == 1:
        pair_rank = pairs[0]
        kickers = sorted((rank for rank in ranks if rank != pair_rank), reverse=True)
        return (1, pair_rank, *kickers)

    return (0, *sorted(ranks, reverse=True))


def evaluate_best(cards: Iterable[Card]) -> tuple[tuple[int, ...], tuple[Card, ...]]:
    cards = list(cards)
    if not 5 <= len(cards) <= 7:
        raise ValueError("evaluate_best requires between five and seven cards")

    best_score: tuple[int, ...] | None = None
    best_cards: tuple[Card, ...] | None = None
    for combo in combinations(cards, 5):
        score = evaluate_five(combo)
        if best_score is None or score > best_score:
            best_score = score
            best_cards = combo

    assert best_score is not None and best_cards is not None
    return best_score, best_cards


def describe_score(score: tuple[int, ...]) -> str:
    return CATEGORY_NAMES[score[0]]
