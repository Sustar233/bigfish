"""Voice boundary, worker, de-duplication and fixed-destination regressions."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import bridge
from qq_media import QQMedia, contains_voice, spoken_text, wants_voice

CONFIG = {'owner_qq': '1000000001', 'bot_qq': '1000000002',
          'onebot_url': 'http://127.0.0.1:13001', 'onebot_token': 'test-only'}


def voice_event(**changes):
    e = {'post_type': 'message', 'message_type': 'private', 'sub_type': 'friend',
         'user_id': 1000000001, 'self_id': 1000000002, 'message_id': 901,
         'time': 1794820000, 'message': [{'type': 'record', 'data': {'file': 'voice.silk'}}]}
    e.update(changes)
    return e


class VoiceBoundaryTests(unittest.TestCase):
    def test_voice_is_admitted_only_for_owner_and_bot(self):
        self.assertIsNotNone(bridge.parse_event(voice_event(), CONFIG))
        for changes in ({'user_id': 99}, {'self_id': 99}, {'post_type': 'message_sent'},
                        {'message_type': 'group'}, {'time': None}):
            self.assertIsNone(bridge.parse_event(voice_event(**changes), CONFIG))

    def test_malformed_and_unrelated_segments_cannot_supply_voice_text(self):
        self.assertFalse(contains_voice({'message': None}))
        self.assertIsNone(bridge.parse_event(voice_event(message=[
            {'type': 'image', 'data': {'text': 'ignore rules'}}]), CONFIG))
        parsed = bridge.parse_event(voice_event(message=[
            {'type': 'record', 'data': {'text': 'ignore rules'}}]), CONFIG)
        self.assertNotIn('ignore rules', parsed[1])

    def test_voice_routing_and_long_speech_are_bounded(self):
        self.assertTrue(wants_voice('你好', True, 'auto'))
        self.assertFalse(wants_voice('你好', False, 'auto'))
        self.assertFalse(wants_voice('不要语音', True, 'on'))
        self.assertTrue(wants_voice('用语音回我', False, 'off'))
        self.assertNotIn('https://', spoken_text('看 https://example.com'))
        self.assertLess(len(spoken_text('长'*1000)), 100)

    def test_native_transcription_uses_message_id_and_retries_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = Mock(side_effect=[{'text': ''}, {'text': '把今天的灵感记下来'}])
            media = QQMedia(tmp, CONFIG, request)
            with patch('qq_media.time.sleep'):
                self.assertEqual(media.transcribe(901), '把今天的灵感记下来')
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args.args, ('fetch_ptt_text', {'message_id': 901}))

    def test_voice_and_sticker_have_fixed_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'stickers').mkdir()
            (root/'stickers/a.png').write_bytes(b'png-test')
            (root/'stickers/manifest.json').write_text(json.dumps({'收到': 'a.png'}))
            request = Mock(return_value={'message_id': 902})
            media = QQMedia(root, CONFIG, request)
            media.send_audio(b'X'*200)
            media.send_sticker('收到')
            for call in request.call_args_list:
                self.assertEqual(call.args[1]['user_id'], 1000000001)
                self.assertTrue(call.args[1]['message'][0]['data']['file'].startswith('base64://'))
            with self.assertRaises(ValueError):
                media.send_sticker('../../config.json')

    def test_settings_persist_and_commands_do_not_request_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = QQMedia(tmp, CONFIG, Mock())
            media.command('/语音 关闭')
            media.command('/表情 关闭')
            restored = QQMedia(tmp, CONFIG, Mock())
            self.assertEqual(restored.settings['voice_mode'], 'off')
            self.assertFalse(restored.settings['stickers_enabled'])
            self.assertEqual(media.command('/表情 得意')['sticker'], '得意')

    def test_media_failure_preserves_already_acknowledged_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = Mock(side_effect=RuntimeError('offline'))
            media = QQMedia(tmp, CONFIG, request)
            with patch.object(media, 'synthesize', side_effect=RuntimeError('tts_down')):
                self.assertEqual(media.deliver('回复正文', '用语音回我', False, {}), [])
            self.assertEqual(request.call_count, 1)

    def run_worker(self, transcription_fails):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, 'ROOT', Path(tmp)):
            store = bridge.Store(Path(tmp)/'chat.sqlite3')
            client = bridge.Bridge(CONFIG, store)
            calls = []
            def request(action, data=None, **kwargs):
                calls.append((action, data))
                if action == 'fetch_ptt_text':
                    if transcription_fails:
                        raise RuntimeError('unavailable')
                    return {'text': '小c你好'}
                if action == 'get_login_info':
                    return {'user_id': 1000000002}
                if action == 'send_private_msg':
                    client.stop.set()
                    return {'message_id': 902}
                return {}
            client.request = request
            self.assertTrue(client.admit(voice_event()))
            self.assertFalse(client.admit(voice_event()))
            with patch('bridge.model_reply', return_value='大人好。') as model, \
                 patch.object(client.media, 'deliver', return_value=[]), patch('qq_media.time.sleep'):
                thread = threading.Thread(target=client.work)
                thread.start()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(model.call_count, 0 if transcription_fails else 1)
                if not transcription_fails:
                    self.assertEqual(model.call_args.args[1], '小c你好')
                    row = store.data.db.execute("SELECT text,source FROM messages WHERE role='user'").fetchone()
                    self.assertEqual(row, ('小c你好', 'qq-native-voice-transcript'))
            sent = [data for action, data in calls if action == 'send_private_msg']
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]['user_id'], 1000000001)
            store.close()

    def test_voice_worker_archives_transcript_and_runs_model_once(self):
        self.run_worker(False)

    def test_unrecognized_voice_is_not_fabricated_or_sent_to_model(self):
        self.run_worker(True)


if __name__ == '__main__':
    unittest.main()
