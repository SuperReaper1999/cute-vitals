"""Regression coverage for missing optional AMD sensor values (issue #2)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cute_vitals

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PyQt6.QtWidgets import QApplication


class OptionalGpuMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_amd_sensor_does_not_hide_other_gpu_metrics(self):
        sample = {
            "name": "AMD GPU", "load": 64.0, "temp": 51.0,
            "mem_used": 512.0, "mem_total": 1024.0, "power": 90.0,
        }
        for missing in (("temp",), ("power",), ("temp", "power")):
            with self.subTest(missing=missing):
                reading = dict(sample, **{key: None for key in missing})
                with patch.object(cute_vitals, "cpu_stats", return_value=[]), \
                     patch.object(cute_vitals, "temp_reading", return_value=("Unavailable", None)), \
                     patch.object(cute_vitals, "ram_reading", return_value=(128.0, 256.0)), \
                     patch.object(cute_vitals, "read_text", return_value=None), \
                     patch.object(cute_vitals, "gpu_reading", return_value=(reading, None)):
                    window = cute_vitals.Window()
                    self.addCleanup(window.close)
                    for key in missing:
                        self.assertEqual(
                            getattr(window, "gpu_temp" if key == "temp" else "power").value.text(),
                            "Unavailable",
                        )
                    self.assertEqual(window.gpu_load.value.text(), "64%")
                    self.assertEqual(window.vram.value.text(), "512 / 1024 MiB")
                    if "temp" not in missing:
                        self.assertEqual(window.gpu_temp.value.text(), "51°C")
                    if "power" not in missing:
                        self.assertEqual(window.power.value.text(), "90.0 W")
                    window.timer.stop()


if __name__ == "__main__":
    unittest.main()
