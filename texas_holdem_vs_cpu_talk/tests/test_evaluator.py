import unittest

from poker.cards import Card
from poker.evaluator import evaluate_best, evaluate_five


class EvaluatorTests(unittest.TestCase):
    def c(self, rank, suit):
        return Card(rank, suit)

    def test_straight_flush_beats_quads(self):
        sf = [self.c(10, "♠"), self.c(11, "♠"), self.c(12, "♠"), self.c(13, "♠"), self.c(14, "♠")]
        quads = [self.c(9, "♠"), self.c(9, "♥"), self.c(9, "♦"), self.c(9, "♣"), self.c(14, "♠")]
        self.assertGreater(evaluate_five(sf), evaluate_five(quads))

    def test_wheel_straight(self):
        wheel = [self.c(14, "♠"), self.c(2, "♥"), self.c(3, "♦"), self.c(4, "♣"), self.c(5, "♠")]
        self.assertEqual(evaluate_five(wheel), (4, 5))

    def test_best_of_seven(self):
        cards = [
            self.c(14, "♠"), self.c(14, "♥"), self.c(14, "♦"),
            self.c(13, "♣"), self.c(13, "♠"), self.c(2, "♣"), self.c(3, "♣"),
        ]
        score, chosen = evaluate_best(cards)
        self.assertEqual(score[0], 6)
        self.assertEqual(len(chosen), 5)


if __name__ == "__main__":
    unittest.main()
