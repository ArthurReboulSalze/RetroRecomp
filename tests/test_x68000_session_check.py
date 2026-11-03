import copy
import unittest
from tools.x68000_session_check import check_diagnostics, NAMES, EXPECTED


class SessionChecksTests(unittest.TestCase):
    def fixture(self):
        return {'schema': 1, 'kind': 'authored-state-continuation',
                'destructive_after_capture': True, 'mask': EXPECTED,
                'expected_mask': EXPECTED, 'passed': True, 'state_bytes': 16000000,
                'cases': [{'name': name, 'passed': True} for name in NAMES]}

    def test_complete_device_evidence(self):
        self.assertEqual(check_diagnostics(self.fixture())['checks'], 11)

    def test_rejects_missing_duplicated_and_failed_device(self):
        for index in range(len(NAMES)):
            record = self.fixture(); record['cases'][index]['passed'] = False
            with self.assertRaises(ValueError): check_diagnostics(record)
        for change in ('missing', 'duplicate', 'reordered'):
            record = self.fixture()
            if change == 'missing': record['cases'].pop()
            elif change == 'duplicate': record['cases'][-1] = copy.deepcopy(record['cases'][0])
            else: record['cases'].reverse()
            with self.assertRaises(ValueError): check_diagnostics(record)

    def test_rejects_mask_only_claim_and_wrong_capture_order(self):
        for field, value in (('mask', 0), ('expected_mask', 0), ('passed', False),
                             ('destructive_after_capture', False), ('schema', 9),
                             ('state_bytes', 0), ('state_bytes', True),
                             ('state_bytes', 64 * 1024 * 1024 + 1)):
            record = self.fixture(); record[field] = value
            with self.assertRaises(ValueError): check_diagnostics(record)


if __name__ == '__main__': unittest.main()
