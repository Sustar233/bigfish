"""Small deterministic QQ client; prompts cannot select a tool, path or recipient."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path('/home/ubuntu/server-maintenance/images')


def parse(text):
    if text.strip() in ('/生图状态', '生图状态'):
        return 'status', ''
    match = re.match(r'^(?:生图\s*[:：]|/生图(?:\s+|$))([\s\S]*)$', text.strip())
    return ('generate', match[1].strip()) if match else None


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


def image_command(text, key, bot='1000000002'):
    parsed = parse(text)
    if parsed is None:
        return None
    action, prompt = parsed
    if action == 'generate' and not 1 <= len(prompt) <= 4000:
        return '用法：生图：一个可爱的小猪\n每条描述请控制在1–4000字，一次画一张。'
    try:
        if action == 'status':
            job = call('/status', {'bot': bot}).get('job')
            if not job:
                return '还没有生图任务。可以发：生图：一个可爱的小猪'
            labels = {'queued': '排队中', 'generating': '正在画', 'generated': '已画好，待投递',
                'sending': '正在发图', 'sent': '已发出', 'failed': '未完成', 'uncertain': '发送结果待核对，未自动重发'}
            return '[绘图' + job['id'][:6] + '] ' + labels.get(job['status'], job['status'])
        result = call('/jobs', {'bot': bot, 'event_key': key, 'prompt': prompt})
        if result.get('error'):
            return '画架前还有几单排着，稍等一会儿再来。' if result['error'] == 'busy' else '这单没接上，稍后再试。'
        if result.get('duplicate'):
            return '这条生图请求已经接过啦，没有重复开画。'
        name = '小c' if bot == '1000000002' else '大肥鱼'
        return name + '接到画单啦，交给Codex画一张，画好就递给大人。[绘图' + result['id'][:6] + ']'
    except Exception:
        return '画架这会儿没接上，暂时不能生图，稍后再试。'
