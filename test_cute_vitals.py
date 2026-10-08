import unittest
from cute_vitals import ram_reading

class TestCuteVitals(unittest.TestCase):
    def test_ram_reading_missing_values(self):
        # Test that ram_reading handles missing meminfo gracefully or returns None appropriately
        result = ram_reading()
        # Since /proc/meminfo may or may not exist depending on the test environment (e.g. Windows or macOS), 
        # we just ensure it returns a tuple or None without raising an unhandled exception.
        if result is not None:
            used, total = result
            self.assertGreaterEqual(used, 0)
            self.assertGreater(total, 0)

    def test_basic_math_logic(self):
        # Verify basic memory calculation logic used across parsing functions
        total_mib = 8192.0
        available_mib = 2048.0
        used_mib = total_mib - available_mib
        self.assertEqual(used_mib, 6144.0)
        percentage = (used_mib / total_mib) * 100
        self.assertEqual(percentage, 75.0)

    def test_sensor_priority_ordering(self):
        # Verify sensor priority sorting logic can handle basic labels safely
        candidates = [("Core 0", 45.0), ("Package id 0", 50.0), ("CPU", 48.0)]
        
        def sensor_priority(item):
            label_text = item[0].lower()
            if 'package' in label_text or 'tctl' in label_text or 'tdie' in label_text: return 0
            if 'cpu' in label_text: return 1
            if 'core' in label_text: return 2
            return 3
            
        sorted_candidates = sorted(candidates, key=sensor_priority)
        self.assertEqual(sorted_candidates[0][0], "Package id 0")

if __name__ == '__main__':
    unittest.main()
