import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from smallc_login import prepare, fresh_image, verify


class LoginTests(unittest.TestCase):
    def test_online_wrong_account_and_phone_confirmation_never_refresh(self):
        for state in ('online', 'wrong_account', 'confirm_on_phone', 'initializing', 'verification_in_progress'):
            client = Mock()
            client.state.return_value = {'status': state}
            self.assertEqual(prepare(client)['status'], state)
            client.api.assert_not_called()

    def test_refresh_once_and_require_new_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'qr.png'
            p.write_bytes(b'\x89PNG\r\n\x1a\nold')
            old = time.time() - 90
            os.utime(p, (old, old))
            client = Mock()
            client.state.return_value = {'status': 'offline'}
            def refresh(action):
                self.assertEqual(action, 'QQLogin/RefreshQRcode')
                p.write_bytes(b'\x89PNG\r\n\x1a\nnew')
                return {'code': 0}
            client.api.side_effect = refresh
            self.assertEqual(prepare(client, p, wait=0)['status'], 'scan_qr')
            self.assertEqual(client.api.call_count, 1)

    def test_old_or_invalid_image_is_not_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'qr.png'
            p.write_bytes(b'\x89PNG\r\n\x1a\nold')
            old = time.time() - 90
            os.utime(p, (old, old))
            self.assertIsNone(fresh_image(p))
            client = Mock()
            client.state.return_value = {'status': 'offline'}
            client.api.return_value = {'code': 0}
            self.assertEqual(prepare(client, p, wait=0)['status'], 'qr_pending')
            p.write_bytes(b'not an image')
            self.assertIsNone(fresh_image(p))

    def test_failed_refresh_does_not_fall_back_to_old_qr(self):
        client = Mock()
        client.state.return_value = {'status': 'offline'}
        client.api.return_value = {'code': -1}
        self.assertEqual(prepare(client, Path('missing-file'), wait=0)['status'], 'refresh_failed')

    def test_verify_only_reads_state(self):
        client = Mock()
        client.state.return_value = {'status': 'online', 'expected_account': True}
        self.assertTrue(verify(client, 0)['expected_account'])
        client.api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
