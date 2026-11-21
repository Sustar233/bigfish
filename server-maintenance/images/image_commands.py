"""Small deterministic QQ client; prompts cannot select a tool, path or recipient."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path('/home/ubuntu/server-maintenance/images')
RULES = json.loads(Path(__file__).with_name('image_intents.json').read_text(encoding='utf-8'))


def parse(text, image_count=0):
    text = text.strip()
    if text in ('/生图状态', '生图状态', '/改图状态', '改图状态'):
        return 'status', ''
    match = re.match(r'^(?:生图\s*[:：]|/生图(?:\s+|$))([\s\S]*)$', text)
    if match:
        return 'generate', match[1].strip()
    match = re.match(r'^(?:(?:改图|修图|编辑图片|修改图片)\s*[:：]|/(?:改图|修图)(?:\s+|$))([\s\S]*)$', text)
    if match:
        return 'edit', match[1].strip()
    if not text or text.startswith('/'):
        return None
    if any(re.search(RULES[k], text, re.I) for k in ('analysis_first', 'negative', 'generation_question', 'non_image_generation')):
        return None
    if (not re.search(RULES['generation_question'], text, re.I)
            and not re.search(RULES['non_image_generation'], text, re.I)
            and not re.match(r'^(?:比如|例如|举例|假设|假如|[“\"「『])', text)):
        if any(re.search(pattern, text, re.I) for pattern in RULES['generation']):
            return 'generate', text
    if not image_count:
        return None
    if re.search(RULES['edit_action'], text, re.I) and not re.search(r'哪里需要|如何修改|怎么修改', text):
        return 'edit', text
    if re.search(RULES['non_edit'], text, re.I):
        return None
    return 'edit', text


def call(path, data):
    token = (ROOT / '.private/client-token').read_text().strip()
    req = urllib.request.Request('http://127.0.0.1:13210' + path,
        data=json.dumps(data).encode(), headers={'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=8) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            return json.load(exc)
        raise


def image_command(text, key, bot=None, image_count=0, message_id=None):
    parsed = parse(text, image_count)
    if parsed is None:
        return None
    action, prompt = parsed
    if action == 'edit' and image_count and not prompt:
        prompt = RULES['default_edit']
    if action == 'edit' and (not image_count or message_id is None):
        return '图没跟过来，把图和要改的地方放同一条消息里发我。'
    if action in ('generate', 'edit') and not 1 <= len(prompt) <= 4000:
        return '用法：生图：一个可爱的小猪\n每条描述请控制在1–4000字，一次画一张。'
    if image_count > 5:
        return '一次最多5张就好，第一张放要改的图，后面放参考图。'
    try:
        if action == 'status':
            job = call('/status', {'bot': bot}).get('job')
            if not job:
                return '还没画过呢。想画什么，发“生图：……”给我就行。'
            labels = {'queued': '前面还有图在画，稍等我一下。', 'generating': '还在画，画好就发你。', 'generated': '图已经好了，等QQ连上就发。',
                'sending': '画好了，正在发给你。', 'sent': '图已经发过去啦。', 'sent_relayed': '图已经补发过去啦。', 'delivery_failed': '图好了，但QQ没传上去，成品还留着。', 'failed': '这次没弄成。', 'uncertain': '刚才没确认发没发到，你先看看聊天里有没有图，我先不重发。'}
            return '[绘图' + job['id'][:6] + '] ' + labels.get(job['status'], job['status'])
        result = call('/jobs', {'bot': bot, 'event_key': key, 'prompt': prompt,
            'kind': action, 'message_id': str(message_id) if image_count else None})
        if result.get('error'):
            return '这会儿还有几张在画，等会儿再来找我。' if result['error'] == 'busy' else '刚才没接上，过会儿再试一下。'
        if result.get('duplicate'):
            return '这条我接过了，没再画一遍。'
        if action == 'edit':
            return '好，改第一张，后面的当参考。' if image_count > 1 else '好，我改改，弄好发你。'
        return '好，我照着参考图画。' if image_count else '好，我画画看。'
    except Exception:
        return '画图那边暂时没连上，过会儿再试。'
