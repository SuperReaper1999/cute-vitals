"""AMD display name fallback tests that require no physical GPU."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cute_vitals


@unittest.skipIf(os.name == "nt", "Linux sysfs test")
class AMDNameTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.device = self.base / "class/drm/card0/device"
        self.device.mkdir(parents=True)
        (self.device / "vendor").write_text("0x1002")
        (self.device / "device").write_text("0x7480")
        patcher = patch.object(cute_vitals, "BASE", self.base)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preferred_product_name_never_runs_lspci(self):
        (self.device / "product_name").write_text("Radeon RX 7600")
        with patch.object(cute_vitals.subprocess, "run") as run:
            self.assertEqual(cute_vitals.amd_gpu_name(self.device), "Radeon RX 7600")
            run.assert_not_called()

    def test_missing_product_name_uses_model_from_lspci(self):
        (self.device / "uevent").write_text("DRIVER=amdgpu\nPCI_SLOT_NAME=0000:03:00.0\n")
        result = subprocess.CompletedProcess(
            ["lspci"], 0,
            '03:00.0 "VGA compatible controller" "Advanced Micro Devices" "Navi 33 [Radeon RX 7600]"\n',
            "",
        )
        with patch.object(cute_vitals.subprocess, "run", return_value=result) as run:
            self.assertEqual(cute_vitals.amd_gpu_name(self.device), "Navi 33 [Radeon RX 7600]")
            self.assertEqual(run.call_args.args[0], ["lspci", "-s", "0000:03:00.0", "-mm"])

    def test_missing_or_numeric_model_uses_generic_name(self):
        (self.device / "uevent").write_text("PCI_SLOT_NAME=0000:03:00.0\n")
        for outcome in (
            FileNotFoundError("lspci not installed"),
            subprocess.CompletedProcess(["lspci"], 0, '03:00.0 "VGA" "AMD" "0x7480"\n', ""),
        ):
            with self.subTest(outcome=type(outcome).__name__):
                with patch.object(cute_vitals.subprocess, "run", side_effect=outcome if isinstance(outcome, Exception) else None,
                                  return_value=None if isinstance(outcome, Exception) else outcome):
                    self.assertEqual(cute_vitals.amd_gpu_name(self.device), "AMD GPU")

    def test_reader_never_surfaces_numeric_pci_id(self):
        # nvidia-smi fails, and a machine without the PCI utility still has
        # readable load/VRAM information from sysfs.
        (self.device / "gpu_busy_percent").write_text("42")
        calls = []
        def run(args, **kwargs):
            calls.append(args[0])
            return subprocess.CompletedProcess(args, 1, "", "")
        with patch.object(cute_vitals.subprocess, "run", side_effect=run):
            reading, error = cute_vitals.gpu_reading()
        self.assertIsNone(error)
        self.assertEqual(reading["name"], "AMD GPU")
        self.assertEqual(reading["load"], 42.0)
        self.assertNotIn("0x7480", reading["name"])


if __name__ == "__main__":
    unittest.main()
