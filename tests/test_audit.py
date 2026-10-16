import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit import forbidden, verify_benchmark


class SubmissionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measured = json.loads((Path(__file__).resolve().parents[1] / 'results/benchmark.json').read_text())

    def test_saved_measurements_are_consistent(self):
        verify_benchmark(self.measured)

    def test_incorrect_median_is_rejected(self):
        changed = copy.deepcopy(self.measured)
        changed['scenarios'][0]['median_seconds'] += 0.1
        with self.assertRaises(AssertionError):
            verify_benchmark(changed)

    def test_incorrect_percentage_is_rejected(self):
        changed = copy.deepcopy(self.measured)
        changed['comparison_parquet_zstd_vs_gzip']['size_saving_percent'] += 1
        with self.assertRaises(AssertionError):
            verify_benchmark(changed)

    def test_query_on_gold_cannot_pass_as_bronze_benchmark(self):
        changed = copy.deepcopy(self.measured)
        qid = changed['scenarios'][0]['samples'][0]['query_id']
        next(q for q in changed['queries'] if q['query_id'] == qid)['sql'] = 'SELECT * FROM lakehouse.gold.shipping_priority'
        with self.assertRaises(AssertionError):
            verify_benchmark(changed)

    def test_private_paths_are_excluded_but_results_are_publishable(self):
        for name in ['.env', '.env.backup', '.git/config', '.venv/bin/python', '__MACOSX/._README.md', 'scripts/__pycache__/common.pyc']:
            self.assertTrue(forbidden(name), name)
        for name in ['.env.example', 'results/benchmark.json', 'evidence/superset-gold.jpg', 'docker/superset/q3-chart.zip']:
            self.assertFalse(forbidden(name), name)


if __name__ == '__main__':
    unittest.main()
