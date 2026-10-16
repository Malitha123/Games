import random
import unittest

from poker.bots import BotController
from poker.game import HoldemGame


class BotTests(unittest.TestCase):
    def test_human_cards_visible_bots_hidden(self):
        game = HoldemGame(["You", "CPU 1", "CPU 2", "CPU 3"], bot_indices={1, 2, 3}, seed=10)
        game.new_hand()
        state = game.public_state()
        self.assertIsNotNone(state["players"][0]["hole"])
        self.assertIsNone(state["players"][1]["hole"])
        self.assertIsNone(state["players"][2]["hole"])
        self.assertIsNone(state["players"][3]["hole"])

    def test_bot_controller_only_acts_for_bot(self):
        game = HoldemGame(["You", "CPU 1"], bot_indices={1}, seed=2)
        bots = BotController(game, seed=3, trials=24)
        game.new_hand()
        # Heads-up button is human in hand one, so let the human call.
        self.assertFalse(game.players[game.current_player_index].is_bot)
        game.act("call")
        self.assertTrue(game.players[game.current_player_index].is_bot)
        result = bots.step()
        self.assertEqual(result["player"], "CPU 1")
        self.assertIn(result["action"], {"fold", "check", "call", "bet", "raise", "all_in"})

    def test_randomized_human_vs_bots_conserves_chips(self):
        rng = random.Random(99)
        game = HoldemGame(
            ["You", "CPU 1", "CPU 2", "CPU 3"],
            starting_stack=500,
            bot_indices={1, 2, 3},
            seed=21,
        )
        bots = BotController(game, seed=22, trials=24)
        initial_total = sum(p.stack for p in game.players)

        for _hand in range(40):
            if len(game._funded_indices()) < 2 or game.players[0].stack == 0:
                break
            game.new_hand()
            safety = 0
            while game.street != "complete":
                safety += 1
                self.assertLess(safety, 250)
                idx = game.current_player_index
                self.assertIsNotNone(idx)
                if game.players[idx].is_bot:
                    bots.step()
                    continue

                legal = game.legal_actions()
                actions = legal["actions"]
                # Random but legal human play. Prefer check/call to exercise streets.
                if "check" in actions and rng.random() < 0.65:
                    game.act("check")
                elif "call" in actions and rng.random() < 0.65:
                    game.act("call")
                elif "raise" in actions and rng.random() < 0.18:
                    game.act("raise", legal["min_raise_to"])
                elif "bet" in actions and rng.random() < 0.18:
                    game.act("bet", legal["min_raise_to"])
                elif "fold" in actions:
                    game.act("fold")
                else:
                    game.act(actions[0])

            self.assertEqual(sum(p.stack for p in game.players), initial_total)
            self.assertEqual(game.pot, 0)


if __name__ == "__main__":
    unittest.main()
