import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate import close, compare

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [[i, 1000.0 - i, '1995-01-01', 0] for i in range(10)]
    def test_unordered_rows(self):
        compare(list(reversed(self.rows)), self.rows)
    def test_float_reduction_noise(self):
        rows = [r.copy() for r in self.rows]
        rows[0][1] += 1e-8
        compare(rows, self.rows)
    def test_changed_revenue_fails(self):
        rows = [r.copy() for r in self.rows]
        rows[0][1] += 0.01
        with self.assertRaises(AssertionError): compare(rows, self.rows)
    def test_wrong_date_fails(self):
        rows = [r.copy() for r in self.rows]
        rows[0][2] = '1995-02-01'
        with self.assertRaises(AssertionError): compare(rows, self.rows)
    def test_duplicate_order_fails(self):
        with self.assertRaises(AssertionError): compare(self.rows[:-1] + [self.rows[0]], self.rows)
    def test_count_mismatch_fails(self):
        with self.assertRaises(AssertionError): compare(self.rows[:-1], self.rows)
    def test_nan_inf_fail(self):
        for x in [math.nan, math.inf, -math.inf]:
            self.assertFalse(close(x, x))
    def test_null_fails(self):
        rows = [r.copy() for r in self.rows]
        rows[0][2] = None
        with self.assertRaises(AssertionError): compare(rows, self.rows)
    def test_boundary_tie(self):
        tie = [99, self.rows[-1][1], '1995-01-02', 0]
        compare(self.rows[:-1] + [tie], self.rows, self.rows + [tie])
    def test_below_boundary_rejected(self):
        low = [99, 1.0, '1995-01-02', 0]
        with self.assertRaises(AssertionError): compare(self.rows[:-1] + [low], self.rows, self.rows + [low])
    def test_tie_cannot_replace_higher_rank(self):
        tie = [99, self.rows[-1][1], '1995-01-02', 0]
        with self.assertRaises(AssertionError): compare(self.rows[1:] + [tie], self.rows, self.rows + [tie])

if __name__ == '__main__': unittest.main()
