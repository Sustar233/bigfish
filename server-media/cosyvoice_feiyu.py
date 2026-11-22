"""Synthesize the selected QQ voice through a local systemd socket."""

import json
import os
from pathlib import Path
import re
import socket
from socketserver import BaseRequestHandler, UnixStreamServer
import sys
import urllib.error
import urllib.parse
import urllib.request


SOCKET = '/run/cosyvoice-feiyu.sock'
XIAOC_SOCKET = '/run/cosyvoice-xiaoc.sock'
FEIYU_INSTRUCTION = '像给熟人发语音，语气柔和，语速稍慢，停顿自然。'
XIAOC_INSTRUCTION = '像给熟人发语音，语气清亮、利落，停顿自然。调侃的话可以带一点笑意。'
MODEL = 'cosyvoice-v3.5-flash'
MAX_TEXT = 400
MAX_AUDIO = 2 * 1024 * 1024 - 1
BASE = 'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def synthesize(text, voice, key, instruction):
    if not re.fullmatch(r'cosyvoice-v3\.5-flash-vd-[A-Za-z0-9_-]{1,120}', voice):
        raise ValueError('invalid_voice_id')
    payload = {'model': MODEL, 'input': {
        'text': text, 'voice': voice, 'format': 'mp3', 'sample_rate': 24000,
        'instruction': instruction,
    }}
    request = urllib.request.Request(BASE + 'SpeechSynthesizer',
                                     data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=18) as response:
        result = json.loads(response.read(128 * 1024))
    url = urllib.parse.urlsplit(result['output']['audio']['url'])
    if not re.fullmatch(r'dashscope-result-[a-z0-9-]+\.oss-cn-[a-z0-9-]+\.aliyuncs\.com', url.netloc):
        raise ValueError('unexpected_audio_host')
    if url.scheme not in ('http', 'https'):
        raise ValueError('unexpected_audio_scheme')
    # The audio URL is pre-signed and does not receive the API credential.
    with opener.open(url._replace(scheme='https').geturl(), timeout=8) as response:
        audio = response.read(MAX_AUDIO + 1)
    if not 100 < len(audio) <= MAX_AUDIO or not (audio.startswith(b'ID3') or audio[0] == 255 and audio[1] & 224 == 224):
        raise ValueError('invalid_mp3')
    return audio


class Handler(BaseRequestHandler):
    def handle(self):
        self.request.settimeout(6)
        try:
            raw = self.request.makefile('rb').readline(4 * MAX_TEXT + 2)
            text = raw.decode('utf-8').strip()
            if not raw.endswith(b'\n') or not 1 <= len(text) <= MAX_TEXT:
                raise ValueError('invalid_text')
            audio = synthesize(text, self.server.voice, self.server.key, self.server.instruction)
            self.request.sendall(audio)
        except urllib.error.HTTPError as error:
            print(f'CosyVoice HTTP {error.code}', file=sys.stderr, flush=True)
        except Exception as error:
            print(f'CosyVoice {type(error).__name__}', file=sys.stderr, flush=True)


def serve(profile):
    socket_path, instruction = {
        'feiyu': (SOCKET, FEIYU_INSTRUCTION),
        'xiaoc': (XIAOC_SOCKET, XIAOC_INSTRUCTION),
    }[profile]
    with UnixStreamServer(socket_path, Handler, bind_and_activate=False) as server:
        server.socket.close()
        server.socket = socket.socket(fileno=3)
        server.voice = Path(f'/etc/cosyvoice-{profile}/voice').read_text().strip()
        server.key = (Path(os.environ['CREDENTIALS_DIRECTORY']) / 'bailian').read_text().strip()
        server.instruction = instruction
        server.serve_forever()


def read_audio(text, socket_path=SOCKET):
    text = ' '.join(text.split())
    if not 1 <= len(text) <= MAX_TEXT:
        raise ValueError('invalid_text')
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(30)
        conn.connect(socket_path)
        conn.sendall(text.encode() + b'\n')
        with conn.makefile('rb') as stream:
            audio = stream.read(MAX_AUDIO + 1)
    if not 100 < len(audio) <= MAX_AUDIO:
        raise RuntimeError('no_audio')
    return audio


if __name__ == '__main__':
    if sys.argv[1:2] == ['serve']:
        serve(sys.argv[2] if len(sys.argv) == 3 else 'feiyu')
    else:
        sys.stdout.buffer.write(read_audio(sys.stdin.read(MAX_TEXT + 1)))
