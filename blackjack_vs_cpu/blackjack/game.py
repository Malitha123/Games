from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import random

from .cards import Card, Shoe


class GameError(ValueError):
    pass


def hand_value(cards: list[Card]) -> tuple[int, bool]:
    total = sum(card.value for card in cards)
    aces = sum(card.rank == 14 for card in cards)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    # A hand is soft if at least one ace is still counted as 11.
    soft = any(card.rank == 14 for card in cards) and total <= 21 and sum(card.value for card in cards) == total
    if not soft and any(card.rank == 14 for card in cards):
        raw = sum(card.value for card in cards)
        reductions = (raw - total) // 10
        soft = sum(card.rank == 14 for card in cards) > reductions
    return total, soft


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    bet: float = 0.0
    status: str = "playing"  # playing, stand, bust, blackjack
    from_split: bool = False
    split_aces: bool = False
    outcome: str = ""
    payout: float = 0.0

    @property
    def total(self) -> int:
        return hand_value(self.cards)[0]

    @property
    def soft(self) -> bool:
        return hand_value(self.cards)[1]

    @property
    def is_blackjack(self) -> bool:
        return not self.from_split and len(self.cards) == 2 and self.total == 21


@dataclass
class Player:
    name: str
    stack: float
    is_bot: bool = False
    hands: list[Hand] = field(default_factory=list)
    round_bet: float = 0.0

    def reset_round(self) -> None:
        self.hands = []
        self.round_bet = 0.0


