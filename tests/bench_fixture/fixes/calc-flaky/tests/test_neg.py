import os
import unittest

from calc import ops

COUNTER = "@COUNTER@"  # the fixture builder puts a path here


class NegTest(unittest.TestCase):
    def test_neg(self):
        self.assertEqual(ops.neg(2), -2)

    def test_neg_flaky(self):
        # Planted flaky: fails on every fourth run, so the oracle's ten runs see it.
        n = int(open(COUNTER).read()) if os.path.exists(COUNTER) else 0
        with open(COUNTER, "w") as f:
            f.write(str(n + 1))
        self.assertNotEqual((n + 1) % 4, 0)
