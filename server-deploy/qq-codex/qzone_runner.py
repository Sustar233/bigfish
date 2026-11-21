"""Fixed-account entry point for the DeepSeek QQ adapter; JSON in/out only."""
import argparse
import json
from pathlib import Path
import sys
import urllib.request

from qzone_commands import parse, qzone_command

CONFIGS = {
    'codex': (Path('/home/ubuntu/qq-codex/bridge/.private/config.json'),
              Path('/home/ubuntu/qq-codex/bridge/.private/records'), 13001),
    'harness': (Path('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json'),
                Path('/home/ubuntu/qq-dsh/records'), 13101),
}


def execute(bot, text):
    if parse(text) is None:
        return None
    path, root, port = CONFIGS[bot]
    config = json.loads(path.read_text())
    if config.get('onebot_url') != f'http://127.0.0.1:{port}':
        raise ValueError('unexpected_endpoint')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(action, data):
        if action not in ('get_login_info', 'get_qzone_msg_list', 'like_qzone'):
            raise ValueError('unexpected_action')
        req = urllib.request.Request(config['onebot_url'] + '/' + action,
            data=json.dumps(data).encode(), headers={
                'Authorization': 'Bearer ' + config['onebot_token'],
                'Content-Type': 'application/json'})
        with opener.open(req, timeout=30) as response:
            result = json.load(response)
        if result.get('status') != 'ok' or result.get('retcode') != 0:
            raise RuntimeError('qzone_api_failed')
        return result.get('data')

    return qzone_command(text, request, config, root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bot', required=True, choices=CONFIGS)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError('input_too_large')
        payload = json.loads(raw)
        text = payload.get('text')
        if not isinstance(text, str) or len(text) > 1000:
            raise ValueError('invalid_text')
        reply = execute(args.bot, text)
        print(json.dumps({'handled': reply is not None, 'reply': reply}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'handled': True, 'reply': '这次空间接口没接上，暂时没法完成点赞。'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
