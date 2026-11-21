import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image, ImageDraw
import image_service as app
from gif_output import wants_gif, encode_storyboard, validate_gif


def atlas(moving=True):
    image = Image.new('RGBA', (256, 128), 'white')
    draw = ImageDraw.Draw(image)
    for i in range(8):
        x, y = (i % 4) * 64 + (i * 4 if moving else 0), (i // 4) * 64 + 10
        draw.rectangle((x + 3, y, x + 20, y + 25), fill='blue')
    result = io.BytesIO()
    image.save(result, format='PNG')
    return result.getvalue()


class GifTests(unittest.TestCase):
    def test_explicit_animation_is_distinct_from_static_request(self):
        for text in ['小猪GIF图', 'a looping GIF', '制作动图', '动态表情']:
            self.assertTrue(wants_gif(text))
        for text in ['静态插画', '不要GIF，画PNG', '不用动图']:
            self.assertFalse(wants_gif(text))

    def test_actual_animation_and_timing_survive_encoding(self):
        raw = encode_storyboard(atlas())
        meta = validate_gif(raw)
        self.assertEqual(meta['frames'], 8)
        self.assertEqual(meta['duration_ms'], 2000)
        self.assertEqual(app.image_bytes(raw), 'gif')

    def test_static_or_renamed_png_cannot_be_claimed_as_gif(self):
        with self.assertRaises(ValueError):
            validate_gif(atlas())
        with self.assertRaises(ValueError):
            encode_storyboard(atlas(moving=False))

    def test_both_accounts_receive_original_gif_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = app.Service(tmp, generator=Mock(return_value=atlas()))
            service.ready = Mock()
            service.notify = Mock()
            service.request = Mock(return_value={'file_id': 'native-file-receipt'})
            for bot in app.ACCOUNTS:
                service.submit(bot, 'gif-fixture', '生成一张小猪GIF图')
                service.run_one()
                self.assertEqual(service.latest(bot)['status'], 'sent')
            for call in service.request.call_args_list:
                bot, action, data = call.args
                self.assertEqual(action, 'upload_private_file')
                self.assertEqual(str(data['user_id']), str(app.OWNER))
                self.assertTrue(data['name'].endswith('.gif'))
                validate_gif(base64.b64decode(data['file'].removeprefix('base64://')))
            self.assertIn('EIGHT', service.generator.call_args.args[0])

    def test_upload_timeout_keeps_uncertain_and_never_reuploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = app.Service(tmp, generator=Mock(return_value=atlas()))
            service.ready = Mock()
            service.notify = Mock()
            service.request = Mock(side_effect=TimeoutError())
            bot = next(iter(app.ACCOUNTS))
            service.submit(bot, 'uncertain-gif', '小猪GIF')
            service.run_one()
            self.assertEqual(service.latest(bot)['status'], 'uncertain')
            self.assertFalse(service.run_one())
            service.request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
