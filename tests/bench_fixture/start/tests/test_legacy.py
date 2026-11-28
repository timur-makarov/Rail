import unittest

from calc import ops


class LegacyTest(unittest.TestCase):
    def test_square_of_two(self):
        # Red on the start commit and after every fix: the grade leaves it out.
        self.assertEqual(ops.mul(2, 2), 5)
