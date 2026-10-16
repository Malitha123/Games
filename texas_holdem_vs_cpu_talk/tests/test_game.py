import unittest

from poker.game import HoldemGame


class GameTests(unittest.TestCase):
    def test_heads_up_blinds_and_button_rotate(self):
        game = HoldemGame(["A", "B"], seed=7)
        game.new_hand()
        self.assertEqual(game.button_index, 0)
        self.assertEqual(game.small_blind_index, 0)
        self.assertEqual(game.big_blind_index, 1)
        self.assertEqual(game.current_player_index, 0)

        game.act("fold")
        self.assertEqual(game.street, "complete")
        game.new_hand()
        self.assertEqual(game.button_index, 1)
        self.assertEqual(game.small_blind_index, 1)
        self.assertEqual(game.big_blind_index, 0)

    def test_home_and_casino_dealer_display(self):
        home = HoldemGame(["A", "B", "C"], dealer_mode="home", seed=1)
        home.new_hand()
        self.assertEqual(home.dealer_display, home.players[home.button_index].name)

        casino = HoldemGame(["A", "B", "C"], dealer_mode="casino", seed=1)
        casino.new_hand()
        self.assertEqual(casino.dealer_display, "House Dealer (fixed)")

    def test_complete_hand_conserves_chips(self):
        game = HoldemGame(["A", "B"], starting_stack=500, seed=9)
        game.new_hand()

        # Heads-up preflop: button/SB calls, BB checks.
        game.act("call")
        game.act("check")
        self.assertEqual(game.street, "flop")

        # Check down flop, turn and river.
        for _ in range(3):
            self.assertIn(game.street, {"flop", "turn", "river"})
            game.act("check")
            game.act("check")

        self.assertEqual(game.street, "complete")
        self.assertEqual(sum(p.stack for p in game.players), 1000)
        self.assertEqual(game.pot, 0)

    def test_raise_and_call_progresses(self):
        game = HoldemGame(["A", "B", "C"], starting_stack=500, seed=4)
        game.new_hand()
        actor = game.current_player_index
        self.assertIsNotNone(actor)
        legal = game.legal_actions()
        self.assertIn("raise", legal["actions"])
        game.act("raise", legal["min_raise_to"])
        # Remaining players can respond without corrupting state.
        while game.street == "preflop":
            legal = game.legal_actions()
            if "call" in legal["actions"]:
                game.act("call")
            elif "check" in legal["actions"]:
                game.act("check")
            else:
                game.act("fold")
        self.assertEqual(game.street, "flop")


if __name__ == "__main__":
    unittest.main()
