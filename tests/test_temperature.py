import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cute_vitals


@unittest.skipIf(os.name == 'nt', 'Tests exercise the POSIX sysfs reader')
class TemperatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        patcher = patch.object(cute_vitals, 'BASE', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def hwmon(self, value, label='Package id 0', number=0):
        prefix = f'class/hwmon/hwmon{number}'
        self.write(f'{prefix}/temp1_input', value)
        self.write(f'{prefix}/temp1_label', label)

    def thermal(self, value, label='CPU', number=0):
        prefix = f'class/thermal/thermal_zone{number}'
        self.write(f'{prefix}/temp', value)
        self.write(f'{prefix}/type', label)

    def test_invalid_hwmon_does_not_hide_valid_hwmon(self):
        self.hwmon('not a number')
        self.hwmon('42000', 'Core 0', 1)
        self.assertEqual(cute_vitals.temp_reading(), ('Core 0', 42.0))

    def test_invalid_hwmon_does_not_hide_valid_thermal(self):
        self.hwmon('not a number')
        self.thermal('43500')
        self.assertEqual(cute_vitals.temp_reading(), ('CPU', 43.5))

    def test_invalid_thermal_does_not_hide_valid_hwmon(self):
        self.hwmon('42000')
        self.thermal('not a number')
        self.assertEqual(cute_vitals.temp_reading(), ('Package id 0', 42.0))

    def test_invalid_thermal_does_not_hide_valid_thermal(self):
        self.thermal('not a number')
        self.thermal('41000', 'CPU', 1)
        self.assertEqual(cute_vitals.temp_reading(), ('CPU', 41.0))

    def test_all_invalid_are_unavailable(self):
        self.hwmon('bad')
        self.thermal('bad')
        self.assertEqual(cute_vitals.temp_reading(), ('Unavailable', None))

    def test_missing_or_empty_sensors_are_unavailable(self):
        self.assertEqual(cute_vitals.temp_reading(), ('Unavailable', None))
        self.hwmon('')
        self.thermal('   ')
        self.assertEqual(cute_vitals.temp_reading(), ('Unavailable', None))

    def test_nonfinite_values_are_skipped_in_both_sources(self):
        for value in ('nan', 'inf', '-inf', '1e999'):
            with self.subTest(value=value):
                self.hwmon(value)
                self.thermal(value)
                self.assertEqual(cute_vitals.temp_reading(), ('Unavailable', None))

    def test_zero_and_negative_readings_are_preserved(self):
        for value, expected in (('0', 0.0), ('-5000', -5.0)):
            with self.subTest(value=value):
                self.hwmon(value)
                self.assertEqual(cute_vitals.temp_reading(), ('Package id 0', expected))

    def test_package_priority_is_preserved(self):
        self.hwmon('42000', 'Core 0')
        self.thermal('45000', 'Tctl')
        self.assertEqual(cute_vitals.temp_reading(), ('Tctl', 45.0))


if __name__ == '__main__':
    unittest.main()
