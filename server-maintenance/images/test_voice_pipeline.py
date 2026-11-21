"""Run the real smallc voice worker with fake transcription, queue and send."""
import tempfile
import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import image_commands
import voice_image
import bridge


class VoicePipelineTests(unittest.TestCase):
    @unittest.skipUnless('voice_image_reply' in inspect.getsource(bridge.Bridge.work),
                         'requires the media and voice patches on the deployed bridge')
    def test_native_voice_request_enters_image_queue_without_chat_model(self):
        config = {'owner_qq': '1000000001', 'bot_qq': '1000000002',
            'onebot_url': 'http://127.0.0.1:13001', 'onebot_token': 'fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            store = bridge.Store(Path(tmp) / 'chat.sqlite3')
            b = bridge.Bridge(config, store)
            b.media = Mock()
            b.media.transcribe.return_value = '嗯，小c，我想让你帮我生成一张小猪图片。'
            b.media.deliver.return_value = []
            b.verify_account = Mock()
            b.send = Mock(side_effect=lambda reply: b.stop.set())
            event = {'post_type': 'message', 'message_type': 'private', 'sub_type': 'friend',
                'self_id': config['bot_qq'], 'user_id': config['owner_qq'],
                'message_id': 123, 'time': 1700000000,
                'message': [{'type': 'record', 'data': {'file': 'fixture'}}]}
            try:
                with patch.object(image_commands, 'call', return_value={'id': 'fixture'}) as enqueue, \
                     patch.object(bridge, 'model_reply', side_effect=AssertionError('unexpected chat model')):
                    self.assertTrue(b.admit(event))
                    self.assertFalse(b.admit(event))
                    b.work()
                    self.assertEqual(enqueue.call_count, 1)
                    payload = enqueue.call_args.args[1]
                    self.assertEqual(payload['kind'], 'generate')
                    self.assertIn('小猪', payload['prompt'])
                    self.assertEqual(payload['event_key'], '1000000002/1700000000/123')
                    b.media.command.assert_not_called()
                    b.send.assert_called_once()
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
