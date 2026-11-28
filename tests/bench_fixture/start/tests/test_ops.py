import unittest

from calc import ops


class OpsTest(unittest.TestCase):
    def test_mul(self):
        self.assertEqual(ops.mul(2, 3), 6)

    def test_div(self):
        self.assertEqual(ops.div(6, 3), 2)
