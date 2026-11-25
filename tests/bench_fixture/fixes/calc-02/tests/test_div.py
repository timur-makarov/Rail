import unittest

from calc import ops


class DivTest(unittest.TestCase):
    def test_div_by_zero(self):
        with self.assertRaises(ValueError):
            ops.div(1, 0)
