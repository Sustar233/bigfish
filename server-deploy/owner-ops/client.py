import json
import re
import socket


def call(request):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(10)
        connection.connect('/run/qq-owner-ops/control.sock')
        connection.sendall((json.dumps(request, ensure_ascii=False) + '\n').encode())
        data = connection.makefile('rb').readline(65536)
    result = json.loads(data)
    if not result['ok']:
        raise RuntimeError(result['error'])
    return result['job']


def private_command(text, key, owner):
    match = re.match(r'^(?:/(codex|harness)|让\s*(codex|harness)|用服务器上的\s*(codex|harness))\s*[:：\s]+([\s\S]+)$', text.strip(), re.I)
    status = re.fullmatch(r'/服务器任务\s+(查询|取消)\s+([a-f0-9-]{36})', text.strip())
    if not match and not status:
        return None
    request = dict(owner=str(owner), channel='private', origin='smallc-private-' + str(owner))
    if match:
        request.update(action='run', provider=next(s for s in match.groups()[:3] if s).lower(), task=match[4], request_key=key)
    else:
        request.update(action='status' if status[1] == '查询' else 'cancel', task_id=status[2])
    try:
        job = call(request)
        return f"服务器任务 {job['id']}\n状态：{job['status']}\n{job['result']}"
    except Exception as error:
        return '服务器任务未执行：' + str(error)
