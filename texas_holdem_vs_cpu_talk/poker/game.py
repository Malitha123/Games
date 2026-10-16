from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any

from .cards import Card, Deck
from .evaluator import describe_score, evaluate_best


class GameError(ValueError):
    pass


@dataclass
class Player:
    name: str
    stack: int
    hole: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    bet_round: int = 0
    total_bet: int = 0
    in_hand: bool = False
    last_acted_generation: int = -1
    is_bot: bool = False

    def reset_for_hand(self) -> None:
        self.hole = []
        self.folded = False
        self.all_in = False
        self.bet_round = 0
        self.total_bet = 0
        self.in_hand = self.stack > 0
        self.last_acted_generation = -1


class HoldemGame:
    """No-limit Texas Hold'em engine supporting human and computer-controlled seats."""

    def __init__(
        self,
        player_names: list[str],
        *,
        starting_stack: int = 500,
        small_blind: int = 5,
        big_blind: int = 10,
        dealer_mode: str = "home",
        bot_indices: set[int] | None = None,
        seed: int | None = None,
    ) -> None:
        if not 2 <= len(player_names) <= 8:
            raise GameError("Texas Hold'em requires 2 to 8 players in this app.")
        if len({name.strip().lower() for name in player_names}) != len(player_names):
            raise GameError("Player names must be unique.")
        if any(not name.strip() for name in player_names):
            raise GameError("Player names cannot be blank.")
        if starting_stack <= 0:
            raise GameError("Starting stack must be greater than zero.")
        if small_blind <= 0 or big_blind <= 0 or small_blind >= big_blind:
            raise GameError("Blinds must satisfy 0 < small blind < big blind.")
        if dealer_mode not in {"home", "casino"}:
            raise GameError("Dealer mode must be 'home' or 'casino'.")

        bot_indices = set(bot_indices or set())
        if any(i < 0 or i >= len(player_names) for i in bot_indices):
            raise GameError("Bot seat index is out of range.")
        self.players = [
            Player(name.strip(), int(starting_stack), is_bot=(i in bot_indices))
            for i, name in enumerate(player_names)
        ]
        self.starting_stack = int(starting_stack)
        self.small_blind = int(small_blind)
        self.big_blind = int(big_blind)
        self.dealer_mode = dealer_mode
        self.rng = random.Random(seed)

        self.button_index = -1
        self.hand_number = 0
        self.deck: Deck | None = None
        self.community: list[Card] = []
        self.street = "waiting"
        self.pot = 0
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.action_generation = 0
        self.current_player_index: int | None = None
        self.small_blind_index: int | None = None
        self.big_blind_index: int | None = None
        self.hand_log: list[str] = []
        self.last_result: list[str] = []
        self.showdown_revealed = False
        self.human_index = next((i for i, p in enumerate(self.players) if not p.is_bot), None)

    # ---------- table helpers ----------
    def _funded_indices(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if p.stack > 0]

    def _hand_indices(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if p.in_hand]

    def _contender_indices(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if p.in_hand and not p.folded]

    def _actionable_indices(self) -> list[int]:
        return [
            i
            for i, p in enumerate(self.players)
            if p.in_hand and not p.folded and not p.all_in and p.stack > 0
        ]

    def _next_matching(self, start: int, valid: set[int]) -> int | None:
        if not valid:
            return None
        n = len(self.players)
        for step in range(1, n + 1):
            idx = (start + step) % n
            if idx in valid:
                return idx
        return None

    def _clockwise(self, start_exclusive: int, candidates: set[int]) -> list[int]:
        n = len(self.players)
        order: list[int] = []
        for step in range(1, n + 1):
            idx = (start_exclusive + step) % n
            if idx in candidates:
                order.append(idx)
        return order

    def _next_funded_button(self) -> int:
        funded = set(self._funded_indices())
        if len(funded) < 2:
            raise GameError("At least two players need chips to start a hand.")
        if self.button_index < 0:
            return min(funded)
        nxt = self._next_matching(self.button_index, funded)
        assert nxt is not None
        return nxt

    @property
    def dealer_display(self) -> str:
        if self.dealer_mode == "casino":
            return "House Dealer (fixed)"
        if self.button_index >= 0:
            return self.players[self.button_index].name
        return "Not assigned"

    # ---------- hand lifecycle ----------
    def new_hand(self) -> None:
        if self.street not in {"waiting", "complete"}:
            raise GameError("Finish the current hand before starting a new one.")
        if len(self._funded_indices()) < 2:
            raise GameError("At least two players need chips to continue.")

        self.hand_number += 1
        self.button_index = self._next_funded_button()
        self.deck = Deck(rng=self.rng)
        self.community = []
        self.street = "preflop"
        self.pot = 0
        self.current_bet = self.big_blind
        self.min_raise = self.big_blind
        self.action_generation = 0
        self.current_player_index = None
        self.small_blind_index = None
        self.big_blind_index = None
        self.hand_log = [f"Hand #{self.hand_number} started."]
        self.last_result = []
        self.showdown_revealed = False

        for p in self.players:
            p.reset_for_hand()

        active = set(self._hand_indices())
        if len(active) == 2:
            # Heads-up: button is small blind, the other player is big blind.
            self.small_blind_index = self.button_index
            self.big_blind_index = self._next_matching(self.button_index, active)
        else:
            self.small_blind_index = self._next_matching(self.button_index, active)
            assert self.small_blind_index is not None
            self.big_blind_index = self._next_matching(self.small_blind_index, active)

        assert self.small_blind_index is not None and self.big_blind_index is not None
        self._post_blind(self.small_blind_index, self.small_blind, "small blind")
        self._post_blind(self.big_blind_index, self.big_blind, "big blind")

        # Deal one card at a time, starting left of the button.
        assert self.deck is not None
        deal_order = self._clockwise(self.button_index, active)
        for _ in range(2):
            for idx in deal_order:
                self.players[idx].hole.append(self.deck.draw())

        for p in self.players:
            p.last_acted_generation = -1

        self._select_next_actor(self.big_blind_index)
        self._advance_until_action_or_complete()

    def _post_blind(self, idx: int, amount: int, label: str) -> None:
        paid = self._commit(idx, min(amount, self.players[idx].stack))
        self.hand_log.append(f"{self.players[idx].name} posts {label} ${paid}.")

    def _commit(self, idx: int, amount: int) -> int:
        p = self.players[idx]
        amount = max(0, min(int(amount), p.stack))
        p.stack -= amount
        p.bet_round += amount
        p.total_bet += amount
        self.pot += amount
        if p.stack == 0 and p.in_hand and not p.folded:
            p.all_in = True
        return amount

    # ---------- betting ----------
    def _needs_action(self, idx: int) -> bool:
        p = self.players[idx]
        if not (p.in_hand and not p.folded and not p.all_in and p.stack > 0):
            return False
        return p.last_acted_generation != self.action_generation or p.bet_round < self.current_bet

    def _round_complete(self) -> bool:
        actionable = self._actionable_indices()
        return all(not self._needs_action(i) for i in actionable)

    def _select_next_actor(self, after_idx: int) -> None:
        candidates = {i for i in self._actionable_indices() if self._needs_action(i)}
        self.current_player_index = self._next_matching(after_idx, candidates)

    def _raise_rights_open(self, idx: int) -> bool:
        return self.players[idx].last_acted_generation != self.action_generation

    def legal_actions(self) -> dict[str, Any]:
        idx = self.current_player_index
        if idx is None or self.street not in {"preflop", "flop", "turn", "river"}:
            return {"actions": []}

        p = self.players[idx]
        to_call = max(0, self.current_bet - p.bet_round)
        max_target = p.bet_round + p.stack
        actions = ["fold"]
        if to_call == 0:
            actions.append("check")
        else:
            actions.append("call")

        raise_open = self._raise_rights_open(idx)
        min_target = None
        if self.current_bet == 0:
            if p.stack > 0:
                actions.append("bet")
                min_target = min(self.big_blind, max_target)
        elif raise_open and max_target > self.current_bet:
            actions.append("raise")
            min_target = min(self.current_bet + self.min_raise, max_target)

        # All-in is always legal as a call/check equivalent. It is only a raise if raise rights are open.
        if p.stack > 0 and (max_target <= self.current_bet or self.current_bet == 0 or raise_open):
            actions.append("all_in")

        return {
            "actions": actions,
            "to_call": to_call,
            "current_bet": self.current_bet,
            "min_raise_to": min_target,
            "max_raise_to": max_target,
            "min_raise_size": self.min_raise,
        }

    def act(self, action: str, amount: int | None = None) -> None:
        idx = self.current_player_index
        if idx is None:
            raise GameError("There is no player waiting to act.")
        if action not in {"fold", "check", "call", "bet", "raise", "all_in"}:
            raise GameError("Unknown action.")

        p = self.players[idx]
        legal = self.legal_actions()["actions"]
        if action not in legal:
            raise GameError(f"{action.replace('_', ' ').title()} is not legal right now.")

        previous_bet = self.current_bet
        full_raise = False

        if action == "fold":
            p.folded = True
            p.last_acted_generation = self.action_generation
            self.hand_log.append(f"{p.name} folds.")

        elif action == "check":
            p.last_acted_generation = self.action_generation
            self.hand_log.append(f"{p.name} checks.")

        elif action == "call":
            needed = max(0, self.current_bet - p.bet_round)
            paid = self._commit(idx, needed)
            p.last_acted_generation = self.action_generation
            suffix = " and is all-in" if p.all_in else ""
            self.hand_log.append(f"{p.name} calls ${paid}{suffix}.")

        elif action in {"bet", "raise"}:
            if amount is None:
                raise GameError("Enter a target amount for the bet or raise.")
            try:
                target = int(amount)
            except (TypeError, ValueError):
                raise GameError("Bet amount must be a whole number.") from None
            max_target = p.bet_round + p.stack
            if target <= p.bet_round or target > max_target:
                raise GameError(f"Target must be between ${p.bet_round + 1} and ${max_target}.")

            if action == "bet":
                if previous_bet != 0:
                    raise GameError("Use raise when there is already a bet.")
                minimum = self.big_blind
                if target < minimum and target != max_target:
                    raise GameError(f"Minimum bet is ${minimum}, unless moving all-in.")
                self._commit(idx, target - p.bet_round)
                self.current_bet = target
                raise_size = target
                full_raise = raise_size >= self.big_blind
                if full_raise:
                    self.min_raise = raise_size
                self.hand_log.append(f"{p.name} bets to ${target}{' all-in' if p.all_in else ''}.")
            else:
                if previous_bet == 0:
                    raise GameError("Use bet when no bet exists yet.")
                if not self._raise_rights_open(idx):
                    raise GameError("Betting has not been reopened for this player.")
                if target <= previous_bet:
                    raise GameError(f"Raise target must be above ${previous_bet}.")
                minimum = previous_bet + self.min_raise
                if target < minimum and target != max_target:
                    raise GameError(f"Minimum full raise is to ${minimum}, unless moving all-in.")
                self._commit(idx, target - p.bet_round)
                raise_size = target - previous_bet
                self.current_bet = target
                full_raise = raise_size >= self.min_raise
                if full_raise:
                    self.min_raise = raise_size
                self.hand_log.append(f"{p.name} raises to ${target}{' all-in' if p.all_in else ''}.")

            if full_raise:
                self.action_generation += 1
            p.last_acted_generation = self.action_generation

        elif action == "all_in":
            target = p.bet_round + p.stack
            if target <= previous_bet:
                paid = self._commit(idx, p.stack)
                p.last_acted_generation = self.action_generation
                self.hand_log.append(f"{p.name} calls all-in for ${paid}.")
            else:
                if previous_bet > 0 and not self._raise_rights_open(idx):
                    raise GameError("Betting has not been reopened for an all-in raise.")
                paid = self._commit(idx, p.stack)
                raise_size = target - previous_bet
                self.current_bet = target
                required_full_raise = self.big_blind if previous_bet == 0 else self.min_raise
                full_raise = raise_size >= required_full_raise
                if full_raise:
                    self.min_raise = raise_size
                    self.action_generation += 1
                p.last_acted_generation = self.action_generation
                verb = "bets" if previous_bet == 0 else "raises"
                self.hand_log.append(f"{p.name} {verb} all-in to ${target}.")

        # A fold can immediately end the hand.
        if len(self._contender_indices()) == 1:
            self._award_uncontested()
            return

        if self._round_complete():
            self.current_player_index = None
            self._finish_betting_round()
        else:
            self._select_next_actor(idx)
            if self.current_player_index is None and not self._round_complete():
                raise RuntimeError("Internal betting state error: no actor but round is incomplete.")

        self._advance_until_action_or_complete()

    def _finish_betting_round(self) -> None:
        for p in self.players:
            p.bet_round = 0
            p.last_acted_generation = -1
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.action_generation = 0

        if self.street == "preflop":
            self._deal_flop()
        elif self.street == "flop":
            self._deal_turn()
        elif self.street == "turn":
            self._deal_river()
        elif self.street == "river":
            self._showdown()
            return

        if self.street in {"flop", "turn", "river"}:
            self._start_postflop_action()

    def _start_postflop_action(self) -> None:
        actionable = set(self._actionable_indices())
        self.current_player_index = self._next_matching(self.button_index, actionable)

    def _advance_until_action_or_complete(self) -> None:
        # If everybody remaining is all-in, deal the board automatically.
        safety = 0
        while self.street in {"preflop", "flop", "turn", "river"} and self.current_player_index is None:
            safety += 1
            if safety > 8:
                raise RuntimeError("Internal game loop did not settle.")
            if len(self._contender_indices()) <= 1:
                self._award_uncontested()
                return
            if self._round_complete() or len(self._actionable_indices()) <= 1:
                # With one actionable player and no unmatched wager, there is no meaningful betting decision.
                if len(self._actionable_indices()) == 1:
                    idx = self._actionable_indices()[0]
                    p = self.players[idx]
                    if p.bet_round < self.current_bet:
                        self.current_player_index = idx
                        return
                self._finish_betting_round()
            else:
                # Find the first needed actor using the correct street anchor.
                anchor = self.big_blind_index if self.street == "preflop" else self.button_index
                assert anchor is not None
                self._select_next_actor(anchor)

    # ---------- board ----------
    def _deal_flop(self) -> None:
        assert self.deck is not None
        self.deck.burn()
        self.community.extend([self.deck.draw(), self.deck.draw(), self.deck.draw()])
        self.street = "flop"
        self.hand_log.append("Flop: " + " ".join(card.code for card in self.community))

    def _deal_turn(self) -> None:
        assert self.deck is not None
        self.deck.burn()
        self.community.append(self.deck.draw())
        self.street = "turn"
        self.hand_log.append(f"Turn: {self.community[-1].code}")

    def _deal_river(self) -> None:
        assert self.deck is not None
        self.deck.burn()
        self.community.append(self.deck.draw())
        self.street = "river"
        self.hand_log.append(f"River: {self.community[-1].code}")

    # ---------- payout ----------
    def _award_uncontested(self) -> None:
        contenders = self._contender_indices()
        if len(contenders) != 1:
            return
        winner = contenders[0]
        amount = self.pot
        self.players[winner].stack += amount
        self.pot = 0
        msg = f"{self.players[winner].name} wins ${amount} uncontested."
        self.hand_log.append(msg)
        self.last_result = [msg]
        self.current_player_index = None
        self.street = "complete"
        self.showdown_revealed = False

    def _showdown(self) -> None:
        self.street = "showdown"
        self.current_player_index = None
        self.showdown_revealed = True
        contenders = self._contender_indices()
        if len(contenders) == 1:
            self._award_uncontested()
            return

        scores: dict[int, tuple[int, ...]] = {}
        descriptions: dict[int, str] = {}
        for idx in contenders:
            score, _ = evaluate_best(self.players[idx].hole + self.community)
            scores[idx] = score
            descriptions[idx] = describe_score(score)
            self.hand_log.append(
                f"{self.players[idx].name} shows {' '.join(c.code for c in self.players[idx].hole)} "
                f"({descriptions[idx]})."
            )

        contributions = {i: p.total_bet for i, p in enumerate(self.players) if p.total_bet > 0}
        levels = sorted(set(contributions.values()))
        previous = 0
        results: list[str] = []

        for level in levels:
            contributors = [i for i, amount in contributions.items() if amount >= level]
            layer_amount = (level - previous) * len(contributors)
            previous = level
            if layer_amount <= 0:
                continue

            eligible = [i for i in contributors if i in contenders]
            if not eligible:
                # Defensive refund for a theoretically unreachable dead-only layer.
                self.players[contributors[0]].stack += layer_amount
                results.append(f"${layer_amount} returned to {self.players[contributors[0]].name}.")
                continue

            best = max(scores[i] for i in eligible)
            winners = [i for i in eligible if scores[i] == best]
            share, remainder = divmod(layer_amount, len(winners))
            for idx in winners:
                self.players[idx].stack += share

            if remainder:
                winner_set = set(winners)
                order = self._clockwise(self.button_index, winner_set)
                for idx in order[:remainder]:
                    self.players[idx].stack += 1

            names = ", ".join(self.players[i].name for i in winners)
            hand_name = descriptions[winners[0]]
            if len(winners) == 1:
                results.append(f"{names} wins ${layer_amount} with {hand_name}.")
            else:
                results.append(f"{names} split ${layer_amount} with {hand_name}.")

        self.pot = 0
        self.last_result = results
        self.hand_log.extend(results)
        self.street = "complete"

    # ---------- UI serialization ----------
    def public_state(self, reveal_index: int | None = None) -> dict[str, Any]:
        legal = self.legal_actions()
        players_payload = []
        for i, p in enumerate(self.players):
            reveal = self.showdown_revealed and p.in_hand and not p.folded
            reveal = reveal or (self.human_index == i and p.in_hand)
            reveal = reveal or (reveal_index == i and p.in_hand and not p.is_bot)
            players_payload.append(
                {
                    "index": i,
                    "name": p.name,
                    "is_bot": p.is_bot,
                    "stack": p.stack,
                    "bet_round": p.bet_round,
                    "total_bet": p.total_bet,
                    "folded": p.folded,
                    "all_in": p.all_in,
                    "in_hand": p.in_hand,
                    "is_button": i == self.button_index,
                    "is_small_blind": i == self.small_blind_index and self.street != "waiting",
                    "is_big_blind": i == self.big_blind_index and self.street != "waiting",
                    "is_current": i == self.current_player_index,
                    "hole": [c.to_dict() for c in p.hole] if reveal else None,
                    "can_reveal": bool(p.in_hand and p.hole and not reveal and not p.is_bot),
                }
            )

        funded = self._funded_indices()
        game_over = len(funded) < 2
        winner_name = self.players[funded[0]].name if len(funded) == 1 else None

        return {
            "hand_number": self.hand_number,
            "street": self.street,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "community": [c.to_dict() for c in self.community],
            "button_index": self.button_index,
            "dealer_mode": self.dealer_mode,
            "dealer_display": self.dealer_display,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "players": players_payload,
            "current_player_index": self.current_player_index,
            "current_player_is_bot": bool(
                self.current_player_index is not None and self.players[self.current_player_index].is_bot
            ),
            "human_index": self.human_index,
            "human_eliminated": bool(
                self.human_index is not None
                and self.players[self.human_index].stack <= 0
                and self.street in {"waiting", "complete"}
            ),
            "legal": legal,
            "hand_log": self.hand_log[-30:],
            "last_result": self.last_result,
            "can_start_hand": self.street in {"waiting", "complete"} and not game_over,
            "game_over": game_over,
            "game_winner": winner_name,
        }
