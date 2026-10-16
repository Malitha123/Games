from __future__ import annotations

from dataclasses import dataclass

from .game import BlackjackGame, GameError, Hand


@dataclass(frozen=True)
class BotProfile:
    name: str


PROFILES = (
    BotProfile("Basic"),
    BotProfile("Calm"),
    BotProfile("Sharp"),
    BotProfile("Bold"),
)


class BotController:
    """Blackjack CPU players using a conventional multi-deck basic strategy."""

    def __init__(self, game: BlackjackGame) -> None:
        self.game = game

    def profile_for(self, player_index: int) -> BotProfile:
        bots = [i for i, p in enumerate(self.game.players) if p.is_bot]
        try:
            slot = bots.index(player_index)
        except ValueError:
            return PROFILES[0]
        return PROFILES[slot % len(PROFILES)]

    def decide(self, player_index: int) -> str:
        game = self.game
        if game.current_player_index != player_index:
            raise GameError("That CPU player is not currently acting.")
        player = game.players[player_index]
        if not player.is_bot:
            raise GameError("The current player is not a CPU player.")
        hand = game.current_hand()
        legal = set(game.legal_actions().get("actions", []))
        if not legal:
            raise GameError("No legal CPU action is available.")

        dealer = game.dealer[0].value
        choice = self._basic_choice(hand, dealer, legal)
        if choice in legal:
            return choice
        if choice == "double" and "hit" in legal:
            return "hit"
        if choice == "split" and "hit" in legal:
            return "hit"
        return "stand" if "stand" in legal else next(iter(legal))

    def _basic_choice(self, hand: Hand, dealer: int, legal: set[str]) -> str:
        total = hand.total

        if "split" in legal:
            rank = hand.cards[0].rank
            if rank in {14, 8}:
                return "split"
            if rank in {10, 11, 12, 13}:
                return "stand"
            if rank == 9:
                return "split" if dealer in {2, 3, 4, 5, 6, 8, 9} else "stand"
            if rank == 7:
                return "split" if dealer in {2, 3, 4, 5, 6, 7} else "hit"
            if rank == 6:
                return "split" if dealer in {2, 3, 4, 5, 6} else "hit"
            if rank == 5:
                return "double" if "double" in legal and dealer <= 9 else "hit"
            if rank == 4:
                return "split" if dealer in {5, 6} else "hit"
            if rank in {2, 3}:
                return "split" if dealer in {2, 3, 4, 5, 6, 7} else "hit"

        if hand.soft and len(hand.cards) >= 2:
            if total >= 19:
                return "stand"
            if total == 18:
                if "double" in legal and dealer in {3, 4, 5, 6}:
                    return "double"
                if dealer in {2, 7, 8}:
                    return "stand"
                return "hit"
            if total == 17:
                return "double" if "double" in legal and dealer in {3, 4, 5, 6} else "hit"
            if total in {15, 16}:
                return "double" if "double" in legal and dealer in {4, 5, 6} else "hit"
            if total in {13, 14}:
                return "double" if "double" in legal and dealer in {5, 6} else "hit"
            return "hit"

        if total >= 17:
            return "stand"
        if 13 <= total <= 16:
            return "stand" if dealer in {2, 3, 4, 5, 6} else "hit"
        if total == 12:
            return "stand" if dealer in {4, 5, 6} else "hit"
        if total == 11:
            return "double" if "double" in legal and dealer != 11 else "hit"
        if total == 10:
            return "double" if "double" in legal and dealer <= 9 else "hit"
        if total == 9:
            return "double" if "double" in legal and dealer in {3, 4, 5, 6} else "hit"
        return "hit"

    def step(self) -> dict:
        idx = self.game.current_player_index
        if idx is None or not self.game.players[idx].is_bot:
            raise GameError("It is not a CPU player's turn.")
        player = self.game.players[idx]
        hand_index = self.game.current_hand_index
        action = self.decide(idx)
        before_bet = self.game.current_hand().bet
        self.game.act(action)
        return {
            "speaker": player.name,
            "player_index": idx,
            "hand_index": hand_index,
            "action": action,
            "amount": before_bet * 2 if action == "double" else before_bet,
            "profile": self.profile_for(idx).name,
        }
