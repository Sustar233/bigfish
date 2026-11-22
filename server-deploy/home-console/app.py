"""Private home console, using the existing Harness session verifier."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from contextlib import closing
import csv
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request

import control

BASE = Path(__file__).resolve().parent
DATA = control.ROOT / 'data'
ORIGIN = os.environ.get('HOME_ORIGIN', '')
LOCAL = timezone(timedelta(hours=8))
LOCK = threading.RLock()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
KEY = secrets.token_bytes(32)
ASSETS = {'/home/': ('index.html', 'text/html; charset=utf-8'),
          '/home/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/home/style.css': ('style.css', 'text/css; charset=utf-8')}


def audit(feature, enabled, result):
    with closing(sqlite3.connect(DATA / 'audit.sqlite3')) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS audit(at TEXT,feature TEXT,enabled INTEGER,result TEXT)')
        db.execute('INSERT INTO audit VALUES(?,?,?,?)', (datetime.now(LOCAL).isoformat(timespec='seconds'), feature, enabled, result))


def history():
    if not (DATA / 'audit.sqlite3').exists():
        return []
    with closing(sqlite3.connect(DATA / 'audit.sqlite3')) as db:
        return [dict(at=r[0], label=control.LABELS.get(r[1], r[1]), enabled=bool(r[2]), result=r[3]) for r in db.execute('SELECT * FROM audit ORDER BY rowid DESC LIMIT 25')]


def authenticate(cookie, method, uri, origin=None):
    """Never trust identity or role headers from the incoming request."""
    if not cookie or len(cookie) > 8192:
        return False, None
    headers = {
        'Cookie': cookie, 'X-Forwarded-Proto': 'https',
        'X-Forwarded-Host': ORIGIN.removeprefix('https://'), 'X-Real-IP': '127.0.0.1',
        'X-Original-URI': uri, 'X-Original-Method': method}
    if origin is not None:
        headers['Origin'] = origin
    req = urllib.request.Request('http://127.0.0.1:3080/auth/verify', headers=headers)
    try:
        with OPENER.open(req, timeout=4) as response:
            roles = response.headers.get('X-Dsh-Auth-Roles', '')
            # The installed verifier supplies a comma-separated role list.
            allowed = 'admin' in roles.replace('[', '').replace(']', '').replace('"', '').replace(' ', ',').split(',')
            return allowed and 200 <= response.status < 300, response.headers.get('Set-Cookie') if allowed else None
    except (OSError, urllib.error.URLError):
        return False, None


def csrf(cookie):
    jar = SimpleCookie()
    try:
        jar.load(cookie)
        value = jar['__Host-dsh_auth_session'].value
    except Exception:
        value = cookie
    return hmac.new(KEY, value.encode(), hashlib.sha256).hexdigest()


def load_login():
    path = BASE / 'smallc_login.py'
    spec = importlib.util.spec_from_file_location('home_login', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accounts():
    result = {}
    module = load_login()
    try:
        result['smallc'] = module.Client().state()['status']
    except Exception:
        result['smallc'] = 'unknown'
    try:
        client = module.Client()
        token_path = Path('/home/ubuntu/qq-dsh/napcat-runtime/app/napcat/config/webui.json')
        token = json.loads(token_path.read_text())['token']
        auth = client.post('http://127.0.0.1:13180/api/auth/login', {'hash': hashlib.sha256((token + '.napcat').encode()).hexdigest()})
        state = client.post('http://127.0.0.1:13180/api/QQLogin/CheckLoginStatus', {}, auth['data']['Credential'], timeout=2)
        result['harness'] = 'online' if (state.get('data') or {}).get('isLogin') else 'offline'
    except Exception:
        result['harness'] = 'unknown'
    return result


def usage():
    day = datetime.now(LOCAL).strftime('%Y-%m-%d')
    path = Path('/home/ubuntu/server-maintenance/usage/data/daily') / (day + '.csv')
    result = {'day': day, 'tokens': None, 'missing': None, 'backup_bytes': None}
    try:
        with path.open(encoding='utf-8-sig') as file:
            rows = list(csv.DictReader(file))
        # Export includes per-project rows; the total CSV is a different file.
        result['tokens'] = sum(int(row['总token'] or 0) for row in rows)
        result['missing'] = sum(int(row['usage缺失次数'] or 0) for row in rows)
        result['updated'] = datetime.fromtimestamp(path.stat().st_mtime, LOCAL).isoformat(timespec='seconds')
    except (OSError, ValueError, KeyError):
        pass
    try:
        traffic = control.run(['sudo', '-n', '/usr/local/sbin/bigfish-home-timer', 'traffic'])
        if traffic.returncode == 0:
            result['traffic'] = json.loads(traffic.stdout)
    except (OSError, ValueError):
        pass
    return result


def state():
    features = control.snapshot()
    return {'features': features, 'revision': control.revision(features), 'accounts': accounts(),
            'checked_at': datetime.now(LOCAL).isoformat(timespec='seconds'), 'history': history(), 'usage': usage()}


class Handler(BaseHTTPRequestHandler):
    last_qr = 0
    server_version = 'Home'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass  # No session headers, QR images, paths or chat content in logs.

    def respond(self, code, payload, content_type='application/json; charset=utf-8', **headers):
        raw = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, (dict, list)) else payload
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if getattr(self, 'renewal', None):
            self.send_header('Set-Cookie', self.renewal)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        cookie = self.headers.get('Cookie', '')
        ok, self.renewal = authenticate(cookie, self.command, self.path, origin=self.headers.get('Origin'))
        if not ok:
            if self.command == 'GET' and self.path in ('/home/', '/home'):
                self.respond(303, b'', Location='/auth/login?returnTo=%2Fhome%2F')
            else:
                self.respond(401, {'error': '请先使用现有后台管理员账号登录。'})
        return ok

    def do_GET(self):
        if not self.authorized():
            return
        try:
            if self.path == '/home':
                return self.respond(308, b'', Location='/home/')
            if self.path in ASSETS:
                filename, kind = ASSETS[self.path]
                return self.respond(200, (BASE / filename).read_bytes(), kind)
            if self.path == '/home/api/state':
                with LOCK:
                    data = state()
                data['csrf'] = csrf(self.headers.get('Cookie', ''))
                return self.respond(200, data)
            self.respond(404, {'error': '页面不存在'})
        except Exception:
            self.respond(503, {'error': '状态读取失败，请稍后刷新；没有修改任何设置。'})

    def do_POST(self):
        if not self.authorized():
            return
        if self.headers.get('Origin') != ORIGIN or not hmac.compare_digest(self.headers.get('X-Home-CSRF', ''), csrf(self.headers.get('Cookie', ''))):
            return self.respond(403, {'error': '页面验证已失效，请刷新后重试。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096 or self.headers.get('Content-Type') != 'application/json':
                return self.respond(400, {'error': '请求格式无效'})
            body = json.loads(self.rfile.read(length))
            with LOCK:
                if self.path == '/home/api/change':
                    key, enabled = body.get('id'), body.get('enabled')
                    if key not in control.LABELS or type(enabled) is not bool:
                        return self.respond(400, {'error': '未知功能或开关值'})
                    before = control.snapshot()
                    if body.get('revision') != control.revision(before):
                        return self.respond(409, {'error': '设置已经变化，请刷新后再操作。'})
                    try:
                        control.change(key, enabled)
                        after = control.snapshot()
                        actual = next(row for row in after if row['id'] == key)
                        verified = actual['enabled'] is enabled
                        audit(key, enabled, 'verified' if verified else 'unconfirmed')
                        return self.respond(200 if verified else 503, {'ok': verified, 'error': None if verified else '操作已提交，但读回不一致，请刷新核对。'})
                    except Exception:
                        audit(key, enabled, 'failed')
                        return self.respond(503, {'error': '未确认操作成功，请刷新核对实际状态。'})
                if self.path == '/home/api/login':
                    if body.get('mode') not in ('prepare', 'verify'):
                        return self.respond(400, {'error': '未知登录操作'})
                    module = load_login()
                    client = module.Client()
                    if body['mode'] == 'verify':
                        result = client.state()
                    elif time.monotonic() - Handler.last_qr < 20:
                        return self.respond(429, {'error': '请稍候再获取新二维码。'})
                    else:
                        Handler.last_qr = time.monotonic()
                        result = module.prepare(client, wait=8)
                    return self.respond(200, result)
            self.respond(404, {'error': '接口不存在'})
        except (ValueError, TypeError, AttributeError):
            self.respond(400, {'error': '请求格式无效'})
        except Exception:
            self.respond(503, {'error': '操作暂时不可用，请稍后重试。'})


if __name__ == '__main__':
    if not ORIGIN.startswith('https://') or '/' in ORIGIN[8:]:
        raise SystemExit('HOME_ORIGIN must be the existing HTTPS origin')
    os.umask(0o077)
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    ThreadingHTTPServer(('127.0.0.1', 13220), Handler).serve_forever()
