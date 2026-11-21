"""QQ conversational text and voice presentation."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile


POLICY = json.loads(Path(__file__).with_name('reply-policy.json').read_text(encoding='utf-8'))


def bubbles(text):
    if len(text)<POLICY['split_at_characters'] or any(marker in text for marker in POLICY['keep_whole_if_contains']):
        return [text]
    cuts=[m.end() for m in re.finditer(POLICY['break_pattern'],text) if 0<m.end()<len(text)]
    at=min(cuts,key=lambda i:abs(i-len(text)/2)) if cuts else len(text)//2
    return [s.strip() for s in (text[:at],text[at:]) if s.strip()]


def audio(text):
    root=Path('/home/ubuntu/qq-codex/bridge')
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)/'reply.mp3'
        subprocess.run([str(root/'.private/media-venv/bin/python'),str(root/'tts_worker.py'),
                        str(out),'zh-CN-YunxiNeural'],input=text,text=True,check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=55)
        raw=out.read_bytes()
        if not 100<len(raw)<2*1024*1024:
            raise ValueError('voice_size')
        return raw


if __name__=='__main__':
    sys.stdout.buffer.write(audio(sys.stdin.read(4001)))
