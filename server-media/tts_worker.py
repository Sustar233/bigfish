"""Isolated Edge TTS worker; only the text to speak is supplied on stdin."""
import asyncio
import sys
import edge_tts


async def main():
    text = sys.stdin.read(4001).strip()
    if not text or len(text) > 4000:
        raise ValueError('invalid_speech_length')
    if sys.argv[2] not in ('zh-CN-YunxiNeural', 'zh-CN-XiaoxiaoNeural'):
        raise ValueError('voice_not_allowed')
    speech = edge_tts.Communicate(text, sys.argv[2], rate='+0%')
    await asyncio.wait_for(speech.save(sys.argv[1]), timeout=40)


if __name__ == '__main__':
    asyncio.run(main())
