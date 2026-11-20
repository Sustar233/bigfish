import base64
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

import image_commands as client
import image_service as app

IMAGE = b'\x89PNG\r\n\x1a\n' + bytes(200)
BOT = '1000000002'


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = app.Service(self.tmp.name, generator=Mock(return_value=IMAGE))
        self.service.ready = Mock()
        self.service.request = Mock(return_value={'message_id': 123})
        self.service.notify = Mock()

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_explicit_commands_match(self):
        for text in ('生图：一个小猪', '生图:一个小猪', '/生图 一个小猪'):
            self.assertEqual(client.parse(text), ('generate', '一个小猪'))
        for text in ('比如“生图：小猪”', '我想研究生图', '给别人发图', '生图像是个好功能'):
            self.assertIsNone(client.parse(text))
        self.assertEqual(client.parse('/生图状态'), ('status', ''))

    def test_invalid_prompts_are_not_submitted(self):
        with patch.object(client, 'call') as call:
            for text in ('生图：', '生图：' + '字' * 4001):
                self.assertIn('用法', client.image_command(text, 'key'))
            call.assert_not_called()

    def test_unknown_bot_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.submit('99999', 'test', 'pig')

    def test_duplicate_does_not_generate_twice(self):
        first = self.service.submit(BOT, 'incoming-1', 'pig')
        self.assertTrue(self.service.submit(BOT, 'incoming-1', 'pig')['duplicate'])
        self.assertTrue(self.service.run_one())
        self.assertFalse(self.service.run_one())
        self.service.generator.assert_called_once()
        self.assertEqual(self.service.latest(BOT)['status'], 'sent')
        self.assertEqual(first['id'], self.service.latest(BOT)['id'])

    def test_each_account_returns_to_fixed_owner(self):
        for bot in app.ACCOUNTS:
            self.service.submit(bot, 'incoming-1', 'pig')
            self.service.run_one()
        for call in self.service.request.call_args_list:
            bot, action, data = call.args
            self.assertIn(bot, app.ACCOUNTS)
            self.assertEqual(action, 'send_private_msg')
            self.assertEqual(data['user_id'], 1000000001)
            self.assertEqual(data['message'][0]['type'], 'image')
        self.assertEqual(self.service.generator.call_count, 2)

    def test_queue_is_bounded(self):
        for n in range(4):
            self.service.submit(BOT, str(n), 'pig')
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.service.submit(BOT, 'overflow', 'pig')

    def test_offline_account_does_not_spend_generation(self):
        self.service.ready.side_effect = RuntimeError('offline')
        self.service.submit(BOT, 'offline', 'pig')
        self.service.run_one()
        self.service.generator.assert_not_called()
        self.assertEqual(self.service.latest(BOT)['error'], 'offline')

    def test_timeout_is_not_retried(self):
        self.service.generator.side_effect = RuntimeError('timeout')
        self.service.submit(BOT, 'timeout', 'pig')
        self.service.run_one()
        self.assertFalse(self.service.run_one())
        self.service.generator.assert_called_once()
        self.assertEqual(self.service.latest(BOT)['error'], 'timeout')

    def test_ambiguous_send_is_not_retried(self):
        self.service.request.side_effect = TimeoutError()
        self.service.submit(BOT, 'uncertain', 'pig')
        self.service.run_one()
        self.assertEqual(self.service.latest(BOT)['status'], 'uncertain')
        self.assertFalse(self.service.run_one())
        self.service.request.assert_called_once()

    def test_restart_does_not_rerun_running_or_sending_jobs(self):
        one = self.service.submit(BOT, 'one', 'pig')
        two = self.service.submit(BOT, 'two', 'pig')
        self.service.mark(one['id'], 'generating')
        self.service.mark(two['id'], 'sending')
        fresh = app.Service(self.tmp.name, generator=Mock())
        self.assertFalse(fresh.run_one())
        fresh.generator.assert_not_called()
        with fresh.db() as db:
            states = {r['id']: r['status'] for r in db.execute('SELECT * FROM jobs')}
        self.assertEqual(states[one['id']], 'failed')
        self.assertEqual(states[two['id']], 'uncertain')

    def test_prose_cannot_select_an_existing_private_file(self):
        with patch.object(app, 'generated_files', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                app.native_image(json.dumps({'item': {'type': 'agent_message',
                    'text': '/home/ubuntu/.codex/auth.json'}}), {})

    def test_native_event_and_single_artifact_are_accepted(self):
        event = {'item': {'type': 'image_generation', 'status': 'completed',
            'result': base64.b64encode(IMAGE).decode()}}
        self.assertEqual(app.native_image(json.dumps(event), {}), IMAGE)
        p = Path(self.tmp.name) / 'native.png'
        p.write_bytes(IMAGE)
        with patch.object(app, 'generated_files', return_value={p: (1, len(IMAGE))}):
            self.assertEqual(app.native_image('', {}), IMAGE)
            with self.assertRaises(RuntimeError):
                app.native_image('', {p: (1, len(IMAGE))})

    def test_http_rejects_unauthenticated_and_wrong_account(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.handler(self.service, 'test-token'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/jobs'
        try:
            for token, expected in (('', 403), ('test-token', 400)):
                request = urllib.request.Request(url, data=json.dumps({'bot': '99999',
                    'prompt': 'pig', 'event_key': 'one'}).encode(),
                    headers={'Authorization': 'Bearer ' + token})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3)
                self.assertEqual(error.exception.code, expected)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
