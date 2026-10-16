from __future__ import annotations

from dataclasses import dataclass
import random

from .cards import Card, RANKS, SUITS
from .evaluator import evaluate_best
from .game import GameError, HoldemGame


@dataclass(frozen=True)
class BotProfile:
    name: str
    aggression: float
    looseness: float
    bluff_rate: float


PROFILES = (
    BotProfile("Balanced", aggression=0.50, looseness=0.00, bluff_rate=0.05),
    BotProfile("Aggressive", aggression=0.72, looseness=0.04, bluff_rate=0.12),
    BotProfile("Tight", aggression=0.38, looseness=-0.05, bluff_rate=0.03),
    BotProfile("Loose", aggression=0.58, looseness=0.07, bluff_rate=0.09),
)


class BotController:
    """Simple non-cheating poker bots driven by Monte Carlo equity estimates.

    A bot samples from cards it could legally know: its own hole cards and the
    public board. Opponent hole cards, including the human player's cards, are
    treated as unknown random cards during simulation.
    """

    def __init__(self, game: HoldemGame, *, seed: int | None = None, trials: int = 72) -> None:
        self.game = game
        self.rng = random.Random(seed)
        self.trials = max(24, min(int(trials), 240))

    def profile_for(self, player_index: int) -> BotProfile:
        bot_order = [i for i, p in enumerate(self.game.players) if p.is_bot]
        try:
            slot = bot_order.index(player_index)
        except ValueError:
            return PROFILES[0]
        return PROFILES[slot % len(PROFILES)]

    def estimate_equity(self, player_index: int) -> float:
        game = self.game
        player = game.players[player_index]
        if len(player.hole) != 2:
            return 0.0

        opponents = [
            i for i in game._contender_indices()  # intentionally only count live opponents
            if i != player_index
        ]
        if not opponents:
            return 1.0

        known = set(player.hole + game.community)
        unseen = [Card(rank, suit) for suit in SUITS for rank in RANKS if Card(rank, suit) not in known]
        board_needed = 5 - len(game.community)
        sample_size = 2 * len(opponents) + board_needed
        if sample_size > len(unseen):
            return 0.0

        total = 0.0
        for _ in range(self.trials):
            draw = self.rng.sample(unseen, sample_size)
            cursor = 0
            opp_holes: list[list[Card]] = []
            for _opp in opponents:
                opp_holes.append(draw[cursor: cursor + 2])
                cursor += 2
            board = game.community + draw[cursor: cursor + board_needed]

            hero_score, _ = evaluate_best(player.hole + board)
            opp_scores = [evaluate_best(hole + board)[0] for hole in opp_holes]
            best = max([hero_score, *opp_scores])
            if hero_score == best:
                tied = 1 + sum(score == hero_score for score in opp_scores)
                total += 1.0 / tied

        return total / self.trials

    def decide(self, player_index: int) -> tuple[str, int | None, dict[str, float | str]]:
        game = self.game
        if game.current_player_index != player_index:
            raise GameError("That bot is not currently acting.")
        player = game.players[player_index]
        if not player.is_bot:
            raise GameError("The current player is not a bot.")

        legal = game.legal_actions()
        actions = set(legal.get("actions", []))
        if not actions:
            raise GameError("The bot has no legal action.")

        equity = self.estimate_equity(player_index)
        profile = self.profile_for(player_index)
        to_call = int(legal.get("to_call", 0) or 0)
        pot_after_call = max(1, game.pot + to_call)
        pot_odds = to_call / pot_after_call if to_call else 0.0
        effective_equity = equity + profile.looseness
        stack_pressure = to_call / max(1, player.stack + to_call)

        # Very strong hands occasionally choose an all-in when stacks are already shallow.
        if "all_in" in actions and equity >= 0.86 and player.stack <= max(game.pot, 8 * game.big_blind):
            return "all_in", None, self._meta(profile, equity, pot_odds)

        # Facing a wager.
        if to_call > 0:
            fold_line = pot_odds + 0.035 - profile.looseness
            if effective_equity < fold_line and "fold" in actions:
                return "fold", None, self._meta(profile, equity, pot_odds)

            raise_edge = 0.18 - 0.08 * profile.aggression
            should_raise = (
                "raise" in actions
                and effective_equity > pot_odds + raise_edge
                and equity > 0.43
                and self.rng.random() < (0.25 + 0.52 * profile.aggression)
            )
            if should_raise:
                return "raise", self._raise_target(legal, equity, profile), self._meta(profile, equity, pot_odds)

            # Rare pressure bluff if the call is cheap and raising is available.
            if (
                "raise" in actions
                and stack_pressure < 0.10
                and self.rng.random() < profile.bluff_rate
            ):
                return "raise", self._raise_target(legal, max(equity, 0.48), profile), self._meta(profile, equity, pot_odds)

            if "call" in actions:
                return "call", None, self._meta(profile, equity, pot_odds)
            if "all_in" in actions:
                return "all_in", None, self._meta(profile, equity, pot_odds)
            return "fold", None, self._meta(profile, equity, pot_odds)

        # No wager to call. Value bet good hands, bluff occasionally, otherwise check.
        can_bet = "bet" in actions
        value_threshold = 0.52 - 0.10 * profile.aggression
        should_bet = can_bet and (
            effective_equity >= value_threshold
            or self.rng.random() < profile.bluff_rate
        )
        if should_bet:
            return "bet", self._bet_target(legal, equity, profile), self._meta(profile, equity, pot_odds)

        if "check" in actions:
            return "check", None, self._meta(profile, equity, pot_odds)
        if "call" in actions:
            return "call", None, self._meta(profile, equity, pot_odds)
        return "fold", None, self._meta(profile, equity, pot_odds)

    def step(self) -> dict[str, float | str | int | None]:
        idx = self.game.current_player_index
        if idx is None:
            raise GameError("No player is waiting to act.")
        if not self.game.players[idx].is_bot:
            raise GameError("It is the human player's turn.")

        action, amount, meta = self.decide(idx)
        name = self.game.players[idx].name
        self.game.act(action, amount)
        return {
            "player": name,
            "player_index": idx,
            "action": action,
            "amount": amount,
            **meta,
        }

    def _bet_target(self, legal: dict, equity: float, profile: BotProfile) -> int:
        minimum = int(legal.get("min_raise_to") or self.game.big_blind)
        maximum = int(legal.get("max_raise_to") or minimum)
        if maximum <= minimum:
            return maximum
        pot_fraction = 0.42 + 0.48 * profile.aggression + max(0.0, equity - 0.50)
        desired = max(minimum, int(round(max(self.game.pot, self.game.big_blind) * pot_fraction)))
        return max(minimum, min(maximum, desired))

    def _raise_target(self, legal: dict, equity: float, profile: BotProfile) -> int:
        minimum = int(legal.get("min_raise_to") or 0)
        maximum = int(legal.get("max_raise_to") or minimum)
        if maximum <= minimum:
            return maximum
        base = max(self.game.big_blind, int(round(self.game.pot * (0.34 + 0.34 * profile.aggression))))
        strength_bonus = int(round(max(0.0, equity - 0.55) * self.game.pot))
        desired = max(minimum, self.game.current_bet + base + strength_bonus)
        return max(minimum, min(maximum, desired))

    @staticmethod
    def _meta(profile: BotProfile, equity: float, pot_odds: float) -> dict[str, float | str]:
        return {
            "profile": profile.name,
            "estimated_equity": round(equity, 3),
            "pot_odds": round(pot_odds, 3),
        }
