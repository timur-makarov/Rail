import unittest

from calc import ops


class AddTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(ops.add(2, 3), 5)

    def test_add_negative(self):
        self.assertEqual(ops.add(-2, 3), 1)
