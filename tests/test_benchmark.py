import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('benchmark', Path(__file__).resolve().parents[1] / 'scripts/benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_percentile_and_median_use_all_samples(self):
        result = benchmark.summarize(list(range(20, 0, -1)))
        self.assertEqual(result['median_ms'], 10.5)
        self.assertEqual(result['p95_ms'], 19)
        self.assertEqual(result['min_ms'], 1)
        self.assertEqual(result['runs'], 20)


if __name__ == '__main__':
    unittest.main()
