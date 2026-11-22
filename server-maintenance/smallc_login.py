"""On-demand smallc login shortcut. Runs on server; never prints credentials."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.request

CONFIG = Path('/home/ubuntu/qq-codex/bridge/.private/config.json')
WEBUI = Path('/home/ubuntu/qq-codex/napcat-runtime/app/napcat/config/webui.json')
QR = Path('/home/ubuntu/qq-codex/napcat-runtime/app/napcat/cache/qrcode.png')


class Client:
    def __init__(self):
        self.config = json.loads(CONFIG.read_text())
        if self.config['onebot_url'] != 'http://127.0.0.1:13001':
            raise ValueError('unexpected_endpoint')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.credential = None

    def post(self, url, data, token=None, timeout=8):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(url, json.dumps(data).encode(), headers, method='POST')
        with self.opener.open(req, timeout=timeout) as response:
            return json.load(response)

    def api(self, path):
        if self.credential is None:
            token = json.loads(WEBUI.read_text())['token']
            result = self.post('http://127.0.0.1:13080/api/auth/login',
                {'hash': hashlib.sha256((token + '.napcat').encode()).hexdigest()})
            self.credential = result['data']['Credential']
        return self.post('http://127.0.0.1:13080/api/' + path, {}, self.credential)

    def state(self):
        try:
            result = self.post(self.config['onebot_url'] + '/get_status', {}, self.config['onebot_token'], timeout=2)
            status = result.get('data') or {}
            if result.get('retcode') == 0 and status.get('online') and status.get('good'):
                info = self.post(self.config['onebot_url'] + '/get_login_info', {}, self.config['onebot_token'], timeout=2)
                correct = str((info.get('data') or {}).get('user_id')) == str(self.config['bot_qq'])
                return {'status': 'online' if correct else 'wrong_account', 'expected_account': correct}
        except Exception:
            pass
        data = self.api('QQLogin/CheckLoginStatus').get('data') or {}
        if data.get('isLogin'):
            info = self.api('QQLogin/GetQQLoginInfo').get('data') or {}
            if str(info.get('uin')) != str(self.config['bot_qq']):
                return {'status': 'wrong_account', 'expected_account': False}
            # OneBot readiness is required before claiming complete recovery.
            return {'status': 'initializing', 'phase': data.get('loginPhase')}
        if data.get('qrLoginAccepted'):
            return {'status': 'confirm_on_phone', 'phase': data.get('loginPhase')}
        phase = data.get('loginPhase')
        return {'status': 'offline' if phase in ('waiting_qrcode', 'offline') else 'verification_in_progress', 'phase': phase}


def fresh_image(path, minimum_mtime=0, now=None):
    now = time.time() if now is None else now
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError:
        return None
    age = now - after.st_mtime
    if (before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size
            or after.st_mtime <= minimum_mtime or not 0 <= age <= 20
            or not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 1024 * 1024):
        return None
    return {'status': 'scan_qr', 'age_seconds': round(age, 1), 'png_base64': base64.b64encode(raw).decode()}


def prepare(client, path=QR, wait=15):
    state = client.state()
    if state['status'] != 'offline':
        return state
    previous = path.stat().st_mtime if path.exists() else 0
    result = client.api('QQLogin/RefreshQRcode')
    if result.get('code') != 0:
        return {'status': 'refresh_failed'}
    deadline = time.monotonic() + wait
    while True:
        image = fresh_image(path, previous)
        if image:
            return image
        if time.monotonic() >= deadline:
            return {'status': 'qr_pending'}
        time.sleep(0.25)


def verify(client, wait):
    deadline = time.monotonic() + wait
    while True:
        state = client.state()
        if state['status'] in ('online', 'wrong_account') or time.monotonic() >= deadline:
            return state
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('prepare', 'verify'), default='prepare')
    parser.add_argument('--wait', type=int, choices=range(0, 46), default=15)
    args = parser.parse_args()
    try:
        client = Client()
        result = prepare(client, wait=args.wait) if args.mode == 'prepare' else verify(client, args.wait)
    except Exception as exc:
        result = {'status': 'unavailable', 'error_type': type(exc).__name__}
    if result.get('status') == 'online' and result.get('expected_account') is True:
        try:
            import sys
            sys.path.insert(0, '/home/ubuntu/qq-codex/bridge')
            from reconnect_push import heartbeat
            result['catchup_scheduled'] = heartbeat(True)
        except Exception as exc:
            result['catchup_error_type'] = type(exc).__name__
    result['checked_at'] = datetime.now().astimezone().isoformat()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
