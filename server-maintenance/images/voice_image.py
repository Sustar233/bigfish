"""Normalize trusted QQ voice transcription before the shared drawing parser."""
import re

LEAD = r'^(?:(?:嗯+|呃+|啊|那个|就是|你好|小c|大肥鱼|请你|我(?:现在)?(?:想要?|需要|希望)(?:让你|你)?)[，,。:：\s]*)+'


def normalize_voice(text):
    if not isinstance(text, str) or not text.strip():
        return ''
    return re.sub(LEAD, '', text.strip(), flags=re.I).strip()


def voice_image_command(text, key, bot, image_count=0, message_id=None):
    from image_commands import parse, image_command
    normalized = normalize_voice(text)
    if not normalized or parse(normalized, image_count) is None:
        return None
    return image_command(normalized, key, bot, image_count=image_count, message_id=message_id)
