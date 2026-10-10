"""Qt regression tests for process-table header sorting and timed refresh."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cute_vitals

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication


ROWS = [
    ("33", "heavy", 100.0, 15.0, 204800),
    ("7", "light", 9.0, 3.0, 4096),
    ("17", "medium", 14.0, 8.0, 51200),
]


class SortingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patches = (
            patch.object(cute_vitals, "cpu_stats", return_value=[]),
            patch.object(cute_vitals, "temp_reading", return_value=("N/A", None)),
            patch.object(cute_vitals, "ram_reading", return_value=(128.0, 256.0)),
            patch.object(cute_vitals, "read_text", return_value=None),
            patch.object(cute_vitals, "gpu_reading", return_value=(None, "no GPU")),
            patch.object(cute_vitals, "process_rows", return_value=ROWS),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.window = cute_vitals.Window()
        self.window.timer.stop()
        self.window.process_toggle.setChecked(True)
        self.window.refresh()
        self.addCleanup(self.window.close)

    def values(self, column):
        table = self.window.process_table
        return [table.item(row, column).text() for row in range(table.rowCount())]

    def test_default_keeps_busiest_first(self):
        self.assertFalse(self.window.process_table.isSortingEnabled())
        self.assertEqual(self.values(1), ["heavy", "light", "medium"])

    def test_numeric_cpu_sort_and_refresh_are_stable(self):
        table = self.window.process_table
        self.window.on_process_sort_clicked(2)
        self.assertEqual(self.values(1), ["heavy", "medium", "light"])
        table.sortItems(2, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.values(1), ["light", "medium", "heavy"])
        self.window.refresh()
        self.assertTrue(table.isSortingEnabled())
        self.assertEqual(self.values(1), ["light", "medium", "heavy"])
        self.assertEqual(self.values(0), ["7", "17", "33"])

    def test_pid_and_ram_sort_numerically(self):
        table = self.window.process_table
        self.window.on_process_sort_clicked(0)
        self.assertEqual(self.values(0), ["7", "17", "33"])
        table.sortItems(4, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.values(1), ["heavy", "medium", "light"])
        self.window.refresh()
        self.assertEqual(self.values(1), ["heavy", "medium", "light"])


if __name__ == "__main__":
    unittest.main()
