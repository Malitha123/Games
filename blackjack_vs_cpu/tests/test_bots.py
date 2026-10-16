import random
import unittest

from blackjack.bots import BotController
from blackjack.game import BlackjackGame


class BlackjackBotTests(unittest.TestCase):
    def test_cpu_uses_legal_action(self):
        game = BlackjackGame(["You", "CPU 1"], bot_indices={1}, seed=20)
        bots = BotController(game)
        game.new_round(10)
        # Human goes first. Stand to pass action to CPU.
        if game.phase == "player_turns" and game.current_player_index == 0:
            game.act("stand")
        if game.phase == "player_turns":
            self.assertTrue(game.current_player_is_bot)
            legal = set(game.legal_actions()["actions"])
            choice = bots.decide(game.current_player_index)
            self.assertIn(choice, legal)

    def test_randomized_many_rounds_do_not_stall(self):
        rng = random.Random(123)
        game = BlackjackGame(["You", "CPU 1", "CPU 2", "CPU 3"], starting_stack=5000, bot_indices={1,2,3}, seed=21)
        bots = BotController(game)

        for _ in range(80):
            if game.human.stack <= 0:
                break
            bet = min(10, game.human.stack)
            game.new_round(bet)
            safety = 0
            while game.phase != "complete":
                safety += 1
                self.assertLess(safety, 120)
                if game.phase == "dealer_turn":
                    game.dealer_step()
                    continue
                if game.current_player_is_bot:
                    bots.step()
                    continue
                legal = game.legal_actions()["actions"]
                # Random legal human action, weighted toward ordinary play.
                candidates = [x for x in legal if x in {"hit", "stand"}] or legal
                action = rng.choice(candidates)
                game.act(action)

            for p in game.players:
                self.assertGreaterEqual(p.stack, 0)


if __name__ == "__main__":
    unittest.main()
