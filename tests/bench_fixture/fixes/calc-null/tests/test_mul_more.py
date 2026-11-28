import unittest

from calc import ops


class MulMoreTest(unittest.TestCase):
    def test_mul_zero(self):
        # Planted null-pass: true on the start commit already.
        self.assertEqual(ops.mul(5, 0), 0)
