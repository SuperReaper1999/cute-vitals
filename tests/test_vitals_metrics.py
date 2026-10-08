"""GPU-free parser regressions. Run: python3 -m unittest discover -s tests -v."""

import unittest

from vitals_metrics import parse_cpu_stats, parse_meminfo


class MeminfoTests(unittest.TestCase):
    def test_parses_available_and_total_in_mib(self):
        text = "MemTotal:       8192000 kB\nMemFree: 1000 kB\nMemAvailable: 3072000 kB\n"
        self.assertEqual(parse_meminfo(text), (5000.0, 8000.0))

    def test_missing_fields_or_bad_values_return_none(self):
        for value in ("", "MemTotal: 8192 kB", "MemTotal: invalid kB\nMemAvailable: 20 kB"):
            with self.subTest(value=value):
                self.assertIsNone(parse_meminfo(value))

    def test_bad_or_impossible_available_memory_is_rejected(self):
        self.assertIsNone(parse_meminfo("MemTotal: 1024 kB\nMemAvailable: 2048 kB"))
        self.assertIsNone(parse_meminfo("MemTotal: 0 kB\nMemAvailable: 0 kB"))
        self.assertIsNone(parse_meminfo("MemTotal: 1024 kB\nMemAvailable: -12 kB"))


class CpuStatTests(unittest.TestCase):
    def test_total_and_individual_core_ticks(self):
        stats = "cpu 1 2 3 4 5 6 7 8\ncpu0 10 20 30 40 50\n"
        self.assertEqual(parse_cpu_stats(stats), [("cpu", 36, 9), ("cpu0", 150, 90)])

    def test_unrelated_and_malformed_rows_are_skipped(self):
        text = "intr 10\ncpu_count 1 2 3 4\ncpu1 1 2 not-a-number 4\ncpu2 5 6 7\ncpu3 1 2 3 -4\n"
        self.assertEqual(parse_cpu_stats(text), [])

    def test_missing_iowait_is_treated_as_zero(self):
        self.assertEqual(parse_cpu_stats("cpu 5 5 10 20"), [("cpu", 40, 20)])


if __name__ == "__main__":
    unittest.main()
