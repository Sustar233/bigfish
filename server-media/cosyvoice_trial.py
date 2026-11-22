"""Generate four CosyVoice design previews from synthetic QQ lines."""

import argparse
import base64
from io import BytesIO
from getpass import getpass
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import wave


MODEL = 'cosyvoice-v3.5-flash'
LINES = (
    '你倒是很会分工，上班归我，发工资归你。',
    '嗯，今天确实挺累的。你慢慢说，我听着。',
    '欸，我回来了。刚才那句没接上，你再说一遍。',
)
PREVIEW_TEXT = '\n'.join(LINES)
VOICES = {
    'xiaoc-a': ('xcav1', '普通话年轻成年男声，音域中低，清冷沉稳，声音干净靠前，'
                        '像朋友发来短语音。第一句淡淡调侃，第二句放软，第三句轻快一点。'
                        '中等语速，停顿贴着意思走，句尾自然落下。'),
    'xiaoc-b': ('xcbv1', '普通话年轻成年男声，嗓音明亮清晰、略低，有一点藏着的笑意。'
                        '第一句后半句稍压低，第二句自然温和，第三句开头像刚想起来。'
                        '短句连贯，重音随话题变化，像熟人说话。'),
    'feiyu-a': ('fyav1', '普通话年轻成年女声，中音偏软，声线圆润，语速略慢。'
                        '偶尔在开头停半拍，后半句自然接上。调侃时轻轻带笑，听人吐槽时温柔，'
                        '报信时语尾轻轻上扬。像熟人随手录的语音。'),
    'feiyu-b': ('fybv1', '普通话年轻成年女声，音色暖而清亮，听起来有点迷糊又认真。'
                        '口语节奏有轻有重，先轻轻接一句，然后说重点。第二句轻缓，第三句有一点开心。'
                        '普通聊天的音量，语尾收得干净。'),
    'xiaoc-female-a': ('xcfav1', '普通话年轻成年女性，女声中音偏低，音色干净清冷，吐字松弛，语尾平稳自然。'
                               '和熟人发语音时的音量和节奏。第一句淡淡调侃，第二句放柔，第三句轻快，停顿跟着意思走。'),
    'xiaoc-female-b': ('xcfbv1', '普通话年轻成年女性，女声清亮有质感，语气冷静、有主见，偶尔带一点藏不住的笑意。'
                               '短句利落，重音克制，像熟人顺手发来的一条语音。第一句微微调侃，第二句轻缓，第三句轻快。'),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def design(key, workspace, prefix, voice_prompt):
    host = f'{workspace}.cn-beijing.maas.aliyuncs.com' if workspace else 'dashscope.aliyuncs.com'
    payload = {
        'model': 'voice-enrollment',
        'input': {'action': 'create_voice', 'target_model': MODEL, 'voice_prompt': voice_prompt,
                  'preview_text': PREVIEW_TEXT, 'prefix': prefix, 'language_hints': ['zh']},
        'parameters': {'sample_rate': 24000, 'response_format': 'wav'},
    }
    request = urllib.request.Request(f'https://{host}/api/v1/services/audio/tts/customization',
                                      data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                      headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=45) as response:
            result = json.loads(response.read(8 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'百炼返回 HTTP {error.code}') from None
    output = result.get('output', {})
    voice = output.get('voice_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{5,160}', voice):
        raise ValueError('百炼响应未返回有效音色 ID')
    data = base64.b64decode(output['preview_audio']['data'], validate=True)
    with wave.open(BytesIO(data)) as sample:
        duration = sample.getnframes() / sample.getframerate()
        if sample.getframerate() != 24000 or not 1 <= duration <= 60:
            raise ValueError('试听音频参数异常')
    return voice, data, duration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    credentials = parser.add_mutually_exclusive_group()
    credentials.add_argument('--key-file', type=Path, default=Path('.private/cosyvoice-api-key.txt'))
    credentials.add_argument('--prompt-key', action='store_true', help='Read the key from a hidden prompt')
    parser.add_argument('--workspace', help='Optional Beijing Model Studio Workspace ID')
    parser.add_argument('--out', type=Path, default=Path('.private/cosyvoice-trial'))
    parser.add_argument('--print-lines', action='store_true')
    parser.add_argument('--voice', choices=VOICES, action='append', help='Generate only the selected variant(s)')
    args = parser.parse_args()
    if args.print_lines:
        print(PREVIEW_TEXT)
        return 0
    if args.workspace and not re.fullmatch(r'[a-zA-Z0-9-]{1,100}', args.workspace):
        parser.error('业务空间 ID 格式不正确')
    try:
        key = (getpass('Bailian API key (hidden): ') if args.prompt_key else
               args.key_file.read_text(encoding='utf-8-sig')).strip()
    except OSError:
        parser.error('找不到百炼 API Key 文件')
    if not re.fullmatch(r'sk-[A-Za-z0-9_-]{16,200}', key):
        parser.error('密钥文件应只有一行百炼 API Key')
    args.out.mkdir(parents=True, exist_ok=True)
    for label in args.voice or VOICES:
        prefix, prompt = VOICES[label]
        audio = args.out / f'{label}.wav'
        metadata = args.out / f'{label}.json'
        if audio.exists() and metadata.exists():
            continue
        try:
            voice, data, duration = design(key, args.workspace, prefix, prompt)
        except (RuntimeError, urllib.error.URLError, TimeoutError, KeyError, ValueError, wave.Error, EOFError) as error:
            message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            print(f'{label} 试音未完成（{message}）', file=sys.stderr)
            return 1
        audio.write_bytes(data)
        metadata.write_text(json.dumps({'voice_id': voice, 'model': MODEL, 'seconds': duration}, ensure_ascii=False) + '\n',
                            encoding='utf-8')
        print(f'{label} 试音完成，{duration:.1f} 秒')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
