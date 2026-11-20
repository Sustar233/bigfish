"""Apply the media integration to the inspected bridge, keeping its existing logic."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/home/ubuntu/qq-codex/bridge')
p = ROOT/'bridge.py'
s = p.read_text()
if 'from qq_media import' in s:
    raise SystemExit('Already integrated; inspect before applying again')
backup = ROOT/'.private'/('media-code-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700)
shutil.copy2(p, backup/'bridge.py')


def replace(old, new):
    global s
    if s.count(old) != 1:
        raise RuntimeError('Expected exactly one patch location: '+old[:90])
    s = s.replace(old, new, 1)


replace('from qq_data import Data, approved_persona',
        'from qq_data import Data, approved_persona\nfrom qq_media import QQMedia, STICKERS, contains_voice')
replace("    if not text or mid is None or not isinstance(event.get('time'), (int, float)):",
        "    if not text and contains_voice(event):\n        text = '[语音消息，等待转写]'\n"
        "    if not text or mid is None or not isinstance(event.get('time'), (int, float)):")
replace("context=None, search_query=None):", "context=None, search_query=None, media=None):")
replace('        command = codex_command(schema, output)\n        system =',
        "        if media is not None:\n"
        "            spec = json.loads(schema.read_text())\n"
        "            spec['properties']['sticker'] = {'type': 'string', 'enum': ['none'] + list(STICKERS)}\n"
        "            spec['required'].append('sticker')\n"
        "            schema.write_text(json.dumps(spec))\n"
        '        command = codex_command(schema, output)\n        system =')
replace("        prompt += '\\n聊天记录 JSON：\\n' + json.dumps(",
        "        if media is not None:\n"
        "            prompt += ('\\n程序已接通QQ语音转写、语音回复与鱼塘表情包。用户语音转写按用户消息理解。'\n"
        "                '程序负责实际发送；不要提前声称语音或图片已送到。'\n"
        "                '同一个JSON另含sticker字段：none、收到、开心、疑惑、委屈、得意、围观、递报、困了。'\n"
        "                '默认none；闲聊确实合适时偶尔选一张，用户明确要表情包时选最贴切的一个。'\n"
        "                '回答正事或严肃话题时用none，不用文字假装发了图片。')\n"
        "        prompt += '\\n聊天记录 JSON：\\n' + json.dumps(")
replace("        reply = result['reply'].strip()[:2300]",
        "        if media is not None:\n"
        "            chosen = result.get('sticker', 'none')\n"
        "            media['sticker'] = chosen if chosen in STICKERS else 'none'\n"
        "        reply = result['reply'].strip()[:2300]")
replace('        self.tasks = queue.Queue(maxsize=5)',
        '        self.tasks = queue.Queue(maxsize=5)\n        self.media_inputs = {}\n'
        "        self.media = QQMedia(ROOT, config, lambda action, data: self.request(action, data)) if 'owner_qq' in config else None")
replace('        self.tasks.put_nowait(parsed)',
        "        self.media_inputs[parsed[0]] = {'voice': contains_voice(event), 'message_id': event.get('message_id')}\n"
        '        self.tasks.put_nowait(parsed)')
replace('                reply, export_path = self.command(text, key)',
        "                incoming = self.media_inputs.pop(key, {})\n"
        "                voice_input = incoming.get('voice', False)\n"
        "                choices = {}\n"
        "                if voice_input:\n"
        "                    try:\n"
        "                        transcript = self.media.transcribe(incoming['message_id'])\n"
        "                    except Exception as exc:\n"
        "                        self.store.data.mark(key+'/user', 'voice_unrecognized')\n"
        "                        self.verify_account()\n"
        "                        self.send('这条语音我没听清，QQ转文字没成功。大人可以再说一遍，或者先打字给我。')\n"
        "                        self.store.mark(key, 'voice_unrecognized')\n"
        "                        log('voice_transcription_failed', error_type=type(exc).__name__)\n"
        "                        continue\n"
        "                    original_text = '' if text == '[语音消息，等待转写]' else text\n"
        "                    text = (original_text+'\\n'+transcript).strip()\n"
        "                    with self.store.data.lock, self.store.data.db:\n"
        "                        self.store.data.db.execute('UPDATE messages SET text=?,source=?,status=? WHERE event_key=?',\n"
        "                            (text, 'qq-native-voice-transcript', 'transcribed', key+'/user'))\n"
        "                    log('voice_transcribed', transcript_chars=len(transcript))\n"
        "                media_command = self.media.command(text)\n"
        "                if media_command is not None:\n"
        "                    choices.update(media_command)\n"
        "                    reply, export_path = media_command['reply'], None\n"
        "                else:\n"
        "                    reply, export_path = self.command(text, key)")
replace("                        context['received_at'] = timestamp(received)",
        "                        context['received_at'] = timestamp(received)\n"
        "                        context['input_kind'] = 'voice_transcript' if voice_input else 'text'\n"
        "                        context['stickers_enabled'] = self.media.settings['stickers_enabled']")
replace('candidates=candidates, context=context)',
        'candidates=candidates, context=context, media=choices)')
replace('                self.send(reply)\n                self.store.data.mark',
        "                self.send(reply)\n"
        "                if append or media_command is not None:\n"
        "                    for item in self.media.deliver(reply, text, voice_input, choices):\n"
        "                        self.store.data.record(key+'/'+item['kind'], 'assistant',\n"
        "                            '[语音回复]' if item['kind']=='voice' else '[表情包：'+item['name']+']',\n"
        "                            status='sent', source='qq-media', payload=item)\n"
        '                self.store.data.mark')
replace('直接发文字聊天；支持北京时间、自然分段和公开联网查询。',
        '直接发文字或语音聊天；支持QQ转文字、语音回复、表情包和公开联网查询。\\n/语音 自动｜开启｜关闭｜测试｜男声｜女声\\n/表情 收到｜开心｜疑惑｜委屈｜得意｜围观｜递报｜困了')
replace('支持北京时间、6小时空闲新话题和公开联网查询；不执行服务器命令。',
        '支持QQ语音转文字、语音回复、鱼塘表情包、北京时间和公开联网查询；不执行服务器命令。')
ast.parse(s)
tmp = p.with_suffix('.py.media-new')
tmp.write_text(s)
tmp.chmod(0o600)
tmp.replace(p)
print('BRIDGE_PATCHED', hashlib.sha256(s.encode()).hexdigest(), 'BACKUP', backup)
