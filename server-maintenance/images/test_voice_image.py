import unittest
from unittest.mock import patch
from voice_image import normalize_voice, voice_image_command


class VoiceImageTests(unittest.TestCase):
    def test_spoken_request_submits_original_event_only_once(self):
        with patch('image_commands.call', return_value={'id': 'fixture'}) as call:
            reply = voice_image_command('嗯，那个，小c，我想让你帮我生成一张小猪图片。',
                                        'same-voice-event', '1000000002', message_id=321)
            self.assertIsNotNone(reply)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[1]['event_key'], 'same-voice-event')
            self.assertIn('小猪', call.call_args.args[1]['prompt'])

    def test_plain_talk_negative_and_capability_questions_do_not_submit(self):
        with patch('image_commands.call') as call:
            for text in ['今天好累啊', '嗯，不要生图，先聊一会儿', '小c，你会生图吗？',
                         '我想了解生图怎么用', '比如，帮我画一张图片', '']:
                self.assertIsNone(voice_image_command(text, 'event', '1000000002'))
            call.assert_not_called()

    def test_reference_images_and_gif_request_reach_queue(self):
        with patch('image_commands.call', return_value={'id': 'fixture'}) as call:
            voice_image_command('你好，我需要你生成一张摇尾巴的鱼GIF图。', 'event',
                                '1000000002', image_count=1, message_id=123)
            payload = call.call_args.args[1]
            self.assertEqual(payload['kind'], 'generate')
            self.assertEqual(payload['message_id'], '123')
            self.assertIn('GIF', payload['prompt'])


if __name__ == '__main__':
    unittest.main()