class BlackjackGame:
    """Local blackjack engine for one human and automated CPU seats.

    Rules used by the app:
    * 6-deck shoe
    * dealer stands on soft 17
    * blackjack pays 3:2
    * double on any first two cards, including after split
    * split to a maximum of four hands
    * split aces receive one card each and then stand
    * no insurance and no surrender
    """

    def __init__(
        self,
        player_names: list[str],
        *,
        starting_stack: float = 500,
        minimum_bet: float = 10,
        bot_indices: set[int] | None = None,
        decks: int = 6,
        seed: int | None = None,
    ) -> None:
        if not 1 <= len(player_names) <= 7:
            raise GameError("Blackjack supports 1 to 7 player seats in this app.")
        if starting_stack <= 0:
            raise GameError("Starting bankroll must be greater than zero.")
        if minimum_bet <= 0:
            raise GameError("Minimum bet must be greater than zero.")
        if len({n.strip().lower() for n in player_names}) != len(player_names):
            raise GameError("Player names must be unique.")
        if any(not n.strip() for n in player_names):
            raise GameError("Player names cannot be blank.")

        bots = bot_indices or set()
        self.players = [Player(name.strip(), float(starting_stack), i in bots) for i, name in enumerate(player_names)]
        self.human_index = next((i for i, p in enumerate(self.players) if not p.is_bot), 0)
        self.minimum_bet = float(minimum_bet)
        self.shoe = Shoe(decks, seed=seed)
        self.rng = random.Random(seed)
        self.round_number = 0
        self.phase = "waiting"  # waiting, player_turns, dealer_turn, complete
        self.dealer: list[Card] = []
        self.dealer_hole_revealed = False
        self.current_player_index: int | None = None
        self.current_hand_index: int | None = None
        self.log: list[str] = []
        self.last_result: list[str] = []
        self.last_human_bet = self.minimum_bet

    @property
    def human(self) -> Player:
        return self.players[self.human_index]

    @property
    def can_start_round(self) -> bool:
        return self.phase in {"waiting", "complete"} and self.human.stack > 0

    @property
    def human_broke(self) -> bool:
        return self.human.stack <= 0

    @property
    def current_player_is_bot(self) -> bool:
        return self.current_player_index is not None and self.players[self.current_player_index].is_bot

    def _fmt(self, amount: float) -> str:
        if abs(amount - round(amount)) < 1e-9:
            return f"${int(round(amount)):,}"
        return f"${amount:,.2f}"

    def _cpu_bet(self, player: Player) -> float:
        if player.stack <= 0:
            return 0.0
        base = min(self.minimum_bet, player.stack)
        if player.stack <= self.minimum_bet:
            return player.stack
        # Mostly table minimum, with occasional 2x/3x bets for variety.
        unit = self.minimum_bet
        multiplier = self.rng.choices([1, 2, 3], weights=[72, 21, 7], k=1)[0]
        return min(player.stack, unit * multiplier)

    def new_round(self, human_bet: float | int | None = None) -> None:
        if self.human.stack <= 0:
            raise GameError("You are out of bankroll. Start a new game to continue.")
        if self.phase not in {"waiting", "complete"}:
            raise GameError("The current round is still in progress.")

        self.shoe.ensure_round_capacity()
        self.round_number += 1
        self.phase = "player_turns"
        self.dealer = []
        self.dealer_hole_revealed = False
        self.current_player_index = None
        self.current_hand_index = None
        self.log = []
        self.last_result = []
        for p in self.players:
            p.reset_round()

        requested = float(self.last_human_bet if human_bet is None else human_bet)
        if requested <= 0:
            raise GameError("Your bet must be greater than zero.")
        if requested > self.human.stack:
            raise GameError("Your bet cannot exceed your bankroll.")
        if requested < self.minimum_bet and requested < self.human.stack:
            raise GameError(f"Minimum bet is {self._fmt(self.minimum_bet)}.")
        self.last_human_bet = requested

        bets: list[float] = []
        for i, p in enumerate(self.players):
            if p.stack <= 0:
                bets.append(0.0)
                continue
            bet = requested if i == self.human_index else self._cpu_bet(p)
            if bet <= 0:
                bets.append(0.0)
                continue
            p.stack -= bet
            p.round_bet = bet
            p.hands = [Hand(bet=bet)]
            bets.append(bet)
            self.log.append(f"{p.name} bets {self._fmt(bet)}.")

        active = [i for i, p in enumerate(self.players) if p.hands]
        if not active:
            raise GameError("No players can afford a wager.")

        # Standard two-pass deal, dealer receives one up card and one hole card.
        for i in active:
            self.players[i].hands[0].cards.append(self.shoe.draw())
        self.dealer.append(self.shoe.draw())
        for i in active:
            self.players[i].hands[0].cards.append(self.shoe.draw())
        self.dealer.append(self.shoe.draw())
        self.log.append("Dealer deals two cards to each active player.")

        for p in self.players:
            for hand in p.hands:
                if hand.is_blackjack:
                    hand.status = "blackjack"
                    self.log.append(f"{p.name} has blackjack.")

        if self._dealer_blackjack():
            self.dealer_hole_revealed = True
            self.log.append("Dealer has blackjack.")
            self._settle(dealer_blackjack=True)
            return

        if not self._set_first_playing_hand():
            # Everyone has a natural blackjack. Dealer cannot have one here.
            self.dealer_hole_revealed = True
            self._settle()

    def _dealer_blackjack(self) -> bool:
        return len(self.dealer) == 2 and hand_value(self.dealer)[0] == 21

    def _set_first_playing_hand(self) -> bool:
        for pi, p in enumerate(self.players):
            for hi, hand in enumerate(p.hands):
                if hand.status == "playing":
                    self.current_player_index = pi
                    self.current_hand_index = hi
                    return True
        self._begin_dealer_turn()
        return False

    def _begin_dealer_turn(self) -> None:
        self.current_player_index = None
        self.current_hand_index = None
        self.phase = "dealer_turn"
        self.dealer_hole_revealed = True
        self.log.append("Dealer reveals the hole card.")

    def current_hand(self) -> Hand:
        if self.current_player_index is None or self.current_hand_index is None:
            raise GameError("No player hand is waiting to act.")
        return self.players[self.current_player_index].hands[self.current_hand_index]

    def legal_actions(self) -> dict[str, Any]:
        if self.phase != "player_turns" or self.current_player_index is None:
            return {"actions": []}
        hand = self.current_hand()
        player = self.players[self.current_player_index]
        if hand.status != "playing":
            return {"actions": []}
        actions = ["hit", "stand"]
        if len(hand.cards) == 2 and player.stack >= hand.bet:
            actions.append("double")
            if len(player.hands) < 4 and hand.cards[0].rank == hand.cards[1].rank:
                actions.append("split")
        return {
            "actions": actions,
            "hand_total": hand.total,
            "soft": hand.soft,
            "bet": hand.bet,
            "stack": player.stack,
        }

    def act(self, action: str) -> None:
        if self.phase != "player_turns" or self.current_player_index is None:
            raise GameError("No player is waiting to act.")
        action = str(action).lower().strip()
        legal = self.legal_actions()["actions"]
        if action not in legal:
            raise GameError(f"{action or 'That action'} is not legal right now.")

        pi = self.current_player_index
        hi = self.current_hand_index
        assert hi is not None
        player = self.players[pi]
        hand = player.hands[hi]

        if action == "hit":
            card = self.shoe.draw()
            hand.cards.append(card)
            self.log.append(f"{player.name} hits and receives {card.rank_text}{card.suit}.")
            if hand.total > 21:
                hand.status = "bust"
                self.log.append(f"{player.name} busts with {hand.total}.")
                self._advance_after(pi, hi)
            elif hand.total == 21:
                hand.status = "stand"
                self.log.append(f"{player.name} has 21 and stands.")
                self._advance_after(pi, hi)
            return

        if action == "stand":
            hand.status = "stand"
            self.log.append(f"{player.name} stands on {hand.total}.")
            self._advance_after(pi, hi)
            return

        if action == "double":
            if player.stack < hand.bet:
                raise GameError("Not enough bankroll to double.")
            player.stack -= hand.bet
            hand.bet *= 2
            card = self.shoe.draw()
            hand.cards.append(card)
            hand.status = "bust" if hand.total > 21 else "stand"
            self.log.append(f"{player.name} doubles to {self._fmt(hand.bet)} and receives {card.rank_text}{card.suit}.")
            if hand.status == "bust":
                self.log.append(f"{player.name} busts with {hand.total}.")
            self._advance_after(pi, hi)
            return

        if action == "split":
            if len(hand.cards) != 2 or hand.cards[0].rank != hand.cards[1].rank:
                raise GameError("Only a matching pair can be split.")
            if len(player.hands) >= 4:
                raise GameError("Maximum of four hands after splitting.")
            if player.stack < hand.bet:
                raise GameError("Not enough bankroll to split.")
            player.stack -= hand.bet
            first_card, second_card = hand.cards
            is_aces = first_card.rank == 14
            h1 = Hand(cards=[first_card, self.shoe.draw()], bet=hand.bet, from_split=True, split_aces=is_aces)
            h2 = Hand(cards=[second_card, self.shoe.draw()], bet=hand.bet, from_split=True, split_aces=is_aces)
            if is_aces:
                h1.status = "stand"
                h2.status = "stand"
            player.hands[hi:hi + 1] = [h1, h2]
            self.log.append(f"{player.name} splits the pair into two {self._fmt(hand.bet)} hands.")
            if is_aces:
                self.log.append(f"{player.name}'s split aces receive one card each and stand.")
                self._advance_after(pi, hi + 1)
            else:
                self.current_hand_index = hi
            return

    def _advance_after(self, player_index: int, hand_index: int) -> None:
        # Search remaining hands of current player, then later seats.
        p = self.players[player_index]
        for hi in range(hand_index + 1, len(p.hands)):
            if p.hands[hi].status == "playing":
                self.current_player_index = player_index
                self.current_hand_index = hi
                return
        for pi in range(player_index + 1, len(self.players)):
            for hi, hand in enumerate(self.players[pi].hands):
                if hand.status == "playing":
                    self.current_player_index = pi
                    self.current_hand_index = hi
                    return
        self._begin_dealer_turn()

    def dealer_step(self) -> dict[str, Any]:
        if self.phase != "dealer_turn":
            raise GameError("It is not the dealer's turn.")

        live_non_blackjack = [
            h for p in self.players for h in p.hands
            if h.status != "bust" and h.status != "blackjack"
        ]
        if not live_non_blackjack:
            self._settle()
            return {"speaker": "Dealer", "action": "collect", "total": hand_value(self.dealer)[0]}

        total, soft = hand_value(self.dealer)
        if total < 17:
            card = self.shoe.draw()
            self.dealer.append(card)
            total, soft = hand_value(self.dealer)
            self.log.append(f"Dealer hits and draws {card.rank_text}{card.suit}, total {total}.")
            if total > 21:
                self.log.append(f"Dealer busts with {total}.")
                self._settle()
            return {
                "speaker": "Dealer",
                "action": "hit",
                "card": card.public(),
                "total": total,
                "soft": soft,
                "resolved": self.phase == "complete",
            }

        self.log.append(f"Dealer stands on {total}.")
        self._settle()
        return {"speaker": "Dealer", "action": "stand", "total": total, "soft": soft, "resolved": True}

    def _settle(self, *, dealer_blackjack: bool = False) -> None:
        dealer_total, _ = hand_value(self.dealer)
        dealer_bust = dealer_total > 21
        results: list[str] = []
        for p in self.players:
            for hi, hand in enumerate(p.hands, start=1):
                if dealer_blackjack:
                    if hand.is_blackjack:
                        p.stack += hand.bet
                        hand.outcome = "Push"
                        hand.payout = hand.bet
                    else:
                        hand.outcome = "Loss"
                        hand.payout = 0.0
                elif hand.status == "bust":
                    hand.outcome = "Loss"
                    hand.payout = 0.0
                elif hand.is_blackjack:
                    hand.payout = hand.bet * 2.5
                    p.stack += hand.payout
                    hand.outcome = f"Blackjack +{self._fmt(hand.bet * 1.5)}"
                elif dealer_bust:
                    hand.payout = hand.bet * 2
                    p.stack += hand.payout
                    hand.outcome = f"Win +{self._fmt(hand.bet)}"
                elif hand.total > dealer_total:
                    hand.payout = hand.bet * 2
                    p.stack += hand.payout
                    hand.outcome = f"Win +{self._fmt(hand.bet)}"
                elif hand.total == dealer_total:
                    hand.payout = hand.bet
                    p.stack += hand.payout
                    hand.outcome = "Push"
                else:
                    hand.outcome = "Loss"
                    hand.payout = 0.0

                suffix = f" hand {hi}" if len(p.hands) > 1 else ""
                results.append(f"{p.name}{suffix}: {hand.outcome} ({hand.total})")

        self.phase = "complete"
        self.current_player_index = None
        self.current_hand_index = None
        self.dealer_hole_revealed = True
        self.last_result = results
        self.log.extend(results)

    def public_state(self) -> dict[str, Any]:
        reveal_dealer = self.dealer_hole_revealed or self.phase in {"dealer_turn", "complete"}
        dealer_cards: list[dict | None] = []
        for i, card in enumerate(self.dealer):
            dealer_cards.append(card.public() if reveal_dealer or i == 0 else None)

        players = []
        for pi, p in enumerate(self.players):
            hand_states = []
            for hi, hand in enumerate(p.hands):
                hand_states.append({
                    "index": hi,
                    "cards": [c.public() for c in hand.cards],
                    "bet": hand.bet,
                    "total": hand.total,
                    "soft": hand.soft,
                    "status": hand.status,
                    "outcome": hand.outcome,
                    "is_current": pi == self.current_player_index and hi == self.current_hand_index,
                })
            players.append({
                "index": pi,
                "name": p.name,
                "stack": p.stack,
                "is_bot": p.is_bot,
                "hands": hand_states,
                "round_bet": p.round_bet,
                "is_current": pi == self.current_player_index,
                "broke": p.stack <= 0 and not p.hands,
            })

        dealer_total = hand_value(self.dealer)[0] if self.dealer else 0
        return {
            "round_number": self.round_number,
            "phase": self.phase,
            "players": players,
            "human_index": self.human_index,
            "human_broke": self.human_broke,
            "can_start_round": self.can_start_round,
            "current_player_index": self.current_player_index,
            "current_hand_index": self.current_hand_index,
            "current_player_is_bot": self.current_player_is_bot,
            "legal": self.legal_actions() if self.current_player_index == self.human_index else {"actions": []},
            "dealer": {
                "cards": dealer_cards,
                "total": dealer_total if reveal_dealer else (self.dealer[0].value if self.dealer else 0),
                "revealed": reveal_dealer,
            },
            "minimum_bet": self.minimum_bet,
            "last_human_bet": self.last_human_bet,
            "shoe_remaining": len(self.shoe.cards),
            "hand_log": list(self.log),
            "last_result": list(self.last_result),
        }
