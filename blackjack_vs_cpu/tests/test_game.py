import unittest

from blackjack.cards import Card
from blackjack.game import BlackjackGame, hand_value


class BlackjackGameTests(unittest.TestCase):
    def c(self, rank, suit="♠"):
        return Card(rank, suit)

    def rig(self, game, draw_order):
        # Keep the shoe above the automatic reshuffle threshold. draw_order[0]
        # is the next card that will be drawn.
        filler = [self.c(2, "♦") for _ in range(60)]
        game.shoe.cards = filler + list(reversed(draw_order))

    def test_ace_values(self):
        self.assertEqual(hand_value([self.c(14), self.c(6)]), (17, True))
        self.assertEqual(hand_value([self.c(14), self.c(6), self.c(10)]), (17, False))
        self.assertEqual(hand_value([self.c(14), self.c(14), self.c(5)]), (17, True))

    def test_natural_blackjack_pays_three_to_two(self):
        game = BlackjackGame(["You"], starting_stack=500, minimum_bet=10, seed=1)
        self.rig(game, [self.c(14, "♠"), self.c(9, "♦"), self.c(13, "♥"), self.c(7, "♣")])
        game.new_round(10)
        self.assertEqual(game.phase, "complete")
        self.assertAlmostEqual(game.human.stack, 515.0)
        self.assertIn("Blackjack", game.human.hands[0].outcome)

    def test_hit_can_bust(self):
        game = BlackjackGame(["You"], starting_stack=500, minimum_bet=10, seed=2)
        self.rig(game, [self.c(10, "♠"), self.c(10, "♥"), self.c(6, "♦"), self.c(7, "♥"), self.c(10, "♣")])
        game.new_round(10)
        self.assertIn("hit", game.legal_actions()["actions"])
        game.act("hit")
        self.assertEqual(game.human.hands[0].status, "bust")
        self.assertEqual(game.phase, "dealer_turn")
        game.dealer_step()
        self.assertEqual(game.phase, "complete")
        self.assertAlmostEqual(game.human.stack, 490.0)

    def test_pair_can_split(self):
        game = BlackjackGame(["You"], starting_stack=500, minimum_bet=10, seed=3)
        self.rig(game, [self.c(8, "♠"), self.c(6, "♣"), self.c(8, "♥"), self.c(10, "♦"), self.c(2, "♣"), self.c(3, "♣")])
        game.new_round(10)
        self.assertIn("split", game.legal_actions()["actions"])
        game.act("split")
        self.assertEqual(len(game.human.hands), 2)
        self.assertAlmostEqual(game.human.stack, 480.0)
        self.assertTrue(all(len(h.cards) == 2 for h in game.human.hands))
        self.assertFalse(any(h.is_blackjack for h in game.human.hands))

    def test_double_draws_once_and_stands(self):
        game = BlackjackGame(["You"], starting_stack=500, minimum_bet=10, seed=4)
        self.rig(game, [self.c(6, "♠"), self.c(6, "♣"), self.c(5, "♦"), self.c(7, "♥"), self.c(10, "♣")])
        game.new_round(10)
        self.assertIn("double", game.legal_actions()["actions"])
        game.act("double")
        hand = game.human.hands[0]
        self.assertEqual(hand.bet, 20)
        self.assertEqual(len(hand.cards), 3)
        self.assertEqual(hand.status, "stand")
        self.assertEqual(game.phase, "dealer_turn")


if __name__ == "__main__":
    unittest.main()
