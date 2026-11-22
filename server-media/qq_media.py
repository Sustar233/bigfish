"""Private QQ voice and curated stickers. No model or shell-selected paths."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

STICKERS = ('收到', '开心', '疑惑', '委屈', '得意', '围观', '递报', '困了')
XIAOC_VOICE_B = 'cosyvoice-xiaoc-b'


def contains_voice(event):
    segments = event.get('message')
    return isinstance(segments, list) and any(
        isinstance(s, dict) and s.get('type') == 'record' for s in segments)


def spoken_text(text):
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'```[\s\S]*?```', '代码请看文字回复。', text)
    text = re.sub(r'[*#`_]+', '', text).strip()
    if len(text) > 240:
        return '这份回复有点长，我给您放在文字里啦，慢慢看。'
    return text or '链接已经放在文字回复里啦。'


def wants_voice(text, voice_input, mode):
    if re.search(r'不要.{0,3}语音|别.{0,3}语音|只.{0,3}文字|用文字回复', text):
        return False
    explicit = bool(re.search(r'用语音|发.{0,4}语音|语音回|说给我听|念给我听|读给我听', text))
    return explicit or mode == 'on' or (mode == 'auto' and voice_input)


class QQMedia:
    def __init__(self, root, config, request):
        self.root = Path(root)
        self.private = self.root / '.private'
        self.owner = int(config['owner_qq'])
        self.request = request
        self.settings_path = self.private / 'media-settings.json'
        self.settings = {'voice_mode': 'auto', 'voice': 'zh-CN-YunxiNeural',
                         'last_sticker_at': 0, 'stickers_enabled': True}
        if self.settings_path.exists():
            saved = json.loads(self.settings_path.read_text())
            self.settings.update({k: saved[k] for k in self.settings if k in saved})

    def save(self):
        self.private.mkdir(mode=0o700, exist_ok=True)
        tmp = self.settings_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.settings_path)

    def transcribe(self, message_id):
        for attempt in range(2):
            try:
                result = self.request('fetch_ptt_text', {'message_id': message_id})
                text = result.get('text', '') if isinstance(result, dict) else ''
                if isinstance(text, str) and text.strip():
                    return text.strip()
            except Exception:
                pass
            if attempt == 0:
                time.sleep(1)
        raise RuntimeError('qq_transcription_unavailable')

    def command(self, text):
        cmd, _, arg = text.strip().partition(' ')
        arg = arg.strip()
        if cmd in ('/语音', '/voice'):
            modes = {'自动': 'auto', 'auto': 'auto', '开启': 'on', '开': 'on',
                     'on': 'on', '关闭': 'off', '关': 'off', 'off': 'off', '文字': 'off'}
            if arg in modes:
                self.settings['voice_mode'] = modes[arg]
                self.save()
                label = {'auto': '你发语音我就用语音回，文字来信就打字。',
                         'on': '好，我用语音回复。',
                         'off': '好，日常回复切回文字；你发来的语音仍然会听。'}
                return {'reply': label[modes[arg]], 'quiet': True}
            if arg == '测试':
                return {'reply': '小c来试个音，你听听这个声音怎么样。', 'voice': True}
            if arg.lower() == 'b':
                self.settings['voice'] = XIAOC_VOICE_B
                self.save()
                return {'reply': '换成小c的 B 版女声啦。', 'voice': True}
            if arg == '女声':
                self.settings['voice'] = 'zh-CN-XiaoxiaoNeural'
                self.save()
                return {'reply': '换成晓晓的普通话女声啦。', 'voice': True}
            if arg == '男声':
                self.settings['voice'] = 'zh-CN-YunxiNeural'
                self.save()
                return {'reply': '换成云希的普通话男声啦。', 'voice': True}
            return {'reply': '直接发语音即可，我用QQ自带功能转文字来听。\n'
                    '/语音 自动｜开启｜关闭\n/语音 B｜男声｜女声｜测试\n'
                    '也可以直接说“用语音回我”。', 'quiet': True}
        if cmd in ('/表情', '/表情包'):
            if arg in ('关闭', '开启'):
                self.settings['stickers_enabled'] = arg == '开启'
                self.save()
                return {'reply': '表情包已' + arg + '。', 'quiet': True}
            if arg in STICKERS:
                return {'reply': {'收到': '收到，大人。', '递报': '大人，报纸送到。',
                        '围观': '小c搬个凳子。'}.get(arg, '给大人来一张。'),
                        'sticker': arg, 'explicit_sticker': True, 'quiet': True}
            return {'reply': '鱼塘表情柜：' + '、'.join(STICKERS)
                    + '。\n例如 /表情 得意；也可以直接让我发表情包。\n/表情 开启｜关闭', 'quiet': True}
        return None

    def synthesize(self, text):
        if self.settings['voice'] == XIAOC_VOICE_B:
            from cosyvoice_feiyu import XIAOC_SOCKET, read_audio
            return read_audio(text, socket_path=XIAOC_SOCKET)
        cache = self.private / 'media-cache'
        cache.mkdir(mode=0o700, exist_ok=True)
        for old in cache.glob('tts-*'):
            if old.is_file() and time.time() - old.stat().st_mtime > 86400:
                old.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix='tts-', dir=cache) as tmp:
            path = Path(tmp) / 'voice.mp3'
            env = {k: v for k, v in os.environ.items()
                   if not any(x in k.upper() for x in ('SECRET', 'TOKEN', 'PASSWORD', 'API_KEY'))}
            result = subprocess.run([str(self.private / 'media-venv/bin/python'),
                str(self.root / 'tts_worker.py'), str(path), self.settings['voice']],
                input=text, text=True, capture_output=True, timeout=50, env=env)
            if result.returncode or not path.exists() or not 100 < path.stat().st_size < 2*1024*1024:
                raise RuntimeError('voice_synthesis_failed')
            return path.read_bytes()

    def send_audio(self, audio):
        if not 100 < len(audio) < 2*1024*1024:
            raise ValueError('invalid_voice_size')
        return self.request('send_private_msg', {'user_id': self.owner,
            'message': [{'type': 'record', 'data': {
                'file': 'base64://' + base64.b64encode(audio).decode()}}]})

    def send_sticker(self, name):
        if name not in STICKERS:
            raise ValueError('unknown_sticker')
        manifest = json.loads((self.root / 'stickers/manifest.json').read_text())
        path = (self.root / 'stickers' / manifest[name]).resolve()
        if path.parent != (self.root / 'stickers').resolve():
            raise ValueError('invalid_sticker_path')
        raw = path.read_bytes()
        return self.request('send_private_msg', {'user_id': self.owner,
            'message': [{'type': 'image', 'data': {'file': 'base64://' +
                        base64.b64encode(raw).decode(), 'sub_type': 1}}]})

    def deliver(self, reply, user_text, voice_input, choices):
        sent = []
        voice = choices.get('voice') or (not choices.get('quiet') and
            wants_voice(user_text, voice_input, self.settings['voice_mode']))
        if voice:
            try:
                raw = self.synthesize(reply)
            except Exception:
                self.request('send_private_msg', {'user_id': self.owner, 'message': [{'type': 'text', 'data': {'text': reply}}]})
            else:
                result = self.send_audio(raw)
                sent.append({'kind': 'voice', 'message_id': (result or {}).get('message_id')})
        sticker = choices.get('sticker', 'none')
        explicit = choices.get('explicit_sticker') or bool(re.search(r'表情包|发.{0,4}表情|来.{0,4}表情', user_text))
        allowed = self.settings['stickers_enabled'] or choices.get('explicit_sticker')
        if allowed and sticker in STICKERS and (explicit or time.time()-self.settings['last_sticker_at'] > 300):
            try:
                result = self.send_sticker(sticker)
                self.settings['last_sticker_at'] = time.time()
                self.save()
                sent.append({'kind': 'sticker', 'name': sticker, 'message_id': (result or {}).get('message_id')})
                print(json.dumps({'event': 'sticker_sent', 'name': sticker,
                                  'message_id': (result or {}).get('message_id')}, ensure_ascii=False), flush=True)
            except Exception as exc:
                print(json.dumps({'event': 'sticker_failed', 'error_type': type(exc).__name__}), flush=True)
                if explicit:
                    self.notify('这张表情包没送稳，先记小c一笔。')
        return sent

    def notify(self, text):
        # Media failure must not turn an acknowledged text reply into an uncertain send.
        try:
            self.request('send_private_msg', {'user_id': self.owner, 'message': [
                {'type': 'text', 'data': {'text': text}}]})
        except Exception as exc:
            print(json.dumps({'event': 'media_notice_failed', 'error_type': type(exc).__name__}), flush=True)
