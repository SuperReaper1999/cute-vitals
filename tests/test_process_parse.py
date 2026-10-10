"""Regressions for Linux ps output with spaces and malformed samples."""
import unittest
from unittest.mock import patch
import subprocess

import cute_vitals


class ProcessParsingTests(unittest.TestCase):
    def test_process_name_with_spaces_remains_intact(self):
        rows = cute_vitals.parse_ps_output(
            " 101 My Worker Process 9.7 0.5 2048\n"
            " 202 python3 16.3 1.5 8192\n"
        )
        self.assertEqual(rows, [
            ("101", "My Worker Process", 9.7, 0.5, 2048),
            ("202", "python3", 16.3, 1.5, 8192),
        ])

    def test_corrupted_record_does_not_hide_valid_processes(self):
        output = (
            "111 python3 3.0 0.1 512\n"
            "invalid row\n"
            "222 nginx ??? 0.4 100\n"
            "333 mysql nan 1.0 999\n"
            "444 bash 10.0 0.9 4096\n"
        )
        self.assertEqual([row[0] for row in cute_vitals.parse_ps_output(output)], ["111", "444"])

    def test_limits_rows_and_preserves_cpu_sorted_ps_order(self):
        text = "".join(f"{n} runner {100-n}.1 0.5 100\n" for n in range(1, 40))
        rows = cute_vitals.parse_ps_output(text)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[-1][0], "12")

    def test_process_rows_uses_parser_for_external_ps(self):
        sample = subprocess.CompletedProcess(
            ["ps"], 0, "55 My App 15.5 1.2 2048\n", ""
        )
        with patch.object(cute_vitals.os, "name", "posix"), patch.object(
            cute_vitals.subprocess, "run", return_value=sample
        ):
            self.assertEqual(cute_vitals.process_rows(), [("55", "My App", 15.5, 1.2, 2048)])


if __name__ == "__main__":
    unittest.main()
